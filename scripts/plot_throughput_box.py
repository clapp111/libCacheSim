#!/usr/bin/env python3
"""Boxplot of one metric column from <dataset>_throughput_log.csv, grouped
by algorithm. Each box pools that algorithm's values across all traces and
cache sizes present in the CSV.

usage: python3 plot_throughput_box.py [column] [input.csv output.png]
  column defaults to "throughput"; any numeric CSV column works
  (e.g. ipc, cpr, elapsed_time_sec).
  without an explicit input/output pair, every dataset in DATASETS is
  plotted to its own PNG.
"""

import csv
import sys
from collections import defaultdict

import matplotlib.pyplot as plt

DEFAULT_COLUMN = "throughput"
DATASETS = ["twitter_small", "twitter_large"]
INPUT_TEMPLATE = "./result/throughput/{dataset}_throughput_log.csv"
OUTPUT_TEMPLATE = "./result/throughput/{dataset}_throughput_box_{column}.png"

ALGO_ORDER = ["FIFO", "SIEVE", "Ghat", "TwoQ", "S3FIFO", "LIRS", "wtinyLFU", ]

COLUMN_YLABEL = {
    "throughput": "Throughput (MQPS)",
    "ipc": "IPC (instructions per cycle)",
    "cpr": "CPU cycles per request",
}


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
    algos = [a for a in ALGO_ORDER if a in by_algo]
    data = [by_algo[a] for a in algos]

    fig, ax = plt.subplots(figsize=(6, 5))
    bp = ax.boxplot(data, tick_labels=algos, patch_artist=True)
    for patch in bp["boxes"]:
        patch.set_facecolor("white")
        patch.set_edgecolor("black")
    for median in bp["medians"]:
        median.set_color("red")

    ax.set_ylabel(COLUMN_YLABEL.get(column, column))

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"saved: {output_path}")


if __name__ == "__main__":
    column = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_COLUMN
    if len(sys.argv) > 3:
        runs = [(sys.argv[2], sys.argv[3])]
    else:
        runs = [
            (
                INPUT_TEMPLATE.format(dataset=d),
                OUTPUT_TEMPLATE.format(dataset=d, column=column),
            )
            for d in DATASETS
        ]

    for input_path, output_path in runs:
        by_algo = load_column(input_path, column)
        for algo in ALGO_ORDER:
            n = len(by_algo.get(algo, []))
            print(f"NOTE: {input_path}: {algo} has {n} samples", file=sys.stderr)

        plot(by_algo, column, output_path)
