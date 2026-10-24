"""Complexity Router : chaque segment est-il mieux servi par LightGBM (spécialiste) ou par Chronos-2 (TSFM) ?

- Variables ex-ante par segment, calculées sur une fenêtre qui finit avant la période où l'on route.
- Étiquette : la branche au MASE moyen le plus bas sur la fenêtre de validation.
- Politiques : toujours une branche, le mélange des deux, un stump (une variable, un seuil) appris sur la
  validation et appliqué tel quel sur l'année de test, et l'oracle (le meilleur a posteriori : une borne, pas une
  politique).
- Dérive : à chaque origine de test, variables recalculées sur les 28 derniers jours connus, stump appliqué, on
  compte les segments qui changent de branche. Le stump de la dérive est appris sur des variables de 28 jours
  (leçon W25 : apprendre sur 8 semaines et appliquer sur 28 jours crée un décalage train/serve).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from flexgrid.backtest.origins import TZ

FEATURES = [
    "n_sites",
    "mean_mw",
    "seasonal_strength_48",
    "seasonal_strength_336",
    "cv",
    "naive_noise",
    "temp_sensitivity",
]
BRANCHES = ("lgbm", "chronos2_cov")


def seasonal_strength(y: pd.Series, period: int) -> float:
    """1 - Var(reste) / Var(y désaisonnalisé de la tendance), profil moyen par position dans la période."""
    v = y.to_numpy()
    n = len(v) // period * period
    if n < 2 * period:
        return np.nan
    v = v[-n:]
    trend = pd.Series(v).rolling(period, center=True, min_periods=1).mean().to_numpy()
    d = v - trend
    prof = d.reshape(-1, period).mean(axis=0)
    rem = d - np.tile(prof, n // period)
    return float(max(0.0, 1 - rem.var() / d.var())) if d.var() > 0 else np.nan


def unit_features(y: pd.Series, sites: pd.Series, temp: pd.Series) -> dict:
    loc = y.index.tz_convert(TZ)
    daily = pd.DataFrame({"y": y.to_numpy(), "t": temp.reindex(y.index).to_numpy()}, index=loc).resample("D").mean()
    daily = daily.dropna()
    slope = np.polyfit(daily.t, daily.y, 1)[0] if len(daily) > 5 else np.nan
    naive = (y - y.shift(336)).abs().mean()
    return {
        "n_sites": float(sites.iloc[-1]),
        "mean_mw": float(y.mean()),
        "seasonal_strength_48": seasonal_strength(y, 48),
        "seasonal_strength_336": seasonal_strength(y, 336),
        "cv": float(y.std() / y.mean()),
        "naive_noise": float(naive / y.mean()),
        "temp_sensitivity": float(abs(slope) / y.mean()),
    }


def features_table(seg: pd.DataFrame, wx_obs: pd.DataFrame, end: pd.Timestamp, days: int) -> pd.DataFrame:
    """Variables de chaque segment sur les `days` jours qui finissent à `end` (exclu)."""
    from flexgrid.models.lgbm import weather_for

    start = end - pd.Timedelta(days=days)
    rows = {}
    for uid, g in seg.groupby("unique_id"):
        g = g.set_index("ds").sort_index().loc[start : end - pd.Timedelta("30min")]
        temp = weather_for(wx_obs, g.region.iloc[0]).temperature_2m
        rows[uid] = unit_features(g.y, g.n_sites, temp)
    return pd.DataFrame.from_dict(rows, orient="index")


def unit_scores(po: pd.DataFrame, window: str, metric: str = "mase") -> pd.DataFrame:
    """MASE moyen par (segment, modèle) sur une fenêtre."""
    p = po[po.window == window]
    return p.pivot_table(index="unique_id", columns="model", values=metric, aggfunc="mean")


def fit_stump(feat: pd.DataFrame, scores: pd.DataFrame, branches=BRANCHES) -> dict:
    """Variable, seuil et sens qui minimisent le MASE total des branches choisies (TSFM si au-dessus du seuil
    quand sens = +1, en dessous quand sens = -1). Sans gain sur « toujours la meilleure branche », renvoie celle-ci."""
    spec, tsfm = scores[branches[0]], scores[branches[1]]
    base_branch = branches[0] if spec.sum() <= tsfm.sum() else branches[1]
    best = {"feature": None, "threshold": None, "sign": 0, "always": base_branch, "loss": min(spec.sum(), tsfm.sum())}
    for f in FEATURES:
        x = feat[f].reindex(scores.index)
        for thr in np.unique(x.dropna()):
            for sign in (1, -1):
                to_tsfm = (x >= thr) if sign == 1 else (x < thr)
                loss = np.where(to_tsfm, tsfm, spec).sum()
                if loss < best["loss"] - 1e-12:
                    best = {"feature": f, "threshold": float(thr), "sign": sign, "always": None, "loss": float(loss)}
    return best


def route(stump: dict, feat: pd.DataFrame, branches=BRANCHES) -> pd.Series:
    if stump["feature"] is None:
        return pd.Series(stump["always"], index=feat.index)
    x = feat[stump["feature"]]
    to_tsfm = (x >= stump["threshold"]) if stump["sign"] == 1 else (x < stump["threshold"])
    return pd.Series(np.where(to_tsfm, branches[1], branches[0]), index=feat.index)


def fit_stump_k(feat: pd.DataFrame, scores: pd.DataFrame, branches: list[str]) -> dict:
    """Stump à K branches (addendum du 2026-10-16) : une variable et un seuil coupent les segments en deux
    groupes ; chaque groupe prend la branche au MASE total le plus bas. Sans gain, la meilleure branche partout."""
    s = scores[branches]
    tot = s.sum()
    best = {"feature": None, "threshold": None, "below": tot.idxmin(), "above": tot.idxmin(), "loss": float(tot.min())}
    for f in FEATURES:
        x = feat[f].reindex(s.index)
        for thr in np.unique(x.dropna()):
            hi = (x >= thr).to_numpy()
            if hi.all() or not hi.any():
                continue
            lo_sum, hi_sum = s[~hi].sum(), s[hi].sum()
            loss = float(lo_sum.min() + hi_sum.min())
            if loss < best["loss"] - 1e-12:
                best = {
                    "feature": f,
                    "threshold": float(thr),
                    "below": lo_sum.idxmin(),
                    "above": hi_sum.idxmin(),
                    "loss": loss,
                }
    return best


def route_k(stump: dict, feat: pd.DataFrame) -> pd.Series:
    if stump["feature"] is None:
        return pd.Series(stump["below"], index=feat.index)
    hi = feat[stump["feature"]] >= stump["threshold"]
    return pd.Series(np.where(hi, stump["above"], stump["below"]), index=feat.index)


def policy_scores(scores: pd.DataFrame, routes: pd.Series, branches=BRANCHES) -> pd.DataFrame:
    """MASE par segment pour chaque politique (sur une fenêtre de scores)."""
    s = scores.loc[routes.index]
    out = pd.DataFrame(index=s.index)
    out["always_lgbm"] = s[branches[0]]
    out["always_chronos2_cov"] = s[branches[1]]
    if "ensemble" in s:
        out["ensemble"] = s["ensemble"]
    out["learned_stump"] = [s.loc[u, b] for u, b in routes.items()]
    out["oracle"] = s[list(branches)].min(axis=1)
    return out


def run(protocol: dict, po: pd.DataFrame, log=print) -> dict:
    """Router complet : apprentissage sur la validation, évaluation sur le test, dérive. Écrit dans results/."""
    import json

    from flexgrid.data import dataset
    from flexgrid.paths import RESULTS

    seg = dataset.load("segments")
    seg = seg[seg.unique_id != dataset.PORTFOLIO_ID]
    wo = dataset.load("weather_observed")
    po = po[po.unique_id != dataset.PORTFOLIO_ID]
    v0 = pd.Timestamp(protocol["windows"]["validation"][0]).tz_localize(TZ).tz_convert("UTC")
    t0 = pd.Timestamp(protocol["windows"]["test"][0]).tz_localize(TZ).tz_convert("UTC")
    # Variables : 8 semaines avant la fenêtre où l'on route (la fin de J-2 du premier jour, arrondie au jour).
    feat_val = features_table(seg, wo, v0 - pd.Timedelta(days=1), 56)
    feat_test = features_table(seg, wo, t0 - pd.Timedelta(days=1), 56)
    s_val, s_test = unit_scores(po, "validation"), unit_scores(po, "test")
    stump = fit_stump(feat_val, s_val)
    routes = route(stump, feat_test)
    pol = policy_scores(s_test, routes)
    # Addendum du 2026-10-16 : quatre branches, et les mélanges de l'addendum, quand leurs prévisions existent.
    b4 = protocol["router"].get("branches4", [])
    stump4 = None
    if b4 and set(b4) <= set(s_val.columns):
        stump4 = fit_stump_k(feat_val, s_val, b4)
        routes4 = route_k(stump4, feat_test)
        for b in b4[2:]:
            pol[f"always_{b}"] = s_test.loc[pol.index, b]
        pol["learned_stump4"] = [s_test.loc[u, b] for u, b in routes4.items()]
        pol["oracle4"] = s_test.loc[pol.index, b4].min(axis=1)
        for m in ["ens_lgbm_timestral", "ens_lgbm_timesfm3", "ens_lgbm_tsfm3", "ens_all4"]:
            if m in s_test:
                pol[m] = s_test.loc[pol.index, m]
    rng = np.random.default_rng(protocol["seed"])
    n = len(pol)
    ci = {}
    for c in pol.columns:
        draws = [
            pol[c].to_numpy()[i].mean() / pol.always_lgbm.to_numpy()[i].mean() for i in rng.integers(0, n, (2000, n))
        ]
        ci[c] = (float(pol[c].mean() / pol.always_lgbm.mean()), *map(float, np.quantile(draws, [0.025, 0.975])))
    # Dérive de la décision : stump appris sur des variables de 28 jours, appliqué chaque semaine du test.
    d = protocol["router"]["drift"]["trailing_days"]
    stump28 = fit_stump(features_table(seg, wo, v0 - pd.Timedelta(days=1), d), s_val)
    drift = []
    for day in pd.date_range(protocol["windows"]["test"][0], protocol["windows"]["test"][1], freq="7D"):
        end = (day - pd.Timedelta(days=1)).tz_localize(TZ).tz_convert("UTC")
        r = route(stump28, features_table(seg, wo, end, d))
        drift.append(r.rename(day))
        log(f"router dérive {day.date()} : {int((r == BRANCHES[1]).sum())} segments vers Chronos-2")
    drift = pd.DataFrame(drift)
    RESULTS.mkdir(exist_ok=True)
    units = feat_test.join(s_test[[b for b in dict.fromkeys([*BRANCHES, *b4]) if b in s_test]], how="left")
    units = units.assign(route=routes)
    if stump4:
        units["route4"] = routes4
    units.to_csv(RESULTS / "router_units.csv")
    pol.to_csv(RESULTS / "router_policies.csv")
    drift.to_csv(RESULTS / "router_drift.csv")
    out = {"stump": stump, "stump28": stump28, "stump4": stump4, "ratio_vs_always_lgbm": ci}
    (RESULTS / "router_summary.json").write_text(json.dumps(out, indent=2, ensure_ascii=False, default=float))
    return out
