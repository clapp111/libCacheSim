#!/usr/bin/env python3
"""Plot request-level GHaT hand progress for one shift repetition.

Usage:
  python3 scripts/plot_shift_hand_distance.py <disjoint|reversal>

Input:
  result/shift/<scenario>_ghat_hand_distance_rep83.csv

Output:
  result/shift/<scenario>_ghat_hand_distance_rep83.png

One panel per configuration, sharing an x axis, each showing the next hand
position in the current queue, normalized so that tail=0 and head=1. One
series per panel keeps the flat trajectory readable, which overlaying all
three did not. This is a single-repetition diagnostic figure; it is not an
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
# Trace repetition this figure is drawn from. run_shift_hand_distance.sh
# writes it into both the file names and the CSV's rep column.
REP = 83

# Panel order top to bottom: baseline, the configuration that stalls, the
# configuration that recovers.
PLOT_ALGOS = [
    "Ghat-g0-t1",
    "Ghat-g0-t2",
    "Ghat-g1-t2",
]

DISPLAY_NAME = {
    "Ghat-g0-t1": "SIEVE-equivalent",
    "Ghat-g1-t2": "Ghat(ghost=on, τ=2)",
    "Ghat-g0-t2": "Ghat(ghost=off, τ=2)",
}

# Matches plot_shift_mechanism.py so a configuration keeps one color across
# figures. With one series per panel the color is a redundant encoding.
ALGO_COLOR = {
    "Ghat-g0-t1": "#eb6834",
    "Ghat-g1-t2": "#4a3aa7",
    "Ghat-g0-t2": "#2a78d6",
}

GRID_COLOR = "#e5e5e5"
RULE_COLOR = "#898781"
MUTED_TEXT = "#666666"


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


def style_axis(ax):
    ax.axvline(0, color=RULE_COLOR, linewidth=0.8, linestyle="--", zorder=1)
    ax.set_axisbelow(True)
    ax.grid(axis="both", color=GRID_COLOR, linewidth=0.6, zorder=0)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def main():
    args = parse_args()
    input_path = RESULT_DIR / f"{args.scenario}_ghat_hand_distance_rep{REP}.csv"
    output_path = RESULT_DIR / f"{args.scenario}_ghat_hand_distance_rep{REP}.png"

    if not input_path.is_file():
        print(f"missing input: {input_path}", file=sys.stderr)
        return 1

    try:
        data = parse_data(input_path)
        validate_data(data)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    fig, axes = plt.subplots(
        len(PLOT_ALGOS),
        1,
        figsize=(7, 4),
        sharex=True,
        sharey=True,
    )

    handles = []
    for ax, algo in zip(axes, PLOT_ALGOS):
        x = np.asarray(data[algo]["x"])
        hand_position = np.asarray(data[algo]["hand_position"])
        line, = ax.step(
            x,
            hand_position,
            where="post",
            color=ALGO_COLOR[algo],
            linewidth=0.8,
            label=DISPLAY_NAME[algo],
        )
        handles.append(line)
        style_axis(ax)

    axes[0].set_ylim(-0.04, 1.04)
    axes[0].set_yticks([0, 1], labels=["Tail", "Head"])
    axes[0].annotate(
        "shift",
        xy=(0, 1.0),
        xycoords=("data", "axes fraction"),
        xytext=(4, -10),
        textcoords="offset points",
        fontsize=9,
        color=MUTED_TEXT,
    )
    fig.supylabel("Hand Position", fontsize=10)

    # Panels are in PLOT_ALGOS order, so the legend entries are too; it names
    # the series once for the whole stack rather than per panel.
    fig.legend(
        handles,
        [h.get_label() for h in handles],
        loc="upper center",
        bbox_to_anchor=(0.5, 1.0),
        frameon=False,
        fontsize=9,
        ncol=len(PLOT_ALGOS),
        handlelength=1.6,
        columnspacing=1.8,
    )

    bottom_ax = axes[-1]
    bottom_ax.set_xlim(REQUEST_LO, REQUEST_HI)
    bottom_ax.set_xticks([-5_000, 0, 10_000, 20_000, 30_000, 40_000, 50_000, 60_000])
    bottom_ax.xaxis.set_major_formatter(FuncFormatter(format_requests))
    bottom_ax.set_xlabel("Requests since the shift")

    fig.tight_layout(rect=(0, 0, 1, 0.95), h_pad=0.4)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    print(f"saved: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
