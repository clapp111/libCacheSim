#!/usr/bin/env python3

import sys
from collections import defaultdict

import matplotlib.pyplot as plt
import numpy as np

DEFAULT_INPUT = "../result/scan/scan_windows.csv"
DEFAULT_HAND_INPUT = "../result/scan/scan_hand.csv"
DEFAULT_OUTPUT = "../result/scan/scan_retention.png"

CACHE_SIZE = 100        # objects; must match run_scan_windows.sh TIMELINE_CACHE

# The figure draws the two sweeping-hand policies, which are the only ones that
# have a hand position to report. The per-scan-length numbers for the whole
# field go in the table instead; this order drives the stderr summary those
# numbers come from. Fixed, not sorted by value.
ALGO_ORDER = ["LIRS", "Sieve", "ARC", "S3FIFO", "Ghat", "LRU"]

# Paper-facing display names are applied to labels only; CSV keys keep the
# result files' spelling.
DISPLAY_NAME = {
    "Sieve": r"Resident-only, $\tau=1$",
    "Ghat": r"Ghost-assisted, $\tau=2$",
}

# Taken from plot_shift_hand_distance.py's ALGO_COLOR so a configuration keeps
# one colour across every hand figure: Ghat is Ghat-g1-t2 there, and the Sieve
# rows here are produced by Ghat-g0-t1. Validated as a pair (worst adjacent
# normal-vision dE 37.6, both above 3:1 against the surface).
COLOR = {
    "Ghat": "#4a3aa7",
    "Sieve": "#eb6834",
}

# Ghat crowds the head end of the axis where Sieve also sits, so the two are
# separated by shape as well as hue and Sieve is drawn last.
MARKER = {"Ghat": "o", "Sieve": "^"}

GRID_COLOR = "#e5e5e5"
INK = "#222222"


def parse_retention(path):
    """retention[algo][scan_len] = [n_target_resident per rep, ...]

    scan_windows.csv carries every window of every run, but n_target_resident
    is filled on one window per run and is -1 on all the others. Skipping those
    rows before splitting keeps this from parsing tens of millions of fields.
    """
    retention = defaultdict(lambda: defaultdict(list))
    with open(path) as f:
        next(f)  # header
        for line in f:
            line = line.rstrip("\n")
            if line.endswith(",-1"):
                continue
            fields = line.split(",")
            algo, scan_len, resident = fields[0], int(fields[1]), int(fields[10])
            retention[algo][scan_len].append(resident)
    return retention


def parse_hand(path):
    """hand[algo] = [(hand_distance, n_target_resident) per rep, ...]"""
    hand = defaultdict(list)
    with open(path) as f:
        next(f)  # header
        for line in f:
            algo, _rep, distance, resident = line.rstrip("\n").split(",")
            hand[algo].append((int(distance), int(resident)))
    return hand


def plot_mechanism_panel(ax, hand):
    """Retention against where the hand sat when the scan began.

    Hand position is normalized over the C object positions: 0 at the tail
    and 1 at the head. Retention remains a fraction of all C cache slots.
    Because the hand's eviction candidate is exposed to the scan, the exact
    prediction is y = ((C - 1) / C) x rather than the unit diagonal.
    """
    prediction_scale = (CACHE_SIZE - 1) / CACHE_SIZE
    ax.plot([0, 1], [0, prediction_scale], color=INK, linewidth=1.0,
            linestyle=(0, (4, 3)), zorder=2)
    # Placed low on the line: the runs all sit in its upper half, so this is
    # the only stretch of it that is clear of points.
    ax.annotate("retained = hand-position prediction",
                (0.28, 0.28 * prediction_scale),
                xytext=(8, -11), textcoords="offset points",
                fontsize=7.5, color=INK, ha="left")

    # Sieve last so its tight cluster at the head end stays visible through
    # Ghat's points, which cover the same stretch of the axis.
    draw_order = ["Ghat", "Sieve"]
    for z, algo in enumerate(a for a in draw_order if a in hand):
        xs = [1.0 - d / (CACHE_SIZE - 1) for d, _ in hand[algo]]
        ys = [r / CACHE_SIZE for _, r in hand[algo]]
        # No outline: the alpha is low enough that a crowded stretch of the
        # axis reads as a darker patch, which is the point -- Sieve's runs all
        # pile up at the head end while Ghat's spread down the line.
        ax.scatter(xs, ys, s=18, color=COLOR[algo], alpha=0.5,
                   marker=MARKER[algo], edgecolors="none", zorder=3 + z,
                   label=DISPLAY_NAME.get(algo, algo))

    ax.set_xlim(-0.03, 1.03)
    ax.set_ylim(-0.03, 1.03)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1])
    ax.set_xticklabels(["0\ntail", "0.25", "0.5", "0.75", "1\nhead"])
    ax.set_xlabel("hand position at scan start")
    ax.set_ylabel("hot objects retained at scan end (fraction of cache)")
    ax.set_axisbelow(True)
    ax.grid(color=GRID_COLOR, linewidth=0.6, zorder=-1)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.legend(frameon=False, fontsize=7.5, loc="upper left")


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INPUT
    dst = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUTPUT
    hand_src = DEFAULT_HAND_INPUT

    retention = parse_retention(src)
    algos = [a for a in ALGO_ORDER if a in retention]
    missing = [a for a in ALGO_ORDER if a not in retention]
    if missing:
        print(f"WARN: absent from {src}: {', '.join(missing)}", file=sys.stderr)

    for algo in algos:
        for scan_len in sorted(retention[algo]):
            vals = retention[algo][scan_len]
            print(f"{algo} L={scan_len}: n={len(vals)}, "
                  f"mean={np.mean(vals):.1f}, median={np.median(vals):.1f}, "
                  f"p10={np.percentile(vals, 10):.0f}, "
                  f"p90={np.percentile(vals, 90):.0f}", file=sys.stderr)

    hand = parse_hand(hand_src)
    for algo, pts in hand.items():
        resid = [r - (CACHE_SIZE - d - 1) for d, r in pts]
        within = sum(1 for x in resid if abs(x) <= 3)
        print(f"{algo} hand: n={len(pts)}, "
              f"|retained - (C - distance - 1)| <= 3 "
              f"in {within}/{len(pts)}",
              file=sys.stderr)

    fig, ax = plt.subplots(figsize=(5.0, 3.9))
    plot_mechanism_panel(ax, hand)
    fig.tight_layout()
    fig.savefig(dst, dpi=200, bbox_inches="tight")
    print(f"wrote {dst}", file=sys.stderr)


if __name__ == "__main__":
    main()
