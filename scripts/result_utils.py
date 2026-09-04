#!/usr/bin/env python3
"""Shared parsing and file-resolution helpers for result plots.

Plot-specific choices such as family membership, algorithm variants, and
display names are passed in by each caller rather than defined here.
"""

import glob
import os
import re


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

LINE_RE = re.compile(
    r"^(\S+)\s+size=(\S+)\s+(\S+)\s+cache size\s+\S+,\s+\d+\s+req,\s+"
    r"miss ratio\s+([\d.]+),\s+byte miss ratio\s+([\d.]+)"
)


def display_name(algo, display_names):
    return display_names.get(algo, algo)


def resolve_family_files(family, family_globs):
    files = []
    for pattern in family_globs[family]:
        path = pattern if os.path.isabs(pattern) else os.path.join(REPO_ROOT, pattern)
        files.extend(sorted(glob.glob(path)))
    return files


def parse_result_file(path, algo_variants):
    """Yield (trace, size, algo, miss_ratio, byte_miss_ratio) rows.

    algo_variants maps a base algorithm name to the collection of raw cache
    names accepted for it; rows carrying any other variant of that base name
    are skipped.
    """
    with open(path) as f:
        for line in f:
            match = LINE_RE.match(line.strip())
            if not match:
                continue
            trace, size, algo_raw, mr, bmr = match.groups()
            algo = algo_raw.split("-")[0]
            if algo in algo_variants and algo_raw not in algo_variants[algo]:
                continue
            yield trace, size, algo, float(mr), float(bmr)
