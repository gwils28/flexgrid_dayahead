"""Emplacements du dépôt. Les données brutes ne sont jamais versionnées ; leur manifeste l'est."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = ROOT / "configs"
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
RESULTS = ROOT / "results"
MANIFEST = ROOT / "data" / "MANIFEST.json"
