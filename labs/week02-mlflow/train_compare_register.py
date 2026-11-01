"""Local MLflow lab: synthetic manufacturing data, validation selection, registry reload."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from mlflow.models import infer_signature
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = ["temperature", "pressure", "speed"]
MODEL_NAME = "ManufacturingQualityDemo"


def dataset():
    """Generated demo data; not measurements from a real factory."""
    rng = np.random.default_rng(42)
    count = 1000
    frame = pd.DataFrame({
        "equipment_id": [f"machine-{i % 8:02d}" for i in range(count)],
        "event_timestamp": pd.date_range("2026-01-01", periods=count, freq="min", tz="UTC"),
        "temperature": rng.uniform(55, 95, count),
        "pressure": rng.uniform(2, 8, count),
        "speed": rng.uniform(80, 140, count),
    })
    frame["prediction_timestamp"] = frame["event_timestamp"] + pd.Timedelta(minutes=1)
    frame["quality"] = (
        80 - 0.025 * (frame["temperature"] - 75) ** 2
        + 1.5 * frame["pressure"] + 0.04 * frame["speed"]
        + rng.normal(0, 0.7, count)
    )
    return frame


def scores(y, prediction):
    return {
        "rmse": float(np.sqrt(mean_squared_error(y, prediction))),
        "mae": float(mean_absolute_error(y, prediction)),
        "r2": float(r2_score(y, prediction)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--tracking-uri", default=os.environ.get("MLFLOW_TRACKING_URI"))
    args = parser.parse_args()
    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    # Kubernetes Jobs use the HTTP Service; standalone CI may use SQLite.
    tracking_uri = args.tracking_uri or ("sqlite:///" + str(Path("mlflow.db").resolve()))
    mlflow.set_tracking_uri(tracking_uri)
    remote = tracking_uri.startswith(("http://", "https://"))
    experiment_name = "week02-manufacturing-quality"
    experiment = mlflow.get_experiment_by_name(experiment_name)
    if experiment:
        experiment_id = experiment.experiment_id
    else:
        options = {} if remote else {"artifact_location": (out / "artifacts").as_uri()}
        experiment_id = mlflow.create_experiment(experiment_name, **options)
    mlflow.set_experiment(experiment_id=experiment_id)
    frame = dataset()
    data_path = out / "synthetic_manufacturing.csv"
    frame.to_csv(data_path, index=False)
    digest = hashlib.sha256(data_path.read_bytes()).hexdigest()
    contract = {
        "data_kind": "synthetic_demo_not_real_factory",
        "seed": 42, "entity": "equipment_id", "feature_time": "event_timestamp",
        "prediction_time": "prediction_timestamp", "features": FEATURES,
        "target": "quality", "sha256": digest,
        "split": {"train": [0, 700], "validation": [700, 850], "test": [850, 1000]},
        "selection": "minimum validation RMSE; test is evaluated only after selection",
    }
    (out / "dataset_contract.json").write_text(json.dumps(contract, indent=2))
    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"],
                            check=True, capture_output=True, text=True)
    (out / "requirements-resolved.txt").write_text(freeze.stdout)
    train, validation, test = frame.iloc[:700], frame.iloc[700:850], frame.iloc[850:]
    candidates = {
        "baseline_mean": DummyRegressor(strategy="mean"),
        "ridge": make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
        "random_forest": RandomForestRegressor(
            n_estimators=100, max_depth=8, random_state=42, n_jobs=1
        ),
    }
    rows, retained = [], {}
    for name, model in candidates.items():
        with mlflow.start_run(run_name=name) as run:
            mlflow.set_tags({"data_kind": contract["data_kind"], "dataset_sha256": digest})
            mlflow.log_params({
                "model_type": name, "seed": 42, "train_rows": len(train),
                "validation_rows": len(validation), "split": "chronological",
            })
            mlflow.log_dict({key: str(value) for key, value in model.get_params(deep=True).items()}, "model_parameters.json")
            started = time.perf_counter()
            model.fit(train[FEATURES], train["quality"])
            fit_seconds = time.perf_counter() - started
            val_prediction = model.predict(validation[FEATURES])
            metrics = scores(validation["quality"], val_prediction)
            mlflow.log_metrics({"val_" + key: value for key, value in metrics.items()})
            mlflow.log_metric("fit_seconds", fit_seconds)
            info = mlflow.sklearn.log_model(
                model, name="model",
                # Only trust the tree type built by this script, not arbitrary imported models.
                skops_trusted_types=["sklearn.tree._tree.Tree"] if name == "random_forest" else [],
                signature=infer_signature(train[FEATURES], model.predict(train[FEATURES])),
                input_example=train[FEATURES].head(3),
            )
            for artifact in [data_path, out / "dataset_contract.json",
                             out / "requirements-resolved.txt"]:
                mlflow.log_artifact(str(artifact), artifact_path="reproducibility")
            rows.append({"model": name, "run_id": run.info.run_id,
                         "val_rmse": metrics["rmse"], "val_mae": metrics["mae"],
                         "val_r2": metrics["r2"], "fit_seconds": fit_seconds})
            retained[name] = (model, info.model_uri, run.info.run_id)
    comparison = pd.DataFrame(rows).sort_values("val_rmse")
    comparison.to_csv(out / "comparison.csv", index=False)
    best_name = comparison.iloc[0]["model"]
    best, source_uri, run_id = retained[best_name]
    version = mlflow.register_model(source_uri, MODEL_NAME)
    registered_uri = f"models:/{MODEL_NAME}/{version.version}"
    reloaded = mlflow.sklearn.load_model(registered_uri)
    before = best.predict(test[FEATURES])
    after = reloaded.predict(test[FEATURES])
    np.testing.assert_allclose(before, after, rtol=1e-10, atol=1e-10)
    test_metrics = scores(test["quality"], after)
    result = {
        "selected_model": best_name, "run_id": run_id, "dataset_sha256": digest,
        "registered_name": MODEL_NAME, "registered_version": version.version,
        "model_uri": registered_uri, "features": FEATURES,
        "reload_equal": True, "reload_max_abs_diff": float(np.max(np.abs(before - after))),
        "test_metrics": test_metrics,
    }
    (out / "selection.json").write_text(json.dumps(result, indent=2))
    pd.DataFrame({"equipment_id": test["equipment_id"],
                  "prediction_timestamp": test["prediction_timestamp"],
                  "actual": test["quality"], "prediction": after}).to_csv(
                      out / "test_predictions.csv", index=False)
    with mlflow.start_run(run_id=run_id):
        mlflow.log_metrics({"test_" + key: value for key, value in test_metrics.items()})
        mlflow.log_metric("reload_max_abs_diff", result["reload_max_abs_diff"])
        for artifact in ["comparison.csv", "selection.json", "test_predictions.csv"]:
            mlflow.log_artifact(str(out / artifact), artifact_path="verification")
    print("\nVALIDATION COMPARISON")
    print(comparison.to_string(index=False))
    print("\nREGISTRY RELOAD VERIFICATION")
    print(json.dumps(result, indent=2))
    print("\nTracking URI:", tracking_uri)
    if remote:
        print("Kubernetes UI: kubectl --context kind-mlops-lab -n week02 port-forward svc/mlflow 5050:5000")


if __name__ == "__main__":
    main()
