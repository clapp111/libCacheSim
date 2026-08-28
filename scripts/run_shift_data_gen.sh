#!/usr/bin/env bash
#
# Regenerate one of the two abrupt-shift workloads:
#   disjoint: switch from hot-set A to a disjoint hot-set B
#   reversal: keep the same objects but reverse their popularity ranks
#
# Traces are generated with a fixed seed per rep (--seed matching the rep
# number for phase A) so a rerun of this script reproduces the same traces.
#
# usage: ./run_shift_data_gen.sh <disjoint|reversal> [n_reps]
#   n_reps defaults to 100

set -euo pipefail
cd "$(dirname "$0")/.."   # repo root (libCacheSim/)

PYTHON=.venv/bin/python3
if [ ! -x "$PYTHON" ]; then
  echo "missing $PYTHON -- create the project virtual environment first" >&2
  exit 1
fi

DATA_DIR=data/shift
mkdir -p "$DATA_DIR"

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "usage: $0 <disjoint|reversal> [n_reps]" >&2
  exit 1
fi

SCENARIO=$1
N_REPS=${2:-100}

case "$SCENARIO" in
  disjoint|reversal) ;;
  *)
    echo "unknown scenario: $SCENARIO (expected disjoint or reversal)" >&2
    exit 1
    ;;
esac

if ! [[ "$N_REPS" =~ ^[1-9][0-9]*$ ]]; then
  echo "n_reps must be a positive integer: $N_REPS" >&2
  exit 1
fi

# --- trace generation params (single source of truth) ---
M=10000              # objects per phase
N_PHASE=200000        # requests per phase (total per trace = 2 * N_PHASE)
ALPHA=1.0
SHIFT_START=10000         # disjoint phase-B start; set to M so there is no gap
POST_SEED_OFFSET=1000000  # keeps reversal phase B independent of phase A

echo "=== regenerating $N_REPS $SCENARIO traces (m=$M, n/phase=$N_PHASE, alpha=$ALPHA) ==="
TMP_DIR=$(mktemp -d "$DATA_DIR/.${SCENARIO}.XXXXXX")
trap 'rm -rf -- "$TMP_DIR"' EXIT
for ((rep = 1; rep <= N_REPS; rep++)); do
  trace="$TMP_DIR/${SCENARIO}_rep${rep}.txt"
  if [ "$SCENARIO" = "disjoint" ]; then
    "$PYTHON" scripts/data_gen.py -m "$M" -n "$N_PHASE" --alpha "$ALPHA" \
      --shift-n "$N_PHASE" --shift-start "$SHIFT_START" --seed "$rep" \
      > "$trace"
  else
    "$PYTHON" scripts/data_gen.py -m "$M" -n "$N_PHASE" --alpha "$ALPHA" \
      --start 0 --seed "$rep" > "$trace"
    "$PYTHON" scripts/data_gen.py -m "$M" -n "$N_PHASE" --alpha "$ALPHA" \
      --start 0 --seed "$((rep + POST_SEED_OFFSET))" \
      | awk -v m="$M" '{print (m - 1) - $1}' >> "$trace"
  fi
  echo "  rep $rep/$N_REPS done"
done

rm -f -- "$DATA_DIR"/"${SCENARIO}"_rep*.txt
mv -- "$TMP_DIR"/"${SCENARIO}"_rep*.txt "$DATA_DIR"/
rmdir "$TMP_DIR"
trap - EXIT
echo "done: $(find "$DATA_DIR" -maxdepth 1 -type f -name "${SCENARIO}_rep*.txt" | wc -l) traces"
