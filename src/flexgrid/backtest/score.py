"""Post-traitement et notation : benchmarks RTE, mélange, réparations conformes, métriques par origine.

Écrit results/per_origin_<famille>.parquet (versionné) : une ligne par (modèle, série, jour de livraison).
"""

from __future__ import annotations

import pandas as pd

from flexgrid import conformal, metrics
from flexgrid.backtest import inputs as I
from flexgrid.backtest.run import all_origins, forecast_dir
from flexgrid.data import dataset
from flexgrid.models import rte
from flexgrid.paths import RESULTS


def load_forecasts(family: str) -> dict[str, pd.DataFrame]:
    return {p.stem: pd.read_parquet(p) for p in sorted(forecast_dir(family).glob("*.parquet"))}


def ensemble(a: pd.DataFrame, b: pd.DataFrame, name: str = "ensemble") -> pd.DataFrame:
    """Moyenne des quantiles de deux modèles (moyenne de Vincent), sur les pas communs."""
    keys = ["unique_id", "day", "ds"]
    m = a.merge(b, on=keys, suffixes=("_a", "_b"))
    out = m[[*keys, "h_a"]].rename(columns={"h_a": "h"})
    for c in I.QCOLS:
        out[c] = (m[f"{c}_a"] + m[f"{c}_b"]) / 2
    return out.assign(model=name)


def add_derived(fcs: dict[str, pd.DataFrame], family: str, protocol: dict) -> dict[str, pd.DataFrame]:
    actuals = I.series(family)
    origins = all_origins(protocol, family)
    if family == "national":
        nat = dataset.load("national")
        w = protocol["models"]["rte_j1_debiased"]["window_days"]
        fcs["rte_j1"] = rte.raw(nat, origins)
        fcs["rte_j1_prev"] = rte.raw(nat, origins, "rte_j1_prev", "rte_j1_prev")
        fcs["rte_j1_debiased"] = rte.debiased(nat, origins, w)
        fcs["rte_j1_debiased_prev"] = rte.debiased(nat, origins, w, column="rte_j1_prev")
    if "lgbm" in fcs and "chronos2_cov" in fcs:
        fcs["ensemble"] = ensemble(fcs["lgbm"], fcs["chronos2_cov"])
    n_cal = protocol["conformal"]["calibration_days"]
    for name in [n for n in list(fcs) if n in ("lgbm", "chronos2_cov", "ensemble", "rte_j1_debiased", "mstl")]:
        parts = [
            conformal.conformalize(g, actuals[actuals.unique_id == u], n_cal) for u, g in fcs[name].groupby("unique_id")
        ]
        fcs[f"{name}_conformal"] = pd.concat(parts, ignore_index=True)
    return fcs


def score(protocol: dict, family: str) -> pd.DataFrame:
    fcs = add_derived(load_forecasts(family), family, protocol)
    actuals = I.series(family)
    prices = dataset.load("prices")
    origins = all_origins(protocol, family)
    cut = pd.DataFrame(
        [(u, o.day, o.cutoff) for o in origins for u in actuals.unique_id.unique()],
        columns=["unique_id", "day", "cutoff"],
    )
    scale = metrics.mase_scale(actuals, cut, protocol["metrics"]["mase_seasonality"])
    parts = []
    for _name, fc in fcs.items():
        rows = metrics.score_rows(fc, actuals, prices)
        parts.append(metrics.per_origin(rows, scale))
    po = pd.concat(parts, ignore_index=True)
    po["window"] = "validation"
    po.loc[po.day >= protocol["windows"]["test"][0], "window"] = "test"
    RESULTS.mkdir(exist_ok=True)
    po.to_parquet(RESULTS / f"per_origin_{family}.parquet")
    return po
