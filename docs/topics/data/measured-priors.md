# Measured layout priors from human boards

**TL;DR**
- The cheap learnable signal in human boards is **relational and per-package**, and it can seed soft constraints immediately, with no ML model [I].
- **Decaps (1 nF–1 µF):**
  - median **3.29 mm** from the IC power pad (0402: **2.51 mm**, 95% on the same side);
  - only **17% within 2 mm**;
  - p90 is **7.7 mm on 4-layer** vs **26.0 mm on 2-layer** boards [P, measured].
- **Routing style:** 89% of boards have a GND zone; signal width 0.25 mm, power 0.40 mm, power/signal ratio **1.88** [P, measured].
- **Corpus priors are looser than datasheet guidance.** Use them as *soft* targets conditioned on package and layer count, and datasheet distances as *hard or tight* targets [I].
- The measurement is heuristic: net-name rules and a nearest-same-net-IC-pad proxy, not human-annotated [P].

## Key facts

### Method (note author's measurement)
- **Boards:** all **128 permissively licensed** boards (MIT, Apache-2.0, BSD-3, CC0, CERN-OHL-P, CC-BY) in the circuit-skills manifest, fetched at pinned commits; 110 have ICs.
- **Parser:** a minimal S-expression parser computes absolute pad positions (footprint `at` plus rotated pad offset). The rotation convention was validated: pads land on track ends 66.9% of the time with the chosen sign vs 30.5% with the opposite sign.
- **Decap definition:** a 2-pad `C*` part with one pad on a GND-like net and one on a power-like net (name heuristics).
- **Distance:** cap power-pad centre to the nearest pad of any `U*`/`IC*` on the same net. The script was `decap_stats.py` in the note author's scratchpad.

### Decoupling-distance priors

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

### Routing-style priors (same 128 boards)

| Measure | Value |
|---|---|
| Boards with a GND zone | 114/128 (89%) |
| Median per-board signal track width | 0.25 mm (IQR 0.20–0.25) |
| Power-net width | 0.40 mm (IQR 0.25–0.50) |
| Power/signal width ratio | median **1.88**; 69% of boards >1.2× |

### Comparison points
- **Datasheet and vendor guidance:**
  - Microchip: ≤6 mm trace through a via;
  - Quilter Pin Distance example: 0–1 cm;
  - kicad-happy decap check: caps within 10 mm;
  - TI: "as close as possible".

  See [../llm/function-to-recipe-mapping.md](../llm/function-to-recipe-mapping.md).
- **Ranker evidence:** decap distance carries weight in circuit-skills' learned route-cleanliness ranker (+1.24 per log unit) ([score_study.md](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/score_study.md)) [P, third-party].

## Recommendations for our system

1. **Ship prior tables now** as soft constraints, keyed by (anchor package, pin function, satellite package, layer count, tier): Δx, Δy, Δθ, side, pad-to-pad distance percentiles [I].
2. **Calibrate relation magnitudes** from these tables: e.g. "tight" for a 0402 decap on 4-layer ≈ p25–p50 (about 2.2–2.5 mm). The datasheet bound, if any, overrides it. See [../llm/interfaces-relations-vs-coordinates.md](../llm/interfaces-relations-vs-coordinates.md).
3. **Never learn priors from "all boards"** unconditioned; that encodes the 2-layer hobby tail (p90 26 mm).
4. **Width defaults:** power ≈ 1.9× signal as a soft prior; ampacity calculators override it.
5. **Publish the tables** as CDLA-Permissive-2.0 data products, computed only from tier-A boards (facts, not geometry).
6. **Extend:** relative-pose tables for all satellite types; diff-pair spacing; via counts; plane usage.

## Conflicts and open questions

- The measurement is heuristic and unvalidated against human annotation; 82 boards.
- Nobody has measured whether these priors raise clean-route rates on held-out boards. Coarse hints did not (see [layout-retrieval-and-reuse.md](layout-retrieval-and-reuse.md)).
- Cross-board variance per motif (how consistently the same buck is laid out) is unmeasured.

## Sources
- research notes: [learning_from_layout_data.md § Q3 (measured priors), § Q7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/learning_from_layout_data.md)

See also: [corpora-and-yield.md](corpora-and-yield.md), [imitation-and-learned-scores.md](imitation-and-learned-scores.md), [../rules/decoupling-pdn.md](../rules/decoupling-pdn.md)
