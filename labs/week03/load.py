"""Local concurrency test; percentile results include failed requests."""
import argparse
import concurrent.futures
import json
import time
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://localhost:8080/infer?mode=cpu")
parser.add_argument("--requests", type=int, default=200)
parser.add_argument("--concurrency", type=int, default=10)
args = parser.parse_args()
if not (1 <= args.requests <= 10000 and 1 <= args.concurrency <= 100):
    parser.error("requests 1..10000; concurrency 1..100")

def one(_):
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(args.url, timeout=10) as response:
            response.read()
            ok = 200 <= response.status < 400
    except Exception:
        ok = False
    return ok, (time.perf_counter() - start) * 1000

def percentile(vals, p):
    vals = sorted(vals)
    if not vals:
        return None
    return round(vals[min(len(vals)-1, int((len(vals)-1)*p))], 2)

start = time.perf_counter()
with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
    samples = list(pool.map(one, range(args.requests)))
duration = time.perf_counter()-start
latencies = [ms for _,ms in samples]
passed = sum(ok for ok,_ in samples)
print(json.dumps({
    "url":args.url, "requests":args.requests, "concurrency":args.concurrency,
    "duration_seconds":round(duration,3), "completed_rps":round(args.requests/duration,2),
    "success":passed, "errors":args.requests-passed,
    "error_rate":round((args.requests-passed)/args.requests,4),
    "p50_ms":percentile(latencies,.50),"p95_ms":percentile(latencies,.95)
}, ensure_ascii=False, indent=2))
