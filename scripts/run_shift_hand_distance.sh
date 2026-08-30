#!/usr/bin/env bash
#
# Generate request-level hand-progress data for a single shift repetition.
# window=1, so every row is one request and hand_distance is an exact hand
# position rather than a window-end snapshot. This is the input to
# plot_shift_hand_distance.py.
#
# The multi-rep aggregate lives in run_shift_ghat_variants.sh, which runs the
# same configs at window=100 over all reps. That script is the source for the
# medians; this one exists only to draw one repetition at full resolution.
#
# usage: ./run_shift_hand_distance.sh [scenario] [rep]
#   scenario: disjoint | reversal   (default disjoint)
#   rep:      trace repetition      (default 83)

set -euo pipefail
cd "$(dirname "$0")/.."   # repo root (libCacheSim/)

SCAN_TIMELINE=_build/bin/scanTimeline

SCENARIO=${1:-disjoint}
REP=${2:-83}

case "$SCENARIO" in
  disjoint | reversal) ;;
  *)
    echo "unknown scenario '$SCENARIO' (expected disjoint | reversal)" >&2
    exit 1
    ;;
esac

# Must match run_shift_data_gen.sh and run_shift_ghat_variants.sh.
M=10000
N_PHASE=200000
CACHE=$(( M / 100 ))   # 1% of the id range
WINDOW=1

# Same target ranges as run_shift_ghat_variants.sh: Disjoint's whole phase A
# is obsolete after the shift, Reversal demotes only the lower half.
if [ "$SCENARIO" = "disjoint" ]; then
  TARGET_RANGE="0:$M"
else
  TARGET_RANGE="0:$(( M / 2 ))"
fi

# Request-index window kept in the CSV. Mirrors REQUEST_LO/REQUEST_HI in
# plot_shift_hand_distance.py, which reads a subset of this range.
LAST_PRE_SHIFT=$(( N_PHASE - 1 ))
REQ_LO=$(( LAST_PRE_SHIFT - 5000 ))
REQ_HI=$(( LAST_PRE_SHIFT + 60000 ))

# label|eviction_algo|eviction_params, same convention as
# run_shift_ghat_variants.sh. Order matches the figure's panel order.
CONFIGS=(
  "Ghat-g0-t1|Ghat|protect-threshold=1,ghost-count-ratio=0"
  "Ghat-g0-t2|Ghat|protect-threshold=2,ghost-count-ratio=0"
  "Ghat-g1-t2|Ghat|protect-threshold=2"
)

trace="data/shift/${SCENARIO}_rep${REP}.txt"
if [ ! -f "$trace" ]; then
  echo "missing $trace -- run run_shift_data_gen.sh $SCENARIO first" >&2
  exit 1
fi
if [ ! -x "$SCAN_TIMELINE" ]; then
  echo "missing $SCAN_TIMELINE -- build first" >&2
  exit 1
fi

out="result/shift/${SCENARIO}_ghat_hand_distance_rep${REP}.csv"
mkdir -p result/shift

echo "=== $out (cache=$CACHE, window=$WINDOW, target=$TARGET_RANGE) ==="

# Written to a temp file first so an aborted run cannot leave a truncated CSV
# that later looks complete.
{
  echo "config,rep,window_idx,req_in_window,miss_in_window,miss_ratio,n_obj,n_protected,n_target_protected,n_demote,n_evict,n_hand_wrap,hand_distance"

  for cfg in "${CONFIGS[@]}"; do
    label=${cfg%%|*}
    algo=$(cut -d'|' -f2 <<< "$cfg")
    params=${cfg##*|}
    echo "  $label" >&2
    "$SCAN_TIMELINE" "$trace" txt "$algo" "$CACHE" "$WINDOW" \
      "$params" "$TARGET_RANGE" sweep 2>/dev/null \
      | tail -n +2 \
      | awk -F, -v OFS=, -v label="$label" -v rep="$REP" \
            -v lo="$REQ_LO" -v hi="$REQ_HI" \
            '$2 >= lo && $2 <= hi {
               print label, rep, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
             }'
  done
} > "$out.tmp"

mv -- "$out.tmp" "$out"
wc -l "$out"
echo "=== DONE ==="
