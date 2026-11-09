# Joint place-and-route experiments (pnr lab)

Scope: experiment log and method index of the pnr lab (own Freerouting-free place-and-route engine, 33 A/B boards); one line + link per method. Mechanism, numbers and provenance live on the method pages in [research/joint](../../research/joint/README.md). Not here: kae's own joint loop -> [kae-joint-loop](../../research/joint/kae-joint-loop.md). [M] = measured by the pnr scripts.
Keys: pnr, joint place-and-route, halo grid, negotiated-congestion router, FFT legal-position maps, seq, seq_phys, anneal, anneal_phys, grow, beam, combo, combo_lv, combo_full, jc, jc_lv, jc_frozen, joint collapse, negotiate, grad, soft-min routing gradient, Physarum, LLM move proposer, seq_margin, CP-SAT windows, Numberlink, Terms.delta, RoutedPhys, score v7, v7-bugs, silk_overlap, solder_mask_bridge, starved_thermal

## Setup and eras

- Suites ab33 / phys10 / dev6, 120 CPU-s per board, KiCad 10.0.7; eras v5 (place tasks, mostly 1 seed), v7 (joint tasks, engine v6.3, 3 seeds), xf3 (engine 4c4330a) → [eras and caveats](../../research/joint/README.md#eras-and-caveats). Compare only runs of one engine version.
- Engine versions v5 → v6.4 and legality calibration (22 → 12 of 33 human placements "illegal") → [engine versions](../../research/joint/engine.md#engine-versions).
- Objectives (length + vias, fast physics `Terms.delta`, full physics `RoutedPhys` at gates) and the three scores on every run → [physics-objective](../../research/joint/physics-objective.md#results).
- Harness bugs found (relative `--command` paths, locked footprints staged off-board, joint methods unscorable; each fixed in a separate commit) → [harness lessons](../../research/joint/README.md#harness-and-engine-lessons).

## Method index

| method | one-line result [M] | page |
|---|---|---|
| engine, `route_only` | human placements routed clean 0.85 (A) / 0.50 (B) in 2–8 s vs tuned Freerouting 0.62 / 0.35 at ≤ 600 s | [engine](../../research/joint/engine.md#results) |
| `seq`, `seq_margin`, `grow` | control; room alone and greedy place-one-route-it do not help | [sequential-controls](../../research/joint/sequential-controls.md) |
| physics place terms (`seq_phys`, `anneal_phys`) | HPWL placements 4.05× human place physics; physics term → 1.52× at no routability cost | [physics-objective](../../research/joint/physics-objective.md) |
| `anneal`, `repair`, `cpsat` | annealing on routed cost and blocker repair work as stages; CP-SAT windows beat the heuristic 0 of 112 | [anneal-and-repair](../../research/joint/anneal-and-repair.md) |
| `beam`, `mcts` | beam keeps alternatives across steps (completion 0.891 vs 0.868 at equal CPU); MCTS gets too few rollouts | [tree-search](../../research/joint/tree-search.md) |
| `combo` (beam → repair → physics anneal) | best v5 pipeline; −13% copper, −54% vias (v7); clean gain within seed noise | [combo](../../research/joint/combo.md) |
| `grad`, Physarum, tension, bloat | continuous forces do not beat HPWL; `grad_phys post=phys` best v5 routed physics | [forces-and-fields](../../research/joint/forces-and-fields.md) |
| LLM move proposer | gain = legality fixes a rule would make; physics ~110× behind `seq_phys` | [llm-proposer](../../research/joint/llm-proposer.md) |
| `negotiate`, `jc`, `jc2` | jc best family; joint vs frozen 0.52× copper on 24/24 boards | [jc](../../research/joint/jc.md) |
| layer-collapse bounds, assignment, terms | no merit; narrow partial results | [layer-collapse-analysis](../../research/joint/layer-collapse-analysis.md) |
| harmonic, learned value, QD, min-plus, exact physics maps | none clearly beat jc | [jc-extensions](../../research/joint/jc-extensions.md) |
| pours, pour-damage maps (`pjc2`) | routed physics 1.05× vs jc 1.18× human, to confirm | [pour-models](../../research/joint/pour-models.md#pour-damage-maps-in-jc-t4) |
| transformations T1–T12, untested catalog ideas | untested | [untested-ideas](../../research/joint/untested-ideas.md) |

Verdict per idea: [scorecard](../../ideas/original/scorecard.md). Merit arms in the 500-board comparison: [merit list](../../research/joint/README.md#merit-list).

## What limits clean pass

DRC types no method's objective sees (`silk_overlap`, `solder_mask_bridge`, `starved_thermal`, `shorting_items`, unenterable 0.5 mm-pitch pads), each traced to placement crowding → [engine verdict](../../research/joint/engine.md#verdict).

## Use in kae

- Make physics a first-class term in every placement objective (`Terms.delta` ~50 µs per move); score routed physics on the final copper. HPWL alone gives electrically wrong boards that route well → [physics-objective](../../research/joint/physics-objective.md#verdict).
- Use `combo` as the baseline to beat ([mcts.py](../../../tools/research/pnr_mcts/mcts.py), [methods_combo.py](../../../tools/research/pnr/methods_combo.py)) → [combo](../../research/joint/combo.md).
- Put every DRC type that blocks clean into the search score: silkscreen, mask apertures, spoke room. Clean depends on these, not on wirelength.
- Use LLMs for diagnosis and structure (blocked parts, connector-to-edge), not move-by-move proposals → [llm-proposer](../../research/joint/llm-proposer.md#verdict).

## Sources

- Code: [tools/research/pnr/](../../../tools/research/pnr/) and `pnr_<tag>/` per experiment; agent brief [AGENT_BRIEF.md](../../../tools/research/pnr/AGENT_BRIEF.md); bug log [v7-bugs.md](../../../tools/research/pnr/results/v7-bugs.md); baselines [v7-baselines.md](../../../tools/research/pnr/results/v7-baselines.md); suite [v7-ab33](../../../tools/research/pnr/suites/v7-ab33.txt); drivers [scripts/](../../../tools/research/pnr/scripts/).
- Ideas: [joint-pnr ideas](../../ideas/original/joint-pnr.md); survey: [literature-survey](../../../research_notes/joint-pnr/literature-survey.md).
- Harness: [harness.md](../verification/harness.md).
