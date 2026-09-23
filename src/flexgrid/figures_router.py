"""Figures du Complexity Router et du cold-start (bloc B, 03_router)."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from flexgrid import plots as P
from flexgrid.paths import RESULTS, ROOT

OUT = ROOT / "03_router" / "figures"
POLICY_LABELS = {
    "always_lgbm": "toujours LightGBM",
    "always_chronos2_cov": "toujours Chronos-2 + cov.",
    "learned_stump": "router appris (stump)",
    "oracle": "router oracle (a posteriori)",
    "ensemble": "mélange des deux",
}
POLICY_COLORS = {
    "always_lgbm": P.color("lgbm"),
    "always_chronos2_cov": P.color("chronos2_cov"),
    "learned_stump": P.SLOTS[6],
    "oracle": P.MUTED,
    "ensemble": P.color("ensemble"),
}


def policies(summary: dict, path: Path) -> Path:
    ci = summary["ratio_vs_always_lgbm"]
    order = ["always_chronos2_cov", "always_lgbm", "learned_stump", "oracle", "ensemble"]
    fig, ax = plt.subplots(figsize=(9, 3.8))
    for i, k in enumerate(order):
        est, lo, hi = ci[k]
        ax.plot([lo, hi], [i, i], color=POLICY_COLORS[k], lw=2.5, solid_capstyle="round")
        ax.plot(est, i, "o", color=POLICY_COLORS[k], ms=9, markeredgecolor=P.SURFACE, markeredgewidth=1.5)
        ax.text(hi + 0.004, i, f"{est:.3f}".replace(".", ","), va="center", fontsize=8, color=P.INK_2)
    ax.axvline(1, color=P.INK, lw=1)
    ax.set_yticks(range(len(order)), [POLICY_LABELS[k] for k in order])
    ax.invert_yaxis()
    ax.set_xlabel("MASE moyen du panel / MASE de « toujours LightGBM » (année de test)")
    P.titled(
        ax,
        "Router : choisir un modèle par segment, ou mélanger ?",
        "81 segments ; trait : IC 95 % (bootstrap sur les segments)",
    )
    fig.tight_layout()
    return P.save(fig, path)


def units(u: pd.DataFrame, stump: dict, path: Path) -> Path:
    f = stump["feature"]
    ratio = u.chronos2_cov / u.lgbm
    band = u.index.str.split("_").str[1]
    fig, ax = plt.subplots(figsize=(9, 5))
    for i, k in enumerate(sorted(set(band))):
        m = band == k
        ax.plot(u[f][m], ratio[m], "o", color=P.SLOTS[i], ms=8, markeredgecolor=P.SURFACE, markeredgewidth=1.2, label=k)
    ax.axhline(1, color=P.INK, lw=1)
    ax.axvline(stump["threshold"], color=P.INK_2, lw=1, ls="--")
    ax.text(stump["threshold"], ax.get_ylim()[1], " seuil appris\n → Chronos-2", va="top", fontsize=8, color=P.INK_2)
    for uid in ["84_P4_ENT1", "76_P4_ENT1", "93_P4_ENT1"]:
        if uid in u.index:
            ax.annotate(uid, (u.loc[uid, f], ratio[uid]), xytext=(6, -10), textcoords="offset points", fontsize=8)
    ax.set_xlabel("coefficient de variation sur les 8 semaines avant le test" if f == "cv" else f)
    ax.set_ylabel("MASE Chronos-2 + cov. / MASE LightGBM")
    P.titled(ax, "Router : qui gagne où, sur l'année de test", "sous 1 : Chronos-2 fait mieux ; couleur : tranche")
    ax.legend(title="tranche", fontsize=8, title_fontsize=8, ncol=5, loc="lower right", bbox_to_anchor=(0.86, 0.0))
    fig.tight_layout()
    return P.save(fig, path)


def drift(d: pd.DataFrame, path: Path) -> Path:
    x = pd.to_datetime(d.index)
    n = (d == "chronos2_cov").sum(axis=1).to_numpy()
    churn = np.r_[np.nan, (d.to_numpy()[1:] != d.to_numpy()[:-1]).sum(axis=1)]
    fig, axes = plt.subplots(2, 1, figsize=(10, 5.5), sharex=True)
    axes[0].plot(x, n, "o-", color=P.color("chronos2_cov"), ms=4)
    axes[0].set_ylabel("segments routés\nvers Chronos-2")
    axes[0].set_ylim(0, len(d.columns))
    P.titled(
        axes[0],
        "Router : la décision dérive-t-elle ?",
        "stump appris sur des variables de 28 jours, réappliqué chaque semaine de l'année de test",
    )
    axes[1].bar(x, churn, width=5, color=P.MUTED)
    axes[1].set_ylabel("segments qui changent\nde branche")
    P.month_axis(axes[1])
    fig.tight_layout()
    return P.save(fig, path)


def coldstart(cs: pd.DataFrame, n_units: int, n_origins: int, path: Path) -> Path:
    """WAPE selon la longueur d'historique ; pointillés : les mêmes modèles avec tout l'historique (backtest)."""
    fig, ax = plt.subplots(figsize=(9, 5))
    lengths = sorted(L for L in cs.history_days.unique() if L > 0)
    for m in ["snaive_week", "chronos2", "chronos2_cov", "chronos2_fewshot", "lgbm"]:
        d = cs[(cs.model == m) & (cs.history_days > 0)].set_index("history_days").reindex(lengths)
        if d.wape.isna().all():
            continue
        # Le few-shot est une variante de Chronos-2 + covariables : même couleur, trait et marqueur différents.
        fewshot = m == "chronos2_fewshot"
        c = P.color("chronos2_cov") if fewshot else P.color(m)
        ax.plot(range(len(lengths)), d.wape * 100, "s--" if fewshot else "o-", color=c, label=P.label(m), ms=7)
        full = cs[(cs.model == m) & (cs.history_days == 0)]
        if len(full):
            ax.axhline(full.wape.iloc[0] * 100, color=c, lw=1, ls=":")
    ax.set_xticks(range(len(lengths)), [f"{L} jours" for L in lengths])
    ax.set_xlabel("historique du segment à l'émission")
    ax.set_ylabel("WAPE (%)")
    ax.set_ylim(bottom=0)
    P.titled(
        ax,
        "Cold-start : que vaut chaque modèle sur un segment presque neuf ?",
        f"{n_units} segments de 3 régions tenues à l'écart, {n_origins} origines ; "
        "pointillés : même modèle, historique complet",
    )
    ax.legend(fontsize=8)
    fig.tight_layout()
    return P.save(fig, path)


def all_figures(protocol: dict) -> list[Path]:
    P.setup()
    summary = json.loads((RESULTS / "router_summary.json").read_text())
    u = pd.read_csv(RESULTS / "router_units.csv", index_col=0)
    d = pd.read_csv(RESULTS / "router_drift.csv", index_col=0)
    return [
        policies(summary, OUT / "router_policies.png"),
        units(u, summary["stump"], OUT / "router_units.png"),
        drift(d, OUT / "router_drift.png"),
        *_coldstart_figures(),
    ]


def _coldstart_figures() -> list[Path]:
    if not (RESULTS / "coldstart_summary.csv").exists():
        return []
    po = pd.read_parquet(RESULTS / "coldstart_per_origin.parquet")
    po = po[po.history_days > 0]
    cs = pd.read_csv(RESULTS / "coldstart_summary.csv")
    return [coldstart(cs, po.unique_id.nunique(), po.day.nunique(), OUT / "coldstart.png")]
