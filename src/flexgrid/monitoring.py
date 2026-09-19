"""Monitoring rejoué sur l'année de test (bloc E) : ce qu'un tableau de bord aurait montré, jour après jour.

- dérive des données : PSI et KS mensuels de la charge, de la température prévue et du prix, contre l'année
  précédente au même mois (référence saisonnière : comparer janvier à juillet ferait toujours sonner l'alarme) ;
- dérive du concept : MAE glissant sur 28 jours du modèle / benchmark ; alerte si > 1 pendant 14 jours de suite ;
- calibration : couverture glissante de l'intervalle 90 % ;
- KPI métier : coût d'écart mensuel.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

PSI_BINS = 10


def psi(reference: np.ndarray, current: np.ndarray, bins: int = PSI_BINS) -> float:
    """Population Stability Index, classes aux déciles de la référence.

    Lecture usuelle : < 0,1 stable, > 0,25 dérive.
    """
    reference, current = reference[~np.isnan(reference)], current[~np.isnan(current)]
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    r = np.histogram(reference, edges)[0] / len(reference)
    c = np.histogram(current, edges)[0] / len(current)
    r, c = np.clip(r, 1e-4, None), np.clip(c, 1e-4, None)
    return float(np.sum((c - r) * np.log(c / r)))


def monthly_drift(s: pd.Series, start: str, end: str) -> pd.DataFrame:
    """PSI et statistique KS de chaque mois de [start, end] contre le même mois un an plus tôt."""
    rows = []
    for m in pd.date_range(start, end, freq="MS", tz="UTC"):
        cur = s.loc[m : m + pd.offsets.MonthEnd(1) + pd.Timedelta(hours=23, minutes=59)]
        ref_start = m - pd.DateOffset(years=1)
        ref = s.loc[ref_start : ref_start + pd.offsets.MonthEnd(1) + pd.Timedelta(hours=23, minutes=59)]
        if len(cur) == 0 or len(ref) == 0:
            continue
        ks = stats.ks_2samp(ref.to_numpy(), cur.to_numpy())
        rows.append({"month": m, "psi": psi(ref.to_numpy(), cur.to_numpy()), "ks": ks.statistic})
    return pd.DataFrame(rows)


def rolling_ratio(po: pd.DataFrame, uid: str, model: str, reference: str, metric: str = "mae", days: int = 28):
    p = po[po.unique_id == uid].pivot_table(index="day", columns="model", values=metric).sort_index()
    r = p[model].rolling(days).mean() / p[reference].rolling(days).mean()
    return r.rename(f"{model}/{reference}")


def alerts(ratio: pd.Series, threshold: float = 1.0, persist: int = 14) -> pd.Series:
    """Vrai les jours où le ratio dépasse le seuil depuis au moins `persist` jours consécutifs."""
    above = ratio > threshold
    run = above.groupby((~above).cumsum()).cumsum()
    return run >= persist


def rolling_coverage(po: pd.DataFrame, uid: str, model: str, days: int = 28) -> pd.Series:
    p = po[(po.unique_id == uid) & (po.model == model)].set_index("day").sort_index()
    return (p.cov90 * p.n).rolling(days).sum() / p.n.rolling(days).sum()
