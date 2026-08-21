"""Lecture du protocole pré-enregistré."""

from __future__ import annotations

from pathlib import Path

import yaml

from flexgrid.paths import CONFIGS

PROTOCOL = CONFIGS / "protocol.yaml"


def load_protocol(path: Path = PROTOCOL) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)
