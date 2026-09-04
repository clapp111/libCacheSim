#!/usr/bin/env bash
#
# Generate windowed miss-ratio data for the scan-resistance workload.
# Runs scanTimeline over every (scan length, rep) trace for each requested
# algorithm at a 1%-of-M cache size. Generate the traces first with
# run_scan_data_gen.sh.
#
# The n_target_resident column carries the retention measurement: how many
# hot-set objects the cache still holds when the scan ends. It is filled on
# exactly one window per run -- the one the scan ends on -- and is -1
# everywhere else, because counting it probes the whole id range.
#
# usage: ./run_scan_windows.sh [n_reps] [algo1 algo2 ...]
#   defaults to: 100 reps, Ghat

set -euo pipefail
cd "$(dirname "$0")/.."   # repo root (libCacheSim/)

SCAN_TIMELINE=_build/bin/scanTimeline
DATA_DIR=data/scan
RESULT_DIR=result/scan
mkdir -p "$RESULT_DIR"

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

# M, N_PHASE and SCAN_LENGTHS must match run_scan_data_gen.sh
M=10000
N_PHASE=200000
SCAN_LENGTHS=(25 50 100 200 400 800)
TIMELINE_CACHE=$(( M / 100 ))   # 1% of the hot set
WINDOW=25                       # divides every scan length, so each scan ends
                                # on a window boundary (see resident_window)
TARGET_RANGE="0:$M"             # the hot set; retention is counted over it

windows_csv="$RESULT_DIR/scan_windows.csv"

# Incremental: only run algorithms not already present in windows_csv, and
# append their rows -- doesn't touch rows for algorithms already there.
if [ -f "$windows_csv" ]; then
  existing_algos=$(awk -F, 'NR>1{print $1}' "$windows_csv" | sort -u)
else
  echo "algo,scan_len,rep,window_idx,req_in_window,miss_in_window,miss_ratio,n_obj,n_protected,n_target_protected,n_target_resident" > "$windows_csv"
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

echo "=== building scan windows CSV (cache=$TIMELINE_CACHE, window=$WINDOW, target=$TARGET_RANGE) ==="
for ((rep = 1; rep <= N_REPS; rep++)); do
  for scan_len in "${SCAN_LENGTHS[@]}"; do
    trace="$DATA_DIR/scan_L${scan_len}_rep${rep}.txt"
    if [ ! -f "$trace" ]; then
      echo "missing $trace -- run run_scan_data_gen.sh first" >&2
      exit 1
    fi

    # The scan ends on request N_PHASE + scan_len; retention is read at the
    # end of the window that request closes. Bail out rather than silently
    # measure the wrong point if the two stop dividing each other.
    scan_end=$(( N_PHASE + scan_len ))
    if (( scan_end % WINDOW != 0 )); then
      echo "scan end $scan_end is not a multiple of window $WINDOW" \
           "(scan_len=$scan_len) -- retention would be read off the scan boundary" >&2
      exit 1
    fi
    resident_window=$(( scan_end / WINDOW - 1 ))

    for algo in "${ALGOS[@]}"; do
      "$SCAN_TIMELINE" "$trace" txt "$algo" "$TIMELINE_CACHE" "$WINDOW" \
        "" "$TARGET_RANGE" "" "$resident_window" 2>/dev/null \
        | tail -n +2 \
        | awk -F, -v OFS=, -v rep="$rep" -v len="$scan_len" \
              '{print $1, len, rep, $2, $3, $4, $5, $6, $7, $8, $9}' \
        >> "$windows_csv"
    done
  done
  echo "  timeline: rep $rep/$N_REPS done"
done

echo "=== DONE ==="
wc -l "$windows_csv"
