"""Lance les prévisions d'une famille sur toutes les origines (validation + test) et les écrit sur disque.

results/forecasts/<famille>/<modèle>.parquet : volumineux, non versionné. Les métriques par origine, elles, le
sont.
"""

from __future__ import annotations

import time

import pandas as pd

from flexgrid.backtest import inputs as I
from flexgrid.backtest import origins as O
from flexgrid.data import dataset
from flexgrid.paths import RAW, RESULTS

STATS = ["snaive_day", "snaive_week", "mstl", "ets_seasonal"]


def forecast_dir(family: str):
    d = RESULTS / "forecasts" / family
    d.mkdir(parents=True, exist_ok=True)
    return d


def all_origins(protocol: dict, family: str) -> list[O.Origin]:
    start = protocol["windows"]["validation"][0]
    end = protocol["windows"]["test"][1]
    return O.origins(start, end, family)


def run(protocol: dict, family: str, model: str, log=print) -> pd.DataFrame:
    t0 = time.time()
    origins = all_origins(protocol, family)
    y = I.series(family)
    m = protocol["models"]
    if model in STATS:
        from flexgrid.models import stats

        parts = []
        for i in range(0, len(origins), 30):
            parts.append(stats.forecast(y, origins[i : i + 30], model, m[model]))
            log(f"{model} {family} {origins[min(i + 29, len(origins) - 1)].day.date()} ({time.time() - t0:.0f} s)")
        fc = pd.concat(parts, ignore_index=True)
    elif model == "lgbm":
        from flexgrid.models import lgbm

        school = pd.read_parquet(RAW / "calendrier_scolaire.parquet")
        fc = lgbm.backtest(
            y,
            dataset.load("weather_observed"),
            dataset.load("weather_forecast"),
            school,
            origins,
            m["lgbm"],
            log=log,
        )
    elif model in ("chronos2", "chronos2_cov"):
        from flexgrid.models import chronos

        spec = m[model]
        school = pd.read_parquet(RAW / "calendrier_scolaire.parquet")
        fc = chronos.backtest(
            y,
            origins,
            spec["context_steps"],
            spec["covariates"],
            dataset.load("weather_observed"),
            dataset.load("weather_forecast"),
            school,
            name=model,
            origins_per_call=1 if spec["covariates"] else 8,
        )
    else:
        raise ValueError(model)
    for name, g in fc.groupby("model"):
        g.reset_index(drop=True).to_parquet(forecast_dir(family) / f"{name}.parquet")
    log(f"{model} {family} terminé en {time.time() - t0:.0f} s, {len(fc)} lignes")
    return fc
