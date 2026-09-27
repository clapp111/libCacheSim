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
  output: <scenario>_mechanism.pdf
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MultipleLocator

RESULT_DIR = Path(__file__).resolve().parent.parent / "result" / "shift"

# same landmarks as plot_shift_recovery.py -- the two figures read the
# same experiment and must agree on where the shift is
SHIFT_WINDOW_IDX = 2000
WINDOW_SIZE = 100

# transient window only; see the module docstring for why
WINDOW_LO = 1995
WINDOW_HI = 2020

PLOT_ALGOS = [
    "Ghat-g0-t1",
    "Ghat-g0-t2",
    "Ghat-g1-t1",
    "Ghat-g1-t2",
]

DISPLAY_NAME = {
    "Ghat-g0-t1": "Ghost queue = off, τ=1",
    "Ghat-g0-t2": "Ghost queue = off, τ=2",
    "Ghat-g1-t1": "Ghost queue = on, τ=1",
    "Ghat-g1-t2": "Ghost queue = on, τ=2",
}

# The four configs are a 2x2, so each factor gets its own visual channel: the
# ghost queue is grey level *and* line width, tau is the dash pattern. A reader
# can then decode "every dashed curve is tau=2" without the legend, which four
# arbitrary colours would not give. The figure is greyscale on purpose, and a
# single grey step turned out not to be separable enough on its own, hence the
# width backing it up redundantly.
#
# (grey, linewidth)
GHOST_STYLE = {"g0": ("#8a8a8a", 1.0), "g1": ("#000000", 1.9)}

# Dashed lines get a small width bump because a dash lays down less ink per
# unit length and otherwise reads lighter than a solid line of the same weight,
# which would leak tau into the ghost channel.
DASH_WIDTH_BUMP = 0.2

# On/off dash lengths in points. matplotlib scales a dash tuple by the line
# width, so it is divided by the width at use -- otherwise the thick ghost-on
# line would come out with a visibly coarser dash than the thin ghost-off one.
DASH_POINTS = (3.5, 2.0)
GRID_COLOR = "#e5e5e5"

# Camera-ready figure box, in millimetres.
FIG_MM = (85.29, 38.60)
MM_PER_INCH = 25.4

# The line weights above were tuned on a 7 in wide draft that LaTeX then shrank
# to the column, and that shrink scaled the ink along with it. The figure is
# now emitted at its final size, so nothing scales it any more and the
# point-valued line geometry has to be scaled here instead -- otherwise every
# stroke lands on the page about twice as heavy as it used to.
DRAFT_WIDTH_IN = 7.0
SCALE = (FIG_MM[0] / MM_PER_INCH) / DRAFT_WIDTH_IN

# The box above is roughly a third of the height this figure used to be drawn
# at, so the type has to come down with it or the two axis labels and the
# legend do not fit. Sizes are in points and therefore absolute: they do *not*
# scale with the figure, which is the whole reason they need setting here.
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


def algo_style(algo):
    """(colour, linestyle, linewidth) for a Ghat-g<ratio>-t<threshold> label."""
    _, ghost, tau = algo.split("-")
    color, linewidth = GHOST_STYLE[ghost]
    if tau == "t1":
        return color, "solid", linewidth * SCALE
    linewidth += DASH_WIDTH_BUMP
    # Divided by the *unscaled* width so that matplotlib, which multiplies the
    # dash tuple by the scaled width it is finally drawn with, lands on
    # DASH_POINTS * SCALE -- the dash shrinks with the stroke, as it did when
    # LaTeX was doing the shrinking.
    dashes = tuple(length / linewidth for length in DASH_POINTS)
    return color, (0, dashes), linewidth * SCALE


def plot_panel(ax, by_algo, ylabel):
    for algo in PLOT_ALGOS:
        if algo not in by_algo:
            continue
        x, center = summarize(by_algo, algo)
        color, linestyle, linewidth = algo_style(algo)
        ax.plot(x, center, color=color, linestyle=linestyle,
                linewidth=linewidth,
                label=DISPLAY_NAME.get(algo, algo), zorder=3)

    ax.set_ylabel(ylabel)
    # Pinned because the auto-locator keys off the axes' physical height, and
    # at the final figure size it drops to 0.2 steps on its own.
    ax.yaxis.set_major_locator(MultipleLocator(0.1))
    ax.set_axisbelow(True)
    ax.grid(axis="both", color=GRID_COLOR, linewidth=0.6 * SCALE, zorder=0)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def main():
    parser = argparse.ArgumentParser(
        description="Plot the Ghat mechanism figure for one shift scenario."
    )
    parser.add_argument("scenario", choices=("disjoint", "reversal"))
    args = parser.parse_args()

    input_path = RESULT_DIR / f"{args.scenario}_ghat_variants_windows.csv"
    output_path = RESULT_DIR / f"{args.scenario}_mechanism.pdf"
    if not input_path.is_file():
        print(f"missing input: {input_path}", file=sys.stderr)
        return 1

    by_algo = parse_mechanism(input_path)
    missing = [a for a in PLOT_ALGOS if a not in by_algo]
    if missing:
        print(f"missing from {input_path}: {', '.join(missing)}", file=sys.stderr)
        return 1

    plt.rcParams.update(RC)
    figsize = tuple(mm / MM_PER_INCH for mm in FIG_MM)
    fig, ax = plt.subplots(1, 1, figsize=figsize)

    plot_panel(ax, by_algo, "OMR")
    ax.set_xlabel("Requests since the shift")

    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.55, 1.01),
               frameon=False, ncol=2, handlelength=1.8, columnspacing=1.0,
               handletextpad=0.5, labelspacing=0.25, borderpad=0.0)

    # rect reserves the top strip for the legend. Note there is no
    # bbox_inches="tight" on the savefig below, on purpose: that option
    # re-crops the canvas to its contents and would silently discard the
    # FIG_MM box this figure exists to hit.
    fig.tight_layout(rect=(0, 0, 1, 0.84))
    fig.savefig(output_path)
    print(f"saved: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
