# Concrete data pipeline plan: scrape, qualify, label, train, evaluate

**TL;DR**
- **Targets:** about 2–5k licence-clear, fully routed boards; about 500–1,000 DRC-clean; about 300–800 with 4+ layers [I].
- **Ship corpus-derived priors and retrieval first** (no training). Then a small pose and assignment model, then LLM SFT on round-trip-verified constraint graphs, then GRPO/DPO [I].
- **The router is the label oracle throughout;** a bounded real route is the acceptance gate [I].
- **Evaluate** on time- and cluster-split held-out boards against designer, swap and auto baselines, with a rules-vs-learned A/B [I].
- This is a synthesis plan from the data note. Yields are extrapolated from small samples and need a full pipeline run [I].

## Key facts
Evidence underpinning the plan; detail lives in the linked docs.
- **Qualification recipe and yields:** 235 boards from 423 candidate repos; 33% DRC-clean (circuit-skills) [P, third-party]. See [corpora-and-yield.md](corpora-and-yield.md).
- **Pitfalls:** legacy `(module …)` in 41% of one sample; pours count as copper; adopt each board's own rules [P, third-party].
- **Representation:** relative/pin-name code 82% vs raw KiCad 32% [P]. See [training-recipes.md](training-recipes.md).
- **Learned scores** don't beat HPWL on small corpora; designer 0.56 vs auto 0.12–0.16 clean [P, third-party]. See [imitation-and-learned-scores.md](imitation-and-learned-scores.md).
- **Measured priors:** 0402 decap median 2.5 mm; 4-layer p90 7.7 mm; power/signal width 1.88; 89% GND zone [P, measured]. See [measured-priors.md](measured-priors.md).

## Recommendations for our system

### 1. Scrape (discovery)
- **Sources:**
  - kicad-happy `repos.md` (5,822 pinned);
  - open-schematics `name` field;
  - circuit-skills-style GitHub queries (topics kicad, kicad-pcb, oshw, open-hardware; language "KiCad Layout");
  - PCBench sources (842 repos, 62% unlicensed);
  - the OSHWA list;
  - Adafruit and SparkFun Eagle via KiCad's importer (log conversion DRC separately).
- **Storage:** pointers plus SHA-256 in the repo; payloads in a git-ignored cache.

### 2. Manifest and licence tiers
- **Fields:** `repo, sha, path, blob, spdx (LICENSE + README + scancode), tier, kicad_version, layers, parts, pads, connections, ref_drv (own rules, error severity), bare_drv, ref_open, has_pro/dru, stars, first_commit_date, category`.
- **Tiers:** A for training, B for attributed retrieval and evaluation, C for private evaluation only; plus an opt-out list. See [licensing-tiers-and-contamination.md](licensing-tiers-and-contamination.md).

### 3. Clean and qualify
- Run `kicad-cli pcb upgrade`; **refuse** legacy constructs the parser doesn't handle.
- Require `ref_open == 0` for routing-imitation data. Keep `ref_drv` as a **quality weight**, not a hard filter (a hard filter shrinks the corpus about 3×).
- Dedup by git blob; cluster by footprint-multiset Jaccard plus netlist WL hash; at most 2 boards per repo.
- Adopt each board's own `(setup …)` and `.kicad_dru` rules when scoring against the human.

### 4. Label automatically (data products)
1. **Subcircuit instances** from rule detectors plus WL/gSpan motif mining over the *PCB* netlist, which avoids cross-sheet blind spots.
2. **Relative-pose tables** per (anchor package, pin function, satellite package): Δx, Δy, Δθ, side, pad-to-pad distance; percentiles by layer count and tier.
3. **Routing-style tables:** width by net function, plane usage, via counts, diff-pair spacing.
4. **Module partition and module-to-edge graphs.**
5. **Round-trip-verified constraint graphs** in an anchor-relative DSL.
6. **Outcome-labelled placement sets** per board (designer, swap25, swap100, σ-calibrated jitter, auto placers), each routed under a fixed budget and DRC-judged. These serve as ranker and DPO data and as a benchmark.

Published data products: CDLA-Permissive-2.0, from tier A only.

### 5. Train, in order
- **Step 0 (no training):** retrieval (WL filter → GNN rerank → max-weight-clique fragment selection) plus prior tables as soft solver constraints. The LLM cites fragments and their licences. See [layout-retrieval-and-reuse.md](layout-retrieval-and-reuse.md).
- **Step 1 (small models):**
  - a DevFormer-style relative-pose and **assignment** model;
  - a pairwise ranker on the outcome-labelled sets with board-grouped CV and σ controls, used only as a tie-breaker.
- **Step 2:** LLM SFT (7–20B LoRA, distilled CoT). Netlist plus board context in, anchor-relative constraint DSL out; decontaminate against eval clusters.
- **Step 3:** GRPO/DAPO with a tiered reward (parse → legality → completion + optimality, + β ranker). VeriReason and CodeV-R1 prompt filters; groups of 4–5 out of 16–36; Best-of-N with router and DRC at inference.
- **Step 4:** a few hundred expert A/B rankings → a ModuPlace-style ranker or DPO; switch to DPO if hacking appears.

### 6. Evaluate
- **Splits:** time-split (first commit after model cutoff), cluster-split, private boards; strata by layers and tier.
- **Baselines:** designer, swap25/swap100, rules-only constraints with the same solver, existing auto placers, frontier LLMs zero-shot.
- **Metrics:** clean-route rate and connections routed under a fixed router budget; error-level DRC; HPWL and via ratio vs designer; prior-table compliance; a blind expert-preference subset.
- **Ablations:** rules vs priors vs pose model vs LLM constraint graphs; retrieval on/off; SFT vs +GRPO.
- **Contamination probes:** Min-K%-style tests on test-board fragments; popular vs obscure splits.

## Conflicts and open questions

- Yields are extrapolations from samples of 22–1,183 boards; a full run is needed.
- The round-trip "equivalence" tolerance needs calibration.
- How much expert preference data is needed is unknown.

## Sources
- research notes: [learning_from_layout_data.md § Q8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/learning_from_layout_data.md)

See also: [corpora-and-yield.md](corpora-and-yield.md), [training-recipes.md](training-recipes.md), [../verification/benchmarks.md](../verification/benchmarks.md)
