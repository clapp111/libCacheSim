"""
plot a trace's raw request scatter: x = time (# request, i.e. request
index within the trace), y = object id. Working-set shifts / access
pattern structure show up as bands, jumps, or diagonal streaks of dots.

Supports two trace formats, auto-detected from the file extension (or
forced via --trace-format):
  - txt: one obj_id per line (data_gen.py's stdout/txt mode)
  - oracleGeneral: 24-byte binary records (uint32 clock_time, uint64
    obj_id, uint32 obj_size, int64 next_access_vtime), little-endian --
    see libCacheSim/traceReader/customizedReader/oracle/oracleGeneralBin.h.
    *.zst files are streamed through the `zstd` CLI, same as
    libCacheSim's own reader treats *.zst as a transparently-compressed
    binary trace.

usage:
`python3 scripts/traceAnalysis/scatter.py --input /path/to/trace`
"""

import logging
import os
import subprocess
import sys

import numpy as np
import matplotlib.pyplot as plt

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/../")
from utils.trace_utils import extract_dataname
from utils.plot_utils import FIG_DIR, FIG_TYPE

logger = logging.getLogger("scatter")

POINT_SIZE = 1
POINT_ALPHA = 0.08
POINT_COLOR = "#1d4ed8"

X_UNIT_DIVISOR = {"K": 1e3, "M": 1e6, "B": 1e9}
X_UNIT_NAME = {"K": "thousand", "M": "million", "B": "billion"}

ORACLE_GENERAL_DTYPE = np.dtype([
    ("clock_time", "<u4"),
    ("obj_id", "<u8"),
    ("obj_size", "<u4"),
    ("next_access_vtime", "<i8"),
])
ORACLE_GENERAL_ITEM_SIZE = ORACLE_GENERAL_DTYPE.itemsize  # 24
CHUNK_RECORDS = 1_000_000


def _load_trace_txt(datapath: str) -> np.ndarray:
    """load a txt-format trace (one obj_id per line) as obj_ids"""
    return np.loadtxt(datapath, dtype=np.int64)


def _load_trace_oracle_general(datapath: str) -> np.ndarray:
    """load an oracleGeneral binary trace (optionally *.zst-compressed) as obj_ids"""
    if datapath.endswith(".zst"):
        proc = subprocess.Popen(["zstd", "-dc", datapath], stdout=subprocess.PIPE)
        stream = proc.stdout
    else:
        proc = None
        stream = open(datapath, "rb")

    obj_id_chunks = []
    try:
        chunk_bytes = ORACLE_GENERAL_ITEM_SIZE * CHUNK_RECORDS
        while True:
            buf = stream.read(chunk_bytes)
            if not buf:
                break
            n_records = len(buf) // ORACLE_GENERAL_ITEM_SIZE
            if n_records == 0:
                break
            records = np.frombuffer(buf, dtype=ORACLE_GENERAL_DTYPE, count=n_records)
            obj_id_chunks.append(records["obj_id"].copy())
    finally:
        stream.close()
        if proc is not None:
            ret = proc.wait()
            if ret != 0:
                raise RuntimeError(f"zstd exited with code {ret} while reading {datapath}")

    return np.concatenate(obj_id_chunks) if obj_id_chunks else np.array([], dtype=np.uint64)


def load_trace(datapath: str, trace_format: str = "auto") -> np.ndarray:
    """load a trace's obj_id sequence

    Args:
        datapath: path to the trace file
        trace_format: "auto" (detect from extension), "txt", or "oracleGeneral"

    Returns:
        obj_ids, one entry per request, in trace order
    """
    if trace_format == "auto":
        trace_format = "txt" if datapath.endswith(".txt") else "oracleGeneral"

    if trace_format == "txt":
        return _load_trace_txt(datapath)
    elif trace_format == "oracleGeneral":
        return _load_trace_oracle_general(datapath)
    else:
        raise ValueError(f"unknown trace_format: {trace_format}")


def plot_scatter(datapath: str, trace_format: str = "auto", figname_prefix: str = "",
                  output_path: str = "", x_unit: str = "K") -> None:
    """plot a trace's request scatter (x = request index, y = object id)"""
    if not figname_prefix:
        figname_prefix = extract_dataname(datapath)

    obj_ids = load_trace(datapath, trace_format)
    x = np.arange(len(obj_ids)) / X_UNIT_DIVISOR[x_unit]

    plt.scatter(x, obj_ids, s=POINT_SIZE, alpha=POINT_ALPHA, color=POINT_COLOR, linewidths=0)
    plt.xlabel("Time (# {} requests)".format(X_UNIT_NAME[x_unit]))
    plt.ylabel("Object ID")

    if not output_path:
        output_path = "{}/{}_scatter.{}".format(FIG_DIR, figname_prefix, FIG_TYPE)
    plt.savefig(output_path, bbox_inches="tight")
    plt.clf()
    logger.info("save fig to {}".format(output_path))


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--input", type=str, required=True, dest="datapath", metavar="INPUT",
        help="path to the input trace file (txt, or oracleGeneral binary/*.zst)",
    )
    ap.add_argument(
        "--output", type=str, default="",
        help="path to save the output plot; defaults to {}/<trace-name>_scatter.{}".format(
            FIG_DIR.rstrip("/"), FIG_TYPE
        ),
    )
    ap.add_argument(
        "--trace-format", type=str, default="auto", choices=["auto", "txt", "oracleGeneral"],
        help="trace format; auto detects txt (*.txt) vs oracleGeneral (everything else)",
    )
    ap.add_argument(
        "--figname-prefix", type=str, default="",
        help="prefix used for the auto-generated output filename (ignored if --output is set)",
    )
    ap.add_argument(
        "--x-unit", type=str, default="K", choices=["K", "M", "B"],
        help="unit for the x (# request) axis: K=thousand, M=million, B=billion (default: K)",
    )
    p = ap.parse_args()

    plot_scatter(p.datapath, p.trace_format, p.figname_prefix, p.output, p.x_unit)
