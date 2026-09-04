"""Figures des blocs B et C : précision, benchmark RTE, calibration, régimes, météo parfaite, portefeuille."""

from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from flexgrid import inference
from flexgrid import plots as P
from flexgrid.backtest.inputs import qcol
from flexgrid.backtest.origins import TZ
from flexgrid.data import calendar as C
from flexgrid.paths import RAW, ROOT

OUT = ROOT / "02_backtest" / "figures"
MAIN = ["lgbm", "chronos2_cov", "ensemble", "chronos2", "mstl", "snaive_week"]


def _test(po: pd.DataFrame, uid: str) -> pd.DataFrame:
    return po[(po.window == "test") & (po.unique_id == uid)]


def forest(po: pd.DataFrame, uid: str, refs: list[str], boot: dict, models: list[str], path: Path, title: str) -> Path:
    t = _test(po, uid)
    fig, axes = plt.subplots(1, len(refs), figsize=(5.5 * len(refs), 0.45 * len(models) + 1.8), sharey=True)
    axes = np.atleast_1d(axes)
    for ax, ref in zip(axes, refs, strict=True):
        for i, m in enumerate(models):
            if m not in t.model.unique() or m == ref:
                continue
            est, lo, hi = inference.compare(t, m, ref, "mae", boot)
            ax.plot([lo, hi], [i, i], color=P.color(m), lw=2.5, solid_capstyle="round")
            ax.plot(est, i, "o", color=P.color(m), ms=8, markeredgecolor=P.SURFACE, markeredgewidth=1.5)
            ax.text(hi + 0.02, i, f"{est:.2f}", va="center", fontsize=8, color=P.INK_2)
        ax.axvline(1, color=P.INK, lw=1)
        ax.set_yticks(range(len(models)), [P.label(m) for m in models])
        ax.invert_yaxis()
        ax.set_xlabel(f"MAE / MAE de {P.label(ref)}")
        P.titled(ax, f"contre {P.label(ref)}", "point : ratio sur l'année ; trait : IC 95 % (blocs de 7 jours)")
    fig.suptitle(title, x=0.02, ha="left", fontweight="bold", fontsize=13)
    fig.tight_layout()
    return P.save(fig, path)


def by_hour(rows_mae: pd.DataFrame, models: list[str], path: Path, title: str, unit: str = "MW") -> Path:
    fig, ax = plt.subplots(figsize=(10, 4.2))
    for m in models:
        d = rows_mae[rows_mae.model == m]
        if d.empty:
            continue
        ls = "--" if m.startswith("rte") else "-"
        ax.plot(d.hour, d.mae, ls, color=P.color(m), label=P.label(m))
    ax.set_xticks(range(0, 25, 3))
    ax.set_xlabel("heure locale du jour J")
    ax.set_ylabel(f"MAE ({unit})")
    ax.set_ylim(bottom=0)
    P.titled(ax, title, "année de test, par demi-heure locale")
    ax.legend(ncol=2)
    fig.tight_layout()
    return P.save(fig, path)


def monthly(po: pd.DataFrame, uid: str, models: list[str], ref: str, path: Path, title: str) -> Path:
    t = _test(po, uid)
    p = t.pivot_table(index="day", columns="model", values="mae")
    mo = p.groupby(p.index.to_period("M")).mean()
    fig, ax = plt.subplots(figsize=(10, 4))
    x = mo.index.to_timestamp()
    for m in models:
        if m in mo:
            ax.plot(x, mo[m] / mo[ref], "o-", color=P.color(m), label=P.label(m), ms=5)
    ax.axhline(1, color=P.INK, lw=1)
    P.month_axis(ax)
    ax.set_ylabel(f"MAE / MAE {P.label(ref)}")
    P.titled(ax, title, f"ratio mensuel ; sous 1, le modèle fait mieux que {P.label(ref)}")
    ax.legend()
    fig.tight_layout()
    return P.save(fig, path)


def calibration(po: pd.DataFrame, uid: str, models: list[str], path: Path, title: str) -> Path:
    t = _test(po, uid)
    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    ax.plot([0.4, 1], [0.4, 1], color=P.INK_2, lw=1, ls=":")
    for m in models:
        # Une prévision ponctuelle (RTE) n'a pas d'intervalle : seule sa réparation conforme est tracée.
        variants = [(m, "o", "-"), (f"{m}_conformal", "s", "--")][1 if m.startswith("rte") else 0 :]
        for variant, marker, ls in variants:
            d = t[t.model == variant]
            if d.empty:
                continue
            cov = [np.average(d[c], weights=d.n) for c in ("cov50", "cov80", "cov90")]
            ax.plot([0.5, 0.8, 0.9], cov, marker=marker, ls=ls, color=P.color(m), label=P.label(variant), ms=7)
    ax.set_xlabel("couverture nominale")
    ax.set_ylabel("couverture observée")
    ax.set_xticks([0.5, 0.8, 0.9])
    P.titled(ax, title, "sur la diagonale : intervalles honnêtes ; dessous : trop étroits")
    ax.legend(fontsize=8)
    fig.tight_layout()
    return P.save(fig, path)


def day_types(po: pd.DataFrame, uid: str, models: list[str], ref: str, path: Path, title: str) -> Path:
    t = _test(po, uid)
    school = pd.read_parquet(RAW / "calendrier_scolaire.parquet")
    days = pd.DatetimeIndex(sorted(t.day.unique()))
    cal = C.features((days + pd.Timedelta(hours=12)).tz_localize(TZ).tz_convert("UTC"), school)
    names = {0: "lundi", 1: "mar-ven", 5: "samedi", 6: "dimanche", 7: "férié", 8: "pont"}
    kind = np.where(cal.holiday == 1, 7, np.where(cal.bridge == 1, 8, cal.dow.clip(upper=6)))
    kind = np.where(np.isin(kind, [1, 2, 3, 4]), 1, kind)
    lab = pd.Series([names[k] for k in kind], index=days)
    p = t.pivot_table(index="day", columns="model", values="mae")
    p["type"] = lab.reindex(p.index).to_numpy()
    order = [n for n in names.values() if n in set(lab)]
    fig, ax = plt.subplots(figsize=(10, 4))
    w = 0.8 / len(models)
    for j, m in enumerate(models):
        if m not in p:
            continue
        r = [p[p.type == k][m].mean() / p[p.type == k][ref].mean() for k in order]
        ax.bar(np.arange(len(order)) + (j - (len(models) - 1) / 2) * w, r, w * 0.92, color=P.color(m), label=P.label(m))
    counts = lab.value_counts()
    ax.set_xticks(range(len(order)), [f"{k}\n(n = {counts[k]})" for k in order])
    ax.axhline(1, color=P.INK, lw=1)
    ax.set_ylabel(f"MAE / MAE {P.label(ref)}")
    P.titled(ax, title, "par type de jour local de l'année de test")
    ax.legend(ncol=3, fontsize=8)
    fig.tight_layout()
    return P.save(fig, path)


def fan(
    fcs: dict, actual: pd.Series, days: list[str], models: list[str], path: Path, title: str, unit: str, div: float
):
    fig, axes = plt.subplots(1, len(days), figsize=(5 * len(days), 4), sharey=False)
    for ax, d in zip(np.atleast_1d(axes), days, strict=True):
        day = pd.Timestamp(d)
        for m in models:
            f = fcs[m]
            f = f[f.day == day].sort_values("ds")
            x = f.ds.dt.tz_convert(TZ).dt.tz_localize(None)
            if m.startswith("rte"):
                ax.plot(x, f[qcol(0.5)] / div, "--", color=P.color(m), lw=1.5, label=P.label(m))
                continue
            ax.fill_between(x, f[qcol(0.1)] / div, f[qcol(0.9)] / div, color=P.color(m), alpha=0.18, lw=0)
            ax.plot(x, f[qcol(0.5)] / div, color=P.color(m), lw=1.8, label=f"{P.label(m)} (médiane, 80 %)")
        a = actual.loc[f.ds.min() : f.ds.max()]
        ax.plot(a.index.tz_convert(TZ).tz_localize(None), a / div, color=P.INK, lw=2.4, label="réalisé")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Hh"))
        ax.set_ylabel(unit)
        P.titled(ax, french_date(day), None)
    handles, labels = np.atleast_1d(axes)[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=len(labels), fontsize=9, bbox_to_anchor=(0.5, -0.06))
    fig.suptitle(title, x=0.02, ha="left", fontweight="bold", fontsize=13)
    fig.tight_layout()
    return P.save(fig, path)


JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = [
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]


def french_date(d: pd.Timestamp) -> str:
    return f"{JOURS[d.dayofweek]} {d.day} {MOIS[d.month - 1]} {d.year}"


def oracle(po: pd.DataFrame, uid: str, path: Path, title: str) -> Path:
    t = _test(po, uid)
    p = t.pivot_table(index="day", columns="model", values="mae")
    mo = p.groupby(p.index.to_period("M"))[["lgbm", "lgbm_oracle"]].mean()
    x = np.arange(len(mo))
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(x - 0.2, mo.lgbm, 0.38, color=P.SLOTS[0], label="LightGBM, météo prévue (ce qu'on sait la veille)")
    ax.bar(x + 0.2, mo.lgbm_oracle, 0.38, color=P.MUTED, label="LightGBM, météo observée (impossible la veille)")
    ax.set_xticks(x, [P.month_label(m) for m in mo.index.to_timestamp()])
    ax.set_ylabel("MAE")
    gain = 1 - p.lgbm_oracle.mean() / p.lgbm.mean()
    P.titled(ax, title, f"sur l'année, la météo parfaite retirerait {100 * gain:.0f} % du MAE")
    ax.legend()
    fig.tight_layout()
    return P.save(fig, path)


def hourly_mae(fc: pd.DataFrame, actual: pd.DataFrame, test_start: str) -> pd.DataFrame:
    a = actual.set_index("ds")
    f = fc[fc.day >= test_start].join(a[["y", "observed"]], on="ds")
    f = f[f.observed]
    loc = f.ds.dt.tz_convert(TZ)
    f["hour"] = loc.dt.hour + loc.dt.minute / 60
    return f.assign(ae=(f.y - f[qcol(0.5)]).abs()).groupby("hour").ae.mean().rename("mae").reset_index()


def national_figures(protocol: dict) -> list[Path]:
    from flexgrid.backtest import inputs as I
    from flexgrid.backtest.score import add_derived, load_forecasts
    from flexgrid.paths import RESULTS

    P.setup()
    boot = protocol["verdict"]["bootstrap"]
    test0 = protocol["windows"]["test"][0]
    po = pd.read_parquet(RESULTS / "per_origin_national.parquet")
    fcs = add_derived(load_forecasts("national"), "national", protocol)
    act = I.series("national")
    out = []
    models = ["ensemble", "lgbm", "chronos2_cov", "chronos2", "mstl", "snaive_week", "rte_j1", "rte_j1_debiased"]
    out.append(
        forest(
            po,
            "FR",
            ["rte_j1", "rte_j1_debiased"],
            boot,
            models,
            OUT / "national_forest.png",
            "National : qui bat RTE J-1 ?",
        )
    )
    hm = pd.concat(
        [
            hourly_mae(fcs[m], act, test0).assign(model=m)
            for m in ["ensemble", "lgbm", "chronos2_cov", "rte_j1", "rte_j1_debiased"]
        ]
    )
    hm["mae"] /= 1e3
    out.append(
        by_hour(
            hm,
            ["ensemble", "lgbm", "chronos2_cov", "rte_j1", "rte_j1_debiased"],
            OUT / "national_by_hour.png",
            "National : erreur selon l'heure",
            "GW",
        )
    )
    out.append(
        monthly(
            po,
            "FR",
            ["ensemble", "lgbm", "chronos2_cov", "rte_j1"],
            "rte_j1_debiased",
            OUT / "national_monthly.png",
            "National : mois par mois, contre RTE débiaisée",
        )
    )
    out.append(
        calibration(
            po,
            "FR",
            ["ensemble", "lgbm", "chronos2_cov", "rte_j1_debiased"],
            OUT / "national_calibration.png",
            "National : les intervalles tiennent-ils ?",
        )
    )
    out.append(
        day_types(
            po,
            "FR",
            ["ensemble", "lgbm", "chronos2_cov"],
            "rte_j1_debiased",
            OUT / "national_day_types.png",
            "National : par type de jour, contre RTE débiaisée",
        )
    )
    out.append(
        oracle(po, "FR", OUT / "national_oracle_weather.png", "National : ce que coûte l'erreur de prévision météo")
    )
    y = act.set_index("ds").y
    out.append(
        fan(
            fcs,
            y,
            ["2026-01-06", "2025-12-25", "2025-08-12"],
            ["lgbm", "chronos2_cov", "rte_j1", "rte_j1_debiased"],
            OUT / "national_fans.png",
            "National : trois jours de l'année de test",
            "GW",
            1e3,
        )
    )
    return out
