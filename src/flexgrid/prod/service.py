"""Les étapes du service J-1, appelées par Dagster ou à la main.

1. `train_weekly` : réapprend LightGBM sur tout l'historique connu à l'émission, l'enregistre dans MLflow.
2. `forecast_day` : prévisions LightGBM (champion du registre) et Chronos-2 + covariables, mélange.
3. `nominate` : programme au pas 30 min (MWh) = médiane du modèle nommé, et quantiles servis par l'API.
Repli : si Chronos-2 échoue (GPU absent, délai dépassé), le modèle de repli est nommé et la raison est écrite.
"""

from __future__ import annotations

import json
import time

import pandas as pd

from flexgrid.backtest import inputs as I
from flexgrid.backtest.origins import Origin
from flexgrid.backtest.score import ensemble
from flexgrid.config import load_protocol
from flexgrid.data import dataset
from flexgrid.models import chronos, lgbm
from flexgrid.paths import RAW
from flexgrid.prod import config, registry


def _inputs(family: str, uid: str):
    y = I.series(family)
    return y[y.unique_id == uid]


def train_weekly(family: str, day: str, cfg: dict | None = None) -> str:
    """Apprentissage pour l'origine `day` (date de livraison J) : lignes dont la cible est connue au cutoff."""
    cfg = cfg or config.load()
    registry.tracking(cfg["mlflow_tracking_uri"])
    p = load_protocol()["models"]["lgbm"]
    o = Origin(pd.Timestamp(day), family)
    school = pd.read_parquet(RAW / "calendrier_scolaire.parquet")
    y = I.series(family)
    t0 = time.time()
    train = lgbm.training_table(y, dataset.load("weather_observed"), school, family)
    train = train[train.ds <= o.cutoff]
    models = lgbm.fit(train, p)
    info = {"as_of": day, "n_rows": len(train), "fit_seconds": float(time.time() - t0)}
    return registry.register(models, family, p, info)


def forecast_day(family: str, day: str, cfg: dict | None = None) -> pd.DataFrame:
    cfg = cfg or config.load()
    uid = cfg["families"][family]["unique_id"]
    o = Origin(pd.Timestamp(day), family)
    y = _inputs(family, uid)
    school = pd.read_parquet(RAW / "calendrier_scolaire.parquet")
    wo, wf = dataset.load("weather_observed"), dataset.load("weather_forecast")
    registry.tracking(cfg["mlflow_tracking_uri"])
    model = registry.load_champion(family)
    rows = lgbm.inference_table(y, wo, wf, school, [o])
    q = model.predict(rows)
    lg = pd.concat([rows[["unique_id", "day", "ds", "h"]].reset_index(drop=True), q], axis=1).assign(model="lgbm")
    out, status = [lg], {"chronos2_cov": "ok"}
    try:
        t0 = time.time()
        ch = chronos.backtest(y, [o], 2048, True, wo, wf, school, name="chronos2_cov", origins_per_call=1)
        if time.time() - t0 > cfg["chronos_timeout_s"]:
            raise TimeoutError(f"Chronos-2 a pris {time.time() - t0:.0f} s")
        out += [ch, ensemble(lg, ch)]
    except Exception as e:  # le repli est une fonction du service, pas un incident silencieux
        status["chronos2_cov"] = f"échec : {e!r}"
    fc = pd.concat(out, ignore_index=True)
    fc.to_parquet(config.store(cfg, "forecasts", family, f"{day}.parquet"))
    config.store(cfg, "forecasts", family, f"{day}.status.json").write_text(json.dumps(status, ensure_ascii=False))
    return fc


def nominate(family: str, day: str, cfg: dict | None = None) -> pd.DataFrame:
    cfg = cfg or config.load()
    fc = pd.read_parquet(config.store(cfg, "forecasts", family, f"{day}.parquet"))
    wanted = cfg["nomination_model"]
    chosen = wanted if wanted in set(fc.model) else cfg["fallback_model"]
    f = fc[fc.model == chosen].sort_values("ds")
    nom = pd.DataFrame(
        {
            "delivery_day": day,
            "ds_utc": f.ds.dt.strftime("%Y-%m-%dT%H:%MZ"),
            "ds_local": f.ds.dt.tz_convert("Europe/Paris").dt.strftime("%Y-%m-%d %H:%M%z"),
            "mw": f[I.qcol(0.5)].round(3),
            "mwh": (f[I.qcol(0.5)] * 0.5).round(3),
            "model": chosen,
        }
    )
    expected = len(Origin(pd.Timestamp(day), family).targets)
    if len(nom) != expected:
        raise ValueError(f"nomination de {len(nom)} pas, {expected} attendus pour le jour local {day}")
    nom.to_csv(config.store(cfg, "nominations", family, f"{day}.csv"), index=False)
    return nom
