import pandas as pd

from flexgrid.backtest.origins import Origin, delivery_day


def test_clock_of_an_ordinary_day():
    o = Origin(pd.Timestamp("2025-11-12"), "national")
    assert o.issue == pd.Timestamp("2025-11-11T08:00Z")  # 09:00 heure d'hiver
    assert o.cutoff == pd.Timestamp("2025-11-11T07:00Z")  # dernier pas connu : 08:00 locale
    assert len(o.targets) == 48 and o.targets[0] == pd.Timestamp("2025-11-11T23:00Z")
    # De 07:30 UTC le 11 à 22:30 UTC le 12 inclus : 79 pas.
    assert o.horizon == 79
    seg = Origin(pd.Timestamp("2025-11-12"), "segments")
    assert seg.cutoff == pd.Timestamp("2025-11-10T22:30Z")  # 23:30 locale le 10 = fin de J-2
    assert seg.horizon == 96


def test_dst_days_have_46_and_50_steps():
    assert len(Origin(pd.Timestamp("2026-03-29"), "national").targets) == 46
    assert len(Origin(pd.Timestamp("2025-10-26"), "national").targets) == 50


def test_nothing_after_the_issue_is_known():
    for fam in ("national", "segments"):
        for d in pd.date_range("2025-03-25", "2025-04-02"):
            o = Origin(d, fam)
            assert o.cutoff < o.issue < o.day_start


def test_delivery_day_is_the_local_date():
    ds = pd.DatetimeIndex(["2025-07-01T21:30Z", "2025-07-01T22:00Z"])
    assert delivery_day(ds).dt.day.tolist() == [1, 2]

