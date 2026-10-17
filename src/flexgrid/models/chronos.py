"""Chronos-2 (amazon/chronos-2) en zero-shot, sans et avec covariables connues à l'avance.

Covariables (variante `chronos2_cov`) : température, nébulosité, rayonnement, férié, pont, zones en vacances
scolaires, jour de week-end. Passé : météo observée ; futur : météo telle que connue à l'émission. La variante
`chronos2_wx` (addendum du 2026-10-16) ne reçoit que la météo : l'écart avec `chronos2_cov` mesure le calendrier.
`cross_learning` reste faux, sauf dans le few-shot du cold-start où un lot ne contient que des séries coupées au
même instant (SPEC, angle mort 11).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import torch

from flexgrid.backtest.inputs import QUANTILES, qcol
from flexgrid.backtest.origins import Origin
from flexgrid.data import calendar as C
from flexgrid.models import features as F
from flexgrid.models.lgbm import weather_for

_PIPE = {}


def pipeline(checkpoint: str = "amazon/chronos-2"):
    if checkpoint not in _PIPE:
        from chronos import Chronos2Pipeline

        device = "cuda" if torch.cuda.is_available() else "cpu"
        _PIPE[checkpoint] = Chronos2Pipeline.from_pretrained(checkpoint, device_map=device)
    return _PIPE[checkpoint]


# Groupes de covariables, partagés par tous les TSFM (models/tsfm.py) : le mode « weather » ne garde que le premier.
WEATHER = ["temp", "cloud", "rad"]
CALENDAR = ["holiday", "bridge", "school", "weekend"]
MODES = {"none": [], "weather": WEATHER, "full": WEATHER + CALENDAR}


def cov_mode(cov: bool | str) -> str:
    """Le protocole d'origine écrit `covariates: true|false` ; l'addendum ajoute `weather`."""
    return {True: "full", False: "none"}.get(cov, cov)


def covariates(
    index: pd.DatetimeIndex, w: pd.DataFrame, school: pd.DataFrame, keys: list[str] | None = None
) -> dict[str, np.ndarray]:
    cal = C.lookup(index, school)
    ww = w.reindex(index)
    out = {
        "temp": ww.temperature_2m.to_numpy(dtype=float),
        "cloud": ww.cloud_cover.to_numpy(dtype=float),
        "rad": ww.shortwave_radiation.to_numpy(dtype=float),
        "holiday": cal.holiday.to_numpy(dtype=float),
        "bridge": cal.bridge.to_numpy(dtype=float),
        "school": cal.school_zones.to_numpy(dtype=float),
        "weekend": (cal.dow >= 5).to_numpy(dtype=float),
    }
    return {k: out[k] for k in (keys or WEATHER + CALENDAR)}


def make_input(
    s: pd.Series,
    o: Origin,
    context: int,
    cov: bool | str,
    wo: pd.DataFrame | None = None,
    wf: pd.DataFrame | None = None,
    school: pd.DataFrame | None = None,
) -> dict:
    hist = s.loc[: o.cutoff].tail(context)
    item = {"target": hist.to_numpy(dtype=float)}
    keys = MODES[cov_mode(cov)]
    if keys:
        w = F.merged_weather(wo, wf, o.issue)
        future = pd.date_range(o.cutoff + pd.Timedelta("30min"), periods=o.horizon, freq="30min")
        item["past_covariates"] = covariates(hist.index, w, school, keys)
        item["future_covariates"] = covariates(future, w, school, keys)
    return item


def predict_items(items: list[dict], horizon: int, cross_learning: bool = False, batch_size: int = 256):
    q, _ = pipeline().predict_quantiles(
        items,
        prediction_length=horizon,
        quantile_levels=QUANTILES,
        batch_size=batch_size,
        cross_learning=cross_learning,
    )
    return [x[0].float().cpu().numpy() for x in q]  # (H, Q) par série


def to_frame(arr: np.ndarray, o: Origin, uid: str) -> pd.DataFrame:
    idx = pd.date_range(o.cutoff + pd.Timedelta("30min"), periods=arr.shape[0], freq="30min")
    d = pd.DataFrame(np.sort(arr, axis=1), columns=[qcol(q) for q in QUANTILES])
    d.insert(0, "ds", idx)
    d.insert(0, "day", o.day)
    d.insert(0, "unique_id", uid)
    d["h"] = np.arange(1, len(idx) + 1)
    return d[(d.ds >= o.day_start) & (d.ds < o.day_end)]


def backtest(
    y: pd.DataFrame,
    origins: list[Origin],
    context: int,
    cov: bool | str,
    wx_obs: pd.DataFrame | None = None,
    wx_fc: pd.DataFrame | None = None,
    school: pd.DataFrame | None = None,
    name: str = "chronos2",
    origins_per_call: int = 8,
) -> pd.DataFrame:
    series = {u: g.set_index("ds").y.sort_index() for u, g in y.groupby("unique_id")}
    regions = y.groupby("unique_id").region.first().to_dict()
    wx = {}
    if cov_mode(cov) != "none":
        wx = {u: (weather_for(wx_obs, r), weather_for(wx_fc, r)) for u, r in regions.items()}
    out = []
    for i in range(0, len(origins), origins_per_call):
        chunk = origins[i : i + origins_per_call]
        keys, items = [], []
        for o in chunk:
            for u, s in series.items():
                wo, wf = wx.get(u, (None, None))
                items.append(make_input(s, o, context, cov, wo, wf, school))
                keys.append((o, u))
        horizon = max(o.horizon for o in chunk)
        if cov_mode(cov) != "none":  # les covariables futures doivent couvrir l'horizon commun du lot
            for o, _ in keys:
                if o.horizon < horizon:
                    raise ValueError("horizons différents dans un lot avec covariables")
        preds = predict_items(items, horizon)
        out += [to_frame(p, o, u) for (o, u), p in zip(keys, preds, strict=True)]
    return pd.concat(out, ignore_index=True).assign(model=name)
