"""Figures du coût d'écart (€) : par modèle, mois par mois, et pourquoi le coût n'est pas un MAE déguisé."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from flexgrid import metrics
from flexgrid import plots as P
from flexgrid.backtest import inputs as I
from flexgrid.backtest.origins import TZ
from flexgrid.data import dataset
from flexgrid.paths import RESULTS, ROOT

OUT = ROOT / "04_cout" / "figures"


def fr(x: float, d: int = 2) -> str:
    return f"{x:.{d}f}".replace(".", ",")


MODELS = ["ensemble", "lgbm", "chronos2_cov", "chronos2", "rte_prorata", "mstl", "snaive_week"]


def annual_bars(cost: pd.DataFrame, saving: pd.DataFrame, ks: list[float], path: Path) -> Path:
    c = cost.loc[[m for m in MODELS if m in cost.index]]
    fig, ax = plt.subplots(figsize=(10, 4.6))
    y = np.arange(len(c))
    ax.barh(y, c.cost_eur / 1e6, 0.6, color=[P.color(m) for m in c.index])
    for i, (_m, r) in enumerate(c.iterrows()):
        pen = " ; ".join(f"{fr(r[f'penalty_k{k:g}'] / 1e3, 0)} k€" for k in ks)
        ax.text(
            r.cost_eur / 1e6 + 0.05,
            i,
            f"{fr(r.cost_eur / 1e6)} M€   (k = {' ; '.join(fr(k, 2).rstrip('0') for k in ks)} : {pen})",
            va="center",
            fontsize=8,
            color=P.INK_2,
        )
    ax.set_yticks(y, [P.label(m) for m in c.index])
    ax.invert_yaxis()
    ax.set_xlim(0, c.cost_eur.max() / 1e6 * 1.75)
    ax.set_xlabel("coût d'écart sur l'année de test, k = 1 (M€)")
    s = saving[(saving.model == "ensemble") & (saving.reference == "rte_prorata")].iloc[0]
    P.titled(
        ax,
        "Portefeuille FlexGrid : ce que coûte chaque nomination",
        f"mélange contre RTE au prorata : {fr(s.saving_eur / 1e6)} M€ évités "
        f"(IC 95 % {fr(s.saving_low / 1e6)} à {fr(s.saving_high / 1e6)}) à k = 1",
    )
    fig.tight_layout()
    return P.save(fig, path)


def monthly_cost(po: pd.DataFrame, path: Path) -> Path:
    t = po[(po.window == "test") & (po.unique_id == dataset.PORTFOLIO_ID)]
    p = t.pivot_table(index="day", columns="model", values="cost_eur", aggfunc="sum")
    mo = p.groupby(p.index.to_period("M")).sum() / 1e3
    x = np.arange(len(mo))
    models = ["ensemble", "rte_prorata", "snaive_week"]
    w = 0.27
    fig, ax = plt.subplots(figsize=(10, 4.2))
    for j, m in enumerate(models):
        ax.bar(x + (j - 1) * w, mo[m], w * 0.92, color=P.color(m), label=P.label(m))
    ax.set_xticks(x, [P.month_label(m) for m in mo.index.to_timestamp()])
    ax.set_ylabel("coût d'écart du mois, k = 1 (k€)")
    share = mo.ensemble.loc["2025-11":"2026-01"].sum() / mo.ensemble.sum()
    P.titled(
        ax, "Portefeuille : où l'argent se perd", f"novembre à janvier : {100 * share:.0f} % du coût annuel du mélange"
    )
    ax.legend()
    fig.tight_layout()
    return P.save(fig, path)


def hourly_cost_vs_error(rows: pd.DataFrame, path: Path) -> Path:
    loc = pd.DatetimeIndex(rows.ds).tz_convert(TZ)
    r = rows.assign(hour=loc.hour + loc.minute / 60)
    g = r.groupby("hour")[["energy_mwh", "cost_eur"]].sum()
    g = g / g.sum() * 100
    pr = r.groupby("hour").price_abs.mean()
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True, height_ratios=[2, 1])
    axes[0].plot(g.index, g.energy_mwh, color=P.MUTED, lw=2, label="part de l'énergie en écart")
    axes[0].plot(g.index, g.cost_eur, color=P.color("ensemble"), lw=2, label="part du coût en €")
    axes[0].set_ylabel("% du total annuel")
    axes[0].set_ylim(bottom=0)
    P.titled(
        axes[0],
        "Mélange, portefeuille : le coût ne suit pas l'erreur",
        "par demi-heure locale ; un MWh d'écart à 8 h coûte plus qu'un MWh à 13 h",
    )
    axes[0].legend()
    axes[1].plot(pr.index, pr, color=P.INK, lw=1.5)
    axes[1].set_ylabel("|prix DA| moyen\n(€/MWh)")
    axes[1].set_ylim(bottom=0)
    axes[1].set_xticks(range(0, 25, 3))
    axes[1].set_xlabel("heure locale du jour J")
    fig.tight_layout()
    return P.save(fig, path)


def all_figures(protocol: dict) -> list[Path]:
    from flexgrid.backtest.score import add_derived, load_forecasts

    P.setup()
    po = pd.read_parquet(RESULTS / "per_origin_segments.parquet")
    cost = pd.read_csv(RESULTS / "cost_portfolio.csv", index_col=0)
    saving = pd.read_csv(RESULTS / "verdicts_portfolio.csv", index_col=0)
    ks = protocol["cost"]["k_scenarios"]
    fcs = add_derived(load_forecasts("segments"), "segments", protocol)
    fc = fcs["ensemble"]
    fc = fc[(fc.unique_id == dataset.PORTFOLIO_ID) & (fc.day >= protocol["windows"]["test"][0])]
    rows = metrics.score_rows(fc, I.series("segments"), dataset.load("prices"))
    return [
        annual_bars(cost, saving, ks, OUT / "cost_annual.png"),
        monthly_cost(po, OUT / "cost_monthly.png"),
        hourly_cost_vs_error(rows, OUT / "cost_vs_error_by_hour.png"),
    ]
