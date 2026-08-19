"""Calendrier scolaire officiel (data.education.gouv.fr), zones A, B, C de métropole."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from flexgrid.paths import RAW
from flexgrid.sources.snapshot import fetch, verify

URL = "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/fr-en-calendrier-scolaire/exports/parquet"


def download(dest: Path | None = None) -> Path:
    dest = dest or RAW / "calendrier_scolaire.parquet"
    params = {"where": 'zones in ("Zone A", "Zone B", "Zone C") and population != "Enseignants"'}
    return fetch(URL, dest, params)


def read(path: Path) -> pd.DataFrame:
    verify(path)
    return pd.read_parquet(path)
