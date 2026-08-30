"""Incertitude sur les origines : bootstrap par blocs de jours consécutifs, et verdict pré-enregistré.

Reprend W25 : les 48 pas d'un jour ne sont pas indépendants, deux jours voisins non plus. On rééchantillonne des
blocs de `block_days` jours consécutifs, jamais des pas isolés.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def block_indices(n: int, block: int, rng: np.random.Generator) -> np.ndarray:
    block = max(1, min(block, n))
    starts = rng.integers(0, n - block + 1, size=int(np.ceil(n / block)))
    return (starts[:, None] + np.arange(block)[None, :]).ravel()[:n]


def bootstrap(stat, arrays: list[np.ndarray], block: int, replicates: int, seed: int, ci: float = 0.95):
    """(estimation, borne basse, borne haute) de stat(*arrays) ; tableaux alignés, dans l'ordre du temps."""
    rng = np.random.default_rng(seed)
    n = len(arrays[0])
    est = float(stat(*arrays))
    draws = np.empty(replicates)
    for b in range(replicates):
        idx = block_indices(n, block, rng)
        draws[b] = stat(*(a[idx] for a in arrays))
    lo, hi = np.quantile(draws, [(1 - ci) / 2, 1 - (1 - ci) / 2])
    return est, float(lo), float(hi)


def ratio_of_means(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(a) / np.mean(b))


def diff_of_sums(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sum(a) - np.sum(b))


def compare(po: pd.DataFrame, challenger: str, reference: str, metric: str, boot: dict, stat=ratio_of_means):
    """Statistique (par défaut ratio des moyennes challenger / référence) sur les jours communs, avec IC."""
    p = po.pivot_table(index="day", columns="model", values=metric, aggfunc="sum").sort_index()
    p = p[[challenger, reference]].dropna()
    return bootstrap(
        stat, [p[challenger].to_numpy(), p[reference].to_numpy()], boot["block_days"], boot["replicates"], boot["seed"]
    )


def mean_ci(values: np.ndarray, boot: dict):
    return bootstrap(np.mean, [np.asarray(values)], boot["block_days"], boot["replicates"], boot["seed"])


def verdict(lo: float, hi: float, cov90: float | None, band: tuple[float, float]) -> str:
    """Lecture pré-enregistrée d'un challenger contre une référence (ratio de MAE)."""
    if hi < 1:
        if cov90 is None:
            return "GAGNE"
        return "GAGNE" if band[0] <= cov90 <= band[1] else "GAGNE EN POINT SEULEMENT"
    if lo > 1:
        return "PERD"
    return "PAS DE DIFFÉRENCE"
