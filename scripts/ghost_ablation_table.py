#!/usr/bin/env python3
"""usage: python3 scripts/ghost_ablation_table.py [FIFO|LRU]"""

import glob
import re
import sys

import pandas as pd

FAMILIES = ["meta-key", "twitter", "meta-cdn", "wikimedia", "tencent-photo"]

CONFIGS = {"Sieve": "off,1", "Ghat-1-1.0000": "on,1",
           "Ghat-2-0.0000": "off,2", "Ghat-2-1.0000": "on,2"}

CORNERS = ["off,1", "on,1", "off,2", "on,2"]

LABELS = {"off,1": "off,1 (SIEVE)", "on,1": "on,1",
          "off,2": "off,2", "on,2": "on,2 (GHAT)"}

EFFECTS = {
    "ghost effect at tau=1": ("on,1", "off,1"),
    "ghost effect at tau=2": ("on,2", "off,2"),
    "tau effect with ghost off": ("off,2", "off,1"),
    "tau effect with ghost on": ("on,2", "on,1"),
}

LINE = re.compile(
    r"^(\S+)\s+size=(\S+)\s+(.+?)\s+cache size\s+(\S+),\s+(\d+) req, "
    r"miss ratio ([\d.]+), byte miss ratio ([\d.]+)")


def load(base):
    keep = dict(CONFIGS)
    keep[base] = base
    recs = []
    for fam in FAMILIES:
        for path in glob.glob(f"result/{fam}/*_result.txt"):
            for line in open(path, errors="ignore"):
                m = LINE.match(line.strip())
                if not m or m.group(3) not in keep:
                    continue
                recs.append((fam, m.group(1), m.group(2),
                             keep[m.group(3)], float(m.group(6))))
    d = pd.DataFrame(recs, columns=["family", "trace", "size", "cfg", "omr"])
    dup = d.groupby(["family", "trace", "size", "cfg"])["omr"].nunique()
    conflicts = int((dup > 1).sum())
    d = d.groupby(["family", "trace", "size", "cfg"], as_index=False).mean()
    return d, conflicts


def matrix(d, base):
    cols = CORNERS + [base]
    n = d.groupby(["family", "trace", "size"])["cfg"].nunique()
    keep = n[n == len(cols)].index
    d = d.set_index(["family", "trace", "size"]).loc[keep].reset_index()
    return d.pivot_table(index=["family", "trace", "size"],
                         columns="cfg", values="omr")[cols]


def reduction(p, base):
    return p[CORNERS].rsub(p[base], axis=0).div(p[base], axis=0) * 100.0


def table_2x2(r, base):
    print(f"\n### 2x2 — median OMR reduction from {base} (relative %)\n")
    print("| | tau=1 | tau=2 |")
    print("|---|---:|---:|")
    for ghost in ["off", "on"]:
        cells = [f"{r[f'{ghost},{t}'].median():.2f}" for t in [1, 2]]
        print(f"| ghost={ghost} | {cells[0]} | {cells[1]} |")


def table_paired(p, base):
    print(f"\n### Paired main effects — normalized by {base} (relative %)\n")
    print("| effect | median | mean | improved configs |")
    print("|---|---:|---:|---:|")
    for name, (a, b) in EFFECTS.items():
        e = (p[b] - p[a]) / p[base] * 100.0
        w = int((e > 0).sum())
        print(f"| {name} | {e.median():+.2f} | {e.mean():+.2f} | "
              f"{w}/{len(e)}, {w / len(e):.0%} |")


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "FIFO"
    d, conflicts = load(base)
    p = matrix(d, base)
    print(f"base={base}  cells={len(p)} ({len(p) // 2} traces x 2 sizes)"
          f"  corners={[LABELS[c] for c in CORNERS]}  value conflicts={conflicts}")
    table_2x2(reduction(p, base), base)
    table_paired(p, base)
