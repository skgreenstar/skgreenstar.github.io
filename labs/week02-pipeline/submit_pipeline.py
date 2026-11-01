"""Submit to an already installed standalone KFP API from a Kubernetes Pod."""
import argparse
import json
from pathlib import Path
import kfp

parser = argparse.ArgumentParser()
parser.add_argument("--source", default="/outputs/selection.json")
parser.add_argument("--host", default="http://ml-pipeline.kubeflow.svc.cluster.local:8888")
args = parser.parse_args()
selection = json.loads(Path(args.source).read_text())
client = kfp.Client(host=args.host, namespace="kubeflow")
run = client.create_run_from_pipeline_package(
    pipeline_file="/app/pipeline.yaml", arguments={"training_run_id": selection["run_id"]},
    run_name="week02-feast-mlflow-batch", experiment_name="week02-manufacturing",
    namespace="kubeflow", enable_caching=False)
print("KFP_RUN_ID=" + run.run_id, flush=True)
result = client.wait_for_run_completion(run.run_id, timeout=1800, sleep_duration=10)
state = getattr(result, "state", None) or getattr(result, "status", None)
print("KFP_RUN_STATE=" + str(state), flush=True)
if str(state).upper() not in {"SUCCEEDED", "SUCCESS"}:
    raise RuntimeError("Pipeline did not succeed: " + str(state))
