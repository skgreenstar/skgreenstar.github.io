# Week 05 · Worker Crash Recovery
The experiment **actually ran locally** using Python 3.13.5 and SQLite, with two independent worker processes. This is **not a Redis or Kubernetes execution**. The logical clock uses 100/101/111, so no real 10-second wait is claimed.

Run: `python demo.py`.

The worker commits task removal (delete mode) or claimed/lease state (lease mode), then crashes with exit 17. We retry once immediately and once after the simulated lease expiration.

| Mode | First exit | Immediate retry | Expired lease retry | Final |
|---|---:|---:|---:|---|
| destructive dequeue | 17 | 3 (no work) | 3 (no work) | task lost |
| lease+ACK | 17 | 3 (lease held) | 0 (processed) | done, attempts=2 |

The assertion test passed twice. The actual observed run is in `results.json`. A lease/ACK path enables recovery but **does not guarantee exactly-once execution**. Real Redis Streams require XACK/claim handling; production systems also need fencing, idempotent writes, timeout renewal, DLQ, and metrics.
