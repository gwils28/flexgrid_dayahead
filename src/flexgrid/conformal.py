"""Réparation a posteriori d'un intervalle : médiane du modèle conservée, quantiles reconstruits à partir de ses
propres erreurs passées.

À l'origine J, l'ensemble de calibration est l'erreur absolue |y - médiane| au même pas de la journée locale, sur
les `n_cal` jours de livraison précédents dont le réalisé est connu à l'émission (jusqu'à J-2). Le quantile q
vaut médiane + signe(q - 0,5) x quantile conforme (échantillon fini) des erreurs au niveau |2q - 1|. Appliqué à
tous les modèles, y compris aux benchmarks : ce n'est pas un avantage donné au seul challenger.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from flexgrid.backtest.inputs import QUANTILES, qcol
from flexgrid.backtest.origins import TZ


def conformal_quantile(errors: np.ndarray, level: float) -> float:
    errors = errors[~np.isnan(errors)]
    n = len(errors)
    if n == 0:
        return np.nan
    k = min(n, int(np.ceil((n + 1) * level)))
    return float(np.sort(errors)[k - 1])


def conformalize(fc: pd.DataFrame, actuals: pd.DataFrame, n_cal: int, name: str | None = None) -> pd.DataFrame:
    """`fc` : une série, un modèle. `actuals` : ds, y, observed. Rend les jours qui ont `n_cal` jours de passé."""
    a = actuals.set_index("ds")
    f = fc.join(a[["y", "observed"]], on="ds")
    loc = f.ds.dt.tz_convert(TZ)
    f["hh"] = loc.dt.hour * 2 + loc.dt.minute // 30
    f["err"] = (f.y - f[qcol(0.5)]).abs().where(f.observed)
    table = f.pivot_table(index="day", columns="hh", values="err", aggfunc="mean")
    days = np.sort(f.day.unique())
    out = []
    for d in days:
        d = pd.Timestamp(d)
        cal = table.loc[d - pd.Timedelta(days=n_cal + 1) : d - pd.Timedelta(days=2)]
        if len(cal) < n_cal:
            continue
        cur = f[f.day == d]
        med = cur[qcol(0.5)].to_numpy()
        res = cur[["unique_id", "day", "ds", "h"]].copy()
        for q in QUANTILES:
            if q == 0.5:
                res[qcol(q)] = med
                continue
            lv = abs(2 * q - 1)
            r = np.array([conformal_quantile(cal[h].to_numpy(), lv) for h in cur.hh])
            res[qcol(q)] = med + np.sign(q - 0.5) * r
        out.append(res)
    return pd.concat(out, ignore_index=True).assign(model=name or f"{fc.model.iloc[0]}_conformal")
