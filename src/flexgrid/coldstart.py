"""Cold-start : que vaut chaque modèle quand un segment n'a que quelques jours d'historique ?

Simulation sur le panel. Trois régions sont tenues à l'écart (Pays de la Loire, Bretagne, Nouvelle-Aquitaine) :
leurs segments jouent les « nouveaux sites ». À chaque origine (un jour sur sept de l'année de test), leur
historique est tronqué à 7, 14, 28 ou 56 jours. Modèles :
- naïve hebdomadaire (même heure locale, 7 jours plus tôt) ;
- Chronos-2 zero-shot, sans et avec covariables, sur l'historique tronqué ;
- Chronos-2 few-shot in-context : `cross_learning`, le lot contient les segments tronqués et leurs « frères »
  (même tranche et même profil, régions non tenues à l'écart) avec 2048 pas d'historique, tous coupés au même
  instant ;
- LightGBM appris sur les seuls segments des régions non tenues à l'écart (il n'a jamais vu les nouveaux sites),
  réappris toutes les 4 semaines.
"""

from __future__ import annotations

import pandas as pd

from flexgrid.backtest import inputs as I
from flexgrid.backtest.origins import Origin, origins
from flexgrid.data import dataset
from flexgrid.models import chronos, lgbm
from flexgrid.models import features as F
from flexgrid.paths import RAW, RESULTS

HELD_OUT = ["52", "53", "75"]


def held_out_ids(y: pd.DataFrame) -> list[str]:
    ids = y.unique_id.unique()
    return sorted(u for u in ids if u[:2] in HELD_OUT)


def siblings(uid: str, ids: list[str]) -> list[str]:
    return sorted(u for u in ids if u[2:] == uid[2:] and u[:2] not in HELD_OUT and u != dataset.PORTFOLIO_ID)


def snaive_week(s: pd.Series, o: Origin) -> pd.DataFrame:
    v = s.reindex(F.local_shift(o.targets, 7)).to_numpy()
    d = pd.DataFrame({"ds": o.targets})
    for c in I.QCOLS:
        d[c] = v
    return d


def run(protocol: dict, step_days: int = 7, log=print) -> pd.DataFrame:
    y = I.series("segments")
    y = y[y.unique_id != dataset.PORTFOLIO_ID]
    ids = sorted(y.unique_id.unique())
    held = held_out_ids(y)
    series = {u: g.set_index("ds").y.sort_index() for u, g in y.groupby("unique_id")}
    region = y.groupby("unique_id").region.first().to_dict()
    wo, wf = dataset.load("weather_observed"), dataset.load("weather_forecast")
    school = pd.read_parquet(RAW / "calendrier_scolaire.parquet")
    wx = {u: (lgbm.weather_for(wo, r), lgbm.weather_for(wf, r)) for u, r in region.items()}
    test = protocol["windows"]["test"]
    ors = origins(test[0], test[1], "segments")[::step_days]
    lengths = protocol["cold_start"]["history_days"]

    train_all = lgbm.training_table(y[~y.unique_id.isin(held)], wo, school, "segments")
    out, models = [], None
    for i, o in enumerate(ors):
        if models is None or i % 4 == 0:
            models = lgbm.fit(train_all[train_all.ds <= o.cutoff], protocol["models"]["lgbm"])
            log(f"cold-start : LightGBM réappris au {o.day.date()} sans les régions {HELD_OUT}")
        for L in lengths:
            start = o.cutoff - pd.Timedelta(days=L) + pd.Timedelta("30min")
            cur: list[pd.DataFrame] = []
            trunc = {u: series[u].loc[start : o.cutoff] for u in held}
            # naïve
            for u in held:
                d = snaive_week(trunc[u], o)
                cur.append(d.assign(model="snaive_week", unique_id=u))
            # LightGBM sur historique tronqué
            rows = []
            for u in held:
                wm = F.merged_weather(*wx[u], o.issue).loc[o.day_start - pd.Timedelta(days=20) : o.day_end]
                f = F.frame(trunc[u], wm, o.targets, "segments", school)
                rows.append(f.assign(unique_id=u, day=o.day, **lgbm.statics(u)))
            r = pd.concat(rows).rename_axis("ds").reset_index()
            cur.append(lgbm.predict(models, r).drop(columns=["day", "h"]).assign(model="lgbm"))
            # Chronos-2 zero-shot, sans et avec covariables
            for cov, name in [(False, "chronos2"), (True, "chronos2_cov")]:
                items = [chronos.make_input(trunc[u], o, L * 48, cov, *wx[u], school) for u in held]
                preds = chronos.predict_items(items, o.horizon)
                for u, p in zip(held, preds, strict=True):
                    cur.append(chronos.to_frame(p, o, u).drop(columns=["day", "h"]).assign(model=name))
            # Chronos-2 few-shot : un lot par (tranche, profil), cible tronquée + frères complets
            groups: dict[str, list[str]] = {}
            for u in held:
                groups.setdefault(u[2:], []).append(u)
            for targets in groups.values():
                sibs = siblings(targets[0], ids)
                batch = [chronos.make_input(trunc[u], o, L * 48, True, *wx[u], school) for u in targets]
                batch += [chronos.make_input(series[s], o, 2048, True, *wx[s], school) for s in sibs]
                preds = chronos.predict_items(batch, o.horizon, cross_learning=True)
                for u, p in zip(targets, preds[: len(targets)], strict=True):
                    cur.append(chronos.to_frame(p, o, u).drop(columns=["day", "h"]).assign(model="chronos2_fewshot"))
            out += [d.assign(history_days=L, day=o.day) for d in cur]
        log(f"cold-start {o.day.date()} ({i + 1}/{len(ors)})")
    fc = pd.concat(out, ignore_index=True)
    (RESULTS / "forecasts").mkdir(parents=True, exist_ok=True)
    fc.to_parquet(RESULTS / "forecasts" / "coldstart.parquet")
    return fc


def score(protocol: dict) -> pd.DataFrame:
    """Métriques par (modèle, historique, segment, origine), plus la référence « historique complet » du backtest.

    Écrit results/coldstart_per_origin.parquet et results/coldstart_summary.csv (WAPE et MAPE par modèle et
    longueur d'historique, avec IC 95 % du ratio de WAPE contre la naïve, bootstrap sur les origines).
    """
    from flexgrid import inference, metrics

    fc = pd.read_parquet(RESULTS / "forecasts" / "coldstart.parquet")
    fc = dataset.as_ns(fc)
    y = I.series("segments")
    parts = []
    for (m, L), g in fc.groupby(["model", "history_days"]):
        r = metrics.score_rows(g.assign(model=m, h=0), y)
        a = r.groupby(["unique_id", "day"]).agg(n=("ae", "size"), ae=("ae", "sum"), y=("y", "sum"), ape=("ape", "mean"))
        parts.append(a.reset_index().assign(model=m, history_days=L))
    po = pd.concat(parts, ignore_index=True)
    # Référence : les mêmes segments et jours dans le backtest à historique complet.
    full = pd.read_parquet(RESULTS / "per_origin_segments.parquet")
    keys = po[["unique_id", "day"]].drop_duplicates()
    full = full[full.model.isin(["lgbm", "chronos2_cov", "ensemble", "snaive_week"])].merge(keys)
    full = full.assign(ae=full.mae * full.n, y=full.y_mean * full.n, ape=full.mape, history_days=0)
    po = pd.concat([po, full[po.columns]], ignore_index=True)
    po.to_parquet(RESULTS / "coldstart_per_origin.parquet", compression="zstd")
    boot = {**protocol["verdict"]["bootstrap"], "block_days": 1}
    rows = []
    for (m, L), g in po.groupby(["model", "history_days"]):
        day = g.groupby("day")[["ae", "y"]].sum()
        ref = po[(po.model == "snaive_week") & (po.history_days == L)].groupby("day")[["ae", "y"]].sum()
        est, lo, hi = inference.bootstrap(
            lambda a, b: a.sum() / b.sum(),
            [day.ae.to_numpy(), ref.ae.reindex(day.index).to_numpy()],
            boot["block_days"],
            boot["replicates"],
            boot["seed"],
        )
        rows.append(
            {
                "model": m,
                "history_days": L,
                "wape": day.ae.sum() / day.y.sum(),
                "mape": g.ape.mean(),
                "wape_vs_snaive": est,
                "ci_low": lo,
                "ci_high": hi,
            }
        )
    out = pd.DataFrame(rows)
    out.round(5).to_csv(RESULTS / "coldstart_summary.csv", index=False)
    return out
