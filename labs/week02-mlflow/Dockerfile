FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt
COPY train_compare_register.py /app/train_compare_register.py
ENV PYTHONUNBUFFERED=1
CMD ["python", "/app/train_compare_register.py"]
