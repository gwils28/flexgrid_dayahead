"""Tableaux de résultats versionnés (results/*.csv) : résumé par modèle, verdicts pré-enregistrés contre RTE."""

from __future__ import annotations

import pandas as pd

from flexgrid import cost, inference, metrics
from flexgrid.data import dataset
from flexgrid.paths import RESULTS

CHALLENGERS = ["ensemble", "lgbm", "chronos2_cov", "chronos2", "mstl", "snaive_day", "snaive_week", "ets_seasonal"]
# Addendum du 2026-10-16. Les TSFM au premier plan sont les variantes « full » ; les autres sont des ablations.
NEW_TSFM = ["timestral_cov", "timesfm3_cov", "timestral5m_cov"]
LONG = ["timestral_cov_long", "timesfm3_cov_long", "chronos2_cov_long"]
NEW_ENSEMBLES = ["ens_lgbm_timestral", "ens_lgbm_timesfm3", "ens_lgbm_tsfm3", "ens_all4", "ens_lgbm_timestral_long"]
# famille -> mode de covariables -> modèle ; « long » : covariables complètes, contexte maximal du modèle.
TSFM_GRID = {
    f: {"none": f, "weather": f"{f}_wx", "full": f"{f}_cov", "long": f"{f}_cov_long"}
    for f in ["chronos2", "timestral", "timesfm3"]
}
TSFM_GRID["timestral5m"] = {"none": "timestral5m", "weather": "timestral5m_wx", "full": "timestral5m_cov"}


def present(po: pd.DataFrame, models: list[str]) -> list[str]:
    have = set(po.model.unique())
    return [m for m in models if m in have]


def day_kinds(days: pd.DatetimeIndex) -> pd.Series:
    """Type de chaque jour local : lundi, mar-ven, samedi, dimanche, férié, pont (férié et pont priment)."""
    import numpy as np

    from flexgrid.backtest.origins import TZ
    from flexgrid.data import calendar as C
    from flexgrid.paths import RAW

    school = pd.read_parquet(RAW / "calendrier_scolaire.parquet")
    days = pd.DatetimeIndex(days)
    cal = C.features((days + pd.Timedelta(hours=12)).tz_localize(TZ).tz_convert("UTC"), school)
    names = {0: "lundi", 1: "mar-ven", 5: "samedi", 6: "dimanche", 7: "férié", 8: "pont"}
    kind = np.where(cal.holiday == 1, 7, np.where(cal.bridge == 1, 8, cal.dow.clip(upper=6)))
    kind = np.where(np.isin(kind, [1, 2, 3, 4]), 1, kind)
    return pd.Series([names[k] for k in kind], index=days)


def national_verdicts(protocol: dict, po: pd.DataFrame) -> pd.DataFrame:
    """Ratio de MAE (IC 95 %) de chaque challenger contre RTE brute et débiaisée, sous les deux alignements."""
    v = protocol["verdict"]
    t = po[(po.window == "test") & (po.unique_id == "FR")]
    cov = t.groupby("model").apply(lambda d: (d.cov90 * d.n).sum() / d.n.sum(), include_groups=False)
    rows = []
    for ref in ["rte_j1", "rte_j1_prev", "rte_j1_debiased", "rte_j1_debiased_prev"]:
        for m in CHALLENGERS + NEW_TSFM + LONG + NEW_ENSEMBLES:
            if m not in cov:
                continue
            est, lo, hi = inference.compare(t, m, ref, "mae", v["bootstrap"])
            c = float(cov.get(f"{m}_conformal", cov[m]))
            rows.append(
                {
                    "reference": ref,
                    "model": m,
                    "mae_ratio": est,
                    "ci_low": lo,
                    "ci_high": hi,
                    "cov90_raw": float(cov[m]),
                    "verdict": inference.verdict(lo, hi, float(cov[m]), tuple(v["coverage90_band"])),
                    "verdict_with_conformal": inference.verdict(lo, hi, c, tuple(v["coverage90_band"])),
                }
            )
    return pd.DataFrame(rows)


# Baselines du portefeuille : ce qu'un BRP sans modèle ferait (naïve S-1, RTE au prorata) et le meilleur modèle simple.
PORTFOLIO_REFERENCES = ["snaive_week", "rte_prorata", "mstl"]


def portfolio_verdicts(protocol: dict, po: pd.DataFrame) -> pd.DataFrame:
    """Ratio de MAE et coût évité (€ sur l'année de test, k = 1) de chaque challenger contre chaque baseline."""
    v = protocol["verdict"]
    t = po[(po.window == "test") & (po.unique_id == dataset.PORTFOLIO_ID)]
    cov = t.groupby("model").apply(lambda d: (d.cov90 * d.n).sum() / d.n.sum(), include_groups=False)
    rows = []
    for ref in PORTFOLIO_REFERENCES:
        for m in present(t, ["ensemble", "lgbm", "chronos2_cov", "chronos2", *NEW_TSFM, *LONG, *NEW_ENSEMBLES]):
            est, lo, hi = inference.compare(t, m, ref, "mae", v["bootstrap"])
            s, slo, shi = cost.saving(po, dataset.PORTFOLIO_ID, m, ref, v["bootstrap"])
            c = float(cov.get(f"{m}_conformal", cov[m]))
            rows.append(
                {
                    "reference": ref,
                    "model": m,
                    "mae_ratio": est,
                    "ci_low": lo,
                    "ci_high": hi,
                    "saving_eur": s,
                    "saving_low": slo,
                    "saving_high": shi,
                    "cov90_raw": float(cov[m]),
                    "verdict": inference.verdict(lo, hi, float(cov[m]), tuple(v["coverage90_band"])),
                    "verdict_with_conformal": inference.verdict(lo, hi, c, tuple(v["coverage90_band"])),
                }
            )
    return pd.DataFrame(rows)


def tsfm_grid(protocol: dict, po: pd.DataFrame, uid: str) -> pd.DataFrame:
    """Chaque variante de TSFM contre Chronos-2 + covariables et contre RTE (national) ou RTE au prorata
    (portefeuille) : ratio de MAE avec IC 95 %, MAPE, couverture 90 % brute (addendum, question 1)."""
    boot = protocol["verdict"]["bootstrap"]
    t = po[(po.window == "test") & (po.unique_id == uid)]
    ref2 = "rte_j1" if uid == "FR" else "rte_prorata"
    rows = []
    for fam, modes in TSFM_GRID.items():
        for mode, m in modes.items():
            if m not in set(t.model):
                continue
            g = t[t.model == m]
            row = {
                "family": fam,
                "covariates": mode,
                "model": m,
                "mape": g.mape.mean(),
                "mae": g.mae.mean(),
                "cov90": (g.cov90 * g.n).sum() / g.n.sum(),
            }
            for ref in ["chronos2_cov", ref2]:
                est, lo, hi = inference.compare(t, m, ref, "mae", boot)
                row |= {f"vs_{ref}": est, f"vs_{ref}_low": lo, f"vs_{ref}_high": hi}
            rows.append(row)
    return pd.DataFrame(rows)


def calendar_ablation(protocol: dict, po: pd.DataFrame, uid: str) -> pd.DataFrame:
    """MAE full / weather (le calendrier) et weather / none (la météo), par type de jour (addendum, question 2).

    Bootstrap par jour (blocs de 1) : les fériés et les ponts ne sont pas des jours contigus."""
    boot = {**protocol["verdict"]["bootstrap"], "block_days": 1}
    t = po[(po.window == "test") & (po.unique_id == uid)]
    kinds = day_kinds(pd.DatetimeIndex(sorted(t.day.unique())))
    t = t.assign(kind=t.day.map(kinds))
    rows = []
    for fam, modes in TSFM_GRID.items():
        for effect, (a, b) in {"calendrier": ("full", "weather"), "météo": ("weather", "none")}.items():
            if not {modes[a], modes[b]} <= set(t.model):
                continue
            for kind, g in [
                ("tous", t),
                ("ouvré", t[t.kind.isin(["lundi", "mar-ven"])]),
                ("week-end", t[t.kind.isin(["samedi", "dimanche"])]),
                ("férié", t[t.kind == "férié"]),
                ("pont", t[t.kind == "pont"]),
            ]:
                est, lo, hi = inference.compare(g, modes[a], modes[b], "mae", boot)
                rows.append(
                    {
                        "family": fam,
                        "effect": effect,
                        "day_kind": kind,
                        "days": g.day.nunique(),
                        "mae_ratio": est,
                        "ci_low": lo,
                        "ci_high": hi,
                    }
                )
    return pd.DataFrame(rows)


def production_switch(protocol: dict, po: pd.DataFrame) -> pd.DataFrame:
    """Question 3 de l'addendum : le service change-t-il de modèle ?

    Règle pré-enregistrée : un mélange de l'addendum remplace `ensemble` seulement si son MAE sur le portefeuille
    est plus bas pendant la validation ; l'année de test confirme ou infirme. Le mélange a posteriori est montré,
    mais n'est pas éligible.
    """
    boot = protocol["verdict"]["bootstrap"]
    pf = po[po.unique_id == dataset.PORTFOLIO_ID]
    val = pf[pf.window == protocol["addendum_2026_10_16"]["production_switch_window"]]
    test = pf[pf.window == "test"]
    ref = val[val.model == "ensemble"].mae.mean()
    rows = []
    for m in present(pf, NEW_ENSEMBLES):
        est, lo, hi = inference.compare(test, m, "ensemble", "mae", boot)
        post_hoc = bool(protocol["models"][m].get("post_hoc", False))
        mae_val = val[val.model == m].mae.mean()
        rows.append(
            {
                "model": m,
                "post_hoc": post_hoc,
                "mae_validation": mae_val,
                "mae_validation_ensemble": ref,
                "eligible_switch": (not post_hoc) and mae_val < ref,
                "test_ratio_vs_ensemble": est,
                "ci_low": lo,
                "ci_high": hi,
                "test_verdict": inference.verdict(lo, hi, None, (0, 1)),
            }
        )
    return pd.DataFrame(rows)


def national_cost_scaled(protocol: dict, po: pd.DataFrame) -> pd.DataFrame:
    """Coût annuel du national ramené à l'énergie du brief (comparaison seulement, SPEC angle mort 6)."""
    test = protocol["windows"]["test"]
    f = cost.scale_factor(dataset.load("national"), test[0], test[1], protocol["portfolio"]["scale_national_to_gwh"])
    t = cost.annual(po, "FR", k_scenarios=protocol["cost"]["k_scenarios"])
    num = t.select_dtypes("number").drop(columns=["days", "mape"])
    t[num.columns] = num * f
    return t.assign(scale_factor=f)


def tables(protocol: dict) -> dict[str, pd.DataFrame]:
    out = {}
    po = pd.read_parquet(RESULTS / "per_origin_national.parquet")
    t = po[(po.window == "test")]
    out["summary_national"] = metrics.summary(t, extra=("bias",))
    out["verdicts_national"] = national_verdicts(protocol, po)
    seg = RESULTS / "per_origin_segments.parquet"
    if seg.exists():
        s = pd.read_parquet(seg)
        pf = s[(s.window == "test") & (s.unique_id == "FLEXGRID")]
        out["summary_portfolio"] = metrics.summary(pf, extra=("bias", "cost_eur", "energy_mwh"))
        panel = s[(s.window == "test") & (s.unique_id != "FLEXGRID")]
        out["summary_panel"] = metrics.summary(panel)
        out["verdicts_portfolio"] = portfolio_verdicts(protocol, s)
        out["cost_portfolio"] = cost.annual(s, dataset.PORTFOLIO_ID, k_scenarios=protocol["cost"]["k_scenarios"])
    out["cost_national_scaled"] = national_cost_scaled(protocol, po)
    if "timestral_cov" in set(po.model):
        out["tsfm_grid_national"] = tsfm_grid(protocol, po, "FR")
        out["calendar_ablation_national"] = calendar_ablation(protocol, po, "FR")
        if seg.exists() and "timestral_cov" in set(s.model):
            out["tsfm_grid_portfolio"] = tsfm_grid(protocol, s, "FLEXGRID")
            out["calendar_ablation_portfolio"] = calendar_ablation(protocol, s, "FLEXGRID")
            out["production_switch"] = production_switch(protocol, s)
    for k, d in out.items():
        d.round(5).to_csv(RESULTS / f"{k}.csv")
    return out
