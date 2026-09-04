#!/usr/bin/env bash
#
# Cache-size robustness sweep of the abrupt-shift mechanism: does the
# ghost-off/tau=2 stall, and the PCF gap, survive at cache sizes other than
# the 1% used by run_shift_ghat_variants.sh?
#
# Writes its own CSV and never touches the Ghat variants window CSV.
# Requires the selected shift traces and a scanTimeline built with the sweep
# counters.
#
# usage: ./run_shift_cachesize_robustness.sh <disjoint|reversal> [n_reps] [cache_size ...]
#   defaults to: 100 reps, caches 10 50 100 200 500 1000
#                (= 0.1% .. 10% of M=10000)

set -euo pipefail
cd "$(dirname "$0")/.."   # repo root (libCacheSim/)

SCAN_TIMELINE=_build/bin/scanTimeline
DATA_DIR=data/shift
RESULT_DIR=result/shift

M=10000
N_PHASE=200000
WINDOW=100
# The shift lands at this window; the last window that ends before it is
# SHIFT_WINDOW_IDX-1, which is where PCF is read. Both are derived, not
# hardcoded, so changing WINDOW stays consistent.
SHIFT_WINDOW_IDX=$(( N_PHASE / WINDOW ))

if [ "$#" -lt 1 ]; then
  echo "usage: $0 <disjoint|reversal> [n_reps] [cache_size ...]" >&2
  exit 1
fi

SCENARIO=$1
shift
case "$SCENARIO" in
  disjoint)
    TARGET_RANGE="0:$M"
    ;;
  reversal)
    # Track the half whose popularity rank drops after the reversal. Unlike
    # Disjoint, these objects remain requestable, so drain_x is only the first
    # window where this count reaches zero, not permanent drainage.
    TARGET_RANGE="0:$(( M / 2 ))"
    ;;
  *)
    echo "unknown scenario: $SCENARIO (expected disjoint or reversal)" >&2
    exit 1
    ;;
esac

N_REPS=${1:-100}
if [ "$#" -gt 0 ]; then
  shift
fi
if ! [[ "$N_REPS" =~ ^[1-9][0-9]*$ ]]; then
  echo "n_reps must be a positive integer: $N_REPS" >&2
  exit 1
fi

if [ "$#" -gt 0 ]; then
  CACHES=("$@")
else
  CACHES=(10 50 100 200 500 1000)
fi

OUT="$RESULT_DIR/${SCENARIO}_cachesize_robustness.csv"

# label|eviction_algo|eviction_params -- same naming as run_shift_ghat_variants.sh.
# SIEVE is measured through Ghat with ghost off and threshold 1: the upstream
# Sieve implementation reports no sweep counters, so scanTimeline rejects it.
CONFIGS=(
  "Ghat-g0-t1|Ghat|protect-threshold=1,ghost-count-ratio=0"
  "Ghat-g1-t2|Ghat|protect-threshold=2"
  "Ghat-g0-t2|Ghat|protect-threshold=2,ghost-count-ratio=0"
)

mkdir -p "$RESULT_DIR"
echo "config,cache,rep,pcf,drain_x,m_at_drain,m_post_median" > "$OUT"

for cache in "${CACHES[@]}"; do
  echo "=== scenario=$SCENARIO cache=$cache  start $(date '+%F %T') ==="
  for ((rep = 1; rep <= N_REPS; rep++)); do
    trace="$DATA_DIR/${SCENARIO}_rep${rep}.txt"
    if [ ! -f "$trace" ]; then
      echo "missing $trace -- run run_shift_data_gen.sh $SCENARIO first" >&2
      exit 1
    fi
    for cfg in "${CONFIGS[@]}"; do
      label=${cfg%%|*}
      algo=$(cut -d'|' -f2 <<< "$cfg")
      params=${cfg##*|}
      "$SCAN_TIMELINE" "$trace" txt "$algo" "$cache" "$WINDOW" \
        "$params" "$TARGET_RANGE" sweep 2>/dev/null \
        | awk -F, -v L="$label" -v C="$cache" -v R="$rep" \
            -v S="$SHIFT_WINDOW_IDX" -v W="$WINDOW" '
            $1 != "algo" {
              w = $2 + 0
              if (w == S - 1 && $6 > 0)
                pcf = 100.0 * $8 / $6
              if (w >= S) {
                m = ($11 > 0) ? $10 / $11 : 0
                mm[w] = m
                ms[++nm] = m
                if (drain == "" && $8 == 0)
                  drain = w
              }
            }

            END {
              n = asort(ms)
              med = (n > 0) ? ms[int((n + 1) / 2)] : 0
              if (drain == "")
                printf "%s,%s,%s,%.2f,,,%.4f\n", L, C, R, pcf, med
              else
                printf "%s,%s,%s,%.2f,%d,%.3f,%.4f\n", \
                       L, C, R, pcf, (drain - S + 1) * W, mm[drain], med
            }
          ' \
        >> "$OUT"
    done
  done
  echo "=== cache=$cache  done  $(date '+%F %T') ==="
done

echo "=== DONE ==="
wc -l "$OUT"
