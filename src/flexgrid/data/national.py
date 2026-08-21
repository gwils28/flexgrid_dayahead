"""Consommation nationale éCO2mix et prévision J-1 de RTE, au pas 30 min UTC.

Transitions d'heure, constatées dans la source (voir SPEC, angle mort 1) :
- mars : l'heure locale 02:xx, qui n'existe pas, est publiée et convertie sur le même instant UTC que
  03:xx. Ces lignes fantômes recopient des valeurs voisines ; on les écarte par leur heure locale.
- octobre : une seule des deux heures locales 02:xx est publiée ; l'heure UTC manquante devient un trou
  de 2 pas, interpolé pour les entrées et jamais noté.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from flexgrid.data.clean import clean, regular
from flexgrid.sources.snapshot import verify

TZ = "Europe/Paris"


def drop_phantom_rows(raw: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Écarte les lignes dont l'heure locale n'existe pas (passage à l'heure d'été)."""
    local = pd.to_datetime(raw["date"].astype(str) + " " + raw["heure"].astype(str))
    utc = local.dt.tz_localize(TZ, nonexistent="NaT", ambiguous="NaT")
    phantom = utc.isna() & (local.dt.month == 3)
    return raw[~phantom], int(phantom.sum())


def read_raw(path: Path) -> pd.DataFrame:
    verify(path)
    raw = pd.read_parquet(path)
    raw["date_heure"] = pd.to_datetime(raw["date_heure"], utc=True)
    return raw


def build(path: Path, physical_range: tuple[float, float], fill_linear_max_steps: int) -> dict:
    """Charge, répare les transitions d'heure et nettoie.

    Renvoie un dict : `load` (MW remplie), `observed`, `gaps`, `rte_j1` (MW, 15 min), `phantom_rows`.
    """
    raw, n_phantom = drop_phantom_rows(read_raw(path))
    df = raw.set_index("date_heure").sort_index().rename_axis("ds")
    if df.index.duplicated().any():
        raise ValueError("horodatages UTC encore en double après retrait des lignes fantômes")
    load = df["consommation"].dropna()
    filled, observed, gaps = clean(load.rename("y"), physical_range, fill_linear_max_steps)
    rte = regular(df["prevision_j1"].astype(float), freq="15min").rename("rte_j1")
    return {"load": filled, "observed": observed, "gaps": gaps, "rte_j1": rte, "phantom_rows": n_phantom}


def rte_at(rte_15: pd.Series, index: pd.DatetimeIndex, alignment: str = "same") -> pd.Series:
    """Prévision RTE J-1 lue aux pas 30 min de `index`.

    same : valeur du quart d'heure de même horodatage (lecture pré-enregistrée) ;
    previous : valeur du quart d'heure précédent (la plus favorable à RTE, test de sensibilité).
    """
    if alignment == "same":
        out = rte_15.reindex(index)
    elif alignment == "previous":
        out = rte_15.shift(1).reindex(index)
    else:
        raise ValueError(alignment)
    return out.rename("rte_j1")
