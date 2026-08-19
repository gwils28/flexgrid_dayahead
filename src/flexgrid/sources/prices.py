"""Prix spot day-ahead France, via l'API publique Energy-Charts (Fraunhofer ISE), sans token.

Pas horaire jusqu'au 30/09/2025, pas 15 min ensuite (passage du couplage SDAC au MTU 15 min le 1er
octobre 2025). La source cite ses propres sources dans `license_info` ; on la conserve au manifeste.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from flexgrid.paths import RAW
from flexgrid.sources.snapshot import fetch, verify

ENERGY_CHARTS = "https://api.energy-charts.info/price"


def download_day_ahead(start: str, end: str, dest: Path | None = None) -> Path:
    dest = dest or RAW / f"price_da_fr_{start}_{end}.json"
    return fetch(ENERGY_CHARTS, dest, {"bzn": "FR", "start": start, "end": end})


def read_day_ahead(path: Path) -> pd.Series:
    """Prix en €/MWh, index UTC au pas natif de la source."""
    verify(path)
    j = json.loads(path.read_text())
    idx = pd.to_datetime(j["unix_seconds"], unit="s", utc=True)
    return pd.Series(j["price"], index=idx, name="price_da", dtype=float).rename_axis("ds")
