import json

import numpy as np
import pandas as pd
import pytest

from flexgrid.data import calendar as C
from flexgrid.data.clean import clean, gap_runs, regular
from flexgrid.data.national import drop_phantom_rows, rte_at
from flexgrid.sources import snapshot


def test_snapshot_refuses_a_modified_file(tmp_path):
    f, man = tmp_path / "x.bin", tmp_path / "MANIFEST.json"
    f.write_bytes(b"abc")
    snapshot.record(f, "http://example", {"a": 1}, path=man)
    snapshot.verify(f, path=man)
    assert json.loads(man.read_text())[str(f.resolve())]["bytes"] == 3
    f.write_bytes(b"abd")
    with pytest.raises(ValueError, match="sha256"):
        snapshot.verify(f, path=man)


def test_snapshot_refuses_an_unknown_file(tmp_path):
    f = tmp_path / "y.bin"
    f.write_bytes(b"1")
    with pytest.raises(FileNotFoundError):
        snapshot.verify(f, path=tmp_path / "MANIFEST.json")


def _series(n=2000, start="2025-01-06"):
    idx = pd.date_range(start, periods=n, freq="30min", tz="UTC")
    return pd.Series(50_000 + 5_000 * np.sin(np.arange(n) * 2 * np.pi / 48), index=idx, name="y")


def test_short_gap_is_linear_long_gap_is_one_week_earlier_and_both_unobserved():
    s = _series()
    short = s.index[1000:1003]  # 3 pas = 1,5 h
    long_ = s.index[1500:1510]  # 10 pas = 5 h
    raw = s.drop(short).drop(long_)
    filled, observed, gaps = clean(raw, (0, 1e6), fill_linear_max_steps=4)
    a, b = s.iloc[999], s.iloc[1003]
    assert np.allclose(filled.loc[short], np.linspace(a, b, 5)[1:-1])
    assert np.allclose(filled.loc[long_], s.shift(336).loc[long_])
    assert not observed.loc[short].any() and not observed.loc[long_].any()
    assert gaps.method.tolist() == ["linear", "week_before"] and gaps.steps.tolist() == [3, 10]


def test_out_of_range_value_becomes_a_gap():
    s = _series()
    s.iloc[700] = 158_000
    filled, observed, gaps = clean(s, (25_000, 105_000), 4)
    assert not observed.iloc[700] and filled.iloc[700] < 105_000 and len(gaps) == 1


def test_duplicated_timestamps_are_refused():
    s = _series(10)
    with pytest.raises(ValueError, match="double"):
        regular(pd.concat([s, s.iloc[:1]]))


def test_gap_runs_on_a_clean_series_is_empty():
    assert gap_runs(pd.Series(True, index=_series(5).index)).empty


def test_phantom_rows_of_spring_forward_are_dropped():
    # Reproduit éCO2mix du 30/03/2025 : 02:00 et 03:00 locales sont publiées toutes les deux sur 01:00 UTC.
    raw = pd.DataFrame(
        {
            "date": ["2025-03-30"] * 4,
            "heure": ["01:30", "02:00", "03:00", "03:30"],
            "date_heure": pd.to_datetime(
                ["2025-03-30T00:30Z", "2025-03-30T01:00Z", "2025-03-30T01:00Z", "2025-03-30T01:30Z"]
            ),
            "consommation": [48415, 47832, 47832, 48397],
        }
    )
    kept, n = drop_phantom_rows(raw)
    assert n == 1 and kept.heure.tolist() == ["01:30", "03:00", "03:30"]
    assert not kept.date_heure.duplicated().any()


def test_october_ambiguous_hour_is_kept():
    raw = pd.DataFrame(
        {
            "date": ["2025-10-26"] * 2,
            "heure": ["02:00", "02:30"],
            "date_heure": ["x", "y"],
            "consommation": [1, 2],
        }
    )
    kept, n = drop_phantom_rows(raw)
    assert n == 0 and len(kept) == 2


def test_rte_alignment_previous_reads_the_quarter_hour_before():
    idx15 = pd.date_range("2025-07-01", periods=8, freq="15min", tz="UTC")
    rte = pd.Series(np.arange(8.0), index=idx15)
    idx30 = idx15[2::2]
    assert rte_at(rte, idx30, "same").tolist() == [2, 4, 6]
    assert rte_at(rte, idx30, "previous").tolist() == [1, 3, 5]


def test_bridges_and_local_clock():
    hol = {pd.Timestamp("2025-12-25").date(), pd.Timestamp("2025-11-11").date()}
    br = C.bridges(hol, range(2025, 2026))
    assert br == {pd.Timestamp("2025-12-26").date(), pd.Timestamp("2025-11-10").date()}
    idx = pd.date_range("2025-10-25T22:00Z", periods=10, freq="30min", tz="UTC")
    school = pd.DataFrame(columns=["start_date", "end_date", "zones"])
    hh = C.features(idx, school).hh.tolist()
    assert hh == [0, 1, 2, 3, 4, 5, 4, 5, 6, 7]  # 02:00 et 02:30 locales apparaissent deux fois


def test_school_zones_count_half_open_interval():
    school = pd.DataFrame(
        {
            "start_date": ["2025-10-17T22:00Z", "2025-10-17T22:00Z"],
            "end_date": ["2025-11-02T23:00Z", "2025-10-24T22:00Z"],
            "zones": ["Zone A", "Zone B"],
        }
    )
    days = pd.DatetimeIndex(["2025-10-17", "2025-10-18", "2025-10-25", "2025-11-03"])
    assert C.school_zones_on_holiday(school, days).tolist() == [0, 2, 1, 0]
