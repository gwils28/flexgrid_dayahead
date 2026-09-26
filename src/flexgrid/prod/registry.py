"""Registre de modèles MLflow : LightGBM quantile emballé en modèle pyfunc, versionné, alias « champion »."""

from __future__ import annotations

import tempfile
from pathlib import Path

import lightgbm as lgb
import mlflow
import mlflow.pyfunc
import numpy as np
import pandas as pd

from flexgrid.backtest.inputs import qcol
from flexgrid.models import features as F
from flexgrid.models import lgbm
from flexgrid.paths import ROOT


class QuantileLGBM(mlflow.pyfunc.PythonModel):
    """Sept boosters (un par quantile), prédiction relative au niveau puis remise à l'échelle, quantiles triés."""

    def load_context(self, context):
        self.models = {
            float(Path(p).stem.removeprefix("q")): lgb.Booster(model_file=p) for p in context.artifacts.values()
        }

    def predict(self, context, model_input: pd.DataFrame, params=None):
        qs = sorted(self.models)
        X = model_input[F.FEATURES + lgbm.CATS]
        rel = np.sort(np.column_stack([self.models[q].predict(X) for q in qs]), axis=1)
        return pd.DataFrame(rel * model_input.level.to_numpy()[:, None], columns=[qcol(q) for q in qs])


def tracking(uri: str) -> None:
    if uri.startswith("sqlite:///") and not uri.startswith("sqlite:////"):
        db = ROOT / uri.removeprefix("sqlite:///")
        db.parent.mkdir(parents=True, exist_ok=True)
        uri = f"sqlite:///{db}"
    mlflow.set_tracking_uri(uri)


def register(models: dict, family: str, params: dict, info: dict) -> str:
    """Journalise un apprentissage et en fait le champion de sa famille. Rend la version enregistrée."""
    name = f"flexgrid-lgbm-{family}"
    mlflow.set_experiment(f"flexgrid-{family}")
    with tempfile.TemporaryDirectory() as tmp, mlflow.start_run(run_name=f"refit-{info['as_of']}") as run:
        arts = {}
        for q, b in models.items():
            p = Path(tmp) / f"q{q:g}.txt"
            b.save_model(str(p))
            arts[f"q{q:g}"] = str(p)
        mlflow.log_params({k: v for k, v in params.items() if not isinstance(v, (dict, list))})
        mlflow.log_params({"family": family, "as_of": info["as_of"], "n_rows": info["n_rows"]})
        mlflow.log_metrics({k: v for k, v in info.items() if isinstance(v, float)})
        mlflow.pyfunc.log_model(name="model", python_model=QuantileLGBM(), artifacts=arts)
        mv = mlflow.register_model(f"runs:/{run.info.run_id}/model", name)
    client = mlflow.MlflowClient()
    client.set_registered_model_alias(name, "champion", mv.version)
    return mv.version


def load_champion(family: str):
    return mlflow.pyfunc.load_model(f"models:/flexgrid-lgbm-{family}@champion")


def champion_as_of(family: str) -> str | None:
    """Jour de livraison pour lequel le champion a été appris (paramètre `as_of` de son run), None sans champion."""
    client = mlflow.MlflowClient()
    try:
        v = client.get_model_version_by_alias(f"flexgrid-lgbm-{family}", "champion")
    except mlflow.exceptions.MlflowException:
        return None
    return client.get_run(v.run_id).data.params.get("as_of")
