#!/usr/bin/env bash
# Generic corpus sweep: run every trace in a corpus x every algorithm x
# {large,small} cache size, oracleGeneralBin format. Consolidates the
# per-corpus run_*_sweep.sh scripts (meta-key/meta-cdn/meta-block/
# cloudphysics/msr/wikimedia) into one script driven by a per-corpus cache-
# size table instead of hardcoded per-corpus arrays.
#
# Takes a corpus NAME, not a data directory -- data/meta/ holds three
# distinct corpora (meta-key, meta-cdn, meta-block) sharing one folder, so
# a data-dir argument can't disambiguate which result dir/trace subset to
# use. The corpus name selects result/<corpus>/working_set_sizes.tsv,
# which lists trace label, repo-root-relative trace path, and precomputed
# large/small byte sizes (see compute_corpus_cache_sizes.sh for computing those --
# this script does not compute or update the table, only reads it, so
# adding a new corpus means creating that TSV first).
#
# Unlike the per-corpus scripts (one background job per trace, algo x size
# looped serially inside), this flattens the whole trace x size x algo
# cross product into one job per (trace,size,algo) combo and fills a
# fixed-size worker pool with them -- keeps threads busy even on corpora
# with few traces (e.g. 3 traces x 2 sizes x 5 algos = 30 jobs, not 3).
# Jobs compute concurrently. Each completed result is appended while holding
# an exclusive lock on its <trace>_result.txt, so jobs for the same trace
# cannot interleave their output.
#
# usage: ./run_real_trace_sweep.sh [-j N] [-e "params"] <corpus> [algo1 algo2 ...]
#   -j N       max concurrent jobs (default: 4)
#   -e params  passed verbatim to cachesim's -e/--eviction-params for every
#              job, e.g. -e "ghost-count-ratio=0.5" (default: none, same as
#              omitting -e -- existing algo defaults apply)
#   corpus     e.g. meta-key, meta-cdn, wikimedia
#   algos      defaults to: Ghat Sieve S3FIFO ARC Cacheus

set -euo pipefail
cd "$(dirname "$0")/.."   # repo root (libCacheSim/)

CACHESIM=_build/bin/cachesim

MAX_JOBS=4
EVICTION_PARAMS=""
while getopts "j:e:" opt; do
  case "$opt" in
    j) MAX_JOBS="$OPTARG" ;;
    e) EVICTION_PARAMS="$OPTARG" ;;
    *) echo "usage: $0 [-j N] [-e \"params\"] <corpus> [algo1 algo2 ...]" >&2; exit 1 ;;
  esac
done
shift $((OPTIND - 1))

CORPUS="${1:?usage: $0 [-j N] <corpus> [algo1 algo2 ...]}"
shift
if [ "$#" -gt 0 ]; then
  ALGOS=("$@")
else
  ALGOS=(Ghat Sieve S3FIFO ARC Cacheus)
fi

RESULT_DIR="result/$CORPUS"
TSV="$RESULT_DIR/working_set_sizes.tsv"
if [ ! -f "$TSV" ]; then
  echo "error: $TSV not found -- generate it first (see compute_corpus_cache_sizes.sh)" >&2
  exit 1
fi

declare -A PATH_OF LARGE_BYTES SMALL_BYTES
TRACES=()
while IFS=$'\t' read -r trace path large small; do
  [ "$trace" = "trace" ] && continue   # header
  [ -z "$trace" ] && continue
  TRACES+=("$trace")
  PATH_OF[$trace]="$path"
  LARGE_BYTES[$trace]="$large"
  SMALL_BYTES[$trace]="$small"
done < "$TSV"

run_job() {
  local trace="$1" size_label="$2" size="$3" algo="$4"
  local tracepath="${PATH_OF[$trace]}"
  local outfile="$RESULT_DIR/${trace}_result.txt"
  local extra_args=()
  local result_line
  [ -n "$EVICTION_PARAMS" ] && extra_args=(-e "$EVICTION_PARAMS")
  echo "running $trace size=$size_label($size B) algo=$algo ..."
  result_line=$(
    "$CACHESIM" "$tracepath" oracleGeneralBin "$algo" "$size" "${extra_args[@]}" -o /dev/null 2>/dev/null \
      | sed "s|^$tracepath|${trace} size=${size_label}|"
  )
  if [ -n "$result_line" ]; then
    {
      flock -x 9
      printf '%s\n' "$result_line" >&9
    } 9>>"$outfile"
  fi
}

for trace in "${TRACES[@]}"; do
  touch "$RESULT_DIR/${trace}_result.txt"
done

for trace in "${TRACES[@]}"; do
  for size_label in large small; do
    size=${LARGE_BYTES[$trace]}
    [ "$size_label" = "small" ] && size=${SMALL_BYTES[$trace]}
    for algo in "${ALGOS[@]}"; do
      run_job "$trace" "$size_label" "$size" "$algo" &
      while [ "$(jobs -r -p | wc -l)" -ge "$MAX_JOBS" ]; do
        wait -n
      done
    done
  done
done
wait

echo "=== DONE ==="
wc -l "$RESULT_DIR"/*_result.txt
