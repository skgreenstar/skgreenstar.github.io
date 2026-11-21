#!/usr/bin/env python3
"""SQLite queue simulation: destructive dequeue vs lease+ack. Not Redis/Kubernetes."""
import json, os, sqlite3, subprocess, sys, tempfile
from pathlib import Path

def db(path):
    c=sqlite3.connect(path)
    c.execute("PRAGMA journal_mode=WAL")
    return c

def initialize(path):
    with db(path) as c:
        c.execute("CREATE TABLE tasks(id TEXT PRIMARY KEY,status TEXT,lease_until INT,attempts INT DEFAULT 0)")
        c.execute("INSERT INTO tasks(id,status) VALUES('train-batch-001','ready')")

def worker(path, mode, now, crash):
    with db(path) as c:
        c.execute("BEGIN IMMEDIATE")
        if mode=="delete":
            row=c.execute("SELECT id FROM tasks WHERE status='ready' LIMIT 1").fetchone()
            if row:c.execute("DELETE FROM tasks WHERE id=?",(row[0],))
        else:
            row=c.execute("SELECT id FROM tasks WHERE status='ready' OR (status='claimed' AND lease_until<=?) LIMIT 1",(now,)).fetchone()
            if row:c.execute("UPDATE tasks SET status='claimed',lease_until=?,attempts=attempts+1 WHERE id=?",(now+10,row[0]))
        c.commit()
    if not row:return 3
    if crash:os._exit(17)
    if mode=="lease":
        with db(path) as c:c.execute("UPDATE tasks SET status='done',lease_until=NULL WHERE id=?",(row[0],))
    return 0

def snapshot(path):
    with db(path) as c:rows=c.execute("SELECT id,status,lease_until,attempts FROM tasks").fetchall()
    return [dict(zip(("id","status","lease_until","attempts"),r)) for r in rows]

def attempt(path,mode,time,crash):
    p=subprocess.run([sys.executable,__file__,"--worker",path,mode,str(time),str(int(crash))],capture_output=True)
    return p.returncode

def main():
    result=[]
    with tempfile.TemporaryDirectory() as d:
        for mode in ("delete","lease"):
            path=str(Path(d)/(mode+".sqlite"));initialize(path)
            first=attempt(path,mode,100,True)
            state_after_crash=snapshot(path)
            immediate=attempt(path,mode,101,False)
            after_expiry=attempt(path,mode,111,False)
            result.append(dict(mode=mode,first_exit=first,immediate_retry_exit=immediate,
                after_expiry_retry_exit=after_expiry,after_crash=state_after_crash,final=snapshot(path)))
    assert result[0]["first_exit"]==17 and result[0]["final"]==[]
    assert result[1]["first_exit"]==17 and result[1]["immediate_retry_exit"]==3
    assert result[1]["after_expiry_retry_exit"]==0 and result[1]["final"][0]["status"]=="done"
    assert result[1]["final"][0]["attempts"]==2
    print(json.dumps({"experiment":"worker-crash-queue-recovery","backend":"sqlite",
        "clock":"simulated logical seconds 100, 101, 111","results":result,
        "assertions_passed":True},ensure_ascii=False,indent=2))

if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]=="--worker":
        sys.exit(worker(sys.argv[2],sys.argv[3],int(sys.argv[4]),bool(int(sys.argv[5]))))
    main()
