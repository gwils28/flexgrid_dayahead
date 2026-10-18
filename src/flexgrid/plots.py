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

# Addendum du 2026-10-16 : trois TSFM de plus, sans neuvième teinte. Une teinte par famille de modèles ; les
# variantes d'une famille (covariables, contexte, taille) gardent sa teinte et se distinguent par le trait ou le
# marqueur, et par leur étiquette. Les modèles secondaires (naïve J-1, ETS) passent en gris.
MODEL_COLORS = {
    "lgbm": SLOTS[0],
    "chronos2_cov": SLOTS[1],
    "ensemble": SLOTS[2],
    "mstl": SLOTS[3],
    "timesfm3_cov": SLOTS[4],
    "snaive_week": SLOTS[5],
    "timestral_cov": SLOTS[6],
    "ens_lgbm_tsfm3": SLOTS[7],
    "snaive_day": MUTED,
    "ets_seasonal": MUTED,
    "rte_j1": INK,
    "rte_j1_debiased": MUTED,
    "rte_prorata": INK,
}
FAMILIES = {
    "chronos2": "chronos2_cov",
    "timestral": "timestral_cov",
    "timesfm3": "timesfm3_cov",
    "ens_lgbm_": "ensemble",
    "ens_all4": "ens_lgbm_tsfm3",
}
MODEL_LABELS = {
    "snaive_day": "Naïve J-1 (48)",
    "snaive_week": "Naïve S-1 (336)",
    "mstl": "MSTL",
    "ets_seasonal": "ETS saisonnier",
    "lgbm": "LightGBM",
    "chronos2": "Chronos-2",
    "chronos2_wx": "Chronos-2 + météo",
    "chronos2_cov": "Chronos-2 + covariables",
    "chronos2_cov_long": "Chronos-2 + cov., contexte long",
    "chronos2_fewshot": "Chronos-2 few-shot",
    "timestral": "Timestral",
    "timestral_wx": "Timestral + météo",
    "timestral_cov": "Timestral + covariables",
    "timestral_cov_long": "Timestral + cov., contexte long",
    "timestral5m": "Timestral-5M",
    "timestral5m_wx": "Timestral-5M + météo",
    "timestral5m_cov": "Timestral-5M + covariables",
    "timestral_fewshot": "Timestral few-shot",
    "timesfm3": "TimesFM 3.0",
    "timesfm3_wx": "TimesFM 3.0 + météo",
    "timesfm3_cov": "TimesFM 3.0 + covariables",
    "timesfm3_cov_long": "TimesFM 3.0 + cov., contexte long",
    "ensemble": "Mélange LGBM + Chronos-2",
    "ens_lgbm_timestral": "Mélange LGBM + Timestral",
    "ens_lgbm_timesfm3": "Mélange LGBM + TimesFM",
    "ens_lgbm_tsfm3": "Mélange LGBM ½ + 3 TSFM ½",
    "ens_all4": "Mélange à parts égales des 4",
    "ens_lgbm_timestral_long": "Mélange LGBM + Timestral long (a posteriori)",
    "rte_j1": "RTE J-1",
    "rte_j1_debiased": "RTE J-1 débiaisée",
    "rte_prorata": "RTE J-1 au prorata",
}


def label(model: str) -> str:
    base = model.removesuffix("_conformal")
    return MODEL_LABELS.get(base, base) + (" + conforme" if model.endswith("_conformal") else "")


def color(model: str) -> str:
    """Teinte du modèle, ou de sa famille pour une variante (`timestral_wx` prend celle de `timestral_cov`)."""
    m = model.removesuffix("_conformal")
    if m in MODEL_COLORS:
        return MODEL_COLORS[m]
    for prefix, ref in FAMILIES.items():
        if m.startswith(prefix):
            return MODEL_COLORS[ref]
    return MUTED


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
