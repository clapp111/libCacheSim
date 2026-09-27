#!/usr/bin/env python3
"""Plot request-level GHaT hand progress for one shift repetition.

Usage:
  python3 scripts/plot_shift_hand_distance.py <disjoint|reversal>

Input:
  result/shift/<scenario>_ghat_hand_distance_rep83.csv

Output:
  result/shift/<scenario>_ghat_hand_distance_rep83.pdf

One panel per configuration, sharing an x axis, each showing the next hand
position in the current queue, normalized so that tail=0 and head=1. One
series per panel keeps the flat trajectory readable, which overlaying all
four did not. This is a single-repetition diagnostic figure; it is not an
aggregate over repetitions.
"""

import argparse
import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter


RESULT_DIR = Path(__file__).resolve().parent.parent / "result" / "shift"

LAST_PRE_SHIFT_IDX = 199_999
REQUEST_LO = -5_000
REQUEST_HI = 60_000
REP = 83

# ghost off/on x tau 1/2; this is also the panel order, grouped by ghost so
# it matches the grey levels below
PLOT_ALGOS = [
    "Ghat-g0-t1",
    "Ghat-g0-t2",
    "Ghat-g1-t1",
    "Ghat-g1-t2",
]

# "Ghost" rather than "Ghost queue" so the legend names the factor exactly as
# the tables' column head does, and so the two factors read as a parallel pair
# next to tau. The tau term is mathtext, matching the body's $\tau=1$.
DISPLAY_NAME = {
    "Ghat-g0-t1": r"Ghost = off, $\tau=1$",
    "Ghat-g0-t2": r"Ghost = off, $\tau=2$",
    "Ghat-g1-t1": r"Ghost = on, $\tau=1$",
    "Ghat-g1-t2": r"Ghost = on, $\tau=2$",
}

# Same encoding as plot_shift_mechanism.py -- the two figures show the same
# four configurations and a reader should be able to carry the mapping across:
# the ghost queue is grey level plus line width, tau is the dash pattern. See
# that script for the reasoning behind each constant. The widths are lower and
# the dash longer than there because these panels are short and the traces are
# dense step functions, which a heavy line or a tight dash smears.
GHOST_STYLE = {"g0": ("#8a8a8a", 0.8), "g1": ("#000000", 1.3)}
DASH_WIDTH_BUMP = 0.2
DASH_POINTS = (4.0, 2.0)

GRID_COLOR = "#e5e5e5"

# Camera-ready figure box, in millimetres.
FIG_MM = (85.29, 49.15)
MM_PER_INCH = 25.4

# The line weights above were tuned on a 7 in wide draft that LaTeX then shrank
# to the column, and that shrink scaled the ink along with it. The figure is
# now emitted at its final size, so nothing scales it any more and the
# point-valued line geometry has to be scaled here instead -- otherwise every
# stroke lands on the page about twice as heavy as it used to.
DRAFT_WIDTH_IN = 7.0
SCALE = (FIG_MM[0] / MM_PER_INCH) / DRAFT_WIDTH_IN

# Matches plot_shift_mechanism.py, so the two shift figures set type at the
# same size. Point sizes are absolute and do not scale with the figure.
RC = {
    "font.size": 7,
    "axes.labelsize": 7,
    # supylabel reads figure.labelsize, not axes.labelsize, and that defaults
    # to "large" -- it does not follow the shrink unless it is named here.
    "figure.labelsize": 7,
    "xtick.labelsize": 6,
    "ytick.labelsize": 6,
    "legend.fontsize": 6,
    # Type 3 fonts are rejected by several publishers' PDF checks; 42 is
    # TrueType.
    "pdf.fonttype": 42,
}


def parse_args():
    parser = argparse.ArgumentParser(
        description=f"Plot request-level GHaT hand progress for repetition {REP}."
    )
    parser.add_argument("scenario", choices=("disjoint", "reversal"))
    return parser.parse_args()


def format_requests(value, _position=None):
    if value == 0:
        return "0"
    if abs(value) < 1_000:
        return f"{value:g}"
    return f"{value / 1_000:g}K"


def parse_data(path):
    data = {
        algo: {
            "x": [],
            "hand_position": [],
            "hand_wrap": [],
        }
        for algo in PLOT_ALGOS
    }

    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        required = {
            "config",
            "rep",
            "window_idx",
            "n_obj",
            "n_hand_wrap",
            "hand_distance",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"{path} is missing required columns: {sorted(missing)}"
            )

        for row in reader:
            algo = row["config"]
            if algo not in data:
                continue

            rep = int(row["rep"])
            if rep != REP:
                raise ValueError(f"unexpected repetition: {rep}")

            window_idx = int(row["window_idx"])
            x = window_idx - LAST_PRE_SHIFT_IDX
            if x < REQUEST_LO or x > REQUEST_HI:
                continue

            n_obj = int(row["n_obj"])
            hand_distance = int(row["hand_distance"])
            if n_obj <= 1 or not 0 <= hand_distance < n_obj:
                raise ValueError(
                    f"invalid hand state: algo={algo}, x={x}, "
                    f"n_obj={n_obj}, distance={hand_distance}"
                )

            hand_position = 1.0 - hand_distance / (n_obj - 1)
            data[algo]["x"].append(x)
            data[algo]["hand_position"].append(hand_position)
            data[algo]["hand_wrap"].append(int(row["n_hand_wrap"]))

    return data


def validate_data(data):
    expected_x = np.arange(REQUEST_LO, REQUEST_HI + 1)

    for algo in PLOT_ALGOS:
        x = np.asarray(data[algo]["x"])
        if not np.array_equal(x, expected_x):
            raise ValueError(
                f"{algo}: expected every request from "
                f"{REQUEST_LO} through {REQUEST_HI}"
            )


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


def style_axis(ax):
    ax.set_axisbelow(True)
    ax.grid(axis="both", color=GRID_COLOR, linewidth=0.6 * SCALE, zorder=0)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def main():
    args = parse_args()
    input_path = RESULT_DIR / f"{args.scenario}_ghat_hand_distance_rep{REP}.csv"
    output_path = RESULT_DIR / f"{args.scenario}_ghat_hand_distance_rep{REP}.pdf"

    if not input_path.is_file():
        print(f"missing input: {input_path}", file=sys.stderr)
        return 1

    try:
        data = parse_data(input_path)
        validate_data(data)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    plt.rcParams.update(RC)
    fig, axes = plt.subplots(
        len(PLOT_ALGOS),
        1,
        figsize=tuple(mm / MM_PER_INCH for mm in FIG_MM),
        sharex=True,
        sharey=True,
    )

    handles = []
    for ax, algo in zip(axes, PLOT_ALGOS):
        x = np.asarray(data[algo]["x"])
        hand_position = np.asarray(data[algo]["hand_position"])
        color, linestyle, linewidth = algo_style(algo)
        line, = ax.step(
            x,
            hand_position,
            where="post",
            color=color,
            linestyle=linestyle,
            linewidth=linewidth,
            label=DISPLAY_NAME[algo],
        )
        handles.append(line)
        style_axis(ax)

    axes[0].set_ylim(-0.04, 1.04)
    axes[0].set_yticks([0, 1], labels=["Tail", "Head"])
    fig.supylabel("Hand position")
    # Panels are in PLOT_ALGOS order, so the legend entries are too; it names
    # the series once for the whole stack rather than per panel. Four entries
    # on one row overflow the column width, so two columns of two.
    fig.legend(
        handles,
        [h.get_label() for h in handles],
        loc="upper center",
        bbox_to_anchor=(0.55, 1.01),
        frameon=False,
        ncol=2,
        handlelength=1.8,
        columnspacing=1.0,
        handletextpad=0.5,
        labelspacing=0.25,
        borderpad=0.0,
    )

    bottom_ax = axes[-1]
    bottom_ax.set_xlim(REQUEST_LO, REQUEST_HI)
    bottom_ax.set_xticks([-5_000, 0, 10_000, 20_000, 30_000, 40_000, 50_000, 60_000])
    bottom_ax.xaxis.set_major_formatter(FuncFormatter(format_requests))
    bottom_ax.set_xlabel("Requests since the shift")

    # rect reserves the top strip for the legend. Note there is no
    # bbox_inches="tight" on the savefig below, on purpose: that option
    # re-crops the canvas to its contents and would silently discard the
    # FIG_MM box this figure exists to hit.
    fig.tight_layout(rect=(0, 0, 1, 0.90), h_pad=0.4)
    fig.savefig(output_path)
    plt.close(fig)

    print(f"saved: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
