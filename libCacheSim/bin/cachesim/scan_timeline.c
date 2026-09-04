#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>

#include "cache_init.h"
#include "libCacheSim/cache.h"
#include "libCacheSim/reader.h"

/* Half-open object-id range [lo, hi), used to single out the objects a
 * shift experiment renders obsolete (Disjoint) or demotes (Reversal).
 * The range lives here, not in any eviction algorithm, so that no
 * algorithm carries knowledge of the shift workloads. */
typedef struct {
  obj_id_t lo;
  obj_id_t hi;
} id_range_t;

static bool obj_id_in_range(const cache_obj_t *obj, void *ctx) {
  const id_range_t *range = (const id_range_t *)ctx;
  return obj->obj_id >= range->lo && obj->obj_id < range->hi;
}

/* How many objects of the target range the cache still holds -- the
 * retention left after a scan has swept through.
 *
 * Walking cache->hashtable would be both wrong and not portable: ARC leaves
 * its B1/B2 ghost entries in that table (it evicts with
 * remove_from_hashtable=false and marks them obj->ARC.ghost), while S3FIFO
 * and LIRS keep no objects there at all -- theirs live in sub-caches. The
 * one residency test every algorithm implements is its own find(), so the
 * range is probed id by id instead. update_cache=false keeps the probe
 * side-effect-free: each find confines its mutations to the update_cache
 * branch, and for the ghost-bearing algorithms it is also what separates a
 * cached object from a ghost entry.
 *
 * This costs hi - lo lookups, which is why the caller runs it on a single
 * window rather than on every one. */
static int64_t count_target_resident(cache_t *cache, const id_range_t *range) {
  request_t *probe = new_request();
  int64_t n_resident = 0;
  for (obj_id_t id = range->lo; id < range->hi; id++) {
    probe->obj_id = id;
    if (cache->find(cache, probe, false) != NULL) {
      n_resident++;
    }
  }
  free_request(probe);
  return n_resident;
}

/* One CSV row per window. The protected-state columns are emitted only
 * when a target id range was given; algorithms with no notion of
 * protected objects report -1. */
static void print_window(const char *algo, int64_t window_idx, int64_t win_req,
                         int64_t win_miss, const cache_t *cache,
                         id_range_t *target, int64_t n_target_resident,
                         const int64_t *sweep_delta) {
  printf("%s,%ld,%ld,%ld,%.4f", algo, (long)window_idx, (long)win_req,
         (long)win_miss, (double)win_miss / (double)win_req);

  if (target != NULL) {
    int64_t n_protected = -1, n_target_protected = -1;
    if (cache->get_n_protected != NULL) {
      n_protected = cache->get_n_protected(cache, NULL, NULL);
      n_target_protected =
          cache->get_n_protected(cache, obj_id_in_range, target);
    }
    printf(",%ld,%ld,%ld,%ld", (long)cache->get_n_obj(cache),
           (long)n_protected, (long)n_target_protected,
           (long)n_target_resident);
  }

  if (sweep_delta != NULL) {
    printf(",%ld,%ld,%ld,%ld", (long)sweep_delta[0], (long)sweep_delta[1],
           (long)sweep_delta[2], (long)cache->get_hand_distance(cache));
  }

  printf("\n");
}

/* count_target_resident on the one requested window, -1 everywhere else. */
static int64_t resident_count_for(cache_t *cache, const id_range_t *target,
                                  int64_t resident_window,
                                  int64_t window_idx) {
  if (target == NULL || window_idx != resident_window) {
    return -1;
  }
  return count_target_resident(cache, target);
}

/* Turns the cache's cumulative sweep counters into this window's delta. */
static void update_sweep_delta(const cache_t *cache, bool want_sweep,
                               int64_t *prev, int64_t *delta) {
  if (!want_sweep) {
    return;
  }
  int64_t now[3];
  cache->get_sweep_stats(cache, &now[0], &now[1]);
  now[2] = cache->get_n_hand_wrap(cache);
  for (int i = 0; i < 3; i++) {
    delta[i] = now[i] - prev[i];
    prev[i] = now[i];
  }
}

/* Reports miss ratio per fixed-size request window, instead of a single
 * trace-wide summary -- used by the abrupt-shift experiments over traces
 * under data/shift/. */
int main(int argc, char **argv) {
  if (argc < 6) {
    fprintf(stderr,
            "usage: %s trace_path trace_type eviction_algo cache_size "
            "window_size [eviction_params] [target_id_range] [sweep] "
            "[resident_window]\n"
            "  trace_type: only txt is supported\n"
            "  target_id_range: lo:hi, half-open; adds the columns\n"
            "                   n_obj,n_protected,n_target_protected,"
            "n_target_resident\n"
            "  sweep: literal \"sweep\"; adds per-window columns\n"
            "         n_demote,n_evict,n_hand_wrap,hand_distance "
            "(hand-sweep algorithms only)\n"
            "  resident_window: window index at which to count the target\n"
            "         range's resident objects into n_target_resident; the\n"
            "         column is -1 on every other window. Needs\n"
            "         target_id_range. One window only -- the count probes\n"
            "         the whole range, so it is far more expensive than the\n"
            "         other columns.\n"
            "  pass \"\" for an earlier optional argument to reach a later "
            "one\n",
            argv[0]);
    return 1;
  }

  const char *trace_path = argv[1];
  const char *trace_type_str = argv[2];
  const char *eviction_algo = argv[3];
  uint64_t cache_size = strtoull(argv[4], NULL, 10);
  int64_t window_size = strtoll(argv[5], NULL, 10);
  const char *eviction_params = argc > 6 ? argv[6] : NULL;
  const char *target_id_range = argc > 7 ? argv[7] : NULL;
  const bool want_sweep = argc > 8 && strcasecmp(argv[8], "sweep") == 0;
  /* -1 disables the count; window indices start at 0 */
  const int64_t resident_window =
      (argc > 9 && argv[9][0] != '\0') ? strtoll(argv[9], NULL, 10) : -1;

  /* let callers pass "" for eviction_params when they only want the range */
  if (eviction_params != NULL && eviction_params[0] == '\0') {
    eviction_params = NULL;
  }
  if (target_id_range != NULL && target_id_range[0] == '\0') {
    target_id_range = NULL;
  }

  id_range_t target;
  id_range_t *target_ptr = NULL;
  if (target_id_range != NULL) {
    const char *sep = strchr(target_id_range, ':');
    if (sep == NULL) {
      fprintf(stderr, "target_id_range must be lo:hi, got %s\n",
              target_id_range);
      return 1;
    }
    target.lo = strtoull(target_id_range, NULL, 10);
    target.hi = strtoull(sep + 1, NULL, 10);
    target_ptr = &target;
  }

  if (resident_window >= 0 && target_ptr == NULL) {
    fprintf(stderr, "resident_window needs a target_id_range\n");
    return 1;
  }

  if (strcasecmp(trace_type_str, "txt") != 0) {
    fprintf(stderr, "unsupported trace_type %s (only txt is supported)\n",
            trace_type_str);
    return 1;
  }

  reader_init_param_t reader_init_params;
  memset(&reader_init_params, 0, sizeof(reader_init_params));
  reader_init_params.ignore_size_zero_req = true;
  reader_init_params.obj_id_is_num = true;
  reader_init_params.cap_at_n_req = -1;

  reader_t *reader =
      setup_reader(trace_path, PLAIN_TXT_TRACE, &reader_init_params);
  cache_t *cache =
      create_cache(trace_path, eviction_algo, cache_size, eviction_params, false);

  if (want_sweep &&
      (cache->get_sweep_stats == NULL || cache->get_n_hand_wrap == NULL ||
       cache->get_hand_distance == NULL)) {
    fprintf(stderr, "%s has no hand sweep to report\n", eviction_algo);
    return 1;
  }

  request_t *req = new_request();
  int64_t win_req = 0, win_miss = 0, window_idx = 0;
  /* cumulative counters read straight off the cache; the CSV carries the
   * per-window delta so rows stay independent of where a run started */
  int64_t prev_sweep[3] = {0, 0, 0}, sweep_delta[3];
  int64_t *sweep_ptr = want_sweep ? sweep_delta : NULL;

  printf("algo,window_idx,req_in_window,miss_in_window,miss_ratio");
  if (target_ptr != NULL) {
    printf(",n_obj,n_protected,n_target_protected,n_target_resident");
  }
  if (want_sweep) {
    printf(",n_demote,n_evict,n_hand_wrap,hand_distance");
  }
  printf("\n");

  read_one_req(reader, req);
  while (req->valid) {
    win_req++;
    if (cache->get(cache, req) == false) {
      win_miss++;
    }
    if (win_req == window_size) {
      update_sweep_delta(cache, want_sweep, prev_sweep, sweep_delta);
      print_window(eviction_algo, window_idx, win_req, win_miss, cache,
                   target_ptr, resident_count_for(cache, target_ptr,
                                                  resident_window, window_idx),
                   sweep_ptr);
      window_idx++;
      win_req = 0;
      win_miss = 0;
    }
    read_one_req(reader, req);
  }
  if (win_req > 0) {
    update_sweep_delta(cache, want_sweep, prev_sweep, sweep_delta);
    print_window(eviction_algo, window_idx, win_req, win_miss, cache,
                 target_ptr, resident_count_for(cache, target_ptr,
                                                resident_window, window_idx),
                 sweep_ptr);
  }

  free_request(req);
  cache->cache_free(cache);
  close_reader(reader);

  return 0;
}
