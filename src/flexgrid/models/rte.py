"""Benchmarks RTE J-1 sur le national : brute, et débiaisée par l'erreur des 28 derniers jours connus.

Une prévision ponctuelle : tous ses quantiles valent la valeur ponctuelle (sa pinball loss est alors son MAE / 2).
Sa version probabiliste équitable est sa réparation conforme (`conformal.py`).
"""

from __future__ import annotations

import pandas as pd

from flexgrid.backtest.inputs import QCOLS
from flexgrid.backtest.origins import TZ, Origin


def _frame(values: pd.Series, origins: list[Origin], name: str) -> pd.DataFrame:
    out = []
    for o in origins:
        v = values.reindex(o.targets)
        d = pd.DataFrame({"unique_id": "FR", "day": o.day, "ds": o.targets, "h": 0})
        for c in QCOLS:
            d[c] = v.to_numpy()
        d["h"] = ((d.ds - o.cutoff) / pd.Timedelta("30min")).astype(int)
        out.append(d)
    return pd.concat(out, ignore_index=True).assign(model=name)


def raw(nat: pd.DataFrame, origins: list[Origin], column: str = "rte_j1", name: str = "rte_j1") -> pd.DataFrame:
    return _frame(nat.set_index("ds")[column], origins, name)


def debiased(nat: pd.DataFrame, origins: list[Origin], window_days: int, column: str = "rte_j1") -> pd.DataFrame:
    """RTE + erreur moyenne (réalisé - RTE) par demi-heure locale sur les jours J-1-window .. J-2."""
    n = nat.set_index("ds")
    err = (n.y - n[column]).where(n.observed)
    loc = err.index.tz_convert(TZ)
    e = pd.DataFrame(
        {
            "err": err.to_numpy(),
            "day": loc.tz_localize(None).normalize(),
            "hh": loc.hour * 2 + loc.minute // 30,
        }
    )
    table = e.pivot_table(index="day", columns="hh", values="err", aggfunc="mean")
    out = []
    for o in origins:
        past = table.loc[o.day - pd.Timedelta(days=window_days + 1) : o.day - pd.Timedelta(days=2)]
        bias = past.mean()
        tl = o.targets.tz_convert(TZ)
        hh = tl.hour * 2 + tl.minute // 30
        v = n[column].reindex(o.targets).to_numpy() + bias.reindex(hh).to_numpy()
        out.append(pd.Series(v, index=o.targets))
    return _frame(pd.concat(out), origins, f"{column.replace('rte_j1', 'rte_j1_debiased')}")
