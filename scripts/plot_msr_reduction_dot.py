#!/usr/bin/env python3
"""Plot family-level mean miss-ratio reductions from FIFO.

Each invocation renders two panels: (a) small cache size and (b) large
cache size.  A marker is one trace family's mean reduction for one
algorithm; color and marker shape identify the family.

KV defaults to object miss ratio for Meta KV and Twitter. CDN defaults
to byte miss ratio for Meta CDN, Wikimedia, and Tencent Photo. The
optional metric argument overrides either default.

usage: python3 plot_msr_reduction_dot.py <kv|cdn> [object|byte]

Outputs:
  result/<mode>/<mode>_reduction_dot_<metric>.png
"""

import os
import sys
from collections import defaultdict

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.ticker import FormatStrFormatter, MultipleLocator

from result_utils import display_name, parse_result_file, resolve_family_files


DISPLAY_NAME = {"Sieve": "SIEVE", "Cacheus": "CACHEUS", "Clock": "CLOCK"}
# Ghat cache names encode protect threshold and ghost-count ratio.
ALGO_VARIANT = {"Ghat": "Ghat-2-1.0000"}
FAMILY_GLOBS = {
    "Twitter": ["result/twitter/*_result.txt"],
    "Meta KV": ["result/meta-key/*_result.txt"],
    "Meta CDN": ["result/meta-cdn/*_result.txt"],
    "Wikimedia": ["result/wikimedia/*_result.txt"],
    "Tencent Photo": ["result/tencent-photo/*_result.txt"],
}

BASELINE_ALGO = "FIFO"
ALGOS = [
    "LRU",
    "Clock",
    "TwoQ",
    "Sieve",
    "S3FIFO",
    "ARC",
    "Cacheus",
    "LIRS",
    "WTinyLFU",
    "LRB",
    "Ghat",
]
SIZES = ["small", "large"]
SIZE_TITLE = {"small": "small cache size", "large": "large cache size"}

MODE_CONFIG = {
    "kv": {
        "families": ["Meta KV", "Twitter"],
        "default_metric": "object",
    },
    "cdn": {
        "families": ["Meta CDN", "Wikimedia", "Tencent Photo"],
        "default_metric": "byte",
    },
}
METRIC_LABEL = {
    "object": "Object Miss Ratio",
    "byte": "Byte Miss Ratio",
}

FAMILY_COLOR = {
    "Twitter": "#e69f00",
    "Meta KV": "#6a3d9a",
    "Meta CDN": "#009e73",
    "Wikimedia": "#cc79a7",
    "Tencent Photo": "#0072b2",
}
FAMILY_MARKER = {
    "Twitter": "s",
    "Meta KV": "o",
    "Meta CDN": "o",
    "Wikimedia": "s",
    "Tencent Photo": "D",
}

MARKER_SIZE = 58


def collect_values(families, size, metric):
    """Return per-family algorithm reductions and FIFO baseline counts."""
    metric_idx = 4 if metric == "byte" else 3
    miss_ratios = {family: defaultdict(dict) for family in families}

    for family in families:
        for path in resolve_family_files(family, FAMILY_GLOBS):
            for row in parse_result_file(path, ALGO_VARIANT):
                trace, row_size, algo = row[0], row[1], row[2]
                if row_size != size:
                    continue
                miss_ratios[family][trace][algo] = row[metric_idx]

    reductions = {family: defaultdict(list) for family in families}
    baseline_counts = {}
    for family in families:
        baseline_counts[family] = sum(
            BASELINE_ALGO in algo_values
            and algo_values[BASELINE_ALGO] != 0
            for algo_values in miss_ratios[family].values()
        )
        for algo_values in miss_ratios[family].values():
            baseline = algo_values.get(BASELINE_ALGO)
            if not baseline:
                continue
            for algo in ALGOS:
                if algo in algo_values:
                    reductions[family][algo].append(
                        (baseline - algo_values[algo]) / baseline
                    )

    return reductions, baseline_counts



def plot_panel(ax, reductions, families):
    algo_x = np.arange(len(ALGOS), dtype=float)

    for family in families:
        xs = []
        means = []
        for i, algo in enumerate(ALGOS):
            values = reductions[family].get(algo, [])
            if not values:
                continue
            xs.append(algo_x[i])
            means.append(float(np.mean(values)))

        ax.scatter(
            xs,
            means,
            color=FAMILY_COLOR[family],
            marker=FAMILY_MARKER[family],
            s=MARKER_SIZE,
            edgecolors="white",
            linewidths=0.5,
            zorder=3,
        )

    ax.axhline(0, color="#888888", linewidth=0.8, zorder=1)
    ax.set_xticks(algo_x)
    ax.set_xticklabels(
        [display_name(algo, DISPLAY_NAME) for algo in ALGOS],
        rotation=45,
        ha="right",
    )
    ax.set_xlim(-0.55, len(ALGOS) - 0.45)
    ax.yaxis.set_major_locator(MultipleLocator(0.1))
    ax.yaxis.set_minor_locator(MultipleLocator(0.05))
    ax.yaxis.set_major_formatter(FormatStrFormatter("%.1f"))
    ax.set_axisbelow(True)
    ax.grid(axis="y", which="major", color="#e5e5e5", linewidth=0.6, zorder=0)
    ax.grid(axis="y", which="minor", color="#eeeeee", linewidth=0.5, zorder=0)
    ax.grid(axis="x", color="#eeeeee", linewidth=0.5, zorder=0)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def plot(data_by_size, baseline_counts, config, metric, output_path):
    families = config["families"]
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.8), sharey=True)

    for ax, size, tag in zip(axes, SIZES, "ab"):
        plot_panel(ax, data_by_size[size], families)
        ax.set_title(f"({tag}) {SIZE_TITLE[size]}", y=-0.32, fontsize=10)

    axes[0].set_ylabel(f"{METRIC_LABEL[metric]} Reduction from {BASELINE_ALGO}")

    legend_handles = []
    for family in families:
        n_small = baseline_counts["small"][family]
        n_large = baseline_counts["large"][family]
        n_label = str(n_small) if n_small == n_large else f"{n_small}/{n_large}"
        legend_handles.append(
            Line2D(
                [],
                [],
                linestyle="none",
                marker=FAMILY_MARKER[family],
                markersize=7,
                markerfacecolor=FAMILY_COLOR[family],
                markeredgecolor="white",
                markeredgewidth=0.5,
                label=f"{family} (n={n_label})",
            )
        )
    fig.legend(
        handles=legend_handles,
        loc="upper center",
        ncol=len(families),
        frameon=False,
        fontsize=9,
        bbox_to_anchor=(0.5, 1.0),
    )

    fig.tight_layout(rect=(0, 0, 1, 0.92))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {output_path}")


def report_coverage(data_by_size, baseline_counts, mode, families):
    for size in SIZES:
        for family in families:
            n_expected = baseline_counts[size][family]
            for algo in ALGOS:
                values = data_by_size[size][family].get(algo, [])
                n = len(values)
                if n == 0:
                    print(
                        f"warning: {mode} [{size}] {family} {algo}: no data",
                        file=sys.stderr,
                    )
                elif n != n_expected:
                    print(
                        f"warning: {mode} [{size}] {family} {algo}: "
                        f"n={n}, FIFO n={n_expected}",
                        file=sys.stderr,
                    )


def main():
    if (
        len(sys.argv) not in (2, 3)
        or sys.argv[1] not in MODE_CONFIG
        or (len(sys.argv) == 3 and sys.argv[2] not in METRIC_LABEL)
    ):
        sys.exit(f"usage: {sys.argv[0]} <kv|cdn> [object|byte]")

    mode = sys.argv[1]
    config = MODE_CONFIG[mode]
    metric = sys.argv[2] if len(sys.argv) == 3 else config["default_metric"]
    families = config["families"]

    missing = [
        family
        for family in families
        if not resolve_family_files(family, FAMILY_GLOBS)
    ]
    if missing:
        sys.exit(f"no result files found for: {', '.join(missing)}")

    data_by_size = {}
    baseline_counts = {}
    for size in SIZES:
        data_by_size[size], baseline_counts[size] = collect_values(
            families, size, metric
        )

    report_coverage(data_by_size, baseline_counts, mode, families)

    output_path = os.path.normpath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "result",
            mode,
            f"{mode}_reduction_dot_{metric}.png",
        )
    )
    plot(data_by_size, baseline_counts, config, metric, output_path)


if __name__ == "__main__":
    main()
