"""L'horloge de la nomination, en code. Tout instant renvoyé est en UTC.

Pour un jour de livraison J (date locale) :
- `issue` : J-1 à 09:00 heure de Paris ;
- `cutoff` : horodatage du dernier pas connu, qui dépend de la famille de séries :
  national -> J-1 08:00 locale ; segments Enedis -> J-2 23:30 locale (fin de J-2) ;
- `targets` : les pas UTC du jour local J (46, 48 ou 50) ;
- l'horizon court de cutoff + 30 min à la fin de J ; seuls les pas de J sont notés.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

TZ = "Europe/Paris"
STEP = pd.Timedelta("30min")
FAMILIES = ("national", "segments")


@dataclass(frozen=True)
class Origin:
    day: pd.Timestamp  # date locale J, minuit naïf
    family: str

    @property
    def day_start(self) -> pd.Timestamp:
        return self.day.tz_localize(TZ).tz_convert("UTC").as_unit("ns")

    @property
    def day_end(self) -> pd.Timestamp:
        return (self.day + pd.Timedelta(days=1)).tz_localize(TZ).tz_convert("UTC").as_unit("ns")

    @property
    def issue(self) -> pd.Timestamp:
        return (self.day - pd.Timedelta(days=1) + pd.Timedelta(hours=9)).tz_localize(TZ).tz_convert("UTC")

    @property
    def cutoff(self) -> pd.Timestamp:
        if self.family == "national":
            local = self.day - pd.Timedelta(days=1) + pd.Timedelta(hours=8)
            return local.tz_localize(TZ).tz_convert("UTC")
        if self.family == "segments":
            return (self.day - pd.Timedelta(days=1)).tz_localize(TZ).tz_convert("UTC") - STEP
        raise ValueError(self.family)

    @property
    def targets(self) -> pd.DatetimeIndex:
        return pd.date_range(self.day_start, self.day_end, freq=STEP, inclusive="left", unit="ns")

    @property
    def horizon(self) -> int:
        """Nombre de pas de cutoff + 30 min à la fin de J."""
        return int((self.day_end - self.cutoff) / STEP) - 1


def days(start: str, end: str) -> list[pd.Timestamp]:
    return list(pd.date_range(start, end, freq="D"))


def origins(start: str, end: str, family: str) -> list[Origin]:
    return [Origin(d.as_unit("ns"), family) for d in days(start, end)]


def delivery_day(ds: pd.Series | pd.DatetimeIndex) -> pd.Series:
    """Date locale (minuit naïf) du jour de livraison de chaque pas UTC."""
    idx = pd.DatetimeIndex(ds)
    return pd.Series(idx.tz_convert(TZ).tz_localize(None).normalize(), index=getattr(ds, "index", None))
