#!/usr/bin/env python3

import sys
from collections import defaultdict

import matplotlib.pyplot as plt
import numpy as np

DEFAULT_INPUT = "../result/scan/scan_windows.csv"
DEFAULT_HAND_INPUT = "../result/scan/scan_ghat_variants_windows.csv"
DEFAULT_OUTPUT = "../result/scan/scan_retention.pdf"

CACHE_SIZE = 100        # objects; must match run_scan_windows.sh TIMELINE_CACHE

# Landmarks for the mechanism panel, which reads one scan length: the hand
# position going into the scan, and the hot objects left when it ends. Must
# match run_scan_ghat_variants.sh. scan_hand.csv carried the same two numbers
# for two configurations; the variants CSV has all four, and was checked to
# agree with it on both, for every rep.
HAND_SCAN_LEN = 800
PRE_WINDOW = 200_000 // 25 - 1
END_WINDOW = (200_000 + HAND_SCAN_LEN) // 25 - 1

# The figure draws the two sweeping-hand policies, which are the only ones that
# have a hand position to report. The per-scan-length numbers for the whole
# field go in the table instead; this order drives the stderr summary those
# numbers come from. Fixed, not sorted by value.
ALGO_ORDER = ["LIRS", "Sieve", "ARC", "S3FIFO", "Ghat", "LRU"]

# The panel's four series: the 2x2 of ghost queue x protect threshold. Order is
# also draw order, so the tight cluster at the head end goes on top.
HAND_CONFIGS = ["Ghat-g1-t1", "Ghat-g1-t2", "Ghat-g0-t2", "Ghat-g0-t1"]

DISPLAY_NAME = {
    "Ghat-g0-t1": r"Ghost = off, $\tau=1$",
    "Ghat-g0-t2": r"Ghost = off, $\tau=2$",
    "Ghat-g1-t1": r"Ghost = on, $\tau=1$",
    "Ghat-g1-t2": r"Ghost = on, $\tau=2$",
}

# Greyscale, matching plot_shift_hand_distance.py's GHOST_STYLE so a
# configuration keeps one ink across every hand figure: the ghost queue is the
# grey level, and here the threshold is the marker instead of the dash pattern.
# Filled markers are the ghost-on pair, hollow the ghost-off pair, which backs
# up the grey level the same way line width does in those figures.
COLOR = {
    "Ghat-g0-t1": "#888888",
    "Ghat-g0-t2": "#888888",
    "Ghat-g1-t1": "#111111",
    "Ghat-g1-t2": "#111111",
}

MARKER = {
    "Ghat-g0-t1": "^",
    "Ghat-g0-t2": "o",
    "Ghat-g1-t1": "^",
    "Ghat-g1-t2": "o",
}

FILLED = {"Ghat-g1-t1", "Ghat-g1-t2"}

# Legend order is the 2x2 read row by row, which is not the draw order above.
LEGEND_ORDER = ["Ghat-g0-t1", "Ghat-g0-t2", "Ghat-g1-t1", "Ghat-g1-t2"]

GRID_COLOR = "#e5e5e5"

# The prediction is a reference, not a measurement, so it is kept lighter than
# either marker ink -- a dotted line at this grey cannot be read as a series.
PREDICTION_COLOR = "#c4c4c4"

# Camera-ready figure box, in millimetres.
FIG_MM = (85.29, 71.76)
MM_PER_INCH = 25.4

# The marker and line sizes above were tuned on a 5 in wide draft that LaTeX
# then shrank to the column, and that shrink scaled the ink with it. The figure
# is now emitted at its final size, so nothing scales it any more and the
# point-valued geometry has to be scaled here instead. Note the draft width is
# 5 in here, not the 7 in the two shift figures were drawn at, so this factor
# is not the same as theirs.
DRAFT_WIDTH_IN = 5.0
SCALE = (FIG_MM[0] / MM_PER_INCH) / DRAFT_WIDTH_IN

# Same type sizes as plot_shift_mechanism.py and plot_shift_hand_distance.py,
# so all three figures set text identically. Point sizes are absolute and do
# not scale with the figure.
RC = {
    "font.size": 7,
    "axes.labelsize": 7,
    "xtick.labelsize": 6,
    "ytick.labelsize": 6,
    "legend.fontsize": 6,
    # Type 3 fonts are rejected by several publishers' PDF checks; 42 is
    # TrueType.
    "pdf.fonttype": 42,
}


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
    """hand[config] = [(hand_distance, n_target_resident) per rep, ...]

    Two rows per run carry the pair: the hand sits at PRE_WINDOW, the surviving
    hot objects are counted at END_WINDOW, and they are joined on the rep.
    """
    distance, resident = defaultdict(dict), defaultdict(dict)
    with open(path) as f:
        next(f)  # header
        for line in f:
            fields = line.rstrip("\n").split(",")
            if int(fields[1]) != HAND_SCAN_LEN:
                continue
            config = fields[0]
            # The CSV also carries hand-less policies (FIFO), whose
            # hand_distance column is empty; only the sweeping-hand configs
            # this panel draws have a position to read.
            if config not in HAND_CONFIGS:
                continue
            rep, window = int(fields[2]), int(fields[3])
            if window == PRE_WINDOW:
                distance[config][rep] = int(fields[14])
            elif window == END_WINDOW:
                resident[config][rep] = int(fields[10])

    hand = defaultdict(list)
    for config, by_rep in distance.items():
        for rep, d in sorted(by_rep.items()):
            hand[config].append((d, resident[config][rep]))
    return hand


def plot_mechanism_panel(ax, hand):
    """Retention against where the hand sat when the scan began.

    Hand position is normalized over the C object positions: 0 at the tail
    and 1 at the head. Retention remains a fraction of all C cache slots.
    Because the hand's eviction candidate is exposed to the scan, the exact
    prediction is y = ((C - 1) / C) x rather than the unit diagonal.
    """
    prediction_scale = (CACHE_SIZE - 1) / CACHE_SIZE
    # The dash tuple is in units of the line width, so scaling the width alone
    # shrinks the dot spacing along with it.
    ax.plot([0, 1], [0, prediction_scale], color=PREDICTION_COLOR,
            linewidth=1.0 * SCALE, linestyle=(0, (1, 2.5)), zorder=2)

    # Ghost-off last: those runs pile up at the head end, where the ghost-on
    # ones also reach, and the tight cluster has to stay visible through them.
    handles = {}
    for z, config in enumerate(c for c in HAND_CONFIGS if c in hand):
        xs = [1.0 - d / (CACHE_SIZE - 1) for d, _ in hand[config]]
        ys = [r / CACHE_SIZE for _, r in hand[config]]
        # The alpha is low enough that a crowded stretch of the axis reads as a
        # darker patch, which is the point -- the ghost-off runs pile up at the
        # head end while the ghost-on ones spread down the line.
        # One thin stroke for every marker, so the only difference between a
        # ghost-on and a ghost-off marker of the same shape is the fill. A
        # hollow marker still reads lighter than a filled one, which is why it
        # gets the higher alpha.
        fill = config in FILLED
        handles[config] = ax.scatter(
            # s is an area in points squared, so the linear shrink enters
            # squared; the edge stroke is a width and takes it once.
            xs, ys, s=18 * SCALE ** 2, marker=MARKER[config],
            alpha=0.5 if fill else 0.8,
            facecolors=COLOR[config] if fill else "none",
            edgecolors=COLOR[config], linewidths=0.6 * SCALE,
            zorder=3 + z, label=DISPLAY_NAME.get(config, config))

    ax.set_xlim(-0.03, 1.03)
    ax.set_ylim(-0.03, 1.03)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1])
    # Tail/Head capitalised to match the same two landmarks in
    # plot_shift_hand_distance.py, which labels its y axis with them.
    ax.set_xticklabels(["0\nTail", "0.25", "0.5", "0.75", "1\nHead"])
    ax.set_xlabel("Hand position at scan start")
    # Wrapped, not shortened: on one line this label is longer than the axis
    # is tall at the final figure size and overruns the top of the canvas.
    ax.set_ylabel("Hot objects retained at scan end\n(fraction of cache)")
    ax.set_axisbelow(True)
    ax.grid(color=GRID_COLOR, linewidth=0.6 * SCALE, zorder=-1)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ordered = [handles[c] for c in LEGEND_ORDER if c in handles]
    ax.legend(ordered, [h.get_label() for h in ordered],
              frameon=False, loc="upper left")


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

    plt.rcParams.update(RC)
    fig, ax = plt.subplots(figsize=tuple(mm / MM_PER_INCH for mm in FIG_MM))
    plot_mechanism_panel(ax, hand)
    # No bbox_inches="tight" on the savefig below, on purpose: that option
    # re-crops the canvas to its contents and would silently discard the
    # FIG_MM box this figure exists to hit.
    fig.tight_layout()
    fig.savefig(dst)
    print(f"wrote {dst}", file=sys.stderr)


if __name__ == "__main__":
    main()
