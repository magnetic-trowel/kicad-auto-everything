# Measured layout priors from human boards

Scope: decoupling-distance and routing-style priors measured on 128 permissive human boards, and how to use them as soft constraints. Not here: decoupling physics and datasheet rules -> [../rules/decoupling-pdn.md](../rules/decoupling-pdn.md); relation vocabulary -> [../llm/interfaces-relations-vs-coordinates.md](../llm/interfaces-relations-vs-coordinates.md).
Keys: decap distance, decoupling prior, same side, GND zone, track width, power/signal ratio, decap_stats.py, prior tables, soft constraint

## Method (note author's measurement)

- Boards: all **128 permissively licensed** boards (MIT, Apache-2.0, BSD-3, CC0, CERN-OHL-P, CC-BY) in the circuit-skills manifest, fetched at pinned commits; 110 have ICs. Licences GitHub-detected, unaudited (`minuet`, recorded MIT, has CERN-OHL-W hardware; [open-board-sources](open-board-sources.md#open-questions)).
- Parser: minimal S-expression parser; absolute pad position = footprint `at` + rotated pad offset. Rotation sign validated: pads land on track ends 66.9% with the chosen sign vs 30.5% with the opposite.
- Decap: 2-pad `C*` part, one pad on a GND-like net, one on a power-like net (name heuristics).
- Distance: Euclidean, cap power-pad centre → centre of nearest pad of any `U*`/`IC*` on the same net. 1 nF–1 µF filter applied after the script. Script: [`tools/research/layout-data/decap_stats.py`](../../../tools/research/layout-data/decap_stats.py).

## Decoupling-distance priors

| Slice | n | Median (mm) | Other stats |
|---|---|---|---|
| 1 nF–1 µF, all | 809 caps / 82 boards | **3.29** | p10 1.55, p25 2.21, p75 5.75, p90 15.1; 17% ≤2 mm, 44% ≤3 mm, 70% ≤5 mm; 85% same side |
| exactly 100 nF | 637 | 3.44 | — |
| 0402 | — | **2.51** | p90 4.93; 63% ≤3 mm; 95% same side |
| 0603 | — | 3.10 | long tail, p90 64.6 (likely loads not named U) |
| 0805 | — | 3.73 | only 54% same side |
| 4-layer boards | — | 3.12 | **p90 7.7**; 97% same side |
| 2-layer boards | — | 3.60 | **p90 26.0**; 77% same side |
| Per-board medians | — | 2.82 (median of medians) | IQR 2.22–4.75 |
| Designer routing DRC-clean vs not | — | — | p90 7.7 vs 17.7 mm |
| By GitHub stars (<100 / 100–1k / >1k) | — | 3.35 / 3.28 / 2.96 | stars barely matter |
| Bulk caps >1 µF | 398 | 5.33 | p90 34 |

## Routing-style priors (same 128 boards)

| Measure | Value |
|---|---|
| Boards with a GND zone | 114/128 (89%) |
| Median per-board signal track width | 0.25 mm (IQR 0.20–0.25) |
| Power-net width | 0.40 mm (IQR 0.25–0.50) |
| Power/signal width ratio | median **1.88**; 69% of boards >1.2× |

## Comparison points

- Datasheet and vendor guidance: Microchip ≤6 mm trace through a via; Quilter Pin Distance example 0–1 cm; kicad-happy decap check: caps within 10 mm; TI "as close as possible". These measure other things (Microchip: trace length; Quilter: closest pin edges): convert our centre-to-centre distances before comparing -> [../llm/function-to-recipe-mapping.md](../llm/function-to-recipe-mapping.md).
- Ranker evidence: decap distance weighs +1.24 per log unit in circuit-skills' route-cleanliness ranker ([imitation-and-learned-scores](imitation-and-learned-scores.md#which-placement-measures-predict-a-clean-route)) [P, third-party].

## Using the priors [I]

The cheap learnable signal in human boards is relational and per-package; it seeds soft constraints now, without an ML model. Corpus priors are looser than datasheet guidance.

1. Ship prior tables now as soft constraints keyed by (anchor package, pin function, satellite package, layer count, tier): Δx, Δy, Δθ, side, pad-to-pad distance percentiles.
2. Calibrate relation magnitudes: "tight" for a 0402 decap ≈ p25–p50 of its slice. No 0402 × 4-layer slice measured yet; all-package p25 = 2.21 mm, 0402 median (all layer counts) = 2.51 mm, both centre-to-centre. A datasheet bound, if any, overrides: datasheet distances are *tight* targets scoped to that part; single-vendor millimetre numbers are soft objectives, not DRC.
3. Never learn priors from "all boards" unconditioned: that encodes the 2-layer hobby tail (p90 26 mm).
4. Width default: power ≈ 1.9× signal as a soft prior; ampacity calculators override.
5. Publish the tables as CDLA-Permissive-2.0 data products from tier-A boards only (facts, not geometry).
6. Extend: relative-pose tables for all satellite types; diff-pair spacing; via counts; plane usage.

## Open questions

- Heuristic, unvalidated against human annotation; 82 boards.
- Nobody has measured whether these priors raise clean-route rates on held-out boards; coarse hints did not ([layout-retrieval-and-reuse](layout-retrieval-and-reuse.md#how-much-do-coarse-human-derived-constraints-transfer)).
- Cross-board variance per motif (how consistently the same buck is laid out) unmeasured.

## Sources

- research notes: [learning_from_layout_data.md § Q3 (measured priors), § Q7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/learning_from_layout_data.md)
