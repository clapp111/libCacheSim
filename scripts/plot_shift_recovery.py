#!/usr/bin/env python3

import sys
from collections import defaultdict

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np

DEFAULT_INPUT = "../result/shift/disjoint_windows.csv"
DEFAULT_OUTPUT = "../result/shift/disjoint_recovery.png"

SHIFT_WINDOW_IDX = 2000
BASELINE_WINDOWS = range(1960, 2000)
WINDOW_SIZE = 100
TOLERANCE = 1.1
ROLL = 3

# This figure compares Ghat with its parent policy, Sieve, and with ARC,
# Cacheus, and LIRS. Other algorithms may be present in the input CSV but are
# outside this figure's scope. The fixed top-to-bottom order (Ghat first) is
# not sorted by median, so it stays consistent across disjoint and reversal
# figures.
ALGO_ORDER = ["Ghat", "ARC", "Cacheus", "LIRS", "Sieve"]

# Paper-facing display names are applied to tick labels only; CSV keys keep
# the result files' spelling.
DISPLAY_NAME = {"Sieve": "SIEVE", "Cacheus": "CACHEUS"}


def parse_windows(path):
    # by_algo_rep[algo][rep][window_idx] = miss_ratio
    by_algo_rep = defaultdict(lambda: defaultdict(dict))
    with open(path) as f:
        next(f)  # header
        for line in f:
            algo, rep, window_idx, req_in_window, miss_in_window, miss_ratio = line.strip().split(",")
            by_algo_rep[algo][int(rep)][int(window_idx)] = float(miss_ratio)
    return by_algo_rep


def requests_to_recover(by_algo_rep):
    # result[algo] = [requests_to_recover per rep, ...]
    result = defaultdict(list)
    for algo in ALGO_ORDER:
        if algo not in by_algo_rep:
            continue
        for rep, windows in by_algo_rep[algo].items():
            max_w = max(windows.keys())
            baseline = np.mean([windows[w] for w in BASELINE_WINDOWS])
            threshold = baseline * TOLERANCE

            recovered_at = None
            for w in range(SHIFT_WINDOW_IDX + 1, max_w - ROLL + 1):
                rolling = np.mean([windows[w + i] for i in range(ROLL)])
                if rolling <= threshold:
                    recovered_at = w
                    break

            if recovered_at is None:
                print(f"WARN: {algo} rep {rep} never recovered within tolerance in observed range", file=sys.stderr)
                continue

            result[algo].append((recovered_at - SHIFT_WINDOW_IDX) * WINDOW_SIZE)

    for algo in ALGO_ORDER:
        if algo in result:
            vals = result[algo]
            print(f"{algo}: n={len(vals)}, median={np.median(vals):.0f}, "
                  f"min={min(vals)}, max={max(vals)}", file=sys.stderr)

    return result


BOX_WIDTH = 0.5
MEDIAN_COLOR = "#e34948"

# Box = P25/median/P75 with P10/P90 whiskers. Points outside the whiskers are
# drawn rather than discarded. Recovery times are quantized in multiples of
# WINDOW_SIZE, although the box plot does not show repeated values stacking at
# the same position.


def _box_stats(vals, label):
    arr = np.array(vals)
    lo, hi = np.percentile(arr, 10), np.percentile(arr, 90)
    return {
        "label": label,
        "med": float(np.median(arr)),
        "q1": float(np.percentile(arr, 25)),
        "q3": float(np.percentile(arr, 75)),
        "whislo": float(lo),
        "whishi": float(hi),
        "fliers": arr[(arr < lo) | (arr > hi)],
    }


def plot_recovery_panel(ax, result):
    """Draw the recovery box plot onto `ax`."""
    algos = [a for a in ALGO_ORDER if a in result]

    # y=0 is at the bottom, so give the first entry of ALGO_ORDER the
    # highest y to place it at the top.
    n = len(algos)
    positions, stats_list = [], []
    for i, algo in enumerate(algos):
        positions.append(n - 1 - i)
        stats_list.append(_box_stats(result[algo], algo))

    bp = ax.bxp(stats_list, positions=positions, widths=BOX_WIDTH,
                orientation="horizontal", patch_artist=True, showmeans=False,
                manage_ticks=False)
    for patch in bp["boxes"]:
        patch.set_facecolor("none")
        patch.set_edgecolor("#222222")
        patch.set_linewidth(0.5)
    for element in ("whiskers", "caps"):
        for line in bp[element]:
            line.set_color("#222222")
            line.set_linewidth(0.5)
    for median in bp["medians"]:
        median.set_color(MEDIAN_COLOR)
        median.set_linewidth(1.0)
    for flier in bp["fliers"]:
        flier.set_marker("o")
        flier.set_markersize(3)
        flier.set_markerfacecolor("#898781")
        flier.set_markeredgecolor("none")
        flier.set_alpha(0.6)

    ax.set_yticks(range(n))
    ax.set_yticklabels([DISPLAY_NAME.get(a, a) for a in reversed(algos)])
    ax.set_ylim(-0.6, n - 0.4)
    ax.set_xlabel("requests to recover (to within 10% of pre-shift baseline)")
    ax.set_axisbelow(True)
    ax.grid(axis="x", color="#e5e5e5", linewidth=0.6, zorder=-1)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def plot(result, output_path):
    algos = [a for a in ALGO_ORDER if a in result]
    fig, ax = plt.subplots(figsize=(8, 0.7 * len(algos) + 1.5))
    plot_recovery_panel(ax, result)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    print(f"saved: {output_path}")


if __name__ == "__main__":
    input_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INPUT
    output_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUTPUT

    by_algo_rep = parse_windows(input_path)
    result = requests_to_recover(by_algo_rep)
    plot(result, output_path)
