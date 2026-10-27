# Research area: data

The benchmark and the measured priors need open boards: boards we may fetch, whose licences we
have read, and whose layouts KiCad 10 can load. This area records how the board corpus was
built and what we measured on it. Boards are never committed; only manifests, scripts and
summaries are (see [licensing tiers](../../topics/data/licensing-tiers-and-contamination.md)).

| Path | Status | One-line result | Page | Code |
|---|---|---|---|---|
| Wide open-board corpus: licence audit, robots policy, stats, DRC | worked (data infrastructure) | 14,318 boards from 8,757 repos; 2,449 (17%) DRC-clean as committed under their own rules | [board-corpus](board-corpus.md) | [tools/research/board-sourcing](../../../tools/research/board-sourcing/README.md) |
| Near-duplicate removal by content fingerprint (MinHash/LSH) | worked | 1,637 revisions, forks and mirrors dropped; ~600 near-empty boards excluded | [board-corpus](board-corpus.md#near-duplicate-removal) | `sig.py` |
| Making foreign and old boards load in KiCad 10 | worked | Eagle 2,472, Altium 419, Allegro 32, PADS 14 imported; every accepted row loads | [board-corpus](board-corpus.md#import-and-load-fixes) | not ported (harness changes on the sourcing branch) |
| Benchmark candidate set (first pass, 297 boards) | worked | 112 boards qualify on KiCad 10.0.7 | [open-board-sources](../../topics/data/open-board-sources.md), [harness](../../topics/verification/harness.md) | `bench/manifests/candidates.jsonl` |
| Decap-to-IC distance priors on 128 permissive boards | worked (measurement) | median 3.29 mm; p90 7.7 mm on 4-layer vs 26.0 mm on 2-layer | [measured-priors](../../topics/data/measured-priors.md) | [tools/research/layout-data](../../../tools/research/layout-data/) |

Untested data ideas (planted-solution boards, git-history repair pairs, inverse optimization from
edits) are in [ideas](../ideas.md#learning-and-data-l).

Related areas: [placement](../placement/README.md) and [physics](../physics/README.md) use the
corpus for priors and physics passports. The [research overview](../README.md) explains the status
words.
