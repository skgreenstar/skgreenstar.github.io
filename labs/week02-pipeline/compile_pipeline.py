"""Compile only: this does not claim a successful Kubernetes KFP run."""
from kfp import compiler, dsl
IMAGE = "mlops-week02-pipeline:0.1"
TRACKING = "http://mlflow.week02.svc.cluster.local:5000"


@dsl.container_component
def prepare(run_id: str, data: dsl.Output[dsl.Dataset]):
    return dsl.ContainerSpec(image=IMAGE, command=["python", "/app/pipeline_tasks.py"],
        args=["prepare", "--run-id", run_id, "--output", data.path])


@dsl.container_component
def features(data: dsl.Input[dsl.Dataset], result: dsl.Output[dsl.Dataset]):
    return dsl.ContainerSpec(image=IMAGE, command=["python", "/app/pipeline_tasks.py"],
        args=["features", "--source", data.path, "--output", result.path])


@dsl.container_component
def inference(data: dsl.Input[dsl.Dataset], feature_data: dsl.Input[dsl.Dataset], result: dsl.Output[dsl.Dataset]):
    return dsl.ContainerSpec(image=IMAGE, command=["python", "/app/pipeline_tasks.py"],
        args=["predict", "--source", data.path, "--features", feature_data.path, "--output", result.path])


@dsl.container_component
def publish(data: dsl.Input[dsl.Dataset], result: dsl.Output[dsl.Dataset]):
    return dsl.ContainerSpec(image=IMAGE, command=["python", "/app/pipeline_tasks.py"],
        args=["publish", "--source", data.path, "--output", result.path])


@dsl.pipeline(name="week02-feast-mlflow-batch")
def pipeline(training_run_id: str):
    first = prepare(run_id=training_run_id)
    second = features(data=first.outputs["data"])
    third = inference(data=first.outputs["data"], feature_data=second.outputs["result"])
    last = publish(data=third.outputs["result"])
    for task in [first, second, third, last]:
        task.set_env_variable("MLFLOW_TRACKING_URI", TRACKING)
        task.set_caching_options(False)
        task.set_cpu_request("250m").set_cpu_limit("1")
        task.set_memory_request("512Mi").set_memory_limit("2Gi")


if __name__ == "__main__":
    compiler.Compiler().compile(pipeline_func=pipeline, package_path="pipeline.yaml")
    print("KFP_COMPILE=PASS: pipeline.yaml")
