"""Adaptateurs des TSFM de l'addendum : grille de quantiles de TimesFM 3.0 et modes de covariables."""

import numpy as np
import pandas as pd
from scipy.stats import norm

from flexgrid.backtest.inputs import QUANTILES
from flexgrid.models import chronos, tsfm


def test_timesfm_grid_matches_a_gaussian():
    """Sur des quantiles exactement gaussiens, la conversion retrouve les 7 niveaux du protocole."""
    levels = np.arange(1, 10) / 10
    q9 = np.tile(100 + 10 * norm.ppf(levels), (3, 1))
    out = tsfm.timesfm_to_grid(q9)
    expected = 100 + 10 * norm.ppf(QUANTILES)
    assert out.shape == (3, len(QUANTILES))
    # q0,25 interpolé linéairement entre q0,2 et q0,3 : erreur de courbure < 0,1 sur un écart-type de 10.
    np.testing.assert_allclose(out[0], expected, atol=0.1)
    assert (np.diff(out, axis=1) > 0).all()


def test_covariate_modes():
    idx = pd.date_range("2025-12-24 23:00", periods=4, freq="30min", tz="UTC")
    w = pd.DataFrame({"temperature_2m": 1.0, "cloud_cover": 2.0, "shortwave_radiation": 3.0}, index=idx)
    school = pd.DataFrame(columns=["start_date", "end_date", "zones"])
    assert chronos.cov_mode(True) == "full" and chronos.cov_mode(False) == "none"
    assert list(chronos.covariates(idx, w, school, chronos.MODES["weather"])) == ["temp", "cloud", "rad"]
    full = chronos.covariates(idx, w, school, chronos.MODES["full"])
    assert list(full) == [*chronos.WEATHER, *chronos.CALENDAR]
    assert full["holiday"][-1] == 1.0  # 25 décembre, heure de Paris
