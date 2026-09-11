"""Style commun des figures. Un modèle garde la même couleur dans toutes les figures.

Palette catégorielle validée (validate_palette.js, fond clair : CVD et vision normale OK ; trois teintes sous
3:1 de contraste, d'où des étiquettes directes ou un tableau à côté). RTE est la référence : encre neutre,
pas une teinte de la palette.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SLOTS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#8a8984"
GRID = "#e6e5e1"
NEUTRAL = "#f0efec"
GOOD, WARNING, CRITICAL = "#0ca30c", "#fab219", "#d03b3b"
BLUES = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
REDS = ["#fbd5d4", "#f3a3a2", "#e86f6e", "#d03b3b", "#a52a2a", "#7a1d1d"]

MODEL_COLORS = {
    "lgbm": SLOTS[0],
    "chronos2_cov": SLOTS[1],
    "ensemble": SLOTS[2],
    "mstl": SLOTS[3],
    "chronos2": SLOTS[4],
    "snaive_day": SLOTS[5],
    "snaive_week": SLOTS[6],
    "ets_seasonal": SLOTS[7],
    "rte_j1": INK,
    "rte_j1_debiased": MUTED,
    "rte_prorata": INK,
}
MODEL_LABELS = {
    "snaive_day": "Naïve J-1 (48)",
    "snaive_week": "Naïve S-1 (336)",
    "mstl": "MSTL",
    "ets_seasonal": "ETS saisonnier",
    "lgbm": "LightGBM",
    "chronos2": "Chronos-2",
    "chronos2_cov": "Chronos-2 + covariables",
    "chronos2_fewshot": "Chronos-2 few-shot",
    "ensemble": "Mélange LGBM + Chronos-2",
    "rte_j1": "RTE J-1",
    "rte_j1_debiased": "RTE J-1 débiaisée",
    "rte_prorata": "RTE J-1 au prorata",
}


def label(model: str) -> str:
    base = model.removesuffix("_conformal")
    return MODEL_LABELS.get(base, base) + (" + conforme" if model.endswith("_conformal") else "")


def color(model: str) -> str:
    return MODEL_COLORS.get(model.removesuffix("_conformal"), MUTED)


def setup() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "axes.edgecolor": GRID,
            "axes.labelcolor": INK_2,
            "axes.titlecolor": INK,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.labelsize": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "xtick.color": INK_2,
            "ytick.color": INK_2,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "lines.linewidth": 2,
            "legend.frameon": False,
            "legend.fontsize": 9,
            "font.size": 10,
            "figure.dpi": 110,
            "savefig.dpi": 150,
            "savefig.bbox": "tight",
            "axes.formatter.use_locale": False,
        }
    )


def save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path


def titled(ax, title: str, sub: str | None = None) -> None:
    """Titre gras, avec une clé de lecture grise entre le titre et le graphique."""
    ax.set_title(title, pad=20 if sub else 8)
    if sub:
        ax.text(0, 1.015, sub, transform=ax.transAxes, fontsize=9, color=INK_2, va="bottom")


MOIS_COURTS = ["janv", "févr", "mars", "avr", "mai", "juin", "juil", "août", "sept", "oct", "nov", "déc"]


def month_label(t) -> str:
    return f"{MOIS_COURTS[t.month - 1]}\n{t.strftime('%y')}"


def month_axis(ax) -> None:
    """Axe des dates en mois français (« janv / 26 »)."""
    import matplotlib.dates as mdates
    from matplotlib.ticker import FuncFormatter

    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=range(1, 13, 2)))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: month_label(mdates.num2date(x))))
