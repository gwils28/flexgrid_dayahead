"""Entrées des modèles : séries d'une famille, coupées à l'horloge de chaque origine."""

from __future__ import annotations

import pandas as pd

from flexgrid.backtest.origins import Origin
from flexgrid.data import dataset

QUANTILES = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]


def qcol(q: float) -> str:
    return f"q{q:g}"


QCOLS = [qcol(q) for q in QUANTILES]


def series(family: str) -> pd.DataFrame:
    """Format long unique_id, ds, y, observed (+ n_sites, region pour les segments)."""
    if family == "national":
        n = dataset.load("national")
        return n.assign(unique_id="FR", region="FR")[["unique_id", "ds", "y", "observed", "region"]]
    if family == "segments":
        return dataset.load("segments")
    raise ValueError(family)


def windows(y: pd.DataFrame, origins: list[Origin], steps: int) -> pd.DataFrame:
    """Les `steps` derniers pas connus de chaque série à chaque origine, empilés.

    unique_id devient « série|jour » : statsforecast parallélise alors sur séries et origines à la fois.
    """
    out = []
    by = {u: g.set_index("ds").y for u, g in y.groupby("unique_id")}
    for o in origins:
        for u, s in by.items():
            w = s.loc[: o.cutoff].tail(steps)
            out.append(pd.DataFrame({"unique_id": f"{u}|{o.day.date()}", "ds": w.index, "y": w.to_numpy()}))
    return pd.concat(out, ignore_index=True)


def split_uid(df: pd.DataFrame) -> pd.DataFrame:
    parts = df.unique_id.str.split("|", expand=True)
    return df.assign(unique_id=parts[0], day=pd.to_datetime(parts[1]))


def keep_targets(fc: pd.DataFrame, origins: list[Origin]) -> pd.DataFrame:
    """Ne garde que les pas du jour de livraison, et numérote l'horizon depuis le cutoff."""
    cut = {o.day: o.cutoff for o in origins}
    start = {o.day: o.day_start for o in origins}
    end = {o.day: o.day_end for o in origins}
    d = fc.day
    keep = (fc.ds >= d.map(start)) & (fc.ds < d.map(end))
    fc = fc[keep].copy()
    fc["h"] = ((fc.ds - fc.day.map(cut)) / pd.Timedelta("30min")).astype(int)
    return fc
