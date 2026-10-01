"""Schéma d'architecture du service J-1 (bloc D)."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from flexgrid import plots as P
from flexgrid.paths import ROOT

OUT = ROOT / "05_production" / "figures"


def _box(ax, x, y, w, h, title, lines, color):
    ax.add_patch(
        FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08", fc=P.SURFACE, ec=color, lw=1.8)
    )
    ax.text(x + 0.12, y + h - 0.18, title, fontsize=10, fontweight="bold", color=P.INK, va="top")
    for i, line in enumerate(lines):
        ax.text(x + 0.12, y + h - 0.55 - 0.32 * i, line, fontsize=8, color=P.INK_2, va="top")


def _arrow(ax, a, b, text=None):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=12, color=P.INK_2, lw=1.2))
    if text:
        ax.text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + 0.12, text, fontsize=7.5, color=P.INK_2, ha="center")


def architecture() -> Path:
    P.setup()
    fig, ax = plt.subplots(figsize=(13, 6.6))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 6.6)
    ax.axis("off")
    _box(
        ax,
        0.1,
        3.6,
        2.6,
        2.7,
        "Sources",
        [
            "éCO2mix (ODRÉ)",
            "Enedis > 36 kVA",
            "Open-Meteo (ECMWF)",
            "Energy-Charts (prix)",
            "ENTSO-E si token (secret)",
        ],
        P.SLOTS[2],
    )
    _box(
        ax,
        3.2,
        3.6,
        2.6,
        2.7,
        "Ingestion",
        [
            "snapshots figés",
            "sha256 au manifeste",
            "lignes fantômes DST",
            "trous : masque observé",
            "horloge J-1 09:00",
        ],
        P.SLOTS[2],
    )
    _box(
        ax,
        6.3,
        4.4,
        2.8,
        1.9,
        "LightGBM (CPU)",
        ["réappris le lundi", "registre MLflow", "alias « champion »"],
        P.SLOTS[0],
    )
    _box(
        ax,
        6.3,
        2.2,
        2.8,
        1.9,
        "Chronos-2 (GPU)",
        ["zero-shot + covariables", "délai max 300 s", "sinon repli LightGBM"],
        P.SLOTS[1],
    )
    _box(
        ax,
        9.6,
        3.6,
        3.2,
        2.7,
        "Nomination",
        [
            "mélange des quantiles",
            "programme 30 min (MWh)",
            "= médiane du modèle",
            "API FastAPI : /forecast",
            "/nomination",
        ],
        P.INK,
    )
    _box(
        ax,
        3.2,
        0.15,
        9.6,
        1.6,
        "Monitoring (bloc E)",
        [
            "dérive des données : PSI / KS mensuels, référence saisonnière    calibration : couverture 90 % glissante sur 28 j",
            "dérive du concept : MAE 28 j / benchmark, seuil auto-référencé    routes : part et bascules    KPI : coût d'écart mensuel (€)",
        ],
        P.SLOTS[3],
    )
    _arrow(ax, (2.7, 4.95), (3.2, 4.95))
    _arrow(ax, (5.8, 5.2), (6.3, 5.3), "features")
    _arrow(ax, (5.8, 4.4), (6.3, 3.3))
    ax.text(5.95, 3.45, "historique\n+ covariables", fontsize=7.5, color=P.INK_2, ha="right")
    _arrow(ax, (9.1, 5.3), (9.6, 5.1))
    _arrow(ax, (9.1, 3.1), (9.6, 4.2))
    _arrow(ax, (11.2, 3.6), (11.2, 1.75), "réalisé J+1")
    ax.text(
        0.1,
        2.9,
        "Dagster : une partition = un jour de livraison J\nplanning 09:00 Europe/Paris, la veille\ncontrôles : quantiles ordonnés, 46/48/50 pas",
        fontsize=8.5,
        color=P.INK,
        va="top",
    )
    ax.set_title("Le service J-1 de FlexGrid", loc="left")
    return P.save(fig, OUT / "architecture.png")


if __name__ == "__main__":
    print(architecture())
