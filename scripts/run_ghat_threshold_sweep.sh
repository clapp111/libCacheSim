#!/usr/bin/env bash
# One-off: Ghat protect-threshold sweep (1-4) across the 5 fixed categories:
# Meta KV, Twitter, Meta CDN, Wikimedia, and Tencent Photo. Expects baseline
# rows (Sieve etc.) to already exist in the *_result.txt files and appends only
# the Ghat threshold runs. Composed externally rather than adding a size-filter
# flag to run_real_trace_sweep.sh.
#
# usage: ./run_ghat_threshold_sweep.sh [small|large]   (default: small)
set -euo pipefail
cd "$(dirname "$0")/.."   # repo root (libCacheSim/)

SIZE_LABEL="${1:-small}"
if [ "$SIZE_LABEL" != "small" ] && [ "$SIZE_LABEL" != "large" ]; then
  echo "usage: $0 [small|large]" >&2
  exit 1
fi

CACHESIM=_build/bin/cachesim
CORPORA=(meta-key twitter meta-cdn wikimedia tencent-photo)
THRESHOLDS=(1 2 3 4)
MAX_JOBS=6

run_job() {
  local corpus="$1" trace="$2" path="$3" size_bytes="$4" th="$5"
  local outfile="result/$corpus/${trace}_result.txt"
  "$CACHESIM" "$path" oracleGeneralBin Ghat "$size_bytes" -e "protect-threshold=$th" -o /dev/null 2>/dev/null \
    | sed "s|^$path|${trace} size=${SIZE_LABEL}|" >> "$outfile"
}

for corpus in "${CORPORA[@]}"; do
  tsv="result/$corpus/working_set_sizes.tsv"
  while IFS=$'\t' read -r trace path large small; do
    [ "$trace" = "trace" ] && continue
    [ -z "$trace" ] && continue
    size_bytes="$small"
    [ "$SIZE_LABEL" = "large" ] && size_bytes="$large"
    for th in "${THRESHOLDS[@]}"; do
      run_job "$corpus" "$trace" "$path" "$size_bytes" "$th" &
      while [ "$(jobs -r -p | wc -l)" -ge "$MAX_JOBS" ]; do
        wait -n
      done
    done
  done < "$tsv"
done
wait

echo "=== DONE ==="
