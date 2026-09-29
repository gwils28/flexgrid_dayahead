"""API des quantiles et des nominations J-1 (lecture seule du magasin du service).

uv run uvicorn flexgrid.prod.api:app --port 8000
"""

from __future__ import annotations

import json

import pandas as pd
from fastapi import FastAPI, HTTPException

from flexgrid.backtest.inputs import QCOLS
from flexgrid.prod import config

app = FastAPI(title="FlexGrid J-1", version="0.1.0")
CFG = config.load()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/forecast/{family}/{day}")
def forecast(family: str, day: str, model: str | None = None) -> dict:
    p = config.store(CFG, "forecasts", family, f"{day}.parquet")
    if not p.exists():
        raise HTTPException(404, f"pas de prévision {family} pour {day}")
    fc = pd.read_parquet(p)
    model = model or CFG["nomination_model"]
    if model not in set(fc.model):
        raise HTTPException(404, f"modèle {model} absent ; disponibles : {sorted(set(fc.model))}")
    f = fc[fc.model == model].sort_values("ds")
    status = json.loads(config.store(CFG, "forecasts", family, f"{day}.status.json").read_text())
    return {
        "family": family,
        "delivery_day": day,
        "model": model,
        "status": status,
        "unit": "MW",
        "steps": [
            {"ds": t.strftime("%Y-%m-%dT%H:%MZ"), **{q: round(float(v), 3) for q, v in zip(QCOLS, row, strict=True)}}
            for t, row in zip(f.ds, f[QCOLS].to_numpy(), strict=True)
        ],
    }


@app.get("/nomination/{family}/{day}")
def nomination(family: str, day: str) -> dict:
    p = config.store(CFG, "nominations", family, f"{day}.csv")
    if not p.exists():
        raise HTTPException(404, f"pas de nomination {family} pour {day}")
    n = pd.read_csv(p)
    return {
        "family": family,
        "delivery_day": day,
        "total_mwh": round(float(n.mwh.sum()), 1),
        "steps": n.to_dict("records"),
    }
