"""Client minimal de l'API ENTSO-E Transparency (REST, réponses XML), activé par un token.

Sans token (cas de ce projet, voir SPEC), le pipeline utilise éCO2mix et Energy-Charts. Le token se lit dans la
variable d'environnement ENTSOE_TOKEN (fichier .env non versionné, ou secret Docker en production) : jamais dans
le code ni dans la configuration.

Documents utilisés (zone France, EIC 10YFR-RTE------C) :
- 6.1.A Actual Total Load : documentType A65, processType A16 ;
- 6.1.B Day-ahead Total Load Forecast : documentType A65, processType A01 ;
- prix day-ahead : documentType A44.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET

import pandas as pd
import requests

API = "https://web-api.tp.entsoe.eu/api"
FR = "10YFR-RTE------C"
DOCS = {
    "load_actual": {"documentType": "A65", "processType": "A16", "outBiddingZone_Domain": FR},
    "load_forecast_d1": {"documentType": "A65", "processType": "A01", "outBiddingZone_Domain": FR},
    "price_day_ahead": {"documentType": "A44", "in_Domain": FR, "out_Domain": FR},
}
RESOLUTION = {"PT15M": "15min", "PT30M": "30min", "PT60M": "60min"}


def token() -> str:
    t = os.environ.get("ENTSOE_TOKEN")
    path = os.environ.get("ENTSOE_TOKEN_FILE")  # secret Docker monté en fichier
    if not t and path and os.path.exists(path):
        t = open(path).read().strip()
    if not t:
        raise RuntimeError("ENTSOE_TOKEN absent : le pipeline utilise éCO2mix et Energy-Charts à la place")
    return t


def parse(xml: str) -> pd.Series:
    """Séries temporelles d'un document ENTSO-E (Period / Point), en UTC.

    Les points absents d'une période (règle A03 : la valeur précédente se répète) sont complétés.
    """
    root = ET.fromstring(xml)
    ns = {"n": root.tag.split("}")[0].strip("{")}
    out = []
    for period in root.iterfind(".//n:Period", ns):
        start = pd.Timestamp(period.find("n:timeInterval/n:start", ns).text)
        end = pd.Timestamp(period.find("n:timeInterval/n:end", ns).text)
        freq = RESOLUTION[period.find("n:resolution", ns).text]
        idx = pd.date_range(start, end, freq=freq, inclusive="left")
        pts = {}
        for p in period.iterfind("n:Point", ns):
            pos = int(p.find("n:position", ns).text)
            val = p.find("n:quantity", ns)
            val = val if val is not None else p.find("n:price.amount", ns)
            pts[pos] = float(val.text)
        s = pd.Series(pts).reindex(range(1, len(idx) + 1)).ffill()
        out.append(pd.Series(s.to_numpy(), index=idx))
    return pd.concat(out).sort_index().rename_axis("ds")


def fetch(doc: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    params = {
        **DOCS[doc],
        "securityToken": token(),
        "periodStart": start.tz_convert("UTC").strftime("%Y%m%d%H%M"),
        "periodEnd": end.tz_convert("UTC").strftime("%Y%m%d%H%M"),
    }
    r = requests.get(API, params=params, timeout=120)
    r.raise_for_status()
    return parse(r.text).rename(doc)
