"""Orchestration Dagster du service J-1 : une partition = un jour de livraison J.

    DAGSTER_HOME=$PWD/dagster_home uv run dagster dev -m flexgrid.prod.dagster_defs

Chaîne : modèle (réappris le lundi d'émission, sinon champion courant du registre MLflow) -> prévisions des deux
familles -> nominations, avec des contrôles d'actifs sur la forme de la nomination. Le planning tourne à 09:00
heure de Paris la veille de J.

Pas de `from __future__ import annotations` ici : Dagster lit l'annotation de `context` à l'exécution.
"""

import pandas as pd
from dagster import (
    AssetCheckResult,
    AssetExecutionContext,
    DailyPartitionsDefinition,
    Definitions,
    asset,
    asset_check,
    build_schedule_from_partitioned_job,
    define_asset_job,
)

from flexgrid.backtest.inputs import QCOLS
from flexgrid.backtest.origins import Origin
from flexgrid.prod import config, registry, service

FAMILIES = ("national", "segments")
# La partition est le jour de livraison ; elle « finit » à minuit J, mais la prévision est émise la veille à 9 h :
# end_offset=2 rend la partition J disponible dès J-1.
days = DailyPartitionsDefinition(start_date="2025-07-01", end_date="2026-07-01", timezone="Europe/Paris", end_offset=2)


def needs_refit(day: str, champion_as_of: str | None) -> bool:
    """Réapprentissage le mardi de livraison (émission du lundi), ou si le champion n'est pas valide pour ce jour.

    Valide = appris pour un jour de la semaine qui précède, jamais après : en rejouant le passé (backfill), un
    champion appris plus tard aurait vu des données postérieures à l'émission.
    """
    d = pd.Timestamp(day)
    if d.dayofweek == 1 or champion_as_of is None:
        return True
    a = pd.Timestamp(champion_as_of)
    return not (d - pd.Timedelta(days=7) < a <= d)


@asset(partitions_def=days)
def lgbm_champion(context: AssetExecutionContext) -> dict:
    """Réapprend LightGBM quand `needs_refit` le demande, sinon garde le champion du registre."""
    day = context.partition_key
    cfg = config.load()
    registry.tracking(cfg["mlflow_tracking_uri"])
    out = {}
    for fam in FAMILIES:
        if needs_refit(day, registry.champion_as_of(fam)):
            out[fam] = service.train_weekly(fam, day, cfg)
            context.log.info(f"{fam} : nouvelle version {out[fam]}")
        else:
            out[fam] = "champion"
    return out


@asset(partitions_def=days, deps=[lgbm_champion])
def day_ahead_forecast(context: AssetExecutionContext) -> dict:
    day = context.partition_key
    return {fam: int(len(service.forecast_day(fam, day))) for fam in FAMILIES}


@asset(partitions_def=days, deps=[day_ahead_forecast])
def nomination(context: AssetExecutionContext) -> dict:
    day = context.partition_key
    res = {}
    for fam in FAMILIES:
        n = service.nominate(fam, day)
        res[fam] = {"model": n.model.iloc[0], "mwh": float(n.mwh.sum())}
        context.add_output_metadata({f"{fam}_mwh": float(n.mwh.sum()), f"{fam}_model": n.model.iloc[0]})
    return res


@asset_check(asset=day_ahead_forecast)
def quantiles_are_ordered_and_complete(context) -> AssetCheckResult:
    cfg = config.load()
    problems = []
    for fam in FAMILIES:
        for p in sorted(config.store(cfg, "forecasts", fam, "x").parent.glob("*.parquet"))[-1:]:
            fc = pd.read_parquet(p)
            if (fc[QCOLS].diff(axis=1).iloc[:, 1:] < -1e-9).any().any():
                problems.append(f"{p.name} : quantiles croisés")
            day = p.stem
            n = len(Origin(pd.Timestamp(day), fam).targets)
            for m, g in fc.groupby("model"):
                if len(g) != n:
                    problems.append(f"{fam} {day} {m} : {len(g)} pas au lieu de {n}")
    return AssetCheckResult(passed=not problems, metadata={"problems": "; ".join(problems) or "aucun"})


day_ahead_job = define_asset_job("day_ahead", selection=[lgbm_champion, day_ahead_forecast, nomination])
schedule = build_schedule_from_partitioned_job(day_ahead_job, hour_of_day=9, minute_of_hour=0)

defs = Definitions(
    assets=[lgbm_champion, day_ahead_forecast, nomination],
    asset_checks=[quantiles_are_ordered_and_complete],
    jobs=[day_ahead_job],
    schedules=[schedule],
)
