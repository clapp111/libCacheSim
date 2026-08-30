#!/usr/bin/env bash
#
# Generate windowed miss-ratio and protected-state data for Ghat variants.
# Runs the four threshold/ghost configurations plus SIEVE using
# scanTimeline's target_id_range mode, which adds protected-object counts
# to the common window columns. Requires the shift traces to exist -- run
# run_shift_data_gen.sh once per scenario first.
#
# This writes its own *_ghat_variants_windows.csv and never touches the
# baseline window CSVs produced by run_shift_windows.sh.
#
# usage: ./run_shift_ghat_variants.sh [scenario] [n_reps]
#   scenario: disjoint | reversal | both   (default both)
#   n_reps:   default 100

set -euo pipefail
cd "$(dirname "$0")/.."   # repo root (libCacheSim/)

SCAN_TIMELINE=_build/bin/scanTimeline

SCENARIO=${1:-both}
N_REPS=${2:-100}

# M must match the gen scripts' M -- only used here to derive TIMELINE_CACHE
M=10000
TIMELINE_CACHE=$(( M / 100 ))   # 1% of the id range
WINDOW=100                      # (2*N_PHASE)/WINDOW = 4000 windows; shift lands at window 2000

# label|eviction_algo|eviction_params
#
# Labels are Ghat-g<ghost-count-ratio>-t<protect-threshold>, ASCII and
# comma-free because they land in the CSV's algo column and the incremental
# check below matches them verbatim. Paper-facing names for the subset plotted
# by plot_shift_mechanism.py live in that script's DISPLAY_NAME. Keeping the
# ratio in the label (g1 = 1.0) leaves room for a ghost-size sweep (g05).
#
# The four Ghat entries form a 2x2 (ghost on/off x threshold 1/2). Ghost
# capacity is derived as n_obj * ratio, so at ratio 0 an entry is trimmed the
# moment it is inserted and no ghost hit can occur; Ghat-g0-t1 therefore
# reproduces the Sieve rows exactly (verified bit-for-bit), which makes plain
# SIEVE the ghost-off/tau=1 corner of the factorial rather than a separate
# baseline. Running each config as its own process also sidesteps
# Ghat_PROTECT_THRESHOLD being a file-static global rather than per-instance.
CONFIGS=(
  "Ghat-g1-t1|Ghat|protect-threshold=1"
  "Ghat-g1-t2|Ghat|protect-threshold=2"
  "Ghat-g0-t2|Ghat|protect-threshold=2,ghost-count-ratio=0"
  "Ghat-g0-t1|Ghat|protect-threshold=1,ghost-count-ratio=0"
)

run_scenario() {
  local data_dir=$1 result_dir=$2 trace_prefix=$3 csv_name=$4 target_range=$5

  mkdir -p "$result_dir"
  local csv="$result_dir/$csv_name"

  # Incremental: only run labels not already present, and append their rows --
  # doesn't touch rows for labels already there.
  local existing
  if [ -f "$csv" ]; then
    existing=$(awk -F, 'NR>1{print $1}' "$csv" | sort -u)
  else
    echo "algo,rep,window_idx,req_in_window,miss_in_window,miss_ratio,n_obj,n_protected,n_target_protected" > "$csv"
    existing=""
  fi

  local new_configs=()
  local cfg
  for cfg in "${CONFIGS[@]}"; do
    if ! grep -qx "${cfg%%|*}" <<< "$existing"; then
      new_configs+=("$cfg")
    fi
  done

  if [ ${#new_configs[@]} -eq 0 ]; then
    echo "all configs already present in $csv -- nothing to do"
    return 0
  fi

  echo "=== $csv (cache=$TIMELINE_CACHE, window=$WINDOW, target=$target_range) ==="
  echo "already have: $(echo "$existing" | tr '\n' ' ')"
  echo "running: $(for c in "${new_configs[@]}"; do printf '%s ' "${c%%|*}"; done)"

  local rep trace label algo params
  for ((rep = 1; rep <= N_REPS; rep++)); do
    trace="$data_dir/${trace_prefix}${rep}.txt"
    if [ ! -f "$trace" ]; then
      echo "missing $trace -- run the matching gen script first" >&2
      exit 1
    fi
    for cfg in "${new_configs[@]}"; do
      label=${cfg%%|*}
      algo=$(cut -d'|' -f2 <<< "$cfg")
      params=${cfg##*|}
      "$SCAN_TIMELINE" "$trace" txt "$algo" "$TIMELINE_CACHE" "$WINDOW" \
        "$params" "$target_range" 2>/dev/null \
        | tail -n +2 \
        | awk -F, -v OFS=, -v rep="$rep" -v label="$label" \
              '{print label, rep, $2, $3, $4, $5, $6, $7, $8}' \
        >> "$csv"
    done
    echo "  variants: rep $rep/$N_REPS done"
  done

  wc -l "$csv"
}

# Disjoint: phase A is [0, M), phase B is [M, 2M) -- the whole of phase A is
# obsolete after the shift.
# Reversal: both phases share [0, M); the lower half [0, M/2) is the half whose
# popularity drops after the shift.
case "$SCENARIO" in
  disjoint)
    run_scenario data/shift result/shift disjoint_rep disjoint_ghat_variants_windows.csv "0:$M"
    ;;
  reversal)
    run_scenario data/shift result/shift reversal_rep \
      reversal_ghat_variants_windows.csv "0:$(( M / 2 ))"
    ;;
  both)
    run_scenario data/shift result/shift disjoint_rep disjoint_ghat_variants_windows.csv "0:$M"
    run_scenario data/shift result/shift reversal_rep \
      reversal_ghat_variants_windows.csv "0:$(( M / 2 ))"
    ;;
  *)
    echo "unknown scenario '$SCENARIO' (expected disjoint | reversal | both)" >&2
    exit 1
    ;;
esac

echo "=== DONE ==="
