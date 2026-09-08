from pathlib import Path

import pandas as pd
import pytest

from flexgrid.sources import entsoe

FIX = Path(__file__).parent / "fixtures" / "entsoe_a65.xml"


def test_parse_fills_omitted_points_with_the_previous_value():
    s = entsoe.parse(FIX.read_text())
    assert s.index[0] == pd.Timestamp("2025-10-25T22:00Z") and len(s) == 4
    assert s.tolist() == [44168, 43714, 43714, 43118]


def test_without_token_the_client_refuses_and_says_why(monkeypatch):
    monkeypatch.delenv("ENTSOE_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="ENTSOE_TOKEN"):
        entsoe.token()
