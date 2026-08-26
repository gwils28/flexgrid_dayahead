"""Naïves et modèles statistiques via statsforecast, réajustés à chaque origine.

Les quantiles viennent des intervalles de niveau 50, 80 et 90 % (quantiles 0,25/0,75, 0,1/0,9, 0,05/0,95) ; la
médiane est la prévision ponctuelle (ces modèles supposent des erreurs symétriques).
"""

from __future__ import annotations

import pandas as pd
from statsforecast import StatsForecast
from statsforecast.models import MSTL, AutoETS, SeasonalNaive

from flexgrid.backtest.inputs import keep_targets, qcol, split_uid, windows
from flexgrid.backtest.origins import Origin

LEVELS = {50: (0.25, 0.75), 80: (0.1, 0.9), 90: (0.05, 0.95)}


def build(name: str, spec: dict):
    if name.startswith("snaive"):
        return SeasonalNaive(season_length=spec["season"], alias=name), 4 * 336
    if name == "mstl":
        trend = AutoETS(model="ZZN")
        return MSTL(season_length=spec["seasons"], trend_forecaster=trend, alias=name), spec["train_steps"]
    if name == "ets_seasonal":
        return AutoETS(season_length=spec["season"], model=spec["spec"], alias=name), spec["train_steps"]
    raise ValueError(name)


def forecast(y: pd.DataFrame, origins: list[Origin], name: str, spec: dict, n_jobs: int = -1) -> pd.DataFrame:
    model, steps = build(name, spec)
    df = windows(y, origins, steps)
    h = max(o.horizon for o in origins)
    sf = StatsForecast(models=[model], freq="30min", n_jobs=n_jobs)
    fc = sf.forecast(df=df, h=h, level=list(LEVELS))
    fc = split_uid(fc.reset_index() if "unique_id" not in fc.columns else fc)
    out = fc[["unique_id", "day", "ds"]].copy()
    out[qcol(0.5)] = fc[name].to_numpy()
    for lv, (lo, hi) in LEVELS.items():
        out[qcol(lo)] = fc[f"{name}-lo-{lv}"].to_numpy()
        out[qcol(hi)] = fc[f"{name}-hi-{lv}"].to_numpy()
    return keep_targets(out.assign(model=name), origins)
