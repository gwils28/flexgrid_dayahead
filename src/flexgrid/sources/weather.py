"""Open-Meteo : météo observée (ERA5) pour l'apprentissage, prévisions archivées pour le backtest.

`<var>_previous_dayN` est la valeur prévue N x 24 h avant l'heure valide, par le run le plus récent à
ce moment-là (API « Previous Runs »). Le modèle est fixé (ecmwf_ifs025) : le défaut `best_match`
change de modèle source au fil du temps (GFS avant 2024, ICON ensuite), ce qui créerait une rupture
silencieuse dans les entrées. Archive ECMWF : température et nébulosité dès février 2024,
rayonnement dès mars-avril 2024.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from flexgrid.paths import CONFIGS, RAW
from flexgrid.sources.snapshot import fetch, verify


def load_config(path: Path = CONFIGS / "weather.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _locations(cfg: dict) -> tuple[list[str], dict]:
    codes = list(cfg["regions"])
    lat = ",".join(str(cfg["regions"][c]["lat"]) for c in codes)
    lon = ",".join(str(cfg["regions"][c]["lon"]) for c in codes)
    return codes, {"latitude": lat, "longitude": lon}


def download_observed(start: str, end: str, cfg: dict | None = None) -> Path:
    cfg = cfg or load_config()
    _, loc = _locations(cfg)
    params = {
        **loc,
        "start_date": start,
        "end_date": end,
        "hourly": ",".join(cfg["variables"]),
        "models": cfg["observed"]["model"],
        "timezone": "GMT",
    }
    return fetch(cfg["observed"]["api"], RAW / "weather" / f"observed_{start}_{end}.json", params)


def download_forecast(start: str, end: str, cfg: dict | None = None) -> Path:
    cfg = cfg or load_config()
    _, loc = _locations(cfg)
    hourly = [f"{v}_previous_day{d}" for v in cfg["variables"] for d in cfg["forecast"]["lead_days"]]
    params = {
        **loc,
        "start_date": start,
        "end_date": end,
        "hourly": ",".join(hourly),
        "models": cfg["forecast"]["model"],
        "timezone": "GMT",
    }
    return fetch(cfg["forecast"]["api"], RAW / "weather" / f"forecast_{start}_{end}.json", params)


def read(path: Path, cfg: dict | None = None) -> pd.DataFrame:
    """Format long : ds (UTC, horaire), region, une colonne par variable."""
    cfg = cfg or load_config()
    verify(path)
    codes, _ = _locations(cfg)
    payload = json.loads(path.read_text())
    payload = payload if isinstance(payload, list) else [payload]
    frames = []
    for code, block in zip(codes, payload, strict=True):
        h = block["hourly"]
        df = pd.DataFrame({k: v for k, v in h.items() if k != "time"})
        df.insert(0, "ds", pd.to_datetime(h["time"], utc=True))
        df.insert(1, "region", code)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)
