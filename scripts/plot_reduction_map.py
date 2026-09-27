#!/usr/bin/env python3
"""usage: python3 scripts/plot_reduction_map.py [object|byte]"""

import os
import sys
from collections import defaultdict

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

from result_utils import display_name, parse_result_file, resolve_family_files


CORPORA = [
    "Twitter",
    "Meta KV",
    "Tencent Photo",
    "Wikimedia",
    "Meta CDN",
    "Alibaba",
    "MSR",
    "FIU",
    "CloudPhysics",
]

FAMILY_GLOBS = {
    "Twitter": ["result/twitter/*_result.txt"],
    "Meta KV": ["result/meta-key/*_result.txt"],
    "Tencent Photo": ["result/tencent-photo/*_result.txt"],
    "Wikimedia": ["result/wikimedia/*_result.txt"],
    "Meta CDN": ["result/meta-cdn/*_result.txt"],
    "Alibaba": ["result/alibaba/*_result.txt"],
    "MSR": ["result/msr/*_result.txt"],
    "FIU": ["result/fiu/*_result.txt"],
    "CloudPhysics": ["result/cloudphysics/*_result.txt"],
}

ALGO_VARIANT = {
    "Ghat": ("Ghat-2-1.0000",),
    "LRB": ("LRB-OMR",),
    "S3FIFO": ("S3FIFO-0.1000-2",),
    "WTinyLFU": ("WTinyLFU-w0.01-SLRU",),
}

BASELINE_ALGO = "FIFO"
ALGOS = [
    "Ghat",
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
]
DISPLAY_NAME = {"Sieve": "SIEVE", "Cacheus": "CACHEUS", "Clock": "CLOCK", "Ghat": "GHAT", "S3FIFO": "S3-FIFO", "WTinyLFU": "W-TinyLFU"}

SIZES = ["small", "large"]
SIZE_TITLE = {"small": "Small cache size", "large": "Large cache size"}
METRIC_LABEL = {"object": "OMR", "byte": "BMR"}

CMAP = LinearSegmentedColormap.from_list(
    "reduction", ["#b3480b", "#d55e00", "#f2c9ae", "#f2f2f2", "#a8cfe5", "#0072b2", "#00456b"]
)
MISSING_COLOR = "#e0e0e0"

# Camera-ready figure box, in millimetres. This is the two-column figure, so
# it is far wider than the single-column shift and scan figures.
FIG_MM = (177.53, 94.05)
MM_PER_INCH = 25.4

# The cell-separator rule below was tuned on a 12.6 in wide draft that LaTeX
# then shrank to the text block, and that shrink scaled the ink with it. The
# figure is now emitted at its final size, so nothing scales it any more and
# the point-valued geometry has to be scaled here instead.
DRAFT_WIDTH_IN = 12.6
SCALE = (FIG_MM[0] / MM_PER_INCH) / DRAFT_WIDTH_IN

# Same type sizes as the shift and scan figures. Point sizes are absolute and
# are deliberately *not* run through SCALE -- text is set at the size it
# should print at, only the geometry above follows the shrink.
RC = {
    "font.size": 7,
    "axes.labelsize": 7,
    "axes.titlesize": 7,
    "xtick.labelsize": 6,
    "ytick.labelsize": 6,
    # Type 3 fonts are rejected by several publishers' PDF checks; 42 is
    # TrueType.
    "pdf.fonttype": 42,
}

# The 198 in-cell numbers are annotations rather than axis furniture, so no rc
# key covers them. They sit at the tick sizes: a cell is about 8 mm wide and
# "+12.3" at 6 pt is about 6 mm, which clears it.
CELL_FONTSIZE = 6


def load(metric):
    metric_idx = 4 if metric == "byte" else 3
    raw = defaultdict(list)
    for corpus in CORPORA:
        paths = resolve_family_files(corpus, FAMILY_GLOBS)
        if not paths:
            sys.exit(f"no result files found for: {corpus}")
        for path in paths:
            for row in parse_result_file(path, ALGO_VARIANT):
                trace, size, algo = row[0], row[1], row[2]
                if size not in SIZES:
                    continue
                raw[(corpus, size, trace, algo)].append(row[metric_idx])

    miss_ratios = defaultdict(dict)
    for (corpus, size, trace, algo), values in raw.items():
        miss_ratios[(corpus, size)].setdefault(trace, {})[algo] = float(np.mean(values))

    reductions = {}
    baseline_counts = {}
    for corpus in CORPORA:
        for size in SIZES:
            per_algo = defaultdict(list)
            n_baseline = 0
            for algo_values in miss_ratios[(corpus, size)].values():
                baseline = algo_values.get(BASELINE_ALGO)
                if not baseline:
                    continue
                n_baseline += 1
                for algo in ALGOS:
                    if algo in algo_values:
                        per_algo[algo].append(
                            (baseline - algo_values[algo]) / baseline * 100.0
                        )
            reductions[(corpus, size)] = per_algo
            baseline_counts[(corpus, size)] = n_baseline
    return reductions, baseline_counts


def build_matrix(reductions, size):
    matrix = np.full((len(ALGOS), len(CORPORA)), np.nan)
    counts = np.zeros((len(ALGOS), len(CORPORA)), dtype=int)
    for i, algo in enumerate(ALGOS):
        for j, corpus in enumerate(CORPORA):
            values = reductions[(corpus, size)].get(algo, [])
            if values:
                matrix[i, j] = float(np.mean(values))
                counts[i, j] = len(values)
    return matrix, counts


def plot_panel(ax, matrix, counts, baseline_counts, size, vmax):
    ax.set_facecolor(MISSING_COLOR)
    masked = np.ma.masked_invalid(matrix)
    im = ax.imshow(masked, cmap=CMAP, vmin=-vmax, vmax=vmax, aspect="auto")

    for i in range(len(ALGOS)):
        for j in range(len(CORPORA)):
            n_expected = baseline_counts[(CORPORA[j], size)]
            if np.isnan(matrix[i, j]):
                ax.text(j, i, "—", ha="center", va="center",
                        fontsize=CELL_FONTSIZE, color="#666666")
                continue
            shade = abs(matrix[i, j]) / vmax if vmax else 0.0
            color = "white" if shade > 0.62 else "#1a1a1a"
            ax.text(
                j,
                i,
                f"{matrix[i, j]:+.1f}",
                ha="center",
                va="center",
                fontsize=CELL_FONTSIZE,
                color=color,
            )
            if counts[i, j] < n_expected:
                ax.add_patch(
                    plt.Rectangle(
                        (j - 0.5, i - 0.5),
                        1,
                        1,
                        fill=False,
                        hatch="///",
                        edgecolor="#555555",
                        linewidth=0.0,
                    )
                )

    ax.set_xticks(np.arange(len(CORPORA)))
    ax.set_xticklabels(CORPORA, rotation=45, ha="right")
    ax.set_xticks(np.arange(len(CORPORA) + 1) - 0.5, minor=True)
    ax.set_yticks(np.arange(len(ALGOS) + 1) - 0.5, minor=True)
    ax.grid(which="minor", color="white", linewidth=1.2 * SCALE)
    ax.tick_params(which="both", length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    return im


def plot(matrices, baseline_counts, metric, output_path):
    vmax = max(
        (np.nanmax(np.abs(matrix)) for matrix, _ in matrices.values()), default=1.0
    )
    vmax = float(np.ceil(vmax / 5.0) * 5.0)

    plt.rcParams.update(RC)
    # constrained rather than tight: tight_layout does not account for a
    # colorbar attached to several axes at once, and the figure has to stay
    # exactly FIG_MM, which rules out letting savefig re-crop it.
    fig, axes = plt.subplots(
        1, 2, figsize=tuple(mm / MM_PER_INCH for mm in FIG_MM),
        sharey=True, layout="constrained",
    )
    for ax, size, tag in zip(axes, SIZES, "ab"):
        matrix, counts = matrices[size]
        im = plot_panel(ax, matrix, counts, baseline_counts, size, vmax)
        # The panel caption is the x label, not a negatively offset title: the
        # layout engine reserves room for a label but not for a title pushed
        # outside its axes, and without bbox_inches="tight" nothing grows the
        # canvas to rescue one that overflows.
        ax.set_xlabel(f"({tag}) {SIZE_TITLE[size]}")

    axes[0].set_yticks(np.arange(len(ALGOS)))
    axes[0].set_yticklabels([display_name(algo, DISPLAY_NAME) for algo in ALGOS])

    cbar = fig.colorbar(im, ax=axes, fraction=0.022, pad=0.02)
    cbar.set_label(f"{METRIC_LABEL[metric]} reduction from {BASELINE_ALGO} (%)")
    cbar.outline.set_visible(False)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    # No bbox_inches="tight": that option re-crops the canvas to its contents
    # and would silently discard the FIG_MM box this figure exists to hit.
    fig.savefig(output_path)
    plt.close(fig)
    print(f"wrote {output_path}")


def report_coverage(matrices, baseline_counts):
    for size in SIZES:
        matrix, counts = matrices[size]
        for i, algo in enumerate(ALGOS):
            for j, corpus in enumerate(CORPORA):
                n_expected = baseline_counts[(corpus, size)]
                if counts[i, j] == 0:
                    print(
                        f"warning: [{size}] {corpus} {algo}: no data", file=sys.stderr
                    )
                elif counts[i, j] != n_expected:
                    print(
                        f"warning: [{size}] {corpus} {algo}: "
                        f"n={counts[i, j]}, {BASELINE_ALGO} n={n_expected}",
                        file=sys.stderr,
                    )


def main():
    if len(sys.argv) > 2 or (len(sys.argv) == 2 and sys.argv[1] not in METRIC_LABEL):
        sys.exit(f"usage: {sys.argv[0]} [object|byte]")
    metric = sys.argv[1] if len(sys.argv) == 2 else "object"

    reductions, baseline_counts = load(metric)
    matrices = {size: build_matrix(reductions, size) for size in SIZES}
    report_coverage(matrices, baseline_counts)

    output_path = os.path.normpath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "result",
            "real",
            f"overall_reduction_map_{metric}.pdf",
        )
    )
    plot(matrices, baseline_counts, metric, output_path)


if __name__ == "__main__":
    main()
