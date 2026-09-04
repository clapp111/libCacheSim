#!/usr/bin/env bash
#
# Generate the scan-resistance workload: a steady Zipf phase, a scan over
# unique never-repeating objects, then a second Zipf phase over the same hot
# set.
#
#   [zipf N_PHASE] -> [scan, gap hot requests before each scan request] -> [zipf N_PHASE]
#
# The gap is what decides whether the scan is felt at all. At gap=0 nothing is
# requested between scan requests, so in a sweeping-hand cache every arriving
# scan object is unvisited, is evicted where it lands, and the hand never has
# to demote anything to move -- measured: 0 demotions and 0 hand wraps over an
# 800-object scan. Interleaving hot requests keeps hot objects visited, so the
# hand has to demote and skip them, and it advances.
#
# The middle phase is (gap hot requests, one scan request) repeated
# SCAN_LENGTH times, so it always ends on a scan request and is
# SCAN_LENGTH*(1+gap) requests long. Since every scan length is a multiple of
# 25, so is the middle phase, and the scan therefore ends on a window boundary
# for any gap -- which is where run_scan_windows.sh reads the hot-set count.
#
# One trace per (scan length, rep). The two outer Zipf phases are generated
# once per rep and reused across every scan length, so traces of the same rep
# are byte-identical outside the middle phase -- that is what makes scan
# lengths paired. Phase A is seeded with the rep number, as in
# run_shift_data_gen.sh, so a rerun of this script reproduces the same traces.
#
# usage: ./run_scan_data_gen.sh [n_reps] [gap]
#   n_reps defaults to 100, gap defaults to 0
#
# gap > 0 writes scan_L<len>_g<gap>_rep<n>.txt and leaves the gap=0 traces
# (scan_L<len>_rep<n>.txt) alone, so the two sweeps coexist.

set -euo pipefail
cd "$(dirname "$0")/.."   # repo root (libCacheSim/)

PYTHON=.venv/bin/python3
if [ ! -x "$PYTHON" ]; then
  echo "missing $PYTHON -- create the project virtual environment first" >&2
  exit 1
fi

DATA_DIR=data/scan
mkdir -p "$DATA_DIR"

if [ "$#" -gt 2 ]; then
  echo "usage: $0 [n_reps] [gap]" >&2
  exit 1
fi

N_REPS=${1:-100}
if ! [[ "$N_REPS" =~ ^[1-9][0-9]*$ ]]; then
  echo "n_reps must be a positive integer: $N_REPS" >&2
  exit 1
fi

GAP=${2:-0}
if ! [[ "$GAP" =~ ^(0|[1-9][0-9]*)$ ]]; then
  echo "gap must be a non-negative integer: $GAP" >&2
  exit 1
fi
SUFFIX=""
if [ "$GAP" -gt 0 ]; then
  SUFFIX="_g${GAP}"
fi

# --- trace generation params (single source of truth) ---
M=10000               # objects in the hot set
N_PHASE=200000        # requests per Zipf phase (pre- and post-scan)
ALPHA=1.0
CACHE=100             # 1% of M; the cache size the scan lengths are scaled to
# Scan burst lengths, as multiples of CACHE: 0.25 0.5 1 2 4 8. Their gcd is
# 25, so every scan boundary falls on a window boundary when the timeline
# runs at window=25 -- needed to read retention exactly at the scan end.
SCAN_LENGTHS=(25 50 100 200 400 800)
SCAN_START=10000          # scan obj_id start; disjoint from the hot set [0, M)
POST_SEED_OFFSET=1000000  # keeps the post-scan phase from replaying the pre-scan one
MID_SEED_OFFSET=2000000   # and keeps the interleaved hot requests independent of both

echo "=== regenerating $N_REPS x ${#SCAN_LENGTHS[@]} scan traces" \
     "(m=$M, n/phase=$N_PHASE, alpha=$ALPHA, cache=$CACHE, gap=$GAP) ==="
TMP_DIR=$(mktemp -d "$DATA_DIR/.scan.XXXXXX")
trap 'rm -rf -- "$TMP_DIR"' EXIT

for ((rep = 1; rep <= N_REPS; rep++)); do
  pre="$TMP_DIR/pre.txt"
  post="$TMP_DIR/post.txt"
  "$PYTHON" scripts/data_gen.py -m "$M" -n "$N_PHASE" --alpha "$ALPHA" \
    --start 0 --seed "$rep" > "$pre"
  "$PYTHON" scripts/data_gen.py -m "$M" -n "$N_PHASE" --alpha "$ALPHA" \
    --start 0 --seed "$((rep + POST_SEED_OFFSET))" > "$post"

  for scan_len in "${SCAN_LENGTHS[@]}"; do
    trace="$TMP_DIR/scan_L${scan_len}${SUFFIX}_rep${rep}.txt"
    cat "$pre" > "$trace"
    if [ "$GAP" -eq 0 ]; then
      seq "$SCAN_START" "$((SCAN_START + scan_len - 1))" >> "$trace"
    else
      mid="$TMP_DIR/mid.txt"
      "$PYTHON" scripts/data_gen.py -m "$M" -n "$((scan_len * GAP))" \
        --alpha "$ALPHA" --start 0 \
        --seed "$((rep + MID_SEED_OFFSET))" > "$mid"
      # GAP hot requests, then one scan request, SCAN_LENGTH times over --
      # streamed from mid rather than held in memory.
      awk -v g="$GAP" -v lo="$SCAN_START" -v n="$scan_len" -v f="$mid" '
        BEGIN {
          for (i = 0; i < n; i++) {
            for (j = 0; j < g; j++) {
              if ((getline line < f) > 0) print line
            }
            print lo + i
          }
        }' >> "$trace"
      rm -f -- "$mid"
    fi
    cat "$post" >> "$trace"
  done

  rm -f -- "$pre" "$post"
  echo "  rep $rep/$N_REPS done"
done

# Match each scan length exactly, so a gap>0 run cannot delete the gap=0
# traces (or the other way round) through a loose glob.
for scan_len in "${SCAN_LENGTHS[@]}"; do
  rm -f -- "$DATA_DIR"/scan_L${scan_len}${SUFFIX}_rep*.txt
  mv -- "$TMP_DIR"/scan_L${scan_len}${SUFFIX}_rep*.txt "$DATA_DIR"/
done
rmdir "$TMP_DIR"
trap - EXIT

# Counted per length for the same reason the deletion is: at gap=0 the glob
# scan_L*_rep*.txt would also pick up the gap>0 traces.
# Trailing slash so find descends when DATA_DIR is a symlink to the real store.
n_traces=0
for scan_len in "${SCAN_LENGTHS[@]}"; do
  n_traces=$(( n_traces + $(find "$DATA_DIR"/ -maxdepth 1 -type f \
    -name "scan_L${scan_len}${SUFFIX}_rep*.txt" | wc -l) ))
done
echo "done: $n_traces traces"
