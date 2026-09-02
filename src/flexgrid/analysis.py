"""Tableaux de résultats versionnés (results/*.csv) : résumé par modèle, verdicts pré-enregistrés contre RTE."""

from __future__ import annotations

import pandas as pd

from flexgrid import inference, metrics
from flexgrid.paths import RESULTS

CHALLENGERS = ["ensemble", "lgbm", "chronos2_cov", "chronos2", "mstl", "snaive_day", "snaive_week", "ets_seasonal"]


def national_verdicts(protocol: dict, po: pd.DataFrame) -> pd.DataFrame:
    """Ratio de MAE (IC 95 %) de chaque challenger contre RTE brute et débiaisée, sous les deux alignements."""
    v = protocol["verdict"]
    t = po[(po.window == "test") & (po.unique_id == "FR")]
    cov = t.groupby("model").apply(lambda d: (d.cov90 * d.n).sum() / d.n.sum(), include_groups=False)
    rows = []
    for ref in ["rte_j1", "rte_j1_prev", "rte_j1_debiased", "rte_j1_debiased_prev"]:
        for m in CHALLENGERS:
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
    for k, d in out.items():
        d.round(5).to_csv(RESULTS / f"{k}.csv")
    return out
