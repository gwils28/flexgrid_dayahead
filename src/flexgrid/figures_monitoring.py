"""Bloc E : le tableau de bord de monitoring, rejoué jour après jour sur l'année de test."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from flexgrid import monitoring as M
from flexgrid import plots as P
from flexgrid.data import dataset
from flexgrid.paths import RESULTS, ROOT

OUT = ROOT / "05_production" / "figures"


def data_drift(protocol: dict) -> tuple[Path, pd.DataFrame]:
    test = protocol["windows"]["test"]
    nat = dataset.load("national").set_index("ds")
    seg = dataset.load("segments")
    pf = seg[seg.unique_id == dataset.PORTFOLIO_ID].set_index("ds").y
    wf = dataset.load("weather_forecast")
    wo = dataset.load("weather_observed")
    temp = pd.concat(
        [
            wo[wo.region == "FR"].set_index("ds").temperature_2m.loc[:"2024-12-31"],
            wf[wf.region == "FR"].set_index("ds").temperature_2m.loc["2025-01-01":],
        ]
    )
    price = dataset.load("prices").set_index("ds").price_da
    series = {"conso nationale": nat.y, "portefeuille": pf, "température": temp, "prix day-ahead": price}
    rows = []
    for name, s in series.items():
        d = M.monthly_drift(s.sort_index(), test[0], test[1]).assign(variable=name)
        rows.append(d)
    drift = pd.concat(rows, ignore_index=True)
    fig, ax = plt.subplots(figsize=(10, 4.2))
    for i, (name, d) in enumerate(drift.groupby("variable", sort=False)):
        ax.plot(d.month, d.psi, "o-", color=P.SLOTS[i], label=name, ms=5)
    ax.axhspan(0.25, max(0.6, drift.psi.max() * 1.1), color=P.REDS[0], alpha=0.5, lw=0)
    ax.axhline(0.1, color=P.WARNING, lw=1, ls="--")
    ax.text(drift.month.min(), 0.26, "dérive (PSI > 0,25)", fontsize=8, color=P.INK_2, va="bottom")
    P.month_axis(ax)
    ax.set_ylabel("PSI contre le même mois un an plus tôt")
    P.titled(ax, "Dérive des données", "référence saisonnière : chaque mois comparé au même mois de l'année précédente")
    ax.legend(ncol=4, fontsize=8)
    fig.tight_layout()
    return P.save(fig, OUT / "data_drift.png"), drift


def concept_drift(po: pd.DataFrame, uid: str, models: list[str], ref: str, path: Path, title: str) -> tuple[Path, dict]:
    t = po[(po.unique_id == uid)]
    fig, axes = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True)
    alerts = {}
    for m in models:
        full = M.rolling_ratio(t, uid, m, ref)
        # Seuil auto-référencé : 1,15 x le ratio médian du modèle sur la validation (janvier-juin 2025).
        level = float(full[(full.index >= "2025-02-01") & (full.index < "2025-07-01")].median())
        r = full[full.index >= "2025-07-01"]
        naive, own = M.alerts(r, 1.0), M.alerts(r, 1.15 * level)
        alerts[m] = {"seuil_1": int(naive.sum()), "seuil_auto": int(own.sum()), "niveau_validation": round(level, 3)}
        axes[0].plot(
            r.index,
            r,
            color=P.color(m),
            label=f"{P.label(m)} : {alerts[m]['seuil_1']} j d'alerte au seuil 1, {alerts[m]['seuil_auto']} au seuil auto ({f'{1.15 * level:.2f}'.replace('.', ',')})",
        )
        axes[0].fill_between(r.index, 1.15 * level, r.where(own), color=P.color(m), alpha=0.25, lw=0)
        axes[0].axhline(1.15 * level, color=P.color(m), lw=0.8, ls=":")
    axes[0].axhline(1, color=P.INK, lw=1)
    axes[0].set_ylabel(f"MAE 28 j / MAE {P.label(ref)}")
    P.titled(
        axes[0],
        title,
        "pointillés : seuil = 1,15 x le niveau du modèle en validation ; zones teintées : 14 jours au-dessus",
    )
    axes[0].legend(fontsize=8)
    for m in models:
        for variant, ls in [(m, "-"), (f"{m}_conformal", "--")]:
            c = M.rolling_coverage(t, uid, variant)
            c = c[c.index >= "2025-07-01"]
            if c.notna().any():
                axes[1].plot(c.index, c, ls, color=P.color(m), label=P.label(variant))
    axes[1].axhspan(0.85, 0.95, color=P.NEUTRAL, lw=0)
    axes[1].axhline(0.9, color=P.INK_2, lw=0.8, ls=":")
    axes[1].set_ylabel("couverture 90 % sur 28 j")
    P.titled(axes[1], "Calibration glissante", "bande grise : [0,85 ; 0,95], la bande pré-enregistrée")
    axes[1].legend(fontsize=8, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.18))
    P.month_axis(axes[1])
    fig.tight_layout()
    return P.save(fig, path), alerts


def monthly_kpi(po: pd.DataFrame, uid: str, model: str, k: float) -> pd.DataFrame:
    """Tableau de bord mensuel du brief : MAPE, couverture 90 % réparée, énergie en écart, coût (k = 1 et k)."""
    t = po[(po.unique_id == uid) & (po.window == "test")]
    m = t[t.model == model]
    c = t[t.model == f"{model}_conformal"]
    g = m.groupby(m.day.dt.to_period("M"))
    out = pd.DataFrame(
        {
            "mape": g.mape.mean(),
            "energy_mwh": g.energy_mwh.sum(),
            "cost_eur_k1": g.cost_eur.sum(),
            f"cost_eur_k{k:g}": g.cost_eur.sum() * k,
            "cov90_conformal": c.groupby(c.day.dt.to_period("M")).apply(
                lambda d: (d.cov90 * d.n).sum() / d.n.sum(), include_groups=False
            ),
        }
    )
    out.index = out.index.astype(str)
    return out


def all_figures(protocol: dict) -> dict:
    import json

    from flexgrid.data import dataset

    P.setup()
    po = pd.read_parquet(RESULTS / "per_origin_national.parquet")
    pf = pd.read_parquet(RESULTS / "per_origin_segments.parquet")
    pf = pf[pf.unique_id == dataset.PORTFOLIO_ID]
    p1, drift = data_drift(protocol)
    p2, alerts_nat = concept_drift(
        po,
        "FR",
        ["ensemble", "lgbm"],
        "rte_j1_debiased",
        OUT / "national_concept_drift.png",
        "National : le modèle reste-t-il au niveau de RTE débiaisée ?",
    )
    p3, alerts_pf = concept_drift(
        pf,
        dataset.PORTFOLIO_ID,
        ["ensemble", "lgbm"],
        "rte_prorata",
        OUT / "portfolio_concept_drift.png",
        "Portefeuille : le modèle garde-t-il son avance sur RTE au prorata ?",
    )
    drift.to_csv(RESULTS / "monitoring_data_drift.csv", index=False)
    kpi = monthly_kpi(pf, dataset.PORTFOLIO_ID, "ensemble", 0.25)
    kpi.round(4).to_csv(RESULTS / "monitoring_monthly_kpi.csv")
    out = {
        "alerts": {"national": alerts_nat, "portfolio": alerts_pf},
        "drift_max": drift.groupby("variable").psi.max().round(3).to_dict(),
    }
    (RESULTS / "monitoring_summary.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    return {"figures": [p1, p2, p3], **out}


if __name__ == "__main__":
    from flexgrid.config import load_protocol

    print(all_figures(load_protocol()))
