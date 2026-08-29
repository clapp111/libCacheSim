# Trace corpora

This directory is the local entry point for the trace corpora used by the
experiments. Large trace files are ignored by Git and are typically provided
through local symbolic links.

| Directory | Type | Contents |
| --- | --- | --- |
| `meta-key` | KV |Meta key-value cache traces |
| `twitter` | KV |Twitter key-value cache traces |
| `meta-cdn` | CDN |Meta CDN request traces |
| `tencent` | CDN |Tencent photo/CDN request traces |
| `wikimedia` | CDN |Wikimedia request traces |
| `cloudphysics` | Block |CloudPhysics block-storage traces |
| `shift` | Synthetic |Synthetic Disjoint and Reversal abrupt-shift traces |

The datasets are not distributed with this repository. Obtain them under
their applicable licenses and create local links as needed.
