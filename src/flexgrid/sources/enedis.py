"""Enedis : agrégats demi-horaires des points de soutirage > 36 kVA, maille régionale.

Un segment = (région, tranche de puissance souscrite, profil). On garde le secteur tertiaire et les
tranches disjointes P1, P2, P4, P5, P6 (P3 et P7 sont des sous-totaux, les garder compterait deux fois).
`total_energie_soutiree_wh` est l'énergie du pas 30 min, `nb_points_soutirage` le nombre de sites.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from flexgrid.paths import RAW
from flexgrid.sources.snapshot import fetch, verify

ENEDIS = "https://opendata.enedis.fr/api/explore/v2.1/catalog/datasets/conso-sup36-region"
BANDS = [
    "P1: ]36-120] kVA",
    "P2: ]120-250] kVA",
    "P4: ]250-1000] kVA",
    "P5: ]1000-2000] kVA",
    "P6: > 2000 kVA",
]
FIELDS = [
    "horodate",
    "code_region",
    "region",
    "profil",
    "plage_de_puissance_souscrite",
    "nb_points_soutirage",
    "total_energie_soutiree_wh",
]


REGIONS = ["11", "24", "27", "28", "32", "44", "52", "53", "75", "76", "84", "93"]


def download_tertiary(region: str) -> Path:
    """Un fichier par région : l'export complet est lent (environ 2 Mo/min), on parallélise par région."""
    dest = RAW / "enedis" / f"sup36_tertiaire_{region}.parquet"
    params = {
        "select": ",".join(FIELDS),
        "where": f'secteur_activite = "S3: Tertiaire" and code_region = "{region}"',
        "order_by": "horodate",
    }
    return fetch(f"{ENEDIS}/exports/parquet", dest, params, timeout=1800)


def read_tertiary(paths: list[Path]) -> pd.DataFrame:
    for p in paths:
        verify(p)
    df = pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)
    df["horodate"] = pd.to_datetime(df["horodate"], utc=True)
    df = df[df.plage_de_puissance_souscrite.isin(BANDS)].copy()
    band = df.plage_de_puissance_souscrite.str.slice(0, 2)
    prof = df.profil.str.slice(0, 4).str.strip()
    df["unique_id"] = df.code_region.astype(str) + "_" + band + "_" + prof
    return df.rename(columns={"horodate": "ds"})
