import numpy as np
import pandas as pd

from flexgrid import router
from flexgrid.coldstart import HELD_OUT, siblings


def test_seasonal_strength_of_a_pure_daily_cycle_is_one_and_of_noise_is_low():
    t = np.arange(48 * 30)
    assert router.seasonal_strength(pd.Series(np.sin(2 * np.pi * t / 48)), 48) > 0.99
    noise = pd.Series(np.random.default_rng(0).normal(size=len(t)))
    assert router.seasonal_strength(noise, 48) < 0.1


def test_stump_finds_the_threshold_that_separates_the_winners():
    idx = [f"u{i}" for i in range(10)]
    feat = pd.DataFrame({f: np.arange(10.0) for f in router.FEATURES}, index=idx)
    feat["cv"] = [0, 0, 0, 0, 0, 1, 1, 1, 1, 1]
    feat["mean_mw"] = np.random.default_rng(1).permutation(10)
    scores = pd.DataFrame(
        {"lgbm": [1, 1, 1, 1, 1, 2, 2, 2, 2, 2], "chronos2_cov": [2, 2, 2, 2, 2, 1, 1, 1, 1, 1]}, index=idx, dtype=float
    )
    s = router.fit_stump(feat, scores)
    r = router.route(s, feat)
    assert (r == np.where(feat.cv == 1, "chronos2_cov", "lgbm")).all()
    assert s["loss"] == 10


def test_stump_falls_back_to_the_best_branch_when_nothing_helps():
    idx = ["a", "b"]
    feat = pd.DataFrame({f: [1.0, 1.0] for f in router.FEATURES}, index=idx)
    scores = pd.DataFrame({"lgbm": [1.0, 1.0], "chronos2_cov": [2.0, 2.0]}, index=idx)
    s = router.fit_stump(feat, scores)
    assert s["feature"] is None and (router.route(s, feat) == "lgbm").all()


def test_cold_start_siblings_never_include_held_out_regions():
    ids = ["52_P2_ENT1", "24_P2_ENT1", "11_P2_ENT1", "11_P1_ENT1", "53_P2_ENT1", "FLEXGRID"]
    sibs = siblings("52_P2_ENT1", ids)
    assert sibs == ["11_P2_ENT1", "24_P2_ENT1"] and not any(s[:2] in HELD_OUT for s in sibs)
