# Concrete data pipeline plan: scrape, qualify, label, train, evaluate

Scope: the planned end-to-end data pipeline from discovery to evaluation (synthesis plan from the data note; yields extrapolated from samples of 22–1,183 boards, a full run is needed) [I]. Not here: what was actually built -> [research/data/board-corpus](../../research/data/board-corpus.md); recipe evidence -> [training-recipes](training-recipes.md); ranker evidence -> [imitation-and-learned-scores](imitation-and-learned-scores.md).
Keys: data pipeline, manifest fields, ref_open, qualification, auto-labelling, outcome-labelled placement sets, training order, evaluation splits, baselines, ablations

## Targets and principles [I]

- Targets: ≈2–5k licence-clear, fully routed boards; ≈500–1,000 DRC-clean; ≈300–800 with 4+ layers.
- Order: corpus-derived priors and retrieval first (no training) → small pose and assignment model → LLM SFT on round-trip-verified constraint graphs → GRPO/DPO.
- The router is the label oracle throughout; a bounded real route is the acceptance gate ([imitation-and-learned-scores](imitation-and-learned-scores.md#which-placement-measures-predict-a-clean-route)).
- Evidence behind the plan: qualification yield 235/423, 33% DRC-clean ([corpora-and-yield](corpora-and-yield.md#circuit-skills-licensed-corpus-most-rigorous-public-collector)); relative/pin-name code 82% vs raw KiCad 32% ([training-recipes](training-recipes.md#representation-results)); designer 0.56 vs auto 0.12–0.16 clean ([imitation-and-learned-scores](imitation-and-learned-scores.md)); priors 0402 decap median 2.5 mm, 4-layer p90 7.7 mm, power/signal width 1.88, 89% GND zone ([measured-priors](measured-priors.md)).

## 1. Scrape (discovery)

- Sources: kicad-happy `repos.md` (5,822 pinned); open-schematics `name` field; circuit-skills-style GitHub queries (topics kicad, kicad-pcb, oshw, open-hardware; language "KiCad Layout"); PCBench sources (842 repos, 62% unlicensed); the OSHWA list; Adafruit and SparkFun Eagle via KiCad's importer (log conversion DRC separately).
- Storage: pointers + SHA-256 in the repo; payloads in a git-ignored cache.

## 2. Manifest and licence tiers

- Fields: `repo, sha, path, blob, spdx (LICENSE + README + scancode), tier, kicad_version, layers, parts, pads, connections, ref_drv (own rules, error severity), bare_drv, ref_open, has_pro/dru, stars, first_commit_date, category`.
- Tiers A/B/C + opt-out list -> [licensing-tiers-and-contamination](licensing-tiers-and-contamination.md#licence-tiers-i).

## 3. Clean and qualify

- `kicad-cli pcb upgrade`; **refuse** legacy constructs the parser doesn't handle (legacy `(module …)` in 41% of one sample); pours count as copper [P, third-party].
- Require `ref_open == 0` for routing-imitation data. Keep `ref_drv` as a **quality weight**, not a hard filter (a hard filter shrinks the corpus ≈3×).
- Dedup by git blob; cluster by footprint-multiset Jaccard + netlist WL hash; ≤2 boards per repo.
- Adopt each board's own `(setup …)` and `.kicad_dru` rules when scoring against the human.

## 4. Label automatically (data products)

1. Subcircuit instances: rule detectors + WL/gSpan motif mining over the *PCB* netlist (avoids cross-sheet blind spots).
2. Relative-pose tables per (anchor package, pin function, satellite package): Δx, Δy, Δθ, side, pad-to-pad distance; percentiles by layer count and tier ([measured-priors](measured-priors.md)).
3. Routing-style tables: width by net function, plane usage, via counts, diff-pair spacing.
4. Module partition and module-to-edge graphs.
5. Round-trip-verified constraint graphs in an anchor-relative DSL ([training-recipes](training-recipes.md#synthetic-generators-in-order-of-value-i)).
6. Outcome-labelled placement sets per board (designer, swap25, swap100, σ-calibrated jitter, auto placers), each routed under a fixed budget and DRC-judged: ranker and DPO data, and a benchmark.

Published data products: CDLA-Permissive-2.0, tier A only.

## 5. Train, in order

| Step | Content |
|---|---|
| 0 (no training) | retrieval (WL filter → GNN rerank → max-weight-clique fragment selection) + prior tables as soft solver constraints; the LLM cites fragments and their licences -> [layout-retrieval-and-reuse](layout-retrieval-and-reuse.md) |
| 1 (small models) | DevFormer-style relative-pose and **assignment** model; pairwise ranker on outcome-labelled sets (board-grouped CV, σ controls), tie-breaker only |
| 2 | LLM SFT (7–20B LoRA, distilled CoT): netlist + board context in, anchor-relative constraint DSL out; decontaminate against eval clusters. Teacher/base-model terms -> [training-recipes](training-recipes.md#training-order) |
| 3 | GRPO/DAPO, tiered reward (parse → legality → completion + optimality, + β ranker) ([reward template](training-recipes.md#reward-template-verireasonfoarl-style)); VeriReason and CodeV-R1 prompt filters; groups of 4–5 out of 16–36; Best-of-N with router and DRC at inference |
| 4 | a few hundred expert A/B rankings → ModuPlace-style ranker or DPO; switch to DPO if hacking appears |

## 6. Evaluate

- Splits: time-split, cluster-split, private boards ([contamination controls](licensing-tiers-and-contamination.md#contamination)); strata by layers and tier.
- Baselines: designer, swap25/swap100, rules-only constraints with the same solver, existing auto placers, frontier LLMs zero-shot.
- Metrics: clean-route rate and connections routed under a fixed router budget; error-level DRC; HPWL and via ratio vs designer; prior-table compliance; a blind expert-preference subset.
- Ablations: rules vs priors vs pose model vs LLM constraint graphs; retrieval on/off; SFT vs +GRPO.
- Contamination probes: Min-K%-style on test-board fragments (open-weight only; weak evidence) [I]; popular vs obscure splits.

## Open questions

- Yields are extrapolations; a full run is needed.
- Round-trip "equivalence" tolerance needs calibration.
- How much expert preference data is needed is unknown.

## Sources

- research notes: [learning_from_layout_data.md § Q8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/learning_from_layout_data.md)
- related: [../verification/benchmarks.md](../verification/benchmarks.md)
