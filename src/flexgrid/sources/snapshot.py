"""Snapshots des sources : les API ODRÉ, Enedis et Open-Meteo ne sont pas versionnées.

Un fichier téléchargé n'est jamais réécrit. Son sha256, sa date de téléchargement et la requête qui l'a
produit vont dans data/MANIFEST.json (versionné) : c'est l'équivalent du DOI d'OPSD pour des API vivantes.
Relire un snapshot dont le sha256 a changé est une erreur.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

from flexgrid.paths import MANIFEST, ROOT

_LOCK = threading.Lock()  # téléchargements parallèles : une seule écriture du manifeste à la fois
USER_AGENT = "flexgrid-dayahead/0.1 (research; github.com/gwils28/flexgrid_dayahead)"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_manifest(path: Path = MANIFEST) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def record(dest: Path, url: str, params: dict | None, path: Path = MANIFEST) -> dict:
    with _LOCK:
        return _record(dest, url, params, path)


def key_of(dest: Path) -> str:
    """Clé du manifeste : chemin relatif au dépôt (absolu hors du dépôt, pour les tests)."""
    d = dest.resolve()
    return str(d.relative_to(ROOT)) if d.is_relative_to(ROOT) else str(d)


def _record(dest: Path, url: str, params: dict | None, path: Path) -> dict:
    m = read_manifest(path)
    key = key_of(dest)
    m[key] = {
        "url": url,
        "params": params or {},
        "downloaded_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sha256": sha256(dest),
        "bytes": dest.stat().st_size,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(sorted(m.items())), indent=2, ensure_ascii=False) + "\n")
    return m[key]


def verify(dest: Path, path: Path = MANIFEST) -> None:
    """Refuse un snapshot absent du manifeste ou modifié depuis son téléchargement."""
    entry = read_manifest(path).get(key_of(dest))
    if entry is None:
        raise FileNotFoundError(f"{dest} n'est pas au manifeste : lancer `flexgrid download`")
    got = sha256(dest)
    if got != entry["sha256"]:
        raise ValueError(f"{dest} a le sha256 {got}, le manifeste dit {entry['sha256']}")


def fetch(url: str, dest: Path, params: dict | None = None, retries: int = 5, timeout: int = 600) -> Path:
    """Télécharge une fois (jamais d'écrasement), en flux, avec des reprises espacées."""
    if dest.exists():
        verify(dest)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(retries):
        try:
            with requests.get(
                url, params=params, stream=True, timeout=timeout, headers={"User-Agent": USER_AGENT}
            ) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            break
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(10 * 2**attempt)
    tmp.rename(dest)
    record(dest, url, params)
    return dest
