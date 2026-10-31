import json, csv, sys
from pathlib import Path
rows=[]
for name in sys.argv[1:]:
    data=json.loads(Path(name).read_text())
    metrics=data.get('metrics',{})
    def get(metric,key): return metrics.get(metric,{}).get('values',{}).get(key,'')
    rows.append({'run':Path(name).stem, 'requests':get('http_reqs','count'), 'rps':get('http_reqs','rate'), 'failure_rate':get('http_req_failed','rate'), 'p50_ms':get('http_req_duration','med'), 'p95_ms':get('http_req_duration','p(95)'), 'p99_ms':get('http_req_duration','p(99)'), 'dropped_iterations':get('dropped_iterations','count')})
if not rows: raise SystemExit('Usage: python analyze.py results/*.json')
out=Path('results/summary.csv')
out.parent.mkdir(exist_ok=True)
with out.open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
print(out)
