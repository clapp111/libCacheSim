#!/usr/bin/env bash
#
# Generate windowed miss-ratio data for one abrupt-shift scenario.
# Runs scanTimeline across each trace for every requested algorithm at a
# 1%-of-M cache size; plot_shift_recovery.py derives recovery time from the
# resulting CSV. Generate the selected scenario's traces first.
#
# usage: ./run_shift_windows.sh <disjoint|reversal> [n_reps] [algo1 algo2 ...]
#   defaults to: 100 reps, Ghat

set -euo pipefail
cd "$(dirname "$0")/.."   # repo root (libCacheSim/)

SCAN_TIMELINE=_build/bin/scanTimeline
DATA_DIR=data/shift
RESULT_DIR=result/shift
mkdir -p "$RESULT_DIR"

if [ "$#" -lt 1 ]; then
  echo "usage: $0 <disjoint|reversal> [n_reps] [algo1 algo2 ...]" >&2
  exit 1
fi

SCENARIO=$1
shift
case "$SCENARIO" in
  disjoint|reversal) ;;
  *)
    echo "unknown scenario: $SCENARIO (expected disjoint or reversal)" >&2
    exit 1
    ;;
esac

N_REPS=${1:-100}
if [ "$#" -gt 0 ]; then shift; fi
if ! [[ "$N_REPS" =~ ^[1-9][0-9]*$ ]]; then
  echo "n_reps must be a positive integer: $N_REPS" >&2
  exit 1
fi

if [ "$#" -gt 0 ]; then
  ALGOS=("$@")
else
  ALGOS=(Ghat)
fi

# M must match run_shift_data_gen.sh's M -- only used here to derive TIMELINE_CACHE
M=10000
TIMELINE_CACHE=$(( M / 100 ))   # 1% of one phase's working set
WINDOW=100                      # (2*N_PHASE)/WINDOW = 4000 windows; shift lands at window 2000

windows_csv="$RESULT_DIR/${SCENARIO}_windows.csv"

# Incremental: only run algorithms not already present in windows_csv, and
# append their rows -- doesn't touch rows for algorithms already there.
if [ -f "$windows_csv" ]; then
  existing_algos=$(awk -F, 'NR>1{print $1}' "$windows_csv" | sort -u)
else
  echo "algo,rep,window_idx,req_in_window,miss_in_window,miss_ratio" > "$windows_csv"
  existing_algos=""
fi

new_algos=()
for algo in "${ALGOS[@]}"; do
  if ! grep -qx "$algo" <<< "$existing_algos"; then
    new_algos+=("$algo")
  fi
done

if [ ${#new_algos[@]} -eq 0 ]; then
  echo "all requested algorithms already present in $windows_csv -- nothing to do"
  exit 0
fi

echo "already have: $(echo "$existing_algos" | tr '\n' ' ')"
echo "running: ${new_algos[*]}"
ALGOS=("${new_algos[@]}")

echo "=== building timeline windows CSV (cache=$TIMELINE_CACHE, window=$WINDOW) ==="
for ((rep = 1; rep <= N_REPS; rep++)); do
  trace="$DATA_DIR/${SCENARIO}_rep${rep}.txt"
  if [ ! -f "$trace" ]; then
    echo "missing $trace -- run run_shift_data_gen.sh $SCENARIO first" >&2
    exit 1
  fi
  for algo in "${ALGOS[@]}"; do
    "$SCAN_TIMELINE" "$trace" txt "$algo" "$TIMELINE_CACHE" "$WINDOW" 2>/dev/null \
      | tail -n +2 \
      | awk -F, -v OFS=, -v rep="$rep" '{print $1, rep, $2, $3, $4, $5}' \
      >> "$windows_csv"
  done
  echo "  timeline: rep $rep/$N_REPS done"
done

echo "=== DONE ==="
wc -l "$windows_csv"
