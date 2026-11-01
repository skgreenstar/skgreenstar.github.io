FROM python:3.12-slim AS compiler
WORKDIR /build
RUN python -m venv /opt/kfp && /opt/kfp/bin/pip install --no-cache-dir kfp==2.9.0
COPY compile_pipeline.py /build/
RUN /opt/kfp/bin/python compile_pipeline.py

FROM mlops-week02-mlflow:0.1
WORKDIR /app
# Preserve the exact runtime used to train/serialize the existing registered model.
RUN python -m pip freeze > /tmp/base-constraints.txt \
 && python -m pip install --no-cache-dir -c /tmp/base-constraints.txt 'feast[redis]==0.67.0'
COPY feature_tasks.py pipeline_tasks.py /app/
COPY submit_pipeline.py /app/
COPY --from=compiler /build/pipeline.yaml /app/pipeline.yaml
COPY --from=compiler /opt/kfp /opt/kfp
ENV PYTHONUNBUFFERED=1
CMD ["python", "/app/feature_tasks.py"]
