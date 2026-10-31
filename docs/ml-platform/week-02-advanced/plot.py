"""Plot measured k6 summary.csv only. Requires matplotlib."""
import csv, sys
from pathlib import Path
import matplotlib.pyplot as plt
source=Path(sys.argv[1] if len(sys.argv)>1 else 'results/summary.csv')
with source.open(newline='') as f: rows=list(csv.DictReader(f))
if not rows: raise SystemExit('No measured runs found')
names=[x['run'] for x in rows]
fig, ax=plt.subplots(figsize=(max(7,len(rows)*1.1),4.5))
for metric in ('p50_ms','p95_ms','p99_ms'):
    vals=[float(x[metric]) if x[metric] not in ('', 'None') else float('nan') for x in rows]
    ax.plot(names,vals,marker='o',label=metric)
ax.set_ylabel('HTTP request duration (ms)')
ax.set_xlabel('Measured run')
ax.tick_params(axis='x',rotation=35)
ax.legend()
fig.tight_layout()
out=source.parent/'latency_comparison.png'
fig.savefig(out,dpi=160)
print(out)
