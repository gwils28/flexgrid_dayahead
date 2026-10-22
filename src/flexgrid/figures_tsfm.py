"""Figures de l'addendum du 2026-10-16 : Timestral et TimesFM 3.0 face à Chronos-2 (02_backtest/figures).

Une figure par question de l'addendum : quel TSFM, que valent les covariables (météo, puis calendrier), que vaut
un contexte long, et les mélanges. Les nombres viennent de results/tsfm_grid_*.csv et calendar_ablation_*.csv.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from flexgrid import inference
from flexgrid import plots as P
from flexgrid.paths import RESULTS, ROOT

OUT = ROOT / "02_backtest" / "figures"
FAMILY_LABELS = {
    "chronos2": "Chronos-2",
    "timestral": "Timestral-209M",
    "timestral5m": "Timestral-5M (CPU)",
    "timesfm3": "TimesFM 3.0",
}
MODE_LABELS = {
    "none": "sans covariables",
    "weather": "+ météo",
    "full": "+ météo + calendrier",
    "long": "+ tout, contexte long",
}
MODE_MARKERS = {"none": "o", "weather": "s", "full": "D", "long": "^"}
TOP = 1.8  # axe coupé : 4 ponts seulement, un IC va au-delà ; sa borne haute est écrite au sommet
SCOPES = {"national": ("FR", "rte_j1"), "portfolio": ("FLEXGRID", "rte_prorata")}


def _fr(x: float, nd: int = 2) -> str:
    return f"{x:.{nd}f}".replace(".", ",")


def grid(path: Path) -> Path:
    """MAE de chaque variante, relatif à Chronos-2 + covariables, national et portefeuille côte à côte."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 6.2), sharey=True)
    for ax, scope in zip(axes, SCOPES, strict=True):
        g = pd.read_csv(RESULTS / f"tsfm_grid_{scope}.csv", index_col=0)
        rows = [(f, m) for f in FAMILY_LABELS for m in MODE_LABELS if ((g.family == f) & (g.covariates == m)).any()]
        for i, (f, m) in enumerate(rows):
            r = g[(g.family == f) & (g.covariates == m)].iloc[0]
            c = P.color(r.model)
            ax.plot([r.vs_chronos2_cov_low, r.vs_chronos2_cov_high], [i, i], color=c, lw=2.5, solid_capstyle="round")
            ax.plot(
                r.vs_chronos2_cov, i, MODE_MARKERS[m], color=c, ms=8, markeredgecolor=P.SURFACE, markeredgewidth=1.5
            )
            ax.text(
                r.vs_chronos2_cov_high + 0.02,
                i,
                f"{_fr(r.vs_chronos2_cov)}  (MAPE {_fr(100 * r.mape, 1)} %)",
                va="center",
                fontsize=8,
                color=P.INK_2,
            )
        ax.axvline(1, color=P.INK, lw=1)
        ax.set_yticks(range(len(rows)), [f"{FAMILY_LABELS[f]} {MODE_LABELS[m]}" for f, m in rows])
        ax.invert_yaxis()
        ax.set_xlabel("MAE / MAE de Chronos-2 + covariables (année de test)")
        P.titled(
            ax,
            "National" if scope == "national" else "Portefeuille FlexGrid",
            "sous 1 : mieux que Chronos-2 + covariables ; trait : IC 95 %",
        )
    fig.suptitle("Trois TSFM, quatre façons de les nourrir", x=0.02, ha="left", fontweight="bold", fontsize=13)
    fig.tight_layout()
    return P.save(fig, path)


def calendar(path: Path) -> Path:
    """Ce que le calendrier (fériés, ponts, vacances, week-end) ajoute à la météo, par type de jour."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)
    kinds = ["tous", "ouvré", "week-end", "férié", "pont"]
    for ax, scope in zip(axes, SCOPES, strict=True):
        a = pd.read_csv(RESULTS / f"calendar_ablation_{scope}.csv", index_col=0)
        a = a[a.effect == "calendrier"]
        fams = [f for f in FAMILY_LABELS if f in set(a.family)]
        w = 0.8 / len(fams)
        for j, f in enumerate(fams):
            d = a[a.family == f].set_index("day_kind").reindex(kinds)
            x = np.arange(len(kinds)) + (j - (len(fams) - 1) / 2) * w
            c = P.color(f"{f}_cov")
            ax.vlines(x, d.ci_low, d.ci_high.clip(upper=TOP), color=c, lw=2)
            for xi, hi in zip(x, d.ci_high, strict=True):
                if hi > TOP:
                    ax.text(xi, TOP, f"↑ {_fr(hi, 1)}", ha="center", va="bottom", fontsize=7, color=P.INK_2)
            ax.plot(
                x, d.mae_ratio, MODE_MARKERS["full"], color=c, ms=7, markeredgecolor=P.SURFACE, label=FAMILY_LABELS[f]
            )
        days = a.drop_duplicates("day_kind").set_index("day_kind").days.reindex(kinds)
        ax.set_xticks(range(len(kinds)), [f"{k}\n(n = {int(n)})" for k, n in days.items()])
        ax.axhline(1, color=P.INK, lw=1)
        ax.set_ylim(0.3, TOP + 0.15)
        ax.set_ylabel("MAE avec calendrier / MAE météo seule")
        P.titled(
            ax,
            "National" if scope == "national" else "Portefeuille FlexGrid",
            "sous 1 : le calendrier aide ; trait : IC 95 % (bootstrap par jour)",
        )
    axes[0].legend(fontsize=8, loc="upper left")
    fig.suptitle(
        "Les jours fériés : le calendrier passé en covariable aide-t-il ?",
        x=0.02,
        ha="left",
        fontweight="bold",
        fontsize=13,
    )
    fig.tight_layout()
    return P.save(fig, path)


def ensembles(protocol: dict, path: Path) -> Path:
    """Mélanges : chaque mélange contre le mélange d'origine (LightGBM + Chronos-2), national et portefeuille."""
    boot = protocol["verdict"]["bootstrap"]
    models = [
        "ens_lgbm_timestral",
        "ens_lgbm_timesfm3",
        "ens_lgbm_tsfm3",
        "ens_all4",
        "lgbm",
        "timestral_cov",
        "timesfm3_cov",
    ]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), sharey=True)
    for ax, (scope, (uid, _)) in zip(axes, SCOPES.items(), strict=True):
        po = pd.read_parquet(RESULTS / f"per_origin_{'national' if scope == 'national' else 'segments'}.parquet")
        t = po[(po.window == "test") & (po.unique_id == uid)]
        for i, m in enumerate(models):
            est, lo, hi = inference.compare(t, m, "ensemble", "mae", boot)
            ax.plot([lo, hi], [i, i], color=P.color(m), lw=2.5, solid_capstyle="round")
            ax.plot(est, i, "o", color=P.color(m), ms=8, markeredgecolor=P.SURFACE, markeredgewidth=1.5)
            ax.text(hi + 0.01, i, _fr(est), va="center", fontsize=8, color=P.INK_2)
        ax.axvline(1, color=P.INK, lw=1)
        ax.set_yticks(range(len(models)), [P.label(m) for m in models])
        ax.invert_yaxis()
        ax.set_xlabel("MAE / MAE du mélange LGBM + Chronos-2")
        P.titled(
            ax,
            "National" if scope == "national" else "Portefeuille FlexGrid",
            "année de test ; trait : IC 95 % (blocs de 7 jours)",
        )
    fig.suptitle("Les nouveaux TSFM améliorent-ils le mélange ?", x=0.02, ha="left", fontweight="bold", fontsize=13)
    fig.tight_layout()
    return P.save(fig, path)


def all_figures(protocol: dict) -> list[Path]:
    P.setup()
    return [
        grid(OUT / "tsfm_grid.png"),
        calendar(OUT / "tsfm_calendar.png"),
        ensembles(protocol, OUT / "tsfm_ensembles.png"),
    ]
