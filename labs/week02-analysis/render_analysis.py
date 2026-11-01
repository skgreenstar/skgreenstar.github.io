"""Render the existing seeded dataset and published validation results for the notes."""
import ast
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "docs/public/images"
HERE = Path(__file__).resolve().parent


def load_dataset():
    # Load the original pure generator without importing the MLflow training runtime.
    source = ROOT / "labs/week02-mlflow/train_compare_register.py"
    tree = ast.parse(source.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "dataset")
    namespace = {"np": np, "pd": pd}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
    return namespace["dataset"](), hashlib.sha256(source.read_bytes()).hexdigest()


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.labelcolor": "#4c5c73", "text.color": "#1c2d47",
                         "xtick.color": "#63728a", "ytick.color": "#63728a",
                         "axes.edgecolor": "#d6deea", "svg.hashsalt": "week02-analysis-v1"})
    frame, generator_sha = load_dataset()
    columns = ["temperature", "pressure", "speed"]
    stats = {"rows": len(frame), "missing_values": int(frame.isna().sum().sum()),
             "entities": int(frame.equipment_id.nunique()), "seed": 42,
             "source_sha256": generator_sha,
             "correlations": {c: float(frame[c].corr(frame.quality)) for c in columns},
             "ranges": {c: [float(frame[c].min()), float(frame[c].max())] for c in columns + ["quality"]}}
    sampled = frame.iloc[::8]
    fig, axes = plt.subplots(3, 1, figsize=(10, 10), layout="constrained")
    fig.set_facecolor("#f7f9fc")
    fig.suptitle("What patterns does the model need to learn?", fontsize=20, fontweight="bold", x=.04, ha="left")
    titles = ["Temperature: a curved relationship", "Pressure: an upward trend", "Speed: a weaker marginal trend"]
    colors = ["#336be3", "#008e80", "#9160c9"]
    for ax, col, title, color in zip(axes, columns, titles, colors):
        ax.set_facecolor("white")
        ax.scatter(sampled[col], sampled.quality, s=15, alpha=.22, color="#7b8da8", edgecolors="none")
        edges = np.linspace(frame[col].min(), frame[col].max(), 13)
        grouped = frame.groupby(pd.cut(frame[col], edges, include_lowest=True), observed=True).agg(
            x=(col, "mean"), y=("quality", "mean"))
        ax.plot(grouped.x, grouped.y, marker="o", markersize=5, linewidth=2.5, color=color)
        ax.set_title(title, loc="left", fontsize=14, fontweight="bold", pad=10)
        ax.text(.98,.93,f"Pearson r = {stats['correlations'][col]:.3f}",transform=ax.transAxes,
                ha="right",va="top", fontsize=11,color="#53657d")
        ax.set_xlabel(col.capitalize(), fontsize=12)
        ax.set_ylabel("Synthetic quality", fontsize=12)
        ax.grid(axis="y", color="#e8edf4", linewidth=.8)
        ax.set_axisbelow(True)
    fig.supxlabel("Line: 12-bin means of all 1,000 rows | Dots: 125 sampled rows | Synthetic demo, seed 42", fontsize=10)
    for ext in ["svg", "png"]:
        fig.savefig(ASSETS / ("week02-feature-quality." + ext), dpi=150, metadata={"Date": None} if ext=="svg" else None)
    plt.close(fig)

    # Values from the already recorded validation comparison; no new training is implied.
    scores = pd.DataFrame({"model": ["Mean baseline", "Ridge", "RandomForest"],
                           "validation_rmse": [4.251555, 3.297208, .983442]})
    scores.to_csv(HERE / "validation_comparison.csv", index=False)
    fig, ax = plt.subplots(figsize=(10, 4.8), layout="constrained")
    fig.set_facecolor("#f7f9fc"); ax.set_facecolor("white")
    ax.barh(scores.model, scores.validation_rmse, color=["#a9b5c7", "#5b83d7", "#159780"], height=.48)
    ax.invert_yaxis()
    for i, value in enumerate(scores.validation_rmse):
        ax.text(value+.08, i, f"{value:.6f}", va="center", fontsize=13, fontweight="bold")
    ax.set_xlim(0,5.1); ax.set_xlabel("Validation RMSE (lower is better)", fontsize=13)
    ax.set_title("Which model explains the held-out data better?", loc="left", fontsize=18,fontweight="bold",pad=20)
    ax.grid(axis="x",color="#e8edf4"); ax.set_axisbelow(True)
    fig.supxlabel("Chronological split: 700 train / 150 validation / 150 test | Published validation results",fontsize=10)
    for ext in ["svg", "png"]:
        fig.savefig(ASSETS / ("week02-model-comparison."+ext), dpi=150,metadata={"Date": None} if ext=="svg" else None)
    plt.close(fig)
    stats["rmse_reduction_vs_baseline_pct"] = 100*(1-.983442/4.251555)
    stats["metric_source"] = "Existing validation comparison in mlflow-model-lifecycle.md; no training rerun"
    (HERE / "analysis_summary.json").write_text(json.dumps(stats,indent=2))
    print(json.dumps(stats,indent=2))


if __name__ == "__main__":
    main()
