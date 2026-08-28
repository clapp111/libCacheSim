#!/usr/bin/env bash
# Compute (or refresh) large/small cache-size bytes for every trace of a
# corpus, writing result/<corpus>/working_set_sizes.tsv -- the table
# run_real_trace_sweep.sh reads. Takes a corpus NAME, not trace paths directly: reads
# the corpus's existing working_set_sizes.tsv for its trace/path columns
# (bootstrap a new corpus by creating that TSV with just those two columns
# filled in first), and recomputes large_bytes/small_bytes for every row. The
# table is replaced only after every row succeeds; if any analysis fails, the
# existing table is left unchanged.
#
# For each trace, runs traceAnalyzer with NO analysis flags (no --common,
# no -o -- -o segfaults on this build anyway) from a throwaway scratch
# directory. The requests/objects/obj-GiB summary line is computed
# unconditionally in the main request loop regardless of which analysis
# flags are set, so skipping all of them (--reuse/--size/--popularity/
# --reqRate/--accessPattern, what --common bundles) avoids their memory
# cost entirely -- notably --accessPattern, which buffers an
# unordered_map<obj_id_t, vector<uint32_t>> that grows unboundedly with
# every request to a sampled object and is a common cause of OOM on huge
# traces (confirmed: tencent_photo1/2, ~35GB compressed / likely billions
# of requests, OOM'd a 31GB+15GB swap machine even without --common --
# see obj_map_'s 1e8-slot preallocation/rehash growth instead). The
# scratch dir still guards against traceAnalyzer's side-file behavior in
# case flags are ever added back to this invocation. Prints a "done" line
# after each trace, and a heartbeat every 60s while a trace is still being
# analyzed (these can take a long time on multi-GB traces).
#
# large_bytes/small_bytes = floor(obj_gib * 1073741824 * {0.1, 0.001}) --
# 10% / 0.1% of the trace's unique-object byte total (logical/payload
# capacity), matching the convention the old per-corpus run_*_sweep.sh
# scripts' hardcoded tables used. obj_gib itself is traceAnalyzer's
# "number of obj GiB" figure, printed at 4-decimal precision -- the exact
# byte integer isn't available from its stdout, so this is subject to the
# same rounding as those original tables (negligible at cache-size scale).
#
# usage: ./compute_corpus_cache_sizes.sh <corpus>
#   corpus  e.g. meta-key, wikimedia

set -uo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

ANALYZER="$repo_root/_build/bin/traceAnalyzer"
HEARTBEAT_SEC=60

CORPUS="${1:?usage: $0 <corpus>}"
RESULT_DIR="result/$CORPUS"
mkdir -p "$RESULT_DIR"
TSV="$RESULT_DIR/working_set_sizes.tsv"
if [ ! -f "$TSV" ]; then
  printf 'trace\tpath\tlarge_bytes\tsmall_bytes\n' > "$TSV"
  echo "created empty $TSV -- fill in trace/path rows, then rerun" >&2
  exit 0
fi

traces=()
paths=()
while IFS=$'\t' read -r trace path _large _small; do
  [ "$trace" = "trace" ] && continue   # header
  [ -z "$trace" ] && continue
  traces+=("$trace")
  case "$path" in
    /*) paths+=("$path") ;;
    *)  paths+=("$repo_root/$path") ;;
  esac
done < "$TSV"

tmp_tsv=$(mktemp)
printf 'trace\tpath\tlarge_bytes\tsmall_bytes\n' > "$tmp_tsv"

for i in "${!traces[@]}"; do
  trace="${traces[$i]}"
  trace_path="${paths[$i]}"
  rel_path="${trace_path#"$repo_root"/}"

  echo "=== starting: $trace ($rel_path) ==="
  start_ts=$(date +%s)
  scratch_dir=$(mktemp -d)
  outfile="$scratch_dir/analyzer_stdout.txt"

  (cd "$scratch_dir" && "$ANALYZER" "$trace_path" oracleGeneralBin > "$outfile" 2>&1) &
  pid=$!

  while kill -0 "$pid" 2>/dev/null; do
    sleep "$HEARTBEAT_SEC"
    if kill -0 "$pid" 2>/dev/null; then
      elapsed=$(( $(date +%s) - start_ts ))
      echo "  [heartbeat] still running: $trace (${elapsed}s elapsed)"
    fi
  done
  wait "$pid"
  status=$?
  elapsed=$(( $(date +%s) - start_ts ))

  if [ "$status" -ne 0 ]; then
    echo "!!! FAILED ($trace) after ${elapsed}s, exit code $status -- see output below"
    cat "$outfile"
    rm -rf "$scratch_dir"
    rm -f "$tmp_tsv"
    exit "$status"
  fi

  obj_gib=$(grep -oP "number of obj GiB: \K[0-9.]+" "$outfile")
  rm -rf "$scratch_dir"

  large_bytes=$(awk -v g="$obj_gib" 'BEGIN{printf "%d", g*1073741824*0.1}')
  small_bytes=$(awk -v g="$obj_gib" 'BEGIN{printf "%d", g*1073741824*0.001}')
  printf '%s\t%s\t%s\t%s\n' "$trace" "$rel_path" "$large_bytes" "$small_bytes" >> "$tmp_tsv"

  echo "=== DONE: $trace (${elapsed}s) -- unique_object_total=${obj_gib} GiB, large_bytes=${large_bytes}, small_bytes=${small_bytes} ==="
done

mv "$tmp_tsv" "$TSV"
echo "=== all traces complete -- wrote $TSV ==="
