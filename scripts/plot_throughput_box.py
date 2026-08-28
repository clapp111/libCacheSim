#!/usr/bin/env python3
"""Boxplot of one metric column from throughput_log.csv, grouped by
algorithm. Each box pools that algorithm's values across all traces and
cache sizes present in the CSV.

usage: python3 plot_throughput_box.py [column] [input.csv] [output.png]
  column defaults to "throughput"; any numeric CSV column works
  (e.g. ipc, cpr, elapsed_time_sec).
"""

import csv
import statistics
import sys
from collections import defaultdict

import matplotlib.pyplot as plt

DEFAULT_COLUMN = "throughput"
DEFAULT_INPUT = "./result/throughput/throughput_log.csv"
DEFAULT_OUTPUT_TEMPLATE = "./result/throughput/throughput_box_{column}.png"

ALGO_ORDER = ["SIEVE", "Ghat", "S3FIFO", "LIRS", "wtinyLFU"]

# columns where a smaller value means better performance (e.g. cycles per
# request, elapsed time); everything else is treated as higher-is-better
# (e.g. throughput, ipc)
LOWER_IS_BETTER = {"cpr", "elapsed_time_sec"}

COLUMN_YLABEL = {
    "throughput": "Throughput (MQPS)",
    "ipc": "IPC (instructions per cycle)",
    "cpr": "CPU cycles per request",
}

# Tick-label highlight for Ghat.
HIGHLIGHT_ALGO = "Ghat"
HIGHLIGHT_COLOR = "#a3201f"


def load_column(path, column):
    by_algo = defaultdict(list)
    with open(path) as f:
        reader = csv.DictReader(f)
        if column not in reader.fieldnames:
            raise ValueError(f"column {column!r} not found; available: {reader.fieldnames}")
        for row in reader:
            by_algo[row["algo"]].append(float(row[column]))
    return by_algo


def plot(by_algo, column, output_path):
    # best-performing algorithm first, i.e. leftmost
    sign = 1 if column in LOWER_IS_BETTER else -1
    algos = sorted(
        (a for a in ALGO_ORDER if a in by_algo),
        key=lambda a: sign * statistics.median(by_algo[a]),
    )
    data = [by_algo[a] for a in algos]

    fig, ax = plt.subplots(figsize=(6, 5))
    bp = ax.boxplot(data, tick_labels=algos, patch_artist=True)
    for patch in bp["boxes"]:
        patch.set_facecolor("white")
        patch.set_edgecolor("black")
    for median in bp["medians"]:
        median.set_color("red")

    for tick, algo in zip(ax.get_xticklabels(), algos):
        if algo == HIGHLIGHT_ALGO:
            tick.set_color(HIGHLIGHT_COLOR)
            tick.set_fontweight("bold")

    ax.set_ylabel(COLUMN_YLABEL.get(column, column))

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    print(f"saved: {output_path}")


if __name__ == "__main__":
    column = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_COLUMN
    input_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_INPUT
    output_path = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_OUTPUT_TEMPLATE.format(column=column)

    by_algo = load_column(input_path, column)
    for algo in ALGO_ORDER:
        n = len(by_algo.get(algo, []))
        print(f"NOTE: {algo} has {n} samples", file=sys.stderr)

    plot(by_algo, column, output_path)
