import numpy as np
import pandas as pd

from flexgrid import inference, metrics
from flexgrid.backtest.inputs import QCOLS


def _fc(values, y, model="m"):
    ds = pd.date_range("2025-07-01", periods=len(y), freq="30min", tz="UTC")
    fc = pd.DataFrame({"model": model, "unique_id": "A", "day": pd.Timestamp("2025-07-01"), "ds": ds, "h": 1})
    for c in QCOLS:
        fc[c] = values
    act = pd.DataFrame({"unique_id": "A", "ds": ds, "y": y, "observed": True})
    return fc, act


def test_point_forecast_pinball_is_half_the_mae_and_textbook_smape():
    fc, act = _fc(np.array([90.0, 110.0]), np.array([100.0, 100.0]))
    r = metrics.score_rows(fc, act)
    assert np.allclose(r.pinball, 5.0)  # pinball moyenne d'un point = |e| / 2
    assert np.allclose(r.sape, [20 / 190, 20 / 210])  # 2|e| / (|y| + |f|)


def test_unobserved_steps_are_not_scored():
    fc, act = _fc(np.array([90.0, 110.0]), np.array([100.0, 100.0]))
    act.loc[1, "observed"] = False
    assert len(metrics.score_rows(fc, act)) == 1


def test_mase_scale_uses_only_the_past():
    ds = pd.date_range("2025-01-01", periods=2000, freq="30min", tz="UTC")
    y = pd.DataFrame({"unique_id": "A", "ds": ds, "y": np.arange(2000.0)})
    cut = pd.DataFrame({"unique_id": ["A"], "day": [pd.Timestamp("2025-01-20")], "cutoff": [ds[1000]]})
    y.loc[1001:, "y"] = 1e9  # le futur ne doit pas changer l'échelle
    assert metrics.mase_scale(y, cut).scale.iloc[0] == 336.0


def test_verdict_reading():
    assert inference.verdict(0.8, 0.9, 0.9, (0.85, 0.95)) == "GAGNE"
    assert inference.verdict(0.8, 0.9, 0.7, (0.85, 0.95)) == "GAGNE EN POINT SEULEMENT"
    assert inference.verdict(0.9, 1.1, None, (0.85, 0.95)) == "PAS DE DIFFÉRENCE"
    assert inference.verdict(1.1, 1.2, None, (0.85, 0.95)) == "PERD"


def test_block_bootstrap_covers_identical_series_with_ratio_one():
    a = np.random.default_rng(0).normal(10, 1, 200)
    est, lo, hi = inference.bootstrap(inference.ratio_of_means, [a, a], 7, 200, 1)
    assert est == lo == hi == 1.0


def test_psi_is_zero_on_identical_samples_and_large_on_a_shift():
    from flexgrid.monitoring import alerts, psi

    a = np.random.default_rng(0).normal(size=5000)
    assert psi(a, a) < 1e-9
    assert psi(a, a + 1) > 0.25
    r = pd.Series([0.9] * 5 + [1.1] * 20)
    assert alerts(r, persist=14).sum() == 7
