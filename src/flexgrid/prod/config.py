from __future__ import annotations

from pathlib import Path

import yaml

from flexgrid.paths import CONFIGS, ROOT


def load() -> dict:
    with open(CONFIGS / "prod.yaml") as f:
        cfg = yaml.safe_load(f)
    cfg["store_path"] = ROOT / cfg["store"]
    return cfg


def store(cfg: dict, *parts: str) -> Path:
    p = Path(cfg["store_path"]).joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
