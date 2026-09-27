#!/usr/bin/env python3
"""
usage: python3 plot_cdn_reduction_scatter.py [object|byte]

Outputs:
  result/real/cdn_reduction_scatter_<metric>.pdf
"""

import os
import sys
from collections import defaultdict

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.ticker import FormatStrFormatter, MultipleLocator

from result_utils import display_name, parse_result_file, resolve_family_files


DISPLAY_NAME = {"Sieve": "SIEVE", "Cacheus": "CACHEUS", "Clock": "CLOCK", "Ghat": "GHAT", "S3FIFO": "S3-FIFO", "WTinyLFU": "W-TinyLFU"}

# Same variant pinning as plot_reduction_map.py (threshold-2 Ghat).
ALGO_VARIANT = {
    "Ghat": ("Ghat-2-1.0000",),
    "LRB": ("LRB-BMR",),
    "S3FIFO": ("S3FIFO-0.1000-2",),
    "WTinyLFU": ("WTinyLFU-w0.01-SLRU",),
}

FAMILIES = ["Meta CDN", "Wikimedia", "Tencent Photo"]
FAMILY_GLOBS = {
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
    "LIRS",
    "WTinyLFU",
    "Cacheus",
    "LRB",
    "Ghat",
]
SIZES = ["small", "large"]
SIZE_TITLE = {"small": "Small cache size", "large": "Large cache size"}
METRIC_LABEL = {"object": "OMR", "byte": "BMR"}

# Greyscale, following plot_scan_retention.py: shape carries the corpus and
# the grey level plus the fill back it up, so the three corpora stay apart in
# print. All three sit at one x per algorithm, hence the white marker edge --
# it keeps overlapping markers readable where alpha alone would not.
FAMILY_COLOR = {
    "Meta CDN": "#8c8c8c",
    "Wikimedia": "#1a1a1a",
    "Tencent Photo": "#1a1a1a",
}
FAMILY_MARKER = {"Meta CDN": "*", "Wikimedia": "s", "Tencent Photo": "^"}
FAMILY_MARKER_SIZE = {"Meta CDN": 130, "Wikimedia": 52, "Tencent Photo": 62}
FAMILY_FILLED = {"Meta CDN", "Wikimedia"}

# Off-scale points get a caret at the panel edge instead of their own marker,
# so "hollow" is never overloaded against Tencent Photo's hollow triangle.
CLIP_COLOR = "#555555"


def collect_values(size, metric):
    """Return {family: {algo: [(trace, reduction), ...]}} and baseline counts."""
    metric_idx = 4 if metric == "byte" else 3
    miss_ratios = {family: defaultdict(dict) for family in FAMILIES}

    for family in FAMILIES:
        for path in resolve_family_files(family, FAMILY_GLOBS):
            for row in parse_result_file(path, ALGO_VARIANT):
                trace, row_size, algo = row[0], row[1], row[2]
                if row_size != size:
                    continue
                miss_ratios[family][trace][algo] = row[metric_idx]

    reductions = {family: defaultdict(list) for family in FAMILIES}
    baseline_counts = {}
    for family in FAMILIES:
        n_baseline = 0
        for trace, algo_values in sorted(miss_ratios[family].items()):
            baseline = algo_values.get(BASELINE_ALGO)
            if not baseline:
                continue
            n_baseline += 1
            for algo in ALGOS:
                if algo in algo_values:
                    reductions[family][algo].append(
                        (trace, (baseline - algo_values[algo]) / baseline * 100.0)
                    )
        baseline_counts[family] = n_baseline

    return reductions, baseline_counts


def panel_ylim(values):
    """Axis range spanning every point inside Tukey's 3xIQR "far out" fence.

    The bound is the most extreme point that survives the fence, not the
    fence itself, so the axis never clips a point it did not have to.
    """
    array = np.asarray(values)
    q1, q3 = np.percentile(array, [25.0, 75.0])
    iqr = q3 - q1
    kept = array[(array >= q1 - 3.0 * iqr) & (array <= q3 + 3.0 * iqr)]
    lo, hi = min(kept.min(), 0.0), max(kept.max(), 0.0)
    pad = 0.08 * (hi - lo)
    return lo - pad, hi + pad


def plot_panel(ax, reductions, algos, ylim, size):
    algo_x = np.arange(len(algos), dtype=float)
    lo, hi = ylim

    for family in FAMILIES:
        for i, algo in enumerate(algos):
            for trace, value in reductions[family].get(algo, []):
                x = algo_x[i]
                if lo <= value <= hi:
                    filled = family in FAMILY_FILLED
                    ax.scatter(
                        [x],
                        [value],
                        facecolors=FAMILY_COLOR[family] if filled else "none",
                        marker=FAMILY_MARKER[family],
                        s=FAMILY_MARKER_SIZE[family],
                        edgecolors="white" if filled else FAMILY_COLOR[family],
                        linewidths=0.5 if filled else 0.9,
                        alpha=0.85,
                        zorder=3,
                    )
                else:
                    below = value < lo
                    ax.scatter(
                        [x],
                        [lo if below else hi],
                        color=CLIP_COLOR,
                        marker="v" if below else "^",
                        s=26,
                        zorder=4,
                    )
                    ax.annotate(
                        f"{value:+.1f}",
                        (x, lo if below else hi),
                        textcoords="offset points",
                        xytext=(0, 7 if below else -13),
                        ha="center",
                        fontsize=9,
                        color=CLIP_COLOR,
                        zorder=4,
                    )
                    print(
                        f"clipped: [{size}] {family} {trace} {algo}: {value:+.4f}",
                        file=sys.stderr,
                    )

    ax.axhline(0, color="#888888", linewidth=0.8, zorder=1)
    ax.set_xticks(algo_x)
    ax.set_xticklabels(
        [display_name(algo, DISPLAY_NAME) for algo in algos],
        rotation=45,
        ha="right",
        rotation_mode="anchor",
    )
    ax.set_xlim(-0.55, len(algos) - 0.45)
    ax.set_ylim(lo, hi)
    ax.yaxis.set_major_locator(MultipleLocator(10))
    ax.yaxis.set_minor_locator(MultipleLocator(5))
    ax.yaxis.set_major_formatter(FormatStrFormatter("%.0f"))
    ax.set_axisbelow(True)
    ax.grid(axis="y", which="major", color="#e5e5e5", linewidth=0.6, zorder=0)
    ax.grid(axis="y", which="minor", color="#eeeeee", linewidth=0.5, zorder=0)
    ax.grid(axis="x", color="#eeeeee", linewidth=0.5, zorder=0)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def plot(data_by_size, baseline_counts, algos, metric, output_path):
    all_values = [
        value
        for size in SIZES
        for family in FAMILIES
        for algo in algos
        for _, value in data_by_size[size][family].get(algo, [])
    ]
    ylim = panel_ylim(all_values)

    fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.8), sharey=True)
    for ax, size, tag in zip(axes, SIZES, "ab"):
        plot_panel(ax, data_by_size[size], algos, ylim, size)
        ax.set_title(f"({tag}) {SIZE_TITLE[size]}", y=-0.50, fontsize=12)

    axes[0].set_ylabel(f"{METRIC_LABEL[metric]} Reduction from {BASELINE_ALGO} (%)")

    legend_handles = [
        Line2D(
            [],
            [],
            linestyle="none",
            marker=FAMILY_MARKER[family],
            markersize=11 if family == "Meta CDN" else 7,
            markerfacecolor=(
                FAMILY_COLOR[family] if family in FAMILY_FILLED else "none"
            ),
            markeredgecolor=(
                "white" if family in FAMILY_FILLED else FAMILY_COLOR[family]
            ),
            markeredgewidth=0.5 if family in FAMILY_FILLED else 0.9,
            label=f"{family}",
        )
        for family in FAMILIES
    ]
    fig.legend(
        handles=legend_handles,
        loc="upper center",
        ncol=len(FAMILIES),
        frameon=False,
        fontsize=10.8,
        bbox_to_anchor=(0.5, 1.0),
    )

    fig.tight_layout(rect=(0, 0, 1, 0.92))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {output_path}")


def report_coverage(data_by_size, baseline_counts, algos):
    for size in SIZES:
        for family in FAMILIES:
            n_expected = baseline_counts[size][family]
            for algo in algos:
                n = len(data_by_size[size][family].get(algo, []))
                if n == 0:
                    print(
                        f"warning: [{size}] {family} {algo}: no data", file=sys.stderr
                    )
                elif n != n_expected:
                    print(
                        f"warning: [{size}] {family} {algo}: "
                        f"n={n}, {BASELINE_ALGO} n={n_expected}",
                        file=sys.stderr,
                    )


def main():
    if len(sys.argv) > 2 or (len(sys.argv) == 2 and sys.argv[1] not in METRIC_LABEL):
        sys.exit(f"usage: {sys.argv[0]} [object|byte]")
    metric = sys.argv[1] if len(sys.argv) == 2 else "byte"

    missing = [f for f in FAMILIES if not resolve_family_files(f, FAMILY_GLOBS)]
    if missing:
        sys.exit(f"no result files found for: {', '.join(missing)}")

    data_by_size = {}
    baseline_counts = {}
    for size in SIZES:
        data_by_size[size], baseline_counts[size] = collect_values(size, metric)

    algos = [
        algo
        for algo in ALGOS
        if any(
            data_by_size[size][family].get(algo)
            for size in SIZES
            for family in FAMILIES
        )
    ]
    for algo in ALGOS:
        if algo not in algos:
            print(f"note: dropping {algo}: no CDN data", file=sys.stderr)

    report_coverage(data_by_size, baseline_counts, algos)

    output_path = os.path.normpath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "result",
            "real",
            f"cdn_reduction_scatter_{metric}.pdf",
        )
    )
    # Type 3 fonts are rejected by several publishers' PDF checks; 42 is
    # TrueType.
    plt.rcParams["pdf.fonttype"] = 42
    # 1.2x the 10 pt default; tick and axis labels follow this size.
    plt.rcParams["font.size"] = 12
    plot(data_by_size, baseline_counts, algos, metric, output_path)


if __name__ == "__main__":
    main()
