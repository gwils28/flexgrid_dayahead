"""Figures du bloc A (données) : ce que la source contient, ses défauts, et pourquoi le protocole est ainsi."""

from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from flexgrid import plots as P
from flexgrid.data import calendar as C
from flexgrid.data import dataset
from flexgrid.paths import RAW, ROOT

OUT = ROOT / "01_donnees" / "figures"
TZ = "Europe/Paris"


def _local(ds: pd.Series) -> pd.Series:
    return ds.dt.tz_convert(TZ)


def national_overview(nat: pd.DataFrame) -> Path:
    n = nat.set_index("ds")
    obs = n[n.observed]
    daily = obs.y.resample("D").mean() / 1e3
    err = (obs.y - obs.rte_j1).dropna()
    mape = (err.abs() / obs.y.loc[err.index]).groupby(err.index.year).mean() * 100
    bias = err.groupby(err.index.year).mean() / 1e3
    fig, axes = plt.subplots(3, 1, figsize=(10, 9), gridspec_kw={"height_ratios": [2, 1, 1]})
    ax = axes[0]
    ax.plot(daily.index, daily, color=P.SLOTS[0], lw=0.8)
    P.titled(ax, "Consommation nationale (moyenne journalière)", "GW, éCO2mix consolidé et définitif, 2015-2026")
    ax.set_ylabel("GW")
    ax = axes[1]
    ax.bar(mape.index, mape, color=[P.SLOTS[0] if y < 2023 else P.SLOTS[1] for y in mape.index], width=0.7)
    for y, v in mape.items():
        ax.text(y, v + 0.05, f"{v:.1f}", ha="center", fontsize=8, color=P.INK_2)
    P.titled(ax, "MAPE de la prévision J-1 de RTE, par année", "%, tous les pas observés (2026 : janvier-juin)")
    ax.set_ylabel("%")
    ax = axes[2]
    ax.bar(bias.index, bias, color=[P.SLOTS[0] if y < 2023 else P.SLOTS[1] for y in bias.index], width=0.7)
    ax.axhline(0, color=P.INK_2, lw=0.8)
    P.titled(ax, "Biais moyen de RTE J-1 (réalisé - prévu)", "GW : depuis 2023, RTE sous-prévoit d'environ 1 GW")
    ax.set_ylabel("GW")
    fig.tight_layout()
    return P.save(fig, OUT / "national_overview.png")


def dst_bug() -> Path:
    raw = pd.read_parquet(sorted(RAW.glob("eco2mix_national_cons_def_*.parquet"))[-1])
    raw["date_heure"] = pd.to_datetime(raw.date_heure, utc=True)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, (day, title) in zip(
        axes,
        [
            ("2025-03-30", "Mars : des lignes pour une heure qui n'existe pas"),
            ("2025-10-26", "Octobre : une heure manquante"),
        ],
        strict=True,
    ):
        w = raw[(raw.date == day) & raw.consommation.notna()].copy()
        w = w[(w.heure >= "00:30") & (w.heure <= "04:30")]
        dup = w.date_heure.duplicated(keep=False)
        phantom = w.heure.str.startswith("02") & dup & (day[5:7] == "03")
        ax.plot(
            w.date_heure[~phantom],
            w.consommation[~phantom] / 1e3,
            "o-",
            color=P.SLOTS[0],
            ms=6,
            label="ligne gardée",
        )
        if phantom.any():
            ax.plot(
                w.date_heure[phantom],
                w.consommation[phantom] / 1e3,
                "X",
                color=P.CRITICAL,
                ms=11,
                label="ligne fantôme (02:xx locale)",
            )
        for t, h, ph in zip(w.date_heure, w.heure, phantom, strict=True):
            ax.annotate(
                h,
                (t, 0),
                xycoords=("data", "axes fraction"),
                xytext=(-6 if ph else 6, 4),
                textcoords="offset points",
                fontsize=7,
                color=P.CRITICAL if ph else P.INK_2,
                rotation=90,
                ha="center",
            )
        if day[5:7] == "10":
            ax.axvspan(
                pd.Timestamp("2025-10-26T00:00Z"),
                pd.Timestamp("2025-10-26T00:45Z"),
                color=P.NEUTRAL,
                zorder=0,
            )
            ax.text(
                pd.Timestamp("2025-10-26T00:20Z"),
                ax.get_ylim()[1],
                "absent\n00:00-00:45 UTC",
                ha="center",
                va="top",
                fontsize=8,
                color=P.INK_2,
            )
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz="UTC"))
        ax.set_xlabel("heure UTC (heure locale publiée en bas)")
        ax.set_ylabel("GW")
        P.titled(ax, title, f"éCO2mix brut, {day}")
        ax.legend(loc="upper right")
    fig.tight_layout()
    return P.save(fig, OUT / "dst_bug.png")


def rte_error_structure(nat: pd.DataFrame, test: tuple[str, str]) -> Path:
    n = nat.set_index("ds")
    n = n[n.observed]
    t = n.loc[test[0] : test[1]].copy()
    t.index = t.index.tz_convert(TZ)
    t = t.loc[test[0] : test[1]]
    e = (t.y - t.rte_j1) / 1e3
    hh = t.index.hour + t.index.minute / 60
    prof = e.groupby(hh).agg(["mean", lambda x: x.abs().mean()])
    prof.columns = ["bias", "mae"]
    monthly = e.resample("MS").mean()
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    ax = axes[0]
    ax.plot(prof.index, prof.mae, color=P.INK, label="erreur absolue moyenne")
    ax.plot(prof.index, prof.bias, color=P.SLOTS[1], label="biais (réalisé - prévu)")
    ax.axhline(0, color=P.INK_2, lw=0.8)
    ax.set_xlabel("heure locale")
    ax.set_ylabel("GW")
    ax.set_xticks(range(0, 25, 3))
    P.titled(ax, "Erreur RTE J-1 selon l'heure", f"année de test {test[0][:7]} → {test[1][:7]}")
    ax.legend()
    ax = axes[1]
    ax.bar(monthly.index, monthly, width=26, align="edge", color=P.SLOTS[1])
    ax.axhline(0, color=P.INK_2, lw=0.8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%y"))
    ax.set_ylabel("GW")
    P.titled(ax, "Biais mensuel de RTE J-1", "positif tous les mois : un biais stable se corrige")
    fig.tight_layout()
    return P.save(fig, OUT / "rte_error_structure.png")


def alignment(nat: pd.DataFrame, test: tuple[str, str]) -> Path:
    raw = pd.read_parquet(sorted(RAW.glob("eco2mix_national_cons_def_*.parquet"))[-1])
    from flexgrid.data.national import drop_phantom_rows

    raw, _ = drop_phantom_rows(raw)
    raw["date_heure"] = pd.to_datetime(raw.date_heure, utc=True)
    q = raw.set_index("date_heure").prevision_j1.sort_index().astype(float)
    n = nat.set_index("ds")
    t = n[n.observed].loc[test[0] : test[1]]
    variants = {
        "même horodatage\n(pré-enregistré)": q.reindex(t.index),
        "quart d'heure\nprécédent": q.shift(1).reindex(t.index),
        "moyenne\n(t-15, t)": ((q + q.shift(1)) / 2).reindex(t.index),
        "moyenne\n(t, t+15)": ((q + q.shift(-1)) / 2).reindex(t.index),
        "quart d'heure\nsuivant": q.shift(-1).reindex(t.index),
    }
    mae = {k: (t.y - v).abs().mean() for k, v in variants.items()}
    fig, ax = plt.subplots(figsize=(9, 3.8))
    cols = [P.INK if i == 0 else P.MUTED for i in range(len(mae))]
    ax.bar(list(mae), list(mae.values()), color=cols, width=0.6)
    for i, v in enumerate(mae.values()):
        ax.text(i, v + 15, f"{v:,.0f}".replace(",", " "), ha="center", fontsize=9, color=P.INK_2)
    ax.set_ylabel("MAE (MW)")
    ax.set_ylim(0, max(mae.values()) * 1.15)
    P.titled(
        ax,
        "Le benchmark dépend de la façon de lire 15 min au pas 30 min",
        "MAE de RTE J-1 sur l'année de test selon la lecture du quart d'heure",
    )
    fig.tight_layout()
    return P.save(fig, OUT / "rte_alignment.png")


def profiles(nat: pd.DataFrame, seg: pd.DataFrame, school: pd.DataFrame, test: tuple[str, str]) -> Path:
    pf = seg[seg.unique_id == dataset.PORTFOLIO_ID].set_index("ds")
    n = nat.set_index("ds")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    names = {0: "lundi", 2: "mercredi", 5: "samedi", 6: "dimanche / férié"}
    colors = {0: P.SLOTS[0], 2: P.SLOTS[2], 5: P.SLOTS[3], 6: P.SLOTS[1]}
    for ax, (s, title) in zip(axes, [(n.y, "National"), (pf.y, "Portefeuille FlexGrid (3 517 sites)")], strict=True):
        s = s.loc[test[0] : test[1]]
        cal = C.features(s.index, school)
        rel = s / s.mean()
        for d, name in names.items():
            m = rel[cal.day_type.to_numpy() == d].groupby(cal.hh[cal.day_type == d]).mean()
            ax.plot(m.index / 2, m, color=colors[d], label=name)
        ax.set_xticks(range(0, 25, 3))
        ax.set_xlabel("heure locale")
        P.titled(ax, title, "profil moyen / moyenne annuelle, année de test")
    axes[0].set_ylabel("charge relative")
    axes[1].legend()
    fig.tight_layout()
    return P.save(fig, OUT / "profiles.png")


def thermosensitivity(nat: pd.DataFrame, seg: pd.DataFrame, wo: pd.DataFrame, test: tuple[str, str]) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    pairs = [
        (nat.set_index("ds").y / 1e3, "FR", "National", "GW"),
        (seg[seg.unique_id == dataset.PORTFOLIO_ID].set_index("ds").y, "PF", "Portefeuille FlexGrid", "MW"),
    ]
    for ax, (s, reg, title, unit) in zip(axes, pairs, strict=True):
        if reg == "PF":  # population des deux régions du portefeuille, à parts égales
            t = wo[wo.region.isin(["24", "27"])].groupby("ds").temperature_2m.mean()
        else:
            t = wo[wo.region == "FR"].set_index("ds").temperature_2m
        s = s.loc[test[0] : test[1]]
        loc = s.index.tz_convert(TZ)
        d = pd.DataFrame({"y": s.to_numpy(), "t": t.reindex(s.index).to_numpy()}, index=loc)
        daily = d.resample("D").mean()
        wd = daily.index.day_of_week < 5
        ax.scatter(daily.t[wd], daily.y[wd], s=10, color=P.SLOTS[0], alpha=0.7, label="lundi-vendredi")
        ax.scatter(daily.t[~wd], daily.y[~wd], s=10, color=P.SLOTS[1], alpha=0.7, label="week-end")
        ax.set_xlabel("température moyenne du jour (°C, ERA5)")
        ax.set_ylabel(unit)
        P.titled(ax, title, "un point = un jour de l'année de test")
    axes[0].legend()
    fig.tight_layout()
    return P.save(fig, OUT / "thermosensitivity.png")


def weather_forecast_error(wo: pd.DataFrame, test: tuple[str, str]) -> Path:
    from flexgrid.data import weather as W

    o = wo[wo.region == "FR"].set_index("ds").temperature_2m
    fig, ax = plt.subplots(figsize=(9, 3.8))
    for lead, col in [(1, P.SLOTS[0]), (2, P.SLOTS[1])]:
        f = W.national(W.to_half_hour(W.forecast(lead))).temperature_2m
        e = (f - o).dropna().loc[test[0] : test[1]]
        m = e.abs().resample("MS").mean()
        ax.plot(
            m.index,
            m,
            "o-",
            color=col,
            ms=5,
            label=f"émise {24 * lead} h avant (MAE {e.abs().mean():.2f} °C)",
        )
    ax.set_ylabel("MAE température (°C)")
    ax.set_ylim(bottom=0)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%y"))
    P.titled(
        ax,
        "Ce que coûte la prévision météo prise 48 h avant",
        "erreur de la température nationale ECMWF vs ERA5, par mois",
    )
    ax.legend()
    fig.tight_layout()
    return P.save(fig, OUT / "weather_forecast_error.png")


def nomination_clock() -> Path:
    fig, ax = plt.subplots(figsize=(11, 3.2))
    ax.set_xlim(-48, 50)
    ax.set_ylim(-0.2, 3.4)
    ax.axis("off")
    ticks = {-48: "J-2 00:00", -24: "J-1 00:00", -15: "J-1 09:00\némission", 0: "J 00:00", 24: "J+1 00:00"}
    for x, lab in ticks.items():
        ax.axvline(x, color=P.GRID, lw=1, zorder=0)
        ax.text(
            x,
            -0.15,
            lab,
            ha="center",
            va="top",
            fontsize=9,
            color=P.INK if x == -15 else P.INK_2,
            weight="bold" if x == -15 else None,
        )
    rows = [
        (2.7, -48, -24, P.SLOTS[2], "segments Enedis connus (fin J-2)"),
        (1.9, -48, -16, P.SLOTS[0], "national connu (jusqu'au pas J-1 08:00)"),
        (1.1, 0, 24, P.SLOTS[1], "météo de J : prévision émise 48 h avant chaque heure"),
        (0.3, 0, 24, P.INK, "jour de livraison J : seul noté (46, 48 ou 50 pas)"),
    ]
    for y, a, b, c, lab in rows:
        ax.barh(y, b - a, left=a, height=0.45, color=c, alpha=0.9)
        ax.text(
            b + 0.8 if b < 24 else a - 0.8,
            y,
            lab,
            va="center",
            ha="left" if b < 24 else "right",
            fontsize=9,
            color=P.INK,
        )
    ax.annotate("", xy=(-15, 3.3), xytext=(-15, 2.95), arrowprops={"arrowstyle": "->", "color": P.INK})
    ax.set_title("L'horloge de la nomination J-1 (heure de Paris)", loc="left")
    return P.save(fig, OUT / "nomination_clock.png")


def panel_map(seg: pd.DataFrame) -> Path:
    s = seg[seg.unique_id != dataset.PORTFOLIO_ID]
    g = s.groupby("unique_id").agg(sites=("n_sites", "last"), mw=("y", "mean"))
    g["band"] = g.index.str[3:5]
    g["prof"] = g.index.str[6:]
    fig, ax = plt.subplots(figsize=(9, 5))
    bands = ["P1", "P2", "P4", "P5", "P6"]
    for i, b in enumerate(bands):
        for prof, marker in [("ENT1", "o"), ("ENT3", "s")]:
            d = g[(g.band == b) & (g.prof == prof)]
            ax.scatter(
                d.sites,
                d.mw,
                s=40,
                marker=marker,
                color=P.SLOTS[i],
                label=f"{b} {prof}" if len(d) else None,
                edgecolor=P.SURFACE,
                lw=1,
            )
    pf = g.loc[["24_P2_ENT1", "27_P2_ENT1"]]
    ax.scatter(pf.sites, pf.mw, s=160, facecolor="none", edgecolor=P.INK, lw=1.5)
    ax.annotate(
        "portefeuille FlexGrid :\n24_P2_ENT1 + 27_P2_ENT1",
        (pf.sites.max(), pf.mw.min()),
        xytext=(25, -40),
        textcoords="offset points",
        fontsize=8,
        color=P.INK,
        arrowprops={"arrowstyle": "-", "color": P.INK_2, "lw": 0.8},
    )
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("nombre de sites (juin 2026)")
    ax.set_ylabel("puissance moyenne (MW)")
    P.titled(
        ax,
        f"Le panel : {len(g)} segments tertiaires Enedis > 36 kVA",
        "région x tranche de puissance x profil ; ronds ENT1, carrés ENT3",
    )
    ax.legend(ncol=2, fontsize=8, loc="upper left")
    fig.tight_layout()
    return P.save(fig, OUT / "panel_map.png")


def prices_figure(pr: pd.DataFrame) -> Path:
    p = pr.set_index("ds").price_da
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), gridspec_kw={"width_ratios": [2, 1]})
    ax = axes[0]
    d = p.resample("D").mean()
    ax.plot(d.index, d, color=P.SLOTS[0], lw=0.9)
    ax.axvline(pd.Timestamp("2025-10-01", tz="UTC"), color=P.INK_2, lw=1, ls="--")
    ax.text(pd.Timestamp("2025-10-05", tz="UTC"), ax.get_ylim()[1] * 0.92, "pas 15 min", fontsize=8, color=P.INK_2)
    ax.set_ylabel("€/MWh")
    P.titled(
        ax,
        "Prix day-ahead France (moyenne journalière)",
        "Energy-Charts ; le couplage passe au pas 15 min le 1er octobre 2025",
    )
    ax = axes[1]
    loc = p.loc["2025-07-01":"2026-06-30"]
    hh = loc.index.tz_convert(TZ)
    m = loc.groupby(hh.hour + hh.minute / 60).mean()
    ax.plot(m.index, m, color=P.SLOTS[1])
    ax.set_xticks(range(0, 25, 6))
    ax.set_xlabel("heure locale")
    P.titled(ax, "Profil moyen", f"année de test ; {100 * (loc < 0).mean():.0f} % des pas négatifs")
    fig.tight_layout()
    return P.save(fig, OUT / "prices.png")


def gaps_table(gaps: pd.DataFrame) -> pd.DataFrame:
    return gaps.groupby(["unique_id", "method"]).agg(n=("steps", "size"), steps=("steps", "sum")).reset_index()


def all_figures(protocol: dict) -> list[Path]:
    P.setup()
    nat, seg = dataset.load("national"), dataset.load("segments")
    wo, pr = dataset.load("weather_observed"), dataset.load("prices")
    school = pd.read_parquet(RAW / "calendrier_scolaire.parquet")
    test = tuple(protocol["windows"]["test"])
    return [
        national_overview(nat),
        dst_bug(),
        rte_error_structure(nat, test),
        alignment(nat, test),
        profiles(nat, seg, school, test),
        thermosensitivity(nat, seg, wo, test),
        weather_forecast_error(wo, test),
        nomination_clock(),
        panel_map(seg),
        prices_figure(pr),
    ]


if __name__ == "__main__":
    from flexgrid.config import load_protocol

    for p in all_figures(load_protocol()):
        print(p)
