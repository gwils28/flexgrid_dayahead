"""Calendrier français au pas 30 min : tout est calculé sur l'heure locale Europe/Paris.

Un jour de livraison local compte 46, 48 ou 50 demi-heures. Les variables « position dans la journée »
utilisent l'heure d'horloge locale, pas un compteur de pas : 08:00 reste 08:00 le jour du changement.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
from jours_feries_france import JoursFeries

TZ = "Europe/Paris"


def holidays(years: range) -> pd.DataFrame:
    rows = [(d, name) for y in years for name, d in JoursFeries.for_year(y).items()]
    return pd.DataFrame(rows, columns=["date", "name"]).sort_values("date").reset_index(drop=True)


def bridges(hol: set[dt.date], years: range) -> set[dt.date]:
    """Ponts : lundi avant un mardi férié, vendredi après un jeudi férié."""
    out = set()
    for d in hol:
        if d.weekday() == 1:
            out.add(d - dt.timedelta(days=1))
        elif d.weekday() == 3:
            out.add(d + dt.timedelta(days=1))
    return {d for d in out if d.year in years and d not in hol}


def school_zones_on_holiday(school: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.Series:
    """Nombre de zones (A, B, C) en vacances scolaires pour chaque date locale (0 à 3).

    Le jeu officiel donne débuts et fins en UTC (minuit local converti) ; une période couvre les dates
    locales [début, fin). Les lignes « Début des Vacances d'Été » (début = fin) sont des annonces, la
    période réelle est la ligne « Vacances d'Été » de population « Élèves ».
    """
    s = school.copy()
    s["start"] = pd.to_datetime(s.start_date, utc=True).dt.tz_convert(TZ).dt.tz_localize(None).dt.normalize()
    s["end"] = pd.to_datetime(s.end_date, utc=True).dt.tz_convert(TZ).dt.tz_localize(None).dt.normalize()
    s = s[s.end > s.start].drop_duplicates(["zones", "start", "end"])
    days = pd.DatetimeIndex(pd.to_datetime(dates).normalize().unique())
    count = pd.Series(0, index=days)
    for _, g in s.groupby("zones"):
        on = np.zeros(len(days), dtype=bool)
        for r in g.itertuples():
            on |= (days >= r.start) & (days < r.end)
        count += on.astype(int)
    return count.rename("school_zones")


def features(index: pd.DatetimeIndex, school: pd.DataFrame) -> pd.DataFrame:
    """Variables calendaires connues à l'avance pour chaque pas UTC de `index`."""
    local = index.tz_convert(TZ)
    dates = pd.DatetimeIndex(local.date)
    years = range(local.year.min() - 1, local.year.max() + 2)
    hol = set(holidays(years).date)
    brg = bridges(hol, years)
    d = pd.Series(local.date, index=index)
    school_count = school_zones_on_holiday(school, dates)
    out = pd.DataFrame(index=index)
    out["hh"] = local.hour * 2 + local.minute // 30
    out["dow"] = local.day_of_week
    out["holiday"] = d.isin(hol).astype(int).to_numpy()
    out["bridge"] = d.isin(brg).astype(int).to_numpy()
    out["school_zones"] = school_count.reindex(dates).to_numpy()
    doy = local.day_of_year.to_numpy()
    out["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    out["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    # Jour de semaine « effectif » : un férié ou un pont se comporte comme un dimanche ou un samedi.
    out["day_type"] = np.where(out.holiday == 1, 6, np.where(out.bridge == 1, 5, out.dow))
    return out


_TABLE: dict[int, pd.DataFrame] = {}
_START = pd.Timestamp("2014-01-01", tz="UTC")


def lookup(index: pd.DatetimeIndex, school: pd.DataFrame) -> pd.DataFrame:
    """`features` lu par position dans une table précalculée sur 2014-2027 (un calcul par calendrier scolaire).

    Lecture positionnelle plutôt que `reindex` : 30 fois plus rapide, ce qui compte pour 45 000 appels.
    """
    key = id(school)
    if key not in _TABLE:
        full = pd.date_range(_START, pd.Timestamp("2027-12-31", tz="UTC"), freq="30min")
        _TABLE[key] = features(full, school)
    pos = ((pd.DatetimeIndex(index) - _START) // pd.Timedelta("30min")).to_numpy()
    out = _TABLE[key].iloc[pos]
    out.index = index
    return out
