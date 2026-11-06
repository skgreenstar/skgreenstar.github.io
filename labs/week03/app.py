"""Synthetic inference load, not a trained model."""
from fastapi import FastAPI, HTTPException
import os
import time

app = FastAPI()
started = time.monotonic()
ready_delay = int(os.getenv("READY_DELAY_SECONDS", "0"))

@app.get("/healthz")
def healthz():
    return {"alive": True}

@app.get("/readyz")
def readyz():
    if time.monotonic() - started < ready_delay:
        raise HTTPException(status_code=503, detail="warming up")
    return {"ready": True}

@app.get("/infer")
def infer(mode: str = "cpu", iterations: int = 500_000, wait_ms: int = 200):
    if mode == "cpu":
        if not 1 <= iterations <= 5_000_000:
            raise HTTPException(422, detail="iterations must be 1..5000000")
        acc = 0
        for i in range(iterations):
            acc = (acc + (i * i) % 97) % 1_000_003
        return {"mode": "cpu", "result": acc}
    if mode == "wait":
        if not 0 <= wait_ms <= 2000:
            raise HTTPException(422, detail="wait_ms must be 0..2000")
        time.sleep(wait_ms / 1000)
        return {"mode": "wait", "wait_ms": wait_ms}
    raise HTTPException(422, detail="mode must be cpu or wait")
