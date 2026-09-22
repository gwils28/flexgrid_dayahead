"""Interface en ligne de commande : `flexgrid <commande>`."""

from __future__ import annotations

import json

import typer

from flexgrid.config import load_protocol

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def download() -> None:
    """Télécharge et fige toutes les sources (jamais d'écrasement)."""
    from concurrent.futures import ThreadPoolExecutor

    from flexgrid.sources import enedis, odre, prices, school, weather

    p = load_protocol()
    e = p["data"]["eco2mix"]
    print(odre.download_eco2mix(e["start"], e["end"]))
    print(school.download())
    print(prices.download_day_ahead("2023-01-01", e["end"]))
    for y in range(2015, 2027):
        print(weather.download_observed(f"{y}-01-01", f"{y}-12-31" if y < 2026 else "2026-06-30"))
    chunks = [
        ("2024-02-01", "2024-07-31"),
        ("2024-08-01", "2025-01-31"),
        ("2025-02-01", "2025-07-31"),
        ("2025-08-01", "2026-01-31"),
        ("2026-02-01", "2026-06-30"),
    ]
    for a, b in chunks:
        print(weather.download_forecast(a, b))
    with ThreadPoolExecutor(6) as ex:
        for path in ex.map(enedis.download_tertiary, enedis.REGIONS):
            print(path)


@app.command()
def build() -> None:
    """Construit les tables intermédiaires (data/interim) à partir des snapshots."""
    from flexgrid.data import dataset

    print(json.dumps(dataset.build_all(load_protocol()), indent=2))


@app.command("figures-data")
def figures_data() -> None:
    """Figures du bloc A."""
    from flexgrid import figures_data as F

    for p in F.all_figures(load_protocol()):
        print(p)


@app.command()
def forecast(family: str, models: list[str]) -> None:
    """Backtest d'une famille (national | segments) pour un ou plusieurs modèles."""
    from flexgrid.backtest.run import run

    for m in models:
        run(load_protocol(), family, m, log=lambda s: print(s, flush=True))


@app.command("score")
def score_cmd(families: list[str]) -> None:
    """Benchmarks RTE, mélange, réparations conformes et métriques par origine."""
    from flexgrid.backtest.score import score

    for f in families:
        po = score(load_protocol(), f)
        print(f, len(po), "lignes")


@app.command("tables")
def tables_cmd() -> None:
    """Tableaux versionnés (results/*.csv) : résumés, verdicts, coût d'écart."""
    from flexgrid import analysis

    for k in analysis.tables(load_protocol()):
        print(f"results/{k}.csv")


@app.command("figures-results")
def figures_results() -> None:
    """Figures des blocs B, C et du coût."""
    from flexgrid import figures_cost, figures_results

    protocol = load_protocol()
    for p in [
        *figures_results.national_figures(protocol),
        *figures_results.portfolio_figures(protocol),
        *figures_cost.all_figures(protocol),
    ]:
        print(p)


@app.command("router")
def router_cmd() -> None:
    """Complexity Router : apprentissage sur la validation, évaluation sur le test, dérive des routes."""
    import pandas as pd

    from flexgrid import router
    from flexgrid.paths import RESULTS

    out = router.run(load_protocol(), pd.read_parquet(RESULTS / "per_origin_segments.parquet"))
    print(json.dumps(out, indent=2, ensure_ascii=False, default=float))


@app.command("figures-router")
def figures_router() -> None:
    """Figures du router et du cold-start (après `router` et `coldstart`)."""
    from flexgrid import figures_router

    for p in figures_router.all_figures(load_protocol()):
        print(p)


@app.command("coldstart")
def coldstart_cmd(score_only: bool = False) -> None:
    """Cold-start : historiques tronqués à 7, 14, 28, 56 jours sur trois régions tenues à l'écart."""
    from flexgrid import coldstart

    protocol = load_protocol()
    if not score_only:
        fc = coldstart.run(protocol, log=lambda s: print(s, flush=True))
        print(len(fc), "lignes")
    print(coldstart.score(protocol).round(4).to_string(index=False))


if __name__ == "__main__":
    app()
