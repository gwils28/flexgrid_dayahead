"""Variables des modèles supervisés, toutes connues à l'émission de la prévision.

Pour un pas cible t du jour J, l'origine est fixée par J (une seule ligne par pas cible) :
- niveau : moyenne des 7 jours qui précèdent le cutoff ; la cible et les retards sont divisés par ce niveau
  (normalisation par série et par origine, dans l'esprit de RevIN) ;
- retards de 2, 7 et 14 jours **en heure locale d'horloge** et dernière valeur connue. Un retard compté en pas UTC
  (96 pas = 48 h) lit, le jour du passage à l'heure d'hiver, 00:30 locale de J-1 : après le cutoff des segments.
  Le test `test_lags_never_read_after_the_cutoff_even_on_dst_days` l'a trouvé ;
- calendrier local (demi-heure, jour, férié, pont, vacances scolaires, saison) ;
- météo au pas cible et lissée (inertie thermique des bâtiments), moyenne du jour, degrés-jours.
  Apprentissage : météo observée. Inférence : observée jusqu'à l'émission, prévue ensuite.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from flexgrid.backtest.origins import TZ, Origin
from flexgrid.data import calendar as C

LAGS = {"lag_2d": 2, "lag_7d": 7, "lag_14d": 14}  # en jours locaux
CAL = ["hh", "dow", "day_type", "holiday", "bridge", "school_zones", "doy_sin", "doy_cos"]
WX = ["temp", "cloud", "rad", "temp_ewm12", "temp_ewm48", "temp_day", "hdd15", "cdd20", "temp_lag_7d"]
FEATURES = ["h", "rel_last", *[f"rel_{k}" for k in LAGS], *CAL, *WX]


def cutoffs(targets: pd.DatetimeIndex, family: str) -> pd.DatetimeIndex:
    """Cutoff de l'origine de chaque pas cible (vectorisé, mêmes règles que `Origin`)."""
    day = targets.tz_convert(TZ).tz_localize(None).normalize()
    if family == "national":
        local = day - pd.Timedelta(days=1) + pd.Timedelta(hours=8)
        return local.tz_localize(TZ).tz_convert("UTC")
    local = day - pd.Timedelta(days=1)
    return local.tz_localize(TZ).tz_convert("UTC") - pd.Timedelta("30min")


def local_shift(targets: pd.DatetimeIndex, days: int) -> pd.DatetimeIndex:
    """Même heure d'horloge locale `days` jours plus tôt, en UTC.

    Heure inexistante (mars) : décalée vers l'avant ; heure ambiguë (octobre) : première occurrence.
    """
    local = targets.tz_convert(TZ).tz_localize(None) - pd.Timedelta(days=days)
    return local.tz_localize(TZ, nonexistent="shift_forward", ambiguous=np.zeros(len(local), dtype=bool)).tz_convert(
        "UTC"
    )


def weather_features(w: pd.DataFrame, targets: pd.DatetimeIndex) -> pd.DataFrame:
    """`w` : index ds (30 min), colonnes temperature_2m, cloud_cover, shortwave_radiation, continu."""
    t = w.temperature_2m
    out = pd.DataFrame(index=targets)
    out["temp"] = t.reindex(targets).to_numpy()
    out["cloud"] = w.cloud_cover.reindex(targets).to_numpy()
    out["rad"] = w.shortwave_radiation.reindex(targets).to_numpy()
    out["temp_ewm12"] = t.ewm(halflife=24).mean().reindex(targets).to_numpy()  # demi-vie 12 h
    out["temp_ewm48"] = t.ewm(halflife=96).mean().reindex(targets).to_numpy()  # demi-vie 48 h
    day = t.index.tz_convert(TZ).date
    tday = t.groupby(day).transform("mean")
    out["temp_day"] = tday.reindex(targets).to_numpy()
    out["hdd15"] = np.maximum(0, 15 - out.temp_day)
    out["cdd20"] = np.maximum(0, out.temp_day - 20)
    out["temp_lag_7d"] = t.reindex(local_shift(targets, 7)).to_numpy()
    return out


def target_features(y: pd.Series, targets: pd.DatetimeIndex, family: str) -> pd.DataFrame:
    """Niveau, retards relatifs et dernière valeur, pour une série `y` (index ds complet au pas 30 min)."""
    cut = cutoffs(targets, family)
    level = y.rolling(336, min_periods=336).mean()  # moyenne des 7 jours finissant au pas courant
    out = pd.DataFrame(index=targets)
    out["cutoff"] = cut
    out["level"] = level.reindex(cut).to_numpy()
    out["h"] = ((targets - cut) / pd.Timedelta("30min")).astype(int)
    out["rel_last"] = y.reindex(cut).to_numpy() / out.level
    for k, n in LAGS.items():
        out[f"rel_{k}"] = y.reindex(local_shift(targets, n)).to_numpy() / out.level
    return out


def frame(y: pd.Series, w: pd.DataFrame, targets: pd.DatetimeIndex, family: str, school: pd.DataFrame) -> pd.DataFrame:
    f = target_features(y, targets, family)
    f = f.join(C.lookup(targets, school)[CAL]).join(weather_features(w, targets))
    f["y_rel"] = y.reindex(targets).to_numpy() / f.level
    return f


def merged_weather(obs: pd.DataFrame, fc: pd.DataFrame, issue: pd.Timestamp) -> pd.DataFrame:
    """Météo telle que connue à l'émission : observée jusqu'à `issue`, prévue après."""
    past = obs.loc[:issue]
    fut = fc.loc[fc.index > issue]
    return pd.concat([past, fut]).sort_index()


def check_no_lookahead(f: pd.DataFrame) -> None:
    """Aucun retard ne lit un pas postérieur au cutoff de son origine."""
    for k, n in LAGS.items():
        if (local_shift(pd.DatetimeIndex(f.index), n) > pd.DatetimeIndex(f.cutoff)).any():
            raise AssertionError(f"{k} lit après le cutoff")


def origin_targets(o: Origin) -> pd.DatetimeIndex:
    return o.targets
