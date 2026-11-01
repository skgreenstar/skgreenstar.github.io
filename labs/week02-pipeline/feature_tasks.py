"""Feast on Kubernetes: validate the existing MLflow data and model, never retrain."""
import argparse
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path

FEATURES = ["temperature", "pressure", "speed"]


def read_inputs(source):
    import pandas as pd
    source = Path(source)
    contract = json.loads((source / "dataset_contract.json").read_text())
    selection = json.loads((source / "selection.json").read_text())
    raw = source / "synthetic_manufacturing.csv"
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    if digest != contract["sha256"] or digest != selection["dataset_sha256"]:
        raise ValueError("Dataset SHA-256 differs from MLflow training")
    if contract["features"] != FEATURES or selection["features"] != FEATURES:
        raise ValueError("Model input feature order differs")
    frame = pd.read_csv(raw)
    for col in ["event_timestamp", "prediction_timestamp"]:
        frame[col] = pd.to_datetime(frame[col], utc=True)
    if frame.duplicated(["equipment_id", "prediction_timestamp"]).any():
        raise ValueError("Duplicate entity/time key")
    if frame[FEATURES].isna().any().any():
        raise ValueError("Missing source features")
    return frame, contract, selection


def historical(source, output, online=False):
    import numpy as np
    import pandas as pd
    import yaml
    from feast import Entity, FeatureService, FeatureStore, FeatureView, Field, FileSource, ValueType
    from feast.types import Float64
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    frame, contract, selection = read_inputs(source)
    repo = output / "feature_repo"
    repo.mkdir(exist_ok=True)
    parquet = repo / "manufacturing.parquet"
    frame[["equipment_id", "event_timestamp"] + FEATURES].to_parquet(parquet, index=False)
    # TTL=0 disables expiry for this fixed historical demo. This is not a freshness policy.
    config = {
        "project": "week02_manufacturing", "provider": "local",
        "registry": str(repo / "registry.db"), "entity_key_serialization_version": 3,
        "offline_store": {"type": "file"},
        "online_store": {"type": "redis", "connection_string": os.environ.get("FEAST_REDIS_ENDPOINT", "redis:6379")} if online else
                        {"type": "sqlite", "path": str(repo / "online.db")},
    }
    (repo / "feature_store.yaml").write_text(yaml.safe_dump(config))
    store = FeatureStore(repo_path=str(repo))
    entity = Entity(name="equipment", join_keys=["equipment_id"], value_type=ValueType.STRING)
    view = FeatureView(name="manufacturing", entities=[entity], ttl=timedelta(0),
                       schema=[Field(name=f, dtype=Float64) for f in FEATURES], online=True,
                       source=FileSource(path=str(parquet), timestamp_field="event_timestamp"))
    service = FeatureService(name="quality_inputs", features=[view])
    store.apply([entity, view, service])
    start, stop = contract["split"]["test"]
    test = frame.iloc[start:stop].copy()
    query = test[["equipment_id", "prediction_timestamp"]].rename(columns={"prediction_timestamp": "event_timestamp"})
    retrieved = store.get_historical_features(entity_df=query, features=service).to_df()
    retrieved = retrieved.rename(columns={"event_timestamp": "prediction_timestamp"})
    keys = ["equipment_id", "prediction_timestamp"]
    aligned = test[keys + FEATURES].merge(retrieved[keys + FEATURES], on=keys,
                                         suffixes=("_expected", ""), validate="one_to_one", how="left")
    if len(retrieved) != len(test) or aligned[FEATURES].isna().any().any():
        raise ValueError("Historical join lost rows or returned missing features")
    np.testing.assert_allclose(aligned[FEATURES].to_numpy(),
                               aligned[[f + "_expected" for f in FEATURES]].to_numpy(), rtol=1e-12, atol=1e-12)
    # Preserve the original request order and keys, independent of Feast output ordering.
    result = aligned[keys + FEATURES].copy()
    result.to_parquet(output / "features.parquet", index=False)
    result.to_csv(output / "historical_features.csv", index=False)
    report = {"run_id": selection["run_id"], "model_uri": selection["model_uri"],
              "dataset_sha256": contract["sha256"], "rows": len(result),
              "historical_matches_source": True, "ttl_seconds": 0,
              "ttl_note": "No expiry for fixed historical demonstration; not production freshness"}
    print("\nHISTORICAL FEATURES (point-in-time, first 3 rows)", flush=True)
    print(result.head(3).to_string(index=False), flush=True)
    if online:
        store.materialize(start_date=(frame.event_timestamp.min() - pd.Timedelta(seconds=1)).to_pydatetime(),
                          end_date=(frame.event_timestamp.max() + pd.Timedelta(seconds=1)).to_pydatetime())
        latest = frame.sort_values("event_timestamp").groupby("equipment_id").tail(1).sort_values("equipment_id")
        response = store.get_online_features(features=service,
                    entity_rows=[{"equipment_id": value} for value in latest.equipment_id]).to_df()
        response = response.sort_values("equipment_id")
        if response[FEATURES].isna().any().any():
            raise ValueError("Online store contains missing values")
        np.testing.assert_allclose(response[FEATURES].to_numpy(), latest[FEATURES].to_numpy(), rtol=1e-12, atol=1e-12)
        response = response.merge(latest[["equipment_id", "event_timestamp"]], on="equipment_id", validate="one_to_one")
        response.to_csv(output / "online_features.csv", index=False)
        print("\nONLINE FEATURES (latest observed values, first 3 entities)", flush=True)
        print(response.head(3).to_string(index=False), flush=True)
        report.update(online_matches_latest=True, online_entities=len(response))
    (output / "feast_verification.json").write_text(json.dumps(report, indent=2))
    return report


def predict(source, features_dir, output):
    import mlflow
    import mlflow.sklearn
    import numpy as np
    import pandas as pd
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    _, contract, selection = read_inputs(source)
    frame = pd.read_parquet(Path(features_dir) / "features.parquet")
    model = mlflow.sklearn.load_model(selection["model_uri"])
    frame["prediction"] = model.predict(frame[FEATURES])
    expected = pd.read_csv(Path(source) / "test_predictions.csv")
    expected["prediction_timestamp"] = pd.to_datetime(expected["prediction_timestamp"], utc=True)
    merged = frame.merge(expected, on=["equipment_id", "prediction_timestamp"],
                         suffixes=("", "_expected"), validate="one_to_one", how="outer", indicator=True)
    if len(merged) != len(expected) or not merged["_merge"].eq("both").all():
        raise ValueError("Prediction row keys differ from training verification")
    np.testing.assert_allclose(merged.prediction, merged.prediction_expected, rtol=1e-10, atol=1e-10)
    result = frame[["equipment_id", "prediction_timestamp", "prediction"]].copy()
    result["model_uri"] = selection["model_uri"]
    result["mlflow_run_id"] = selection["run_id"]
    result["dataset_sha256"] = contract["sha256"]
    result.to_csv(output / "predictions.csv", index=False)
    report = {"rows": len(result), "model_uri": selection["model_uri"],
              "prediction_max_abs_diff": float(np.max(np.abs(merged.prediction - merged.prediction_expected))),
              "prediction_matches_mlflow": True, "dataset_sha256": contract["sha256"], "run_id": selection["run_id"]}
    (output / "prediction_verification.json").write_text(json.dumps(report, indent=2))
    print("\nREGISTERED MODEL / FEAST PREDICTION CHECK", flush=True)
    print(json.dumps(report, indent=2), flush=True)
    return report


def main():
    import mlflow
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="/outputs")
    parser.add_argument("--output", default="/outputs/feast")
    args = parser.parse_args()
    historical(args.source, args.output, online=True)
    report = predict(args.source, args.output, args.output)
    with mlflow.start_run(run_id=report["run_id"]):
        for name in ["historical_features.csv", "online_features.csv", "feast_verification.json", "predictions.csv", "prediction_verification.json"]:
            mlflow.log_artifact(str(Path(args.output) / name), artifact_path="feast")
    print("\nFEAST_VALIDATION=PASS", flush=True)


if __name__ == "__main__":
    main()
