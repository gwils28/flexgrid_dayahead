"""Du MW à l'euro : coût d'écart d'équilibre de la nomination J-1 (bloc C, métrique métier).

Écart (MWh) = |réalisé - nomination| x 0,5 h, nomination = médiane du modèle. Coût = écart x |prix day-ahead| x k.
k = 1 est la définition du brief (« volume x prix ») : la valeur de l'énergie mal placée, une borne haute. Une
pénalité réelle est un écart de prix : k = 0,1 à 0,5 (SPEC, angle mort 8). Le coût étant proportionnel à k, le
classement des modèles en € ne dépend pas de k.
"""

from __future__ import annotations

import pandas as pd

from flexgrid.inference import bootstrap, diff_of_sums


def annual(po: pd.DataFrame, uid: str, window: str = "test", k_scenarios=(0.1, 0.25, 0.5)) -> pd.DataFrame:
    p = po[(po.unique_id == uid) & (po.window == window)]
    t = p.groupby("model").agg(
        days=("day", "nunique"), mape=("mape", "mean"), energy_mwh=("energy_mwh", "sum"), cost_eur=("cost_eur", "sum")
    )
    for k in k_scenarios:
        t[f"penalty_k{k:g}"] = t.cost_eur * k
    return t.sort_values("cost_eur")


def saving(po: pd.DataFrame, uid: str, model: str, reference: str, boot: dict, window: str = "test"):
    """Coût évité sur la fenêtre (référence - modèle), en €, avec IC par blocs de jours."""
    p = po[(po.unique_id == uid) & (po.window == window)]
    piv = p.pivot_table(index="day", columns="model", values="cost_eur", aggfunc="sum")[[reference, model]].dropna()
    return bootstrap(
        diff_of_sums,
        [piv[reference].to_numpy(), piv[model].to_numpy()],
        boot["block_days"],
        boot["replicates"],
        boot["seed"],
    )


def scale_factor(national: pd.DataFrame, start: str, end: str, target_gwh: float) -> float:
    """Facteur qui ramène l'énergie nationale de la fenêtre à `target_gwh` (mise à l'échelle de comparaison)."""
    n = national.set_index("ds").loc[start:end]
    gwh = n.y.sum() * 0.5 / 1e3
    days = (pd.Timestamp(end) - pd.Timestamp(start)).days + 1
    return target_gwh / (gwh * 365 / days)
