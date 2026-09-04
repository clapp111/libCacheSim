#!/usr/bin/env python3
"""Block-workload miss ratio evidence: GHAT vs SIEVE (paired) and GHAT's
position in the baseline field.

Reads the miss-ratio sweep output already in result/{msr,cloudphysics,fiu,
meta-block,alibaba}/*_result.txt and prints two markdown tables:

  Table A  paired GHAT vs SIEVE, per family x cache size
  Table B  field ranking, family-balanced, per cache size

usage: python3 scripts/block_miss_ratio_table.py [omr|bmr]
"""

import glob
import re
import sys

import pandas as pd

FAMILIES = ["msr", "cloudphysics", "fiu", "meta-block", "alibaba"]

# Canonical GHAT is protect threshold 2, ghost ratio 1.0. "Ghat-1.0000" is the
# pre-rename name for that same configuration: on all 14 msr trace x size cells
# where both names were run the miss ratios are bit-identical, while tau=1/3/4
# match on only 1 of 14.
GHAT_NAMES = {"Ghat-1.0000", "Ghat-2-1.0000"}

# Parameter sweeps and ablations are not baselines; they stay out of the field.
ABLATION = re.compile(r"^(Ghat-0\.5000|Ghat-[1345]-|SieveGhost)")

DISPLAY = {"Sieve": "SIEVE", "S3FIFO-0.1000-2": "S3FIFO",
           "WTinyLFU-w0.01-SLRU": "WTinyLFU", "Cacheus": "CACHEUS",
           "LRB-BMR": "LRB"}

# Present in all five families. Clock (missing in fiu, alibaba) and LRB (fiu
# only) are excluded so every family is scored against an identical field.
FIELD = ["GHAT", "SIEVE", "FIFO", "LRU", "S3FIFO", "ARC", "LIRS", "LHD",
         "WTinyLFU", "CACHEUS"]

LINE = re.compile(
    r"^(\S+)\s+size=(\S+)\s+(.+?)\s+cache size\s+(\S+),\s+(\d+) req, "
    r"miss ratio ([\d.]+), byte miss ratio ([\d.]+)")


def load():
    recs = []
    for fam in FAMILIES:
        for path in glob.glob(f"result/{fam}/*_result.txt"):
            for line in open(path, errors="ignore"):
                m = LINE.match(line.strip())
                if not m or ABLATION.match(m.group(3)):
                    continue
                algo = m.group(3)
                algo = "GHAT" if algo in GHAT_NAMES else DISPLAY.get(algo, algo)
                recs.append((fam, m.group(1), m.group(2), algo,
                             float(m.group(6)), float(m.group(7))))
    d = pd.DataFrame(recs, columns=["family", "trace", "size", "algo", "omr", "bmr"])
    # a cell can carry both GHAT names; they are the same configuration
    return d.groupby(["family", "trace", "size", "algo"], as_index=False).mean()


def matrix(d, metric):
    """trace x size cells where every field policy ran, as a policy matrix."""
    d = d[d.algo.isin(FIELD)]
    n = d.groupby(["family", "trace", "size"])["algo"].nunique()
    keep = n[n == len(FIELD)].index
    d = d.set_index(["family", "trace", "size"]).loc[keep].reset_index()
    return d.pivot_table(index=["family", "trace", "size"], columns="algo", values=metric)


def table_a(p, metric):
    print(f"\n### Table A — GHAT vs SIEVE, paired per trace ({metric})\n")
    print("| cache | family | n | median rel. reduction | mean | wins | sign |")
    print("|---|---|---|---|---|---|---|")
    for size in ["small", "large"]:
        q = p.xs(size, level="size")
        rel = (q["SIEVE"] - q["GHAT"]) / q["SIEVE"] * 100.0
        for fam, g in rel.groupby(level="family"):
            w = int((g > 0).sum())
            print(f"| {size} | {fam} | {len(g)} | {g.median():+.2f}% | "
                  f"{g.mean():+.2f}% | {w}/{len(g)} | "
                  f"{'+' if g.median() > 0 else '-'} |")
        fam_med = rel.groupby(level="family").median()
        w = int((rel > 0).sum())
        print(f"| {size} | **family-balanced** | 5 fam | "
              f"**{fam_med.median():+.2f}%** | — | {w}/{len(rel)} pooled | |")


def table_b(p, metric):
    print(f"\n### Table B — field position, mean rank of 10 ({metric})\n")
    print("| policy | small | large |")
    print("|---|---|---|")
    cols = {}
    for size in ["small", "large"]:
        q = p.xs(size, level="size")
        # rank 1 = lowest miss ratio; each family weighted equally
        cols[size] = q.rank(axis=1).groupby(level="family").mean().mean()
    t = pd.DataFrame(cols).sort_values("small")
    for algo, row in t.iterrows():
        name = f"**{algo}**" if algo == "GHAT" else algo
        print(f"| {name} | {row['small']:.2f} | {row['large']:.2f} |")


if __name__ == "__main__":
    metric = sys.argv[1] if len(sys.argv) > 1 else "omr"
    d = load()
    p = matrix(d, metric)
    n_cells = len(p) // 2
    print(f"metric={metric}  complete cells={len(p)} "
          f"({n_cells} traces x 2 cache sizes)  field={len(FIELD)} policies")
    table_a(p, metric)
    table_b(p, metric)
