"""Métriques par origine (un jour de livraison d'une série), puis moyennées sur les origines.

L'origine est l'unité de l'expérience et celle que le bootstrap rééchantillonne. Seuls les pas observés sont notés.

- mae (MW), bias (réalisé - médiane, MW)
- mape : |e| / y ; smape : 2|e| / (|y| + |f|), la définition de manuel (bornée par 2, PAS celle d'utilsforecast)
- wape : somme |e| / somme y sur le jour
- mase : MAE / échelle, échelle = MAE in-sample de la naïve hebdomadaire (336 pas) sur tout l'historique connu au
  cutoff de l'origine
- pinball : moyenne de la pinball loss sur les 7 quantiles (MW) ; crps : 2 x pinball, approximation du CRPS par la
  grille ; spl : pinball / échelle
- cov50, cov80, cov90 : part des pas dans les intervalles centraux ; width90 : largeur moyenne de l'intervalle 90 %
  en % du réalisé moyen ; winkler90 : score d'intervalle 90 % / échelle
- energy_mwh : |e| x 0,5 h sommé (écart d'équilibre si la nomination est la médiane) ; cost_eur : même chose
  pondéré par |prix day-ahead| (k = 1, définition du brief)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from flexgrid.backtest.inputs import QUANTILES, qcol

INTERVALS = {50: (0.25, 0.75), 80: (0.1, 0.9), 90: (0.05, 0.95)}


def mase_scale(y: pd.DataFrame, cutoffs: pd.DataFrame, season: int = 336) -> pd.DataFrame:
    """Échelle MASE par (unique_id, day) : moyenne de |y_t - y_{t-m}| sur les pas <= cutoff."""
    out = []
    for uid, g in y.groupby("unique_id"):
        s = g.set_index("ds").y.sort_index()
        d = (s - s.shift(season)).abs()
        cum = d.fillna(0).cumsum() / d.notna().cumsum()
        c = cutoffs[cutoffs.unique_id == uid]
        out.append(c.assign(scale=cum.reindex(pd.DatetimeIndex(c.cutoff)).to_numpy()))
    return pd.concat(out, ignore_index=True)[["unique_id", "day", "scale"]]


def pinball(y: np.ndarray, q: np.ndarray, tau: float) -> np.ndarray:
    e = y - q
    return np.maximum(tau * e, (tau - 1) * e)


def score_rows(fc: pd.DataFrame, actuals: pd.DataFrame, prices: pd.DataFrame | None = None) -> pd.DataFrame:
    """Une ligne par pas cible observé, avec les erreurs élémentaires."""
    a = actuals[["unique_id", "ds", "y", "observed"]]
    f = fc.merge(a, on=["unique_id", "ds"], how="left")
    if f.y.isna().any():
        raise ValueError("pas cibles sans réalisé")
    f = f[f.observed].drop(columns="observed")
    med = f[qcol(0.5)].to_numpy()
    y = f.y.to_numpy()
    e = y - med
    r = f[["model", "unique_id", "day", "ds", "h"]].copy()
    r["y"], r["med"], r["e"] = y, med, e
    r["ae"] = np.abs(e)
    r["ape"] = r.ae / np.abs(y)
    r["sape"] = 2 * r.ae / (np.abs(y) + np.abs(med))
    r["pinball"] = np.mean([pinball(y, f[qcol(q)].to_numpy(), q) for q in QUANTILES], axis=0)
    for lv, (lo, hi) in INTERVALS.items():
        r[f"in{lv}"] = (y >= f[qcol(lo)].to_numpy()) & (y <= f[qcol(hi)].to_numpy())
    lo, hi = f[qcol(0.05)].to_numpy(), f[qcol(0.95)].to_numpy()
    r["width90"] = hi - lo
    alpha = 0.1
    r["winkler90"] = (hi - lo) + 2 / alpha * (np.maximum(lo - y, 0) + np.maximum(y - hi, 0))
    r["energy_mwh"] = r.ae * 0.5
    if prices is not None:
        p = prices.set_index("ds").price_da.abs()
        r["price_abs"] = p.reindex(pd.DatetimeIndex(r.ds)).to_numpy()
        r["cost_eur"] = r.energy_mwh * r.price_abs
    return r


def per_origin(rows: pd.DataFrame, scale: pd.DataFrame) -> pd.DataFrame:
    g = rows.groupby(["model", "unique_id", "day"])
    out = g.agg(
        n=("ae", "size"),
        mae=("ae", "mean"),
        bias=("e", "mean"),
        mape=("ape", "mean"),
        smape=("sape", "mean"),
        pinball=("pinball", "mean"),
        cov50=("in50", "mean"),
        cov80=("in80", "mean"),
        cov90=("in90", "mean"),
        width_mw=("width90", "mean"),
        winkler=("winkler90", "mean"),
        energy_mwh=("energy_mwh", "sum"),
        y_mean=("y", "mean"),
        y_sum=("y", "sum"),
        ae_sum=("ae", "sum"),
    )
    if "cost_eur" in rows:
        out["cost_eur"] = g.cost_eur.sum()
    out = out.reset_index().merge(scale, on=["unique_id", "day"], how="left")
    out["wape"] = out.ae_sum / out.y_sum
    out["mase"] = out.mae / out.scale
    out["crps"] = 2 * out.pinball
    out["spl"] = out.pinball / out.scale
    out["width90"] = out.width_mw / out.y_mean
    out["winkler90"] = out.winkler / out.scale
    return out.drop(columns=["ae_sum", "y_sum", "width_mw", "winkler"])


COLUMNS = ["mae", "mape", "smape", "wape", "mase", "pinball", "crps", "cov50", "cov80", "cov90", "width90"]


def summary(po: pd.DataFrame, order: list[str] | None = None, extra: tuple[str, ...] = ()) -> pd.DataFrame:
    t = po.groupby("model")[[*COLUMNS, *extra]].mean()
    t.insert(0, "origins", po.groupby("model").size())
    return t.reindex(order) if order else t.sort_values("mae")
