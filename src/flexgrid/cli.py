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


if __name__ == "__main__":
    app()
