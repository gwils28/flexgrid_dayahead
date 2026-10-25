"""Timestral (Mistral AI) et TimesFM 3.0 (Google Research), en zero-shot, avec les entrées de Chronos-2.

Addendum du protocole du 2026-10-16 (`configs/protocol.yaml`, `models.timestral*`, `models.timesfm3*`). Les
entrées sont construites par `chronos.make_input` : même historique, mêmes covariables, même horloge. Seul le
modèle change. Trois modes de covariables connues à l'avance : aucune, météo seule, météo + calendrier.

Ce qui diffère d'un modèle à l'autre, et qui est dit au rapport :
- Timestral émet 21 quantiles, dont les 7 de la grille du protocole : ils sont lus tels quels.
- TimesFM 3.0 émet 9 quantiles (0,1 à 0,9). q0,25 et q0,75 sont interpolés linéairement entre q0,2 et q0,3
  (q0,7 et q0,8) ; q0,05 et q0,95 sont extrapolés en supposant des queues gaussiennes autour de la médiane
  (écart q0,1-médiane multiplié par z0,95 / z0,9). L'intervalle 90 % de TimesFM est donc une hypothèse, que la
  réparation conforme corrige comme pour les autres modèles.
- Les deux modèles sont appelés avec leurs réglages publiés par défaut (moyenne symétrique, sortie positive).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import torch
from scipy.stats import norm

from flexgrid.backtest.inputs import QUANTILES
from flexgrid.backtest.origins import Origin
from flexgrid.models import chronos
from flexgrid.models.lgbm import weather_for

_MODELS: dict[str, object] = {}
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def _timestral(checkpoint: str, device: str):
    key = f"{checkpoint}@{device}"
    if key not in _MODELS:
        from timestral import TimestralForecaster

        _MODELS[key] = TimestralForecaster.from_pretrained(checkpoint, device=device)
    return _MODELS[key]


def _timesfm(checkpoint: str, device: str, batch_size: int = 64):
    key = f"{checkpoint}@{device}"
    if key not in _MODELS:
        from timesfm3 import ModelConfig, TimesFM3Evaluator

        _MODELS[key] = TimesFM3Evaluator(
            ModelConfig(checkpoint_path=checkpoint, per_core_batch_size=batch_size, device=device)
        )
    return _MODELS[key]


def _known(item: dict) -> np.ndarray | None:
    """(C, T + H) : covariables du passé suivies de celles de l'horizon, dans l'ordre de `chronos.covariates`."""
    if "past_covariates" not in item:
        return None
    keys = list(item["past_covariates"])
    return np.stack([np.r_[item["past_covariates"][k], item["future_covariates"][k]] for k in keys])


def predict_timestral(items: list[dict], horizon: int, checkpoint: str, device: str = DEVICE) -> list[np.ndarray]:
    """(H, Q) par série. Les historiques de longueurs différentes sont complétés à gauche par NaN (« manquant »)."""
    model = _timestral(checkpoint, device)
    T = max(len(it["target"]) for it in items)
    ctx = np.full((len(items), 1, T), np.nan)
    for i, it in enumerate(items):
        ctx[i, 0, T - len(it["target"]) :] = it["target"]
    known = None
    if "past_covariates" in items[0]:
        k0 = _known(items[0])
        known = np.full((len(items), k0.shape[0], T + horizon), np.nan)
        for i, it in enumerate(items):
            k = _known(it)
            known[i, :, T + horizon - k.shape[1] :] = k
    f = model.forecast(ctx.astype(np.float32), prediction_length=horizon, known_covariates=known)
    levels = np.round(np.asarray(f.quantile_levels), 4)
    idx = [int(np.flatnonzero(levels == round(q, 4))[0]) for q in QUANTILES]
    q = f.quantiles.float().cpu().numpy() if torch.is_tensor(f.quantiles) else np.asarray(f.quantiles)
    return [q[i, 0][:, idx] for i in range(len(items))]


def predict_timestral_fewshot(
    targets: list[dict], siblings: list[np.ndarray], horizon: int, checkpoint: str, device: str = DEVICE
) -> list[np.ndarray]:
    """Few-shot du cold-start : les historiques complets des frères entrent comme covariables passées.

    `targets` : entrées de `chronos.make_input` sur 2 048 pas, dont la cible a déjà été masquée (NaN) avant la
    troncature ; `siblings` : (C, T) aux mêmes instants. Les covariables connues (météo, calendrier) restent."""
    model = _timestral(checkpoint, device)
    ctx = np.stack([it["target"] for it in targets])[:, None, :].astype(np.float32)
    past = np.repeat(np.stack(siblings)[None], len(targets), axis=0).astype(np.float32)
    known = np.stack([_known(it) for it in targets]).astype(np.float32)
    f = model.forecast(ctx, prediction_length=horizon, past_covariates=past, known_covariates=known)
    levels = np.round(np.asarray(f.quantile_levels), 4)
    idx = [int(np.flatnonzero(levels == round(q, 4))[0]) for q in QUANTILES]
    q = f.quantiles.float().cpu().numpy() if torch.is_tensor(f.quantiles) else np.asarray(f.quantiles)
    return [q[i, 0][:, idx] for i in range(len(targets))]


def timesfm_to_grid(q9: np.ndarray) -> np.ndarray:
    """(H, 9) aux niveaux 0,1..0,9 -> (H, 7) aux niveaux du protocole (interpolation, queues gaussiennes)."""
    levels = np.round(np.arange(1, 10) / 10, 1)
    med = q9[:, 4]
    tail = norm.ppf(0.95) / norm.ppf(0.9)
    out = []
    for q in QUANTILES:
        if q == 0.05:
            out.append(med - (med - q9[:, 0]) * tail)
        elif q == 0.95:
            out.append(med + (q9[:, 8] - med) * tail)
        else:
            out.append(np.array([np.interp(q, levels, row) for row in q9]))
    return np.stack(out, axis=1)


def predict_timesfm(items: list[dict], horizon: int, checkpoint: str, device: str = DEVICE) -> list[np.ndarray]:
    model = _timesfm(checkpoint, device)
    contexts = [it["target"].astype(np.float32) for it in items]
    known = [_known(it) for it in items]
    outs = model.predict_batch(
        contexts,
        horizon=horizon,
        past_future_covariates=None if known[0] is None else [k.astype(np.float32) for k in known],
        return_quantiles=True,
    )
    return [timesfm_to_grid(np.asarray(o.quantiles).reshape(horizon, -1)) for o in outs]


def predict(items: list[dict], horizon: int, spec: dict, batch: int = 32) -> list[np.ndarray]:
    """Par lots de `batch` séries : 82 segments à 32 768 pas de contexte ne tiennent pas en 8 Go de GPU."""
    if len(items) > batch:
        return [p for i in range(0, len(items), batch) for p in predict(items[i : i + batch], horizon, spec, batch)]
    family = spec["family"]
    if family == "timestral":
        return predict_timestral(items, horizon, spec["checkpoint"], spec.get("device", DEVICE))
    if family == "timesfm3":
        return predict_timesfm(items, horizon, spec["checkpoint"], spec.get("device", DEVICE))
    if family == "chronos2":
        return chronos.predict_items(items, horizon)
    raise ValueError(family)


def backtest(
    y: pd.DataFrame,
    origins: list[Origin],
    spec: dict,
    wx_obs: pd.DataFrame | None = None,
    wx_fc: pd.DataFrame | None = None,
    school: pd.DataFrame | None = None,
    name: str = "timestral",
    log=None,
) -> pd.DataFrame:
    """Une origine par appel : toutes les séries d'un lot sont coupées au même instant, avec le même horizon."""
    series = {u: g.set_index("ds").y.sort_index() for u, g in y.groupby("unique_id")}
    regions = y.groupby("unique_id").region.first().to_dict()
    mode = chronos.cov_mode(spec["covariates"])
    wx = {}
    if mode != "none":
        wx = {u: (weather_for(wx_obs, r), weather_for(wx_fc, r)) for u, r in regions.items()}
    out = []
    for i, o in enumerate(origins):
        keys = list(series)
        items = [
            chronos.make_input(series[u], o, spec["context_steps"], mode, *wx.get(u, (None, None)), school)
            for u in keys
        ]
        preds = predict(items, o.horizon, spec, spec.get("batch", 32))
        out += [chronos.to_frame(p, o, u) for u, p in zip(keys, preds, strict=True)]
        if log and (i % 30 == 0 or i == len(origins) - 1):
            log(f"{name} {o.day.date()} ({i + 1}/{len(origins)})")
    return pd.concat(out, ignore_index=True).assign(model=name)
