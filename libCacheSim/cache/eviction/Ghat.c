//  Ghat.c
//  libCacheSim
//
//  Resident objects are kept in insertion order, and evicted object IDs are
//  kept in a bounded FIFO ghost history. A resident hit increments the
//  object's frequency up to Ghat_PROTECT_THRESHOLD. During eviction, objects
//  at or above the threshold are reset to zero and skipped; the first object
//  below the threshold is evicted. A ghost hit causes the object to be
//  reinserted at the protection threshold instead of zero.
//
//  Ghost capacity is the current resident-object count multiplied by
//  ghost-count-ratio.

#include <stdlib.h>

#include "dataStructure/hashtable/hashtable.h"
#include "libCacheSim/evictionAlgo.h"

#ifdef __cplusplus
extern "C" {
#endif

// Number of resident hits required to reach protection. Defaults to 2 and is
// overridable via the "protect-threshold" cache parameter. This value is
// file-static and shared by every Ghat cache instance in the process.
static int32_t Ghat_PROTECT_THRESHOLD = 2;

// A Ghost entry stores only an object ID and links for the hash chain and
// FIFO. It stores neither object size nor payload.
typedef struct Ghat_entry {
  obj_id_t           obj_id;
  struct Ghat_entry *hash_next;
  struct Ghat_entry *fifo_prev;
  struct Ghat_entry *fifo_next;
} Ghat_entry_t;

typedef struct {
  cache_obj_t *q_head;
  cache_obj_t *q_tail;
  cache_obj_t *pointer;

  // Ghost: independent lightweight FIFO + chained hashtable, decoupled
  // from libCacheSim's byte-accounted cache_t machinery.
  Ghat_entry_t **ghost_bucket;
  int64_t        ghost_n_bucket;
  Ghat_entry_t   *ghost_head;  // oldest -- next to trim
  Ghat_entry_t   *ghost_tail;  // newest
  int64_t        ghost_n_obj;
  double         ghost_count_ratio;

  bool hit_on_ghost;

  /* hand-sweep instrumentation; see cache_get_sweep_stats_func_ptr */
  int64_t n_demote;
  int64_t n_evict;
} Ghat_params_t;

static const char *DEFAULT_CACHE_PARAMS = "ghost-count-ratio=1.0";

#define Ghat_INITIAL_GHOST_N_BUCKET 1024

// ***********************************************************************
// ****                                                               ****
// ****                   function declarations                       ****
// ****                                                               ****
// ***********************************************************************
static void         Ghat_free(cache_t *cache);
static bool          Ghat_get(cache_t *cache, const request_t *req);
static cache_obj_t  *Ghat_find(cache_t *cache, const request_t *req,
                               bool update_cache);
static cache_obj_t  *Ghat_insert(cache_t *cache, const request_t *req);
static cache_obj_t  *Ghat_to_evict(cache_t *cache, const request_t *req);
static void          Ghat_evict(cache_t *cache, const request_t *req);
static bool          Ghat_remove(cache_t *cache, obj_id_t obj_id);
static void          Ghat_get_sweep_stats(const cache_t *cache,
                                          int64_t *n_demote, int64_t *n_evict);
static int64_t       Ghat_get_n_protected(const cache_t *cache,
                                          cache_obj_filter_func_ptr filter,
                                          void *filter_ctx);
static void          Ghat_parse_params(cache_t *cache,
                                       const char *cache_specific_params);
static void          Ghat_verify(cache_t *cache);

// Ghost: independent lightweight FIFO + hashtable helpers.
static uint64_t      Ghat_ghost_hash(obj_id_t obj_id);
static Ghat_entry_t  *Ghat_ghost_find(Ghat_params_t *params, obj_id_t obj_id);
static void          Ghat_ghost_resize(Ghat_params_t *params);
static void          Ghat_ghost_insert(Ghat_params_t *params, obj_id_t obj_id);
static void          Ghat_ghost_remove_entry(Ghat_params_t *params,
                                             Ghat_entry_t *entry);
static void          Ghat_ghost_trim(cache_t *cache);
static void          Ghat_ghost_free_all(Ghat_params_t *params);

// ***********************************************************************
// ****                                                               ****
// ****            Ghost: independent lightweight FIFO + hashtable    ****
// ****                                                               ****
// ***********************************************************************

static uint64_t
Ghat_ghost_hash(obj_id_t obj_id) {
  uint64_t h = (uint64_t)obj_id;
  h ^= h >> 33;
  h *= 0xff51afd7ed558ccdULL;
  h ^= h >> 33;
  h *= 0xc4ceb9fe1a85ec53ULL;
  h ^= h >> 33;
  return h;
}

static Ghat_entry_t *
Ghat_ghost_find(Ghat_params_t *params, obj_id_t obj_id) {
  uint64_t idx = Ghat_ghost_hash(obj_id) & (params->ghost_n_bucket - 1);
  Ghat_entry_t *entry = params->ghost_bucket[idx];

  while (entry != NULL) {
    if (entry->obj_id == obj_id) return entry;
    entry = entry->hash_next;
  }

  return NULL;
}

static void
Ghat_ghost_resize(Ghat_params_t *params) {
  int64_t new_n_bucket = params->ghost_n_bucket * 2;
  Ghat_entry_t **new_bucket =
      (Ghat_entry_t **)calloc(new_n_bucket, sizeof(Ghat_entry_t *));

  for (int64_t i = 0; i < params->ghost_n_bucket; i++) {
    Ghat_entry_t *entry = params->ghost_bucket[i];
    while (entry != NULL) {
      Ghat_entry_t *next = entry->hash_next;
      uint64_t idx = Ghat_ghost_hash(entry->obj_id) & (new_n_bucket - 1);
      entry->hash_next = new_bucket[idx];
      new_bucket[idx]  = entry;
      entry            = next;
    }
  }

  free(params->ghost_bucket);
  params->ghost_bucket   = new_bucket;
  params->ghost_n_bucket = new_n_bucket;
}

static void
Ghat_ghost_insert(Ghat_params_t *params, obj_id_t obj_id) {
  Ghat_entry_t *entry = (Ghat_entry_t *)malloc(sizeof(Ghat_entry_t));
  entry->obj_id = obj_id;

  uint64_t idx = Ghat_ghost_hash(obj_id) & (params->ghost_n_bucket - 1);
  entry->hash_next          = params->ghost_bucket[idx];
  params->ghost_bucket[idx] = entry;

  entry->fifo_next = NULL;
  entry->fifo_prev = params->ghost_tail;
  if (params->ghost_tail != NULL) {
    params->ghost_tail->fifo_next = entry;
  } else {
    params->ghost_head = entry;
  }
  params->ghost_tail = entry;

  params->ghost_n_obj++;
  if (params->ghost_n_obj > params->ghost_n_bucket) {
    Ghat_ghost_resize(params);
  }
}

static void
Ghat_ghost_remove_entry(Ghat_params_t *params, Ghat_entry_t *entry) {
  uint64_t idx = Ghat_ghost_hash(entry->obj_id) & (params->ghost_n_bucket - 1);
  Ghat_entry_t **slot = &params->ghost_bucket[idx];
  while (*slot != entry) slot = &(*slot)->hash_next;
  *slot = entry->hash_next;

  if (entry->fifo_prev != NULL) {
    entry->fifo_prev->fifo_next = entry->fifo_next;
  } else {
    params->ghost_head = entry->fifo_next;
  }
  if (entry->fifo_next != NULL) {
    entry->fifo_next->fifo_prev = entry->fifo_prev;
  } else {
    params->ghost_tail = entry->fifo_prev;
  }

  params->ghost_n_obj--;
  free(entry);
}

static void
Ghat_ghost_trim(cache_t *cache) {
  Ghat_params_t *params = (Ghat_params_t *)cache->eviction_params;
  int64_t ghost_capacity =
      (int64_t)((double)cache->get_n_obj(cache) * params->ghost_count_ratio);

  while (params->ghost_n_obj > ghost_capacity) {
    Ghat_entry_t *oldest = params->ghost_head;
    if (oldest == NULL) break;
    Ghat_ghost_remove_entry(params, oldest);
  }
}

static void
Ghat_ghost_free_all(Ghat_params_t *params) {
  Ghat_entry_t *entry = params->ghost_head;
  while (entry != NULL) {
    Ghat_entry_t *next = entry->fifo_next;
    free(entry);
    entry = next;
  }
  free(params->ghost_bucket);
}

// ***********************************************************************
// ****                                                               ****
// ****                   end user facing functions                   ****
// ****                                                               ****
// ****                       init, free, get                         ****
// ***********************************************************************

cache_t *Ghat_init(const common_cache_params_t ccache_params,
                   const char *cache_specific_params) {
  cache_t *cache =
      cache_struct_init("Ghat", ccache_params, cache_specific_params);
  cache->cache_init = Ghat_init;
  cache->cache_free = Ghat_free;
  cache->get        = Ghat_get;
  cache->find       = Ghat_find;
  cache->insert     = Ghat_insert;
  cache->evict      = Ghat_evict;
  cache->remove     = Ghat_remove;
  cache->to_evict   = Ghat_to_evict;
  cache->get_n_protected = Ghat_get_n_protected;
  cache->get_sweep_stats = Ghat_get_sweep_stats;

  if (ccache_params.consider_obj_metadata) {
    cache->obj_md_size = 1;
  } else {
    cache->obj_md_size = 0;
  }

  cache->eviction_params = malloc(sizeof(Ghat_params_t));
  memset(cache->eviction_params, 0, sizeof(Ghat_params_t));
  Ghat_params_t *params      = (Ghat_params_t *)cache->eviction_params;
  params->pointer           = NULL;
  params->q_head            = NULL;
  params->q_tail            = NULL;
  params->hit_on_ghost      = false;
  params->ghost_count_ratio = 1.0;

  Ghat_parse_params(cache, DEFAULT_CACHE_PARAMS);
  if (cache_specific_params != NULL) {
    Ghat_parse_params(cache, cache_specific_params);
  }

  params->ghost_n_bucket = Ghat_INITIAL_GHOST_N_BUCKET;
  params->ghost_bucket =
      (Ghat_entry_t **)calloc(params->ghost_n_bucket, sizeof(Ghat_entry_t *));
  params->ghost_head  = NULL;
  params->ghost_tail  = NULL;
  params->ghost_n_obj = 0;

  snprintf(cache->cache_name, CACHE_NAME_ARRAY_LEN, "Ghat-%d-%.4lf",
           Ghat_PROTECT_THRESHOLD, params->ghost_count_ratio);

  return cache;
}

static void Ghat_free(cache_t *cache) {
  Ghat_params_t *params = (Ghat_params_t *)cache->eviction_params;
  Ghat_ghost_free_all(params);
  free(cache->eviction_params);
  cache_struct_free(cache);
}

static bool Ghat_get(cache_t *cache, const request_t *req) {
  bool ck_hit = cache_get_base(cache, req);
  return ck_hit;
}

// ***********************************************************************
// ****                                                               ****
// ****       developer facing APIs (used by cache developer)         ****
// ****                                                               ****
// ***********************************************************************

static cache_obj_t *Ghat_find(cache_t *cache, const request_t *req,
                              bool update_cache) {
  Ghat_params_t *params   = (Ghat_params_t *)cache->eviction_params;
  cache_obj_t *cache_obj = cache_find_base(cache, req, update_cache);

  if (cache_obj != NULL) {
    if (update_cache) {
      // A resident hit increments frequency by one, capped at the protection
      // threshold. When the hand encounters an object at the threshold, it
      // resets the frequency to zero and advances to the next queue entry.
      if (cache_obj->sieve.freq < Ghat_PROTECT_THRESHOLD) {
        cache_obj->sieve.freq += 1;
      }
    }
    return cache_obj;
  }

  // On a resident-cache miss, a real access checks the Ghost history and
  // consumes a matching entry.
  if (update_cache) {
    Ghat_entry_t *ghost_entry = Ghat_ghost_find(params, req->obj_id);
    if (ghost_entry != NULL) {
      Ghat_ghost_remove_entry(params, ghost_entry);
      params->hit_on_ghost = true;
    }
  }

  return NULL;
}

static cache_obj_t *Ghat_insert(cache_t *cache, const request_t *req) {
  Ghat_params_t *params = (Ghat_params_t *)cache->eviction_params;

  cache_obj_t *obj = cache_insert_base(cache, req);
  prepend_obj_to_head(&params->q_head, &params->q_tail, obj);

  // A Ghost hit reinserts the object at the protection threshold. An object
  // without a Ghost hit starts at frequency zero.
  obj->sieve.freq      = params->hit_on_ghost ? Ghat_PROTECT_THRESHOLD : 0;
  params->hit_on_ghost = false;

  Ghat_ghost_trim(cache);

  return obj;
}

// Finds the first object below the protection threshold, starting at the
// current hand position and falling back to the queue tail. Returns NULL if
// every resident object is protected.
static cache_obj_t *Ghat_to_evict(cache_t *cache, const request_t *req) {
  Ghat_params_t *params = (Ghat_params_t *)cache->eviction_params;
  cache_obj_t *pointer  = params->pointer;

  if (pointer == NULL) pointer = params->q_tail;

  while (pointer != NULL && pointer->sieve.freq >= Ghat_PROTECT_THRESHOLD) {
    pointer = pointer->queue.prev;
  }

  if (pointer == NULL) {
    pointer = params->q_tail;
    while (pointer != NULL && pointer->sieve.freq >= Ghat_PROTECT_THRESHOLD) {
      pointer = pointer->queue.prev;
    }
  }

  return pointer;
}

static void Ghat_evict(cache_t *cache, const request_t *req) {
  Ghat_params_t *params = (Ghat_params_t *)cache->eviction_params;

  // The hand resets each protected object to zero and advances, then evicts
  // the first object below the protection threshold.
  cache_obj_t *obj = params->pointer == NULL ? params->q_tail : params->pointer;
  while (obj->sieve.freq >= Ghat_PROTECT_THRESHOLD) {
    obj->sieve.freq = 0;
    params->n_demote++;
    obj = obj->queue.prev == NULL ? params->q_tail : obj->queue.prev;
  }
  params->n_evict++;

  params->pointer = obj->queue.prev;
  remove_obj_from_list(&params->q_head, &params->q_tail, obj);

  // Preserve the evicted object's identity in Ghost before it is freed.
  Ghat_ghost_insert(params, obj->obj_id);

  cache_evict_base(cache, obj, true);
}

static void Ghat_remove_obj(cache_t *cache, cache_obj_t *obj_to_remove) {
  DEBUG_ASSERT(obj_to_remove != NULL);
  Ghat_params_t *params = (Ghat_params_t *)cache->eviction_params;
  if (obj_to_remove == params->pointer) {
    params->pointer = obj_to_remove->queue.prev;
  }
  remove_obj_from_list(&params->q_head, &params->q_tail, obj_to_remove);
  cache_remove_obj_base(cache, obj_to_remove, true);
}

static bool Ghat_remove(cache_t *cache, obj_id_t obj_id) {
  Ghat_params_t *params = (Ghat_params_t *)cache->eviction_params;

  cache_obj_t *obj = hashtable_find_obj_id(cache->hashtable, obj_id);
  if (obj != NULL) {
    Ghat_remove_obj(cache, obj);
    return true;
  }

  Ghat_entry_t *ghost_entry = Ghat_ghost_find(params, obj_id);
  if (ghost_entry != NULL) {
    Ghat_ghost_remove_entry(params, ghost_entry);
    return true;
  }

  return false;
}

// Counts resident objects whose frequency is at or above the protection
// threshold. Under the default threshold of 2, frequency 1 is excluded. If a
// filter is provided, only matching resident objects are counted. Ghost
// entries are not counted. Neither the hand nor any frequency is modified.
static int64_t Ghat_get_n_protected(const cache_t *cache,
                                    cache_obj_filter_func_ptr filter,
                                    void *filter_ctx) {
  Ghat_params_t *params = (Ghat_params_t *)cache->eviction_params;
  int64_t n_protected = 0;

  for (cache_obj_t *obj = params->q_head; obj != NULL; obj = obj->queue.next) {
    if (obj->sieve.freq >= Ghat_PROTECT_THRESHOLD &&
        (filter == NULL || filter(obj, filter_ctx))) {
      n_protected++;
    }
  }

  return n_protected;
}

// Cumulative hand-sweep counters, read-only. n_demote counts protected
// objects reset to zero, and n_evict counts resident-object evictions.
static void Ghat_get_sweep_stats(const cache_t *cache, int64_t *n_demote,
                                 int64_t *n_evict) {
  Ghat_params_t *params = (Ghat_params_t *)cache->eviction_params;
  *n_demote = params->n_demote;
  *n_evict = params->n_evict;
}

static void Ghat_parse_params(cache_t *cache,
                              const char *cache_specific_params) {
  Ghat_params_t *params = (Ghat_params_t *)cache->eviction_params;

  char *params_str     = strdup(cache_specific_params);
  char *old_params_str = params_str;

  while (params_str != NULL && params_str[0] != '\0') {
    char *key   = strsep((char **)&params_str, "=");
    char *value = strsep((char **)&params_str, ",");

    while (params_str != NULL && *params_str == ' ') {
      params_str++;
    }

    if (strcasecmp(key, "ghost-count-ratio") == 0) {
      params->ghost_count_ratio = strtod(value, NULL);
    } else if (strcasecmp(key, "protect-threshold") == 0) {
      Ghat_PROTECT_THRESHOLD = (int32_t)strtol(value, NULL, 10);
    } else if (strcasecmp(key, "print") == 0) {
      printf("parameters: ghost-count-ratio=%.4lf, protect-threshold=%d\n",
             params->ghost_count_ratio, Ghat_PROTECT_THRESHOLD);
      exit(0);
    } else {
      ERROR("%s does not have parameter %s\n", cache->cache_name, key);
      exit(1);
    }
  }

  free(old_params_str);
}

static void Ghat_verify(cache_t *cache) {
  Ghat_params_t *params = (Ghat_params_t *)cache->eviction_params;
  int64_t n_obj = 0, n_byte = 0;
  cache_obj_t *obj = params->q_head;

  while (obj != NULL) {
    assert(hashtable_find_obj_id(cache->hashtable, obj->obj_id) != NULL);
    n_obj++;
    n_byte += obj->obj_size;
    obj = obj->queue.next;
  }

  assert(n_obj == cache->get_n_obj(cache));
  assert(n_byte == cache->get_occupied_byte(cache));
}

#ifdef __cplusplus
}
#endif
