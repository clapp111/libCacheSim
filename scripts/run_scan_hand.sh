#!/usr/bin/env bash
#
# Pair each run's hand position going into the scan with the hot objects it
# still holds when the scan ends -- the input to the mechanism panel of
# plot_scan_retention.py.
#
# Kept separate from run_scan_windows.sh for three reasons: it needs eviction
# params (that script passes none), only hand-sweep policies can report
# hand_distance at all, and one scan length is enough because retention does
# not vary with scan length. The result is a few hundred rows rather than the
# tens of millions in scan_windows.csv.
#
# SIEVE is measured through Ghat with ghost off and threshold 1, which the
# repo already relies on as a bit-exact stand-in and which, unlike the
# upstream Sieve implementation, exposes the sweep counters.
#
# usage: ./run_scan_hand.sh [n_reps]
#   n_reps defaults to 100

set -euo pipefail
cd "$(dirname "$0")/.."   # repo root (libCacheSim/)

SCAN_TIMELINE=_build/bin/scanTimeline
DATA_DIR=data/scan
RESULT_DIR=result/scan
mkdir -p "$RESULT_DIR"

N_REPS=${1:-100}
if ! [[ "$N_REPS" =~ ^[1-9][0-9]*$ ]]; then
  echo "n_reps must be a positive integer: $N_REPS" >&2
  exit 1
fi

# Must match run_scan_data_gen.sh / run_scan_windows.sh
M=10000
N_PHASE=200000
SCAN_LEN=800
TIMELINE_CACHE=$(( M / 100 ))
WINDOW=25
TARGET_RANGE="0:$M"

# Last window before the scan, and the window the scan ends on.
PRE_WINDOW=$(( N_PHASE / WINDOW - 1 ))
END_WINDOW=$(( (N_PHASE + SCAN_LEN) / WINDOW - 1 ))

CONFIGS=(
  "Sieve|protect-threshold=1,ghost-count-ratio=0"
  "Ghat|ghost-count-ratio=1.0"
)

out="$RESULT_DIR/scan_hand.csv"
echo "algo,rep,hand_distance,n_target_resident" > "$out"

echo "=== hand position vs retention (cache=$TIMELINE_CACHE, scan=$SCAN_LEN, $N_REPS reps) ==="
for cfg in "${CONFIGS[@]}"; do
  algo=${cfg%%|*}
  params=${cfg##*|}
  for ((rep = 1; rep <= N_REPS; rep++)); do
    trace="$DATA_DIR/scan_L${SCAN_LEN}_rep${rep}.txt"
    if [ ! -f "$trace" ]; then
      echo "missing $trace -- run run_scan_data_gen.sh first" >&2
      exit 1
    fi
    "$SCAN_TIMELINE" "$trace" txt Ghat "$TIMELINE_CACHE" "$WINDOW" \
      "$params" "$TARGET_RANGE" sweep "$END_WINDOW" 2>/dev/null \
      | awk -F, -v a="$algo" -v r="$rep" -v pre="$PRE_WINDOW" -v end="$END_WINDOW" \
            'NR>1 { if ($2 == pre) hd = $13; if ($2 == end) res = $9 }
             END  { print a "," r "," hd "," res }' \
      >> "$out"
  done
  echo "  $algo done"
done

echo "=== DONE ==="
wc -l "$out"
