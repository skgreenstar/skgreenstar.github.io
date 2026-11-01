#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
LAB_CONTEXT=kind-mlops-lab
k() { kubectl --context "$LAB_CONTEXT" -n week02 "$@"; }
k get pvc mlflow-results
k rollout status deployment/mlflow --timeout=120s
docker image inspect mlops-week02-mlflow:0.1 >/dev/null
docker build -t mlops-week02-pipeline:0.1 .
kind load docker-image mlops-week02-pipeline:0.1 --name mlops-lab
if k get job feast-verify >/dev/null 2>&1; then
  echo 'feast-verify already exists. Inspect its logs; delete only that Job before repeating.' >&2
  exit 1
fi
k apply -f feast-job.yaml
k rollout status deployment/redis --timeout=180s
k logs -f job/feast-verify -c feast --pod-running-timeout=300s
k wait --for=condition=Complete job/feast-verify --timeout=900s
k get job feast-verify
echo 'Feast log should end with FEAST_VALIDATION=PASS.'
echo 'Next: install/check standalone KFP and run the four-component pipeline.'
