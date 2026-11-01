"""KFP container entrypoints. Inputs are fetched via MLflow HTTP, not cross-namespace PVCs."""
import argparse
import json
from pathlib import Path
import shutil


def main():
    import mlflow
    from feature_tasks import historical, predict, read_inputs
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["prepare", "features", "predict", "publish"])
    parser.add_argument("--run-id")
    parser.add_argument("--source")
    parser.add_argument("--features")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    if args.stage == "prepare":
        client = mlflow.MlflowClient()
        paths = {"synthetic_manufacturing.csv": "reproducibility", "dataset_contract.json": "reproducibility",
                 "selection.json": "verification", "test_predictions.csv": "verification"}
        for filename, folder in paths.items():
            downloaded = client.download_artifacts(args.run_id, folder + "/" + filename)
            shutil.copyfile(downloaded, output / filename)
        _, _, selection = read_inputs(output)
        if selection["run_id"] != args.run_id:
            raise ValueError("Selection manifest differs from requested MLflow Run")
        print("INPUT_CONTRACT=PASS", flush=True)
    elif args.stage == "features":
        historical(args.source, output)
    elif args.stage == "predict":
        predict(args.source, args.features, output)
    else:
        import pandas as pd
        source = Path(args.source)
        report = json.loads((source / "prediction_verification.json").read_text())
        result = pd.read_csv(source / "predictions.csv")
        if len(result) != report["rows"] or result.isna().any().any():
            raise ValueError("Invalid prediction file")
        if result.duplicated(["equipment_id", "prediction_timestamp"]).any():
            raise ValueError("Duplicate prediction keys")
        with mlflow.start_run(experiment_id=mlflow.MlflowClient().get_run(report["run_id"]).info.experiment_id,
                              run_name="kfp-feast-batch-inference") as run:
            mlflow.set_tags({"training_run_id": report["run_id"], "model_uri": report["model_uri"],
                             "dataset_sha256": report["dataset_sha256"], "pipeline_version": "week02-v1"})
            mlflow.log_metric("prediction_max_abs_diff", report["prediction_max_abs_diff"])
            mlflow.log_artifact(str(source / "predictions.csv"), artifact_path="batch")
            report["result_run_id"] = run.info.run_id
            report["columns"] = list(result.columns)
            mlflow.log_dict(report, "batch/verification.json")
        (output / "verification.json").write_text(json.dumps(report, indent=2))
        shutil.copyfile(source / "predictions.csv", output / "predictions.csv")
        print("\nKFP_BATCH_VALIDATION=PASS", flush=True)
        print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
