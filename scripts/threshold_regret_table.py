#!/usr/bin/env python3
"""usage: python3 scripts/threshold_regret_table.py"""

import glob
import re

import numpy as np
import pandas as pd

FAMILIES = ["meta-key", "twitter", "meta-cdn", "wikimedia", "tencent-photo"]

THRESHOLDS = [1, 2, 3, 4]

TAU_NAMES = {f"Ghat-{t}-1.0000": t for t in THRESHOLDS}

SIZES = ["small", "large"]

LINE = re.compile(
    r"^(\S+)\s+size=(\S+)\s+(.+?)\s+cache size\s+(\S+),\s+(\d+) req, "
    r"miss ratio ([\d.]+), byte miss ratio ([\d.]+)")


def load():
    recs = []
    for fam in FAMILIES:
        for path in glob.glob(f"result/{fam}/*_result.txt"):
            for line in open(path, errors="ignore"):
                m = LINE.match(line.strip())
                if not m or m.group(3) not in TAU_NAMES:
                    continue
                recs.append((fam, m.group(1), m.group(2),
                             TAU_NAMES[m.group(3)], float(m.group(6))))
    d = pd.DataFrame(recs, columns=["family", "trace", "size", "tau", "omr"])
    dup = d.groupby(["family", "trace", "size", "tau"])["omr"].nunique()
    conflicts = int((dup > 1).sum())
    d = d.groupby(["family", "trace", "size", "tau"], as_index=False).mean()
    return d, conflicts


def matrix(d):
    n = d.groupby(["family", "trace", "size"])["tau"].nunique()
    keep = n[n == len(THRESHOLDS)].index
    d = d.set_index(["family", "trace", "size"]).loc[keep].reset_index()
    return d.pivot_table(index=["family", "trace", "size"],
                         columns="tau", values="omr")


def regret(p):
    best = p.min(axis=1)
    return (p.sub(best, axis=0)).div(best, axis=0) * 100.0


def table_regret(r):
    for size in SIZES:
        q = r.xs(size, level="size")
        print(f"\n### Regret — {size} cache (n={len(q)})\n")
        print("| tau | mean | median | P90 | worst |")
        print("|---:|---:|---:|---:|---:|")
        for t in THRESHOLDS:
            g = q[t]
            p90 = np.percentile(g, 90, method="higher")
            print(f"| {t} | {g.mean():.3f}% | {g.median():.3f}% | "
                  f"{p90:.3f}% | {g.max():.3f}% |")


def table_paired(p, a=2, b=1):
    print(f"\n### Paired raw OMR, tau={a} vs tau={b}\n")
    print(f"| cache | tau={a} wins | ties | tau={b} wins | mean MR difference |")
    print("|---|---:|---:|---:|---:|")
    for size in SIZES:
        q = p.xs(size, level="size")
        diff = q[a] - q[b]
        n = len(diff)
        win = int((diff < 0).sum())
        tie = int((diff == 0).sum())
        loss = int((diff > 0).sum())
        print(f"| {size.capitalize()} | {win}, {win / n:.0%} | {tie} | "
              f"{loss}, {loss / n:.0%} | {diff.mean():+.4f} |")


if __name__ == "__main__":
    d, conflicts = load()
    p = matrix(d)
    print(f"cells={len(p)} ({len(p) // len(SIZES)} traces x {len(SIZES)} sizes)"
          f"  taus={THRESHOLDS}  value conflicts={conflicts}")
    table_regret(regret(p))
    table_paired(p)
