#!/usr/bin/env python3
"""Mechanism figure for the abrupt shift: the windowed object miss ratio
around the shift, for the SIEVE-equivalent cell and the two tau=2 cells.

The protected-object trajectory that used to be panel (a) is intentionally
omitted here. This script renders only the miss-ratio trajectory; protected-
state summaries are reported separately in the paper.

x is deliberately clipped to the transient window; full recovery is the
recovery box plot's job (plot_shift_recovery.py), not this figure's.

usage: python3 scripts/plot_shift_mechanism.py <disjoint|reversal>

The scenario selects both paths under result/shift:
  input:  <scenario>_ghat_variants_windows.csv
  output: <scenario>_mechanism.png
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

RESULT_DIR = Path(__file__).resolve().parent.parent / "result" / "shift"

# same landmarks as plot_shift_recovery.py -- the two figures read the
# same experiment and must agree on where the shift is
SHIFT_WINDOW_IDX = 2000
WINDOW_SIZE = 100

# transient window only; see the module docstring for why
WINDOW_LO = 1995
WINDOW_HI = 2020

# tau is held at 2 and Ghost is the axis that varies, which is what this
# section argues about; the tau sweep is a separate experiment on real
# traces. Ghat-g0-t1 is the bit-for-bit SIEVE-equivalent baseline;
# Ghat-g1-t1 is absent because varying two axes at once is the other section's
# question. Order sets legend order.
PLOT_ALGOS = ["Ghat-g0-t1", "Ghat-g0-t2", "Ghat-g1-t2"]

# Paper-facing display names -- same mapping as plot_shift_recovery.py.
# Ghat-g0-t1 is bit-for-bit identical to Sieve for policy behavior, but the
# label keeps clear that the diagnostic data comes from the Ghat code path.
DISPLAY_NAME = {
    "Ghat-g0-t1": "SIEVE-equivalent",
    "Ghat-g1-t2": "Ghat",
    "Ghat-g0-t2": "Ghat(ghost=off)",
}

# Three-series palette validated pairwise for color-vision deficiencies and
# normal vision; every color has at least 3:1 contrast against the surface.
ALGO_COLOR = {
    "Ghat-g1-t2": "#4a3aa7",
    "Ghat-g0-t2": "#2a78d6",
    "Ghat-g0-t1": "#eb6834",
}

LINE_WIDTH = 1.4
GRID_COLOR = "#e5e5e5"
RULE_COLOR = "#898781"
MUTED_TEXT = "#666666"


def window_end(window_idx):
    """Requests elapsed since the shift at the *end* of a window.

    Every row is state as of the window's last request, so a window has to
    be placed at its end, not its start. This also puts window 1999 -- the
    last one that finishes before the shift -- exactly at x=0, which is
    where the pre-shift protected fraction belongs.
    """
    return (window_idx - SHIFT_WINDOW_IDX + 1) * WINDOW_SIZE


def parse_mechanism(path):
    """by_algo[algo][window_idx] -> list over reps of miss_ratio"""
    by_algo = defaultdict(lambda: defaultdict(list))
    with open(path) as f:
        next(f)  # header
        for line in f:
            fields = line.rstrip().split(",")
            algo, window_idx = fields[0], int(fields[2])
            if not WINDOW_LO <= window_idx <= WINDOW_HI:
                continue
            by_algo[algo][window_idx].append(float(fields[5]))
    return by_algo


def summarize(by_algo, algo):
    """mean across reps, over the plotted windows.

    No spread band is drawn. A band's job here would be to say whether the
    gap between the curves is bigger than run-to-run noise, and the paired
    statistics answer that far more sharply: reps share a seed, so the same
    trace is compared against itself. Overlaying unpaired percentile bands
    would only invite the "the bands overlap, so there is no difference"
    reading, which is wrong for paired data. Report the paired numbers in
    the caption instead.

    The centre is the arithmetic mean across repetitions.
    """
    windows = sorted(by_algo[algo])
    x = np.array([window_end(w) for w in windows])
    center = np.array([np.mean(by_algo[algo][w]) for w in windows])
    return x, center


def plot_panel(ax, by_algo, ylabel):
    for algo in PLOT_ALGOS:
        if algo not in by_algo:
            continue
        x, center = summarize(by_algo, algo)
        color = ALGO_COLOR[algo]
        ax.plot(x, center, color=color, linewidth=LINE_WIDTH,
                label=DISPLAY_NAME.get(algo, algo), zorder=3)

    ax.axvline(0, color=RULE_COLOR, linewidth=0.8, linestyle="--", zorder=1)
    ax.set_ylabel(ylabel)
    ax.set_axisbelow(True)
    ax.grid(axis="both", color=GRID_COLOR, linewidth=0.6, zorder=0)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def main():
    parser = argparse.ArgumentParser(
        description="Plot the Ghat mechanism figure for one shift scenario."
    )
    parser.add_argument("scenario", choices=("disjoint", "reversal"))
    args = parser.parse_args()

    input_path = RESULT_DIR / f"{args.scenario}_ghat_variants_windows.csv"
    output_path = RESULT_DIR / f"{args.scenario}_mechanism.png"
    if not input_path.is_file():
        print(f"missing input: {input_path}", file=sys.stderr)
        return 1

    by_algo = parse_mechanism(input_path)
    missing = [a for a in PLOT_ALGOS if a not in by_algo]
    if missing:
        print(f"missing from {input_path}: {', '.join(missing)}", file=sys.stderr)
        return 1

    fig, ax = plt.subplots(1, 1, figsize=(7, 3.2))

    plot_panel(ax, by_algo, "Object miss ratio")
    ax.set_xlabel("Requests since the shift")

    ax.annotate("shift", xy=(0, 1.0), xycoords=("data", "axes fraction"),
                xytext=(4, -10), textcoords="offset points",
                fontsize=9, color=MUTED_TEXT)

    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", bbox_to_anchor=(0.98, 0.98),
               frameon=False, fontsize=9, ncol=len(labels))

    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"saved: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
