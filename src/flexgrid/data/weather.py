"""Météo par région et nationale, au pas 30 min UTC.

- observée : ERA5 (réanalyse), sert à l'apprentissage et à l'ablation « météo parfaite » ;
- prévue : ECMWF IFS 0,25°, valeur émise 48 h avant l'heure valide (`previous_day2`), sert au backtest.
  Lecture prudente : à l'heure d'émission J-1 09:00, le run 24 h avant une heure de J postérieure à
  ~01:00 n'est pas encore publié ; le run 48 h avant l'est toujours (SPEC, angle mort 3).

La moyenne nationale pondère les 12 régions par leur population. Le passage horaire → 30 min est une
interpolation linéaire (température, nébulosité) ; le rayonnement est une moyenne horaire, interpolé de même.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from flexgrid.paths import RAW
from flexgrid.sources import weather as src

VARS = ["temperature_2m", "cloud_cover", "shortwave_radiation"]


def _read_all(pattern: str, cfg: dict) -> pd.DataFrame:
    files = sorted((RAW / "weather").glob(pattern))
    if not files:
        raise FileNotFoundError(pattern)
    df = pd.concat([src.read(f, cfg) for f in files], ignore_index=True)
    return df.drop_duplicates(["ds", "region"]).sort_values(["region", "ds"])


def observed(cfg: dict | None = None) -> pd.DataFrame:
    cfg = cfg or src.load_config()
    return _read_all("observed_*.json", cfg)[["ds", "region", *VARS]]


def forecast(lead_day: int = 2, cfg: dict | None = None) -> pd.DataFrame:
    cfg = cfg or src.load_config()
    df = _read_all("forecast_*.json", cfg)
    cols = {f"{v}_previous_day{lead_day}": v for v in VARS}
    return df[["ds", "region", *cols]].rename(columns=cols)


def to_half_hour(df: pd.DataFrame) -> pd.DataFrame:
    """Horaire → 30 min par région, interpolation linéaire entre heures valides."""
    out = []
    for region, g in df.groupby("region"):
        g = g.set_index("ds")[VARS]
        idx = pd.date_range(g.index.min(), g.index.max(), freq="30min", tz="UTC")
        h = g.reindex(idx).interpolate(method="time", limit=1, limit_area="inside")
        out.append(h.assign(region=region).rename_axis("ds").reset_index())
    return pd.concat(out, ignore_index=True)


def national(df: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    """Moyenne pondérée par la population des régions présentes à chaque pas."""
    cfg = cfg or src.load_config()
    w = pd.Series({k: v["pop"] for k, v in cfg["regions"].items()}, name="w")
    d = df.join(w, on="region")
    num = d[VARS].mul(d.w, axis=0).groupby(d.ds).sum(min_count=1)
    den = d[VARS].notna().mul(d.w, axis=0).groupby(d.ds).sum()
    return (num / den).rename_axis("ds")


def regional(df: pd.DataFrame) -> pd.DataFrame:
    """Format large par région : index ds, colonnes (variable, région)."""
    return df.pivot(index="ds", columns="region", values=VARS)


def cache(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    return path
