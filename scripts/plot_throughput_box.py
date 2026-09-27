#!/usr/bin/env python3
"""Boxplot of one metric column from <dataset>_throughput_log.csv, grouped
by algorithm. Each box pools that algorithm's values across all traces in
the CSV.

The datasets in DATASETS become panels of one figure, in that order, sharing
a y axis so the two cache sizes can be read against each other.

usage: python3 plot_throughput_box.py [column] [input.csv output.pdf]
  column defaults to "throughput"; any numeric CSV column works
  (e.g. ipc, cpr, elapsed_time_sec).
  an explicit input/output pair plots that one CSV as a single panel.
"""

import csv
import sys
from collections import defaultdict

import matplotlib.pyplot as plt

from result_utils import display_name

DEFAULT_COLUMN = "throughput"
DATASETS = ["twitter_small", "twitter_large"]
DATASET_TITLE = {
    "twitter_small": "Small cache size",
    "twitter_large": "Large cache size",
}
INPUT_TEMPLATE = "./result/throughput/{dataset}_throughput_log.csv"
OUTPUT_TEMPLATE = "./result/throughput/twitter_throughput_box_{column}.pdf"

ALGO_ORDER = ["FIFO", "SIEVE", "Ghat", "TwoQ", "S3FIFO", "LIRS", "wtinyLFU", ]

DISPLAY_NAME = {"Ghat": "GHAT", "S3FIFO": "S3-FIFO", "wtinyLFU": "W-TinyLFU"}

COLUMN_YLABEL = {
    "throughput": "Throughput (Mreq/s)",
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


def plot(panels, column, output_path):
    """panels is [(title, by_algo), ...], drawn left to right on one y axis."""
    # only the algorithms every panel has, so the panels stay column-aligned
    algos = [a for a in ALGO_ORDER if all(a in by_algo for _, by_algo in panels)]
    labels = [display_name(a, DISPLAY_NAME) for a in algos]

    fig, axes = plt.subplots(
        1, len(panels), figsize=(6 * len(panels), 5), sharey=True, squeeze=False
    )
    for ax, (title, by_algo), tag in zip(axes[0], panels, "abcdefg"):
        bp = ax.boxplot(
            [by_algo[a] for a in algos], tick_labels=labels, patch_artist=True
        )
        for patch in bp["boxes"]:
            patch.set_facecolor("white")
            patch.set_edgecolor("black")
        for median in bp["medians"]:
            median.set_color("red")
        if len(panels) > 1:
            ax.set_title(f"({tag}) {title}", y=-0.14, fontsize=12)

    axes[0][0].set_ylabel(COLUMN_YLABEL.get(column, column))

    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    print(f"saved: {output_path}")


if __name__ == "__main__":
    column = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_COLUMN
    if len(sys.argv) > 3:
        sources = [(sys.argv[2], sys.argv[2])]
        output_path = sys.argv[3]
    else:
        sources = [
            (INPUT_TEMPLATE.format(dataset=d), DATASET_TITLE.get(d, d))
            for d in DATASETS
        ]
        output_path = OUTPUT_TEMPLATE.format(column=column)

    panels = []
    for input_path, title in sources:
        by_algo = load_column(input_path, column)
        for algo in ALGO_ORDER:
            n = len(by_algo.get(algo, []))
            print(f"NOTE: {input_path}: {algo} has {n} samples", file=sys.stderr)
        panels.append((title, by_algo))

    # Same as plot_cdn_reduction_scatter.py: 1.2x the 10 pt default; tick and
    # axis labels follow this size.
    plt.rcParams["font.size"] = 12
    # Type 3 fonts are rejected by several publishers' PDF checks; 42 is
    # TrueType.
    plt.rcParams["pdf.fonttype"] = 42
    plot(panels, column, output_path)
