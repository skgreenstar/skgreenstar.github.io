#!/usr/bin/env python3
"""Simulate a Kubernetes Job retry after an external DB write, using local processes."""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

JOB_ID = "retrain-2026w05"
MODEL_URI = "models:/price-predictor/17"

def setup(db: Path, mode: str):
    with sqlite3.connect(db) as con:
        if mode == "naive":
            con.execute("CREATE TABLE results (id INTEGER PRIMARY KEY, job_id TEXT, model_uri TEXT)")
        else:
            con.execute("CREATE TABLE results (id INTEGER PRIMARY KEY, job_id TEXT NOT NULL UNIQUE, model_uri TEXT)")

def attempt(db: Path, mode: str, crash_after_commit: bool):
    with sqlite3.connect(db) as con:
        if mode == "naive":
            con.execute("INSERT INTO results (job_id, model_uri) VALUES (?, ?)", (JOB_ID, MODEL_URI))
        else:
            con.execute("""INSERT INTO results (job_id, model_uri) VALUES (?, ?)
                           ON CONFLICT(job_id) DO NOTHING""", (JOB_ID, MODEL_URI))
        con.commit()
    if crash_after_commit:
        os._exit(17)

def run():
    output = []
    with tempfile.TemporaryDirectory(prefix="job-retry-") as tempdir:
        for mode in ("naive", "idempotent"):
            db = Path(tempdir) / (mode + ".sqlite")
            setup(db, mode)
            commands = []
            for fail in (True, False):
                p = subprocess.run(
                    [sys.executable, __file__, "--attempt", "--db", str(db),
                     "--mode", mode, "--crash" if fail else "--normal"],
                    capture_output=True, text=True, check=False,
                )
                commands.append({"attempt": "first" if fail else "retry", "exit_code": p.returncode})
            with sqlite3.connect(db) as con:
                count = con.execute("SELECT COUNT(*) FROM results WHERE job_id=?", (JOB_ID,)).fetchone()[0]
                records = con.execute("SELECT job_id, model_uri FROM results ORDER BY id").fetchall()
            output.append({"mode": mode, "attempts": commands, "row_count": count,
                           "rows": [{"job_id": a, "model_uri": b} for a, b in records]})
    assert [x["row_count"] for x in output] == [2, 1], output
    assert all(x["attempts"][0]["exit_code"] == 17 and x["attempts"][1]["exit_code"] == 0 for x in output)
    print(json.dumps({"scenario": "crash_after_db_commit_then_retry", "results": output,
                      "assertions_passed": True}, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt", action="store_true")
    parser.add_argument("--db", type=Path)
    parser.add_argument("--mode", choices=["naive", "idempotent"])
    parser.add_argument("--crash", action="store_true")
    parser.add_argument("--normal", action="store_true")
    args = parser.parse_args()
    if args.attempt:
        attempt(args.db, args.mode, args.crash)
    else:
        run()
