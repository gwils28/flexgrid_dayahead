"""Nettoyage générique d'une série au pas 30 min : contrôle physique, trous, masque d'observation.

Règles (cahier des charges A) :
- une valeur hors de la plage physique devient manquante ;
- un trou de 2 h au plus (4 pas) est interpolé linéairement ;
- un trou plus long prend la valeur du même pas une semaine plus tôt, et il est listé dans le rapport
  de trous : pas de remplissage silencieux ;
- le masque `observed` est faux sur tout pas qui n'était pas une observation valide. Un pas imputé peut
  servir d'entrée à un modèle, il n'est jamais noté comme cible.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

STEP = pd.Timedelta("30min")
WEEK_STEPS = 336


def regular(s: pd.Series, freq: str = "30min") -> pd.Series:
    """Réindexe sur une grille UTC complète entre la première et la dernière valeur."""
    if s.index.duplicated().any():
        raise ValueError("horodatages en double : traiter les transitions d'heure avant")
    s = s.sort_index()
    s = s.loc[s.first_valid_index() : s.last_valid_index()]
    return s.reindex(pd.date_range(s.index[0], s.index[-1], freq=freq, tz="UTC")).rename_axis("ds")


def gap_runs(observed: pd.Series) -> pd.DataFrame:
    """Début, fin et longueur (en pas) de chaque suite de pas non observés."""
    bad = ~observed.to_numpy()
    if not bad.any():
        return pd.DataFrame(
            {"start": pd.DatetimeIndex([], tz="UTC"), "end": pd.DatetimeIndex([], tz="UTC"), "steps": []}
        )
    edges = np.diff(np.concatenate([[0], bad.astype(int), [0]]))
    starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
    return pd.DataFrame(
        {"start": observed.index[starts], "end": observed.index[ends - 1], "steps": ends - starts}
    )


def clean(
    s: pd.Series, physical_range: tuple[float, float], fill_linear_max_steps: int = 4
) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    """Renvoie (série remplie, masque observé, rapport des trous avec la méthode appliquée)."""
    lo, hi = physical_range
    s = regular(s.astype(float))
    s = s.where((s >= lo) & (s <= hi))
    observed = s.notna().rename("observed")
    gaps = gap_runs(observed)
    gaps["method"] = np.where(gaps.steps <= fill_linear_max_steps, "linear", "week_before")

    run_id = observed.cumsum()
    run_len = (~observed).groupby(run_id).transform("sum")
    short = ~observed & (run_len <= fill_linear_max_steps)
    linear = s.interpolate(method="linear", limit_area="inside")
    filled = s.where(observed, linear.where(short))
    # Trous longs : une semaine plus tôt, répété si le trou dépasse une semaine.
    while filled.isna().any():
        before = filled.isna().sum()
        filled = filled.fillna(filled.shift(WEEK_STEPS))
        if filled.isna().sum() == before:
            raise ValueError("trou en tête de série sans semaine précédente")
    return filled.rename(s.name), observed, gaps
