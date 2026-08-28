"""LightGBM global, un modèle par quantile, réappris chaque semaine.

Une famille de séries = un modèle : le national seul, ou le panel de segments mis en commun (la cible relative
au niveau rend les segments comparables ; région, tranche et profil sont des catégories). Les quantiles appris
séparément peuvent se croiser : ils sont triés à la prédiction.
"""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd

from flexgrid.backtest.inputs import QUANTILES, qcol
from flexgrid.backtest.origins import Origin
from flexgrid.models import features as F

CATS = ["region_c", "band_c", "profile_c"]


def weather_for(wx: pd.DataFrame, region: str) -> pd.DataFrame:
    """Météo d'une série : sa région, FR pour le national, moyenne Centre-Val de Loire + BFC pour FlexGrid."""
    cols = ["temperature_2m", "cloud_cover", "shortwave_radiation"]
    if region == "PF":
        return wx[wx.region.isin(["24", "27"])].groupby("ds")[cols].mean()
    return wx[wx.region == region].set_index("ds")[cols].sort_index()


def statics(uid: str) -> dict:
    if uid == "FR":
        return {"region_c": -1, "band_c": -1, "profile_c": -1}
    if uid == "FLEXGRID":
        return {"region_c": 99, "band_c": 2, "profile_c": 1}
    return {"region_c": int(uid[:2]), "band_c": int(uid[4]), "profile_c": int(uid[-1])}


def training_table(y: pd.DataFrame, wx_obs: pd.DataFrame, school: pd.DataFrame, family: str) -> pd.DataFrame:
    """Une ligne par pas cible observé de l'historique, météo observée."""
    out = []
    for uid, g in y.groupby("unique_id"):
        s = g.set_index("ds").y.sort_index()
        w = weather_for(wx_obs, g.region.iloc[0])
        targets = s.index[s.index >= s.index[0] + pd.Timedelta(days=16)]
        targets = targets[targets.isin(w.index)]
        f = F.frame(s, w, targets, family, school)
        f["observed"] = g.set_index("ds").observed.reindex(targets).to_numpy()
        out.append(f.assign(unique_id=uid, **statics(uid)))
    t = pd.concat(out).rename_axis("ds").reset_index()
    return t[t.observed & t.level.notna()].drop(columns="observed")


def inference_table(
    y: pd.DataFrame,
    wx_obs: pd.DataFrame,
    wx_fc: pd.DataFrame,
    school: pd.DataFrame,
    origins: list[Origin],
    weather: str = "forecast",
) -> pd.DataFrame:
    """Variables des pas cibles de chaque origine, avec la météo connue à l'émission (ou observée : ablation)."""
    out = []
    for uid, g in y.groupby("unique_id"):
        s = g.set_index("ds").y.sort_index()
        region = g.region.iloc[0]
        wo, wf = weather_for(wx_obs, region), weather_for(wx_fc, region)
        for o in origins:
            known = s.loc[: o.cutoff]
            w = wo if weather == "observed" else F.merged_weather(wo, wf, o.issue)
            f = F.frame(known, w.loc[o.day_start - pd.Timedelta(days=20) : o.day_end], o.targets, o.family, school)
            out.append(f.assign(unique_id=uid, day=o.day, **statics(uid)))
    return pd.concat(out).rename_axis("ds").reset_index()


def fit(train: pd.DataFrame, params: dict, quantiles=QUANTILES, threads: int = 0) -> dict:
    X = train[F.FEATURES + CATS]
    base = {
        "objective": "quantile",
        "learning_rate": params["learning_rate"],
        "num_leaves": params["num_leaves"],
        "min_data_in_leaf": params["min_data_in_leaf"],
        "feature_fraction": params["feature_fraction"],
        "bagging_fraction": params.get("bagging_fraction", 1.0),
        "bagging_freq": params.get("bagging_freq", 0),
        "seed": params["seed"],
        "deterministic": True,
        "verbose": -1,
        "num_threads": threads,
    }
    ds = lgb.Dataset(X, train.y_rel, categorical_feature=CATS, free_raw_data=False)
    return {q: lgb.train({**base, "alpha": q}, ds, num_boost_round=params["num_boost_round"]) for q in quantiles}


def predict(models: dict, rows: pd.DataFrame) -> pd.DataFrame:
    X = rows[F.FEATURES + CATS]
    qs = sorted(models)
    rel = np.sort(np.column_stack([models[q].predict(X) for q in qs]), axis=1)  # pas de croisement
    out = rows[["unique_id", "day", "ds", "h"]].copy()
    for i, q in enumerate(qs):
        out[qcol(q)] = rel[:, i] * rows.level.to_numpy()
    return out


def is_refit_day(o: Origin) -> bool:
    """Réapprentissage hebdomadaire : émission le lundi, donc livraison le mardi."""
    return o.day.dayofweek == 1


def backtest(
    y: pd.DataFrame,
    wx_obs: pd.DataFrame,
    wx_fc: pd.DataFrame,
    school: pd.DataFrame,
    origins: list[Origin],
    params: dict,
    variants: dict | None = None,
    log=print,
) -> pd.DataFrame:
    """`variants` : nom du modèle -> météo d'inférence. Par défaut lgbm (prévue) et lgbm_oracle (observée,
    ablation) : mêmes modèles appris, seule l'entrée météo change."""
    variants = variants or {"lgbm": "forecast", "lgbm_oracle": "observed"}
    train_all = training_table(y, wx_obs, school, origins[0].family)
    rows = {n: inference_table(y, wx_obs, wx_fc, school, origins, w) for n, w in variants.items()}
    preds, models = [], None
    for o in origins:
        if models is None or is_refit_day(o):
            tr = train_all[train_all.ds <= o.cutoff]
            models = fit(tr, params)
            log(f"lgbm {o.family} refit {o.day.date()} sur {len(tr)} lignes")
        for n, r in rows.items():
            preds.append(predict(models, r[r.day == o.day]).assign(model=n))
    return pd.concat(preds, ignore_index=True)
