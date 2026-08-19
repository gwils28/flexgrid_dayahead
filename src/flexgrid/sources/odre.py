"""ODRÉ (Opendatasoft) : éCO2mix national consolidé/définitif et températures départementales.

La conso réalisée est au pas 30 min, les prévisions RTE J-1 et J au pas 15 min : une même table porte
les deux pas, avec `consommation` vide aux quarts d'heure. L'horodatage `date_heure` est en UTC ; les
colonnes `date`/`heure` sont en heure locale et dupliquent 02:00 le dernier dimanche d'octobre.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from flexgrid.paths import RAW
from flexgrid.sources.snapshot import fetch, verify

ODRE = "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets"
ECO2MIX_FIELDS = ["date", "heure", "date_heure", "consommation", "prevision_j1", "prevision_j"]


def download_eco2mix(start: str, end: str, dest: Path | None = None) -> Path:
    dest = dest or RAW / f"eco2mix_national_cons_def_{start}_{end}.parquet"
    params = {
        "select": ",".join(ECO2MIX_FIELDS),
        "where": f'date_heure >= "{start}T00:00:00+00:00" and date_heure < "{end}T00:00:00+00:00"',
        "order_by": "date_heure",
    }
    return fetch(f"{ODRE}/eco2mix-national-cons-def/exports/parquet", dest, params)


def read_eco2mix(path: Path) -> pd.DataFrame:
    """Table brute, index UTC au pas 15 min, colonnes en MW. Aucune réparation ici."""
    verify(path)
    df = pd.read_parquet(path)
    df["date_heure"] = pd.to_datetime(df["date_heure"], utc=True)
    return df.set_index("date_heure").sort_index().rename_axis("ds")


def download_temperatures(start: str, end: str, dest: Path | None = None) -> Path:
    """Températures quotidiennes observées par département (Météo-France via ODRÉ), pour l'ablation."""
    dest = dest or RAW / f"temperature_departementale_{start}_{end}.parquet"
    params = {"where": f'date_obs >= "{start}" and date_obs < "{end}"', "order_by": "date_obs"}
    return fetch(f"{ODRE}/temperature-quotidienne-departementale/exports/parquet", dest, params)
