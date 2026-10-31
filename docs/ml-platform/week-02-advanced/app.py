import os, math, time
from fastapi import FastAPI, Response
app = FastAPI()
ready_at = time.monotonic() + float(os.getenv("READY_DELAY", "0"))
@app.get("/healthz")
def health(): return {"alive": True}
@app.get("/readyz")
def ready(r: Response):
    ok = time.monotonic() >= ready_at
    if not ok: r.status_code = 503
    return {"ready": ok}
@app.get("/work")
def work(n: int = 120000):
    t = time.perf_counter()
    v = sum(math.sqrt(i) for i in range(n))
    return {"result": round(v,2), "duration_ms": round((time.perf_counter()-t)*1000,2), "pod":os.getenv("HOSTNAME","unknown")}
