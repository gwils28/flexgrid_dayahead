import pandas as pd
import pytest
from fastapi.testclient import TestClient

from flexgrid.backtest.inputs import QCOLS
from flexgrid.backtest.origins import Origin


@pytest.fixture
def client(tmp_path, monkeypatch):
    from flexgrid.prod import api, service

    cfg = {**api.CFG, "store_path": tmp_path}
    monkeypatch.setattr(api, "CFG", cfg)
    o = Origin(pd.Timestamp("2025-10-26"), "segments")  # 50 pas : jour du passage à l'heure d'hiver
    fc = pd.DataFrame({"unique_id": "FLEXGRID", "day": o.day, "ds": o.targets, "h": range(len(o.targets))})
    for i, c in enumerate(QCOLS):
        fc[c] = 100.0 + i
    fc = pd.concat([fc.assign(model="lgbm"), fc.assign(model="ensemble")])
    (tmp_path / "forecasts" / "segments").mkdir(parents=True)
    fc.to_parquet(tmp_path / "forecasts" / "segments" / "2025-10-26.parquet")
    (tmp_path / "forecasts" / "segments" / "2025-10-26.status.json").write_text('{"chronos2_cov": "ok"}')
    service.nominate("segments", "2025-10-26", cfg)
    return TestClient(api.app)


def test_forecast_and_nomination_on_a_50_step_day(client):
    r = client.get("/forecast/segments/2025-10-26").json()
    assert r["model"] == "ensemble" and len(r["steps"]) == 50
    n = client.get("/nomination/segments/2025-10-26").json()
    assert len(n["steps"]) == 50 and n["total_mwh"] == pytest.approx(50 * 103 * 0.5)


def test_missing_day_is_a_404(client):
    assert client.get("/forecast/segments/2025-01-01").status_code == 404


def test_a_champion_from_the_future_is_never_reused():
    from flexgrid.prod.dagster_defs import needs_refit

    assert needs_refit("2025-10-26", "2026-06-30")  # backfill : champion appris plus tard
    assert not needs_refit("2025-10-26", "2025-10-21")  # appris le mardi précédent
    assert needs_refit("2025-10-26", "2025-10-14")  # trop ancien
    assert needs_refit("2025-10-28", "2025-10-21")  # mardi : réapprentissage hebdomadaire
    assert needs_refit("2025-10-26", None)
