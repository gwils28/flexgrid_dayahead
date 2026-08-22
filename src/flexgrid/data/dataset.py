"""Construction des tables intermédiaires (data/interim), une fois, à partir des snapshots.

- national.parquet : ds, y (MW), observed, rte_j1 (même horodatage), rte_j1_prev (quart d'heure précédent)
- segments.parquet : unique_id, ds, y (MW), observed, n_sites, region ; panel + portefeuille FLEXGRID
- weather_{observed,forecast}.parquet : ds, region (code ou "FR"), variables météo au pas 30 min
- prices.parquet : ds, price_da (€/MWh, moyenne au pas 30 min)
- gaps.parquet : rapport des trous de chaque série, avec la méthode de remplissage
"""

from __future__ import annotations

import pandas as pd

from flexgrid.data import national as nat
from flexgrid.data import weather as W
from flexgrid.data.clean import clean
from flexgrid.paths import INTERIM, RAW
from flexgrid.sources import enedis, prices

PORTFOLIO_ID = "FLEXGRID"


def build_national(protocol: dict) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    d = protocol["data"]
    path = RAW / f"eco2mix_national_cons_def_{d['eco2mix']['start']}_{d['eco2mix']['end']}.parquet"
    b = nat.build(path, tuple(d["national_range_mw"]), d["fill_linear_max_steps"])
    out = pd.DataFrame({"y": b["load"], "observed": b["observed"]})
    out["rte_j1"] = nat.rte_at(b["rte_j1"], out.index, "same")
    out["rte_j1_prev"] = nat.rte_at(b["rte_j1"], out.index, "previous")
    gaps = b["gaps"].assign(unique_id="FR")
    return out.reset_index(), gaps, b["phantom_rows"]


def panel_ids(raw: pd.DataFrame, protocol: dict) -> list[str]:
    """Segments disjoints du panel : assez de sites, presque pas de pas masqués (SPEC, angle mort 10)."""
    p = protocol["panel"]
    g = raw.groupby("unique_id")
    sites = (
        raw[raw.ds >= raw.ds.max() - pd.Timedelta(days=30)].groupby("unique_id").nb_points_soutirage.mean()
    )
    missing = g.total_energie_soutiree_wh.apply(lambda x: x.isna().mean())
    ok = (sites >= p["min_sites"]) & (missing <= p["max_missing"])
    return sorted(ok[ok].index)


def build_segments(protocol: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = enedis.read_tertiary(sorted((RAW / "enedis").glob("sup36_tertiaire_*.parquet")))
    ids = panel_ids(raw, protocol)
    rng = protocol["data"]["segment_range"]  # DÉVIATION datée dans le protocole
    frames, gaps = [], []
    raw = raw[raw.unique_id.isin(ids)]
    raw = raw.assign(y=raw.total_energie_soutiree_wh / 1e6 * 2)  # Wh par 30 min -> MW moyens
    for uid, g in raw.groupby("unique_id"):
        g = g.set_index("ds").sort_index()
        bounds = (rng["low_vs_median"] * g.y.median(), rng["high_vs_q999"] * g.y.quantile(0.999))
        filled, observed, gp = clean(g.y, bounds, protocol["data"]["fill_linear_max_steps"])
        n_sites = g.nb_points_soutirage.reindex(filled.index).ffill().bfill()
        frames.append(
            pd.DataFrame(
                {"unique_id": uid, "y": filled, "observed": observed, "n_sites": n_sites, "region": uid[:2]}
            )
        )
        gaps.append(gp.assign(unique_id=uid))
    seg = pd.concat(frames).rename_axis("ds").reset_index()
    pf = seg[seg.unique_id.isin(protocol["portfolio"]["segments"])]
    if pf.unique_id.nunique() != len(protocol["portfolio"]["segments"]):
        raise ValueError("un segment du portefeuille n'est pas dans le panel")
    port = pf.groupby("ds").agg(y=("y", "sum"), observed=("observed", "all"), n_sites=("n_sites", "sum"))
    port = port.assign(unique_id=PORTFOLIO_ID, region="PF").reset_index()
    seg = pd.concat([seg, port[seg.columns]], ignore_index=True)
    return seg, pd.concat(gaps, ignore_index=True)


def build_weather() -> tuple[pd.DataFrame, pd.DataFrame]:
    out = []
    for raw in (W.observed(), W.forecast(lead_day=2)):
        hh = W.to_half_hour(raw)
        fr = W.national(hh).reset_index().assign(region="FR")
        out.append(pd.concat([hh, fr[hh.columns]], ignore_index=True))
    return out[0], out[1]


def build_prices() -> pd.DataFrame:
    p = prices.read_day_ahead(sorted(RAW.glob("price_da_fr_*.json"))[-1])
    # Pas natif horaire puis 15 min : on remplit au pas 15 min (une heure = 4 quarts au même prix), puis
    # moyenne au pas 30 min.
    q = p.resample("15min").ffill()
    return q.resample("30min").mean().rename("price_da").rename_axis("ds").reset_index()


def build_all(protocol: dict) -> dict:
    INTERIM.mkdir(parents=True, exist_ok=True)
    national, ngaps, phantom = build_national(protocol)
    national.to_parquet(INTERIM / "national.parquet")
    seg, sgaps = build_segments(protocol)
    seg.to_parquet(INTERIM / "segments.parquet")
    pd.concat([ngaps, sgaps], ignore_index=True).to_parquet(INTERIM / "gaps.parquet")
    wo, wf = build_weather()
    wo.to_parquet(INTERIM / "weather_observed.parquet")
    wf.to_parquet(INTERIM / "weather_forecast.parquet")
    build_prices().to_parquet(INTERIM / "prices.parquet")
    return {
        "national_steps": len(national),
        "phantom_rows_dropped": phantom,
        "national_gaps": len(ngaps),
        "segments": seg.unique_id.nunique(),
    }


def load(name: str) -> pd.DataFrame:
    return pd.read_parquet(INTERIM / f"{name}.parquet")
