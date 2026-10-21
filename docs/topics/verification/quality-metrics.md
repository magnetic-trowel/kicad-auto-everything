# Layout quality metrics beyond DRC

**TL;DR**
- Published metrics fall into three layers:
  - **legality and connectivity**: Clean Pass, NRR/PRR, open and short rates, DRC violations by cause;
  - **efficiency**: wirelength, vias, layers, runtime;
  - **physics checks (Quilter PRCs)**: pin distance, layer switches, ground-plane overlap, length mismatch, uncoupled spacing, overheated length.
- There is one published human-likeness metric, OmniRouting's Multi-Scale Graph Similarity (MGS). It measures agreement with the expert reference, not correctness, so use it only as a diagnostic.
- Human reference boards are not perfect (OmniRouting human NRR 93.58%). Score humans on the same metrics and normalize against them.
- HPWL and crossings cannot tell a sensible layout from a scattered one, so add intent conformance and convention metrics.
- No validated figure of merit links any score to lab EMC/SI/thermal outcomes.

## Key facts

Tags: [P] primary; [S] snippet/secondary; [V] vendor; [I] inference.

| Source | Metrics and definitions | Tag |
|---|---|---|
| PCBWorld | **CP** (Clean Pass: fully connected and 0 error-level DRVs); **Potential gain** Φ over unconnected, DRV, WL and vias; Routability; DRV; WL; Via; Time; Parse-fail. @5 = best of five rollouts by Φ, with Time averaged over all rollouts. DRC is re-run on saved boards against each board's own rules ([METRICS.md](https://github.com/LGAI-Research/PCBWorld/blob/main/docs/METRICS.md)) | [P] |
| OmniRouting | **PR** (load and schema success); **NRR** (% of expected nets connected and DRC-clean); **PRR** (% of the Σ(\|Pₙ\|−1) minimum pad connections routed and clean; missing outputs stay in denominators); **Open / PShort / NShort** (PShort counts only different-net wire–wire and via–wire contacts); **Clr./Dist.** violation counts by cause; **Polygon** (copper-pour use); **TWL**; **#Vias**; **#Layers**; **RT** ([arXiv 2608.04434](https://arxiv.org/html/2608.04434v1)) | [P] |
| OmniRouting MGS | Predicted and reference routings become pad-aware, layer-specific graphs at coarse (corridor/topology) and fine (geometry) resolution, with coarse weighted more. Measures agreement with the expert reference, **not correctness** | [P] |
| OmniRouting human reference | NRR 93.58%, PRR 95.91%, Open 4.38%, PShort 0.38%, Clr. 0.80 | [P] |
| Quilter candidates | % pins routed; DRC count (candidates with DRC errors are not surfaced); sides; layers; min trace width; clearance; via and drill used; via count. PRCs carry explicit pass criteria and units, e.g. Pin Distance 0–1 cm, Overheated Length 0–10% ([candidate details](https://docs.quilter.ai/candidate-review/candidate-details)) | [V] |
| Cypress (ISPD '25) | Placement quality = routability: % of routed pin pairs using **Freerouting v1.9.0 with two free copper layers at default settings**; also routed track length and runtime | [P] |
| RL_PCB | HPWL, Euclidean WL, overlap, post-route WL vs a simulated-annealing baseline | [P] |
| KiCadRoutingTools | "crossings and hpwl … are indifferent between a sensible layout and a scattered one", which motivates floorplan-intent grading ([floorplan-intent.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/floorplan-intent.md)) | [P] |
| Freerouting v2.5.0 scores (VK) | Router score `V2_CONTINUOUS` = max(0, 1000 − W1·o1 − W2·o2 − W_C·N_viol/D − W_D·ΣL_um/(U·D)), open fraction split at F = 0.5 with W1 ≈ 333.3 and W2 ≈ 666.7, and D = max(1, pins × signal layers). Optimizer score `V2_LOWER_BOUND` measures copper efficiency against placement-derived bounds; incomplete nets and DRC hits are vetoes. `normalized_score` is 0–1000 ([scoring.md](https://github.com/freerouting/freerouting/blob/master/docs/scoring.md)) | [P] |
| Quilter blog | Routing metrics without first-pass yield or bring-up data do not prove boards work | [S] |
| Practitioners | "how to calculate a figure of merit for an attempt at a PCB, which is a necessary step in reinforcement learning" (AndyC_772); AI needs "a clear definition of a correct vs incorrect classification" (TheHeintzel) | [P] |

### Recommended union metric set

| Layer | Metrics |
|---|---|
| Gates | PR/loadable; LVS parity; CP |
| Routing | NRR, PRR, Open/PShort/NShort, DRV by cause, TWL, vias, layers, RT |
| Placement | HPWL, overlap, out-of-bounds, net crossings, net separation, Freerouting-based routability (Cypress protocol), intent conformance |
| Physics PRCs | Pin distance, layer-switch count, ground-plane overlap, length mismatch, uncoupled spacing, overheated length, return-path violations, IR-drop margin |
| Human-relative | MGS-style graph similarity; WL, via and HPWL ratios to the human board |

## Recommendations for our system

- Adopt the union set above. Report human scores on every metric and normalize, because human boards are themselves not 100% clean. PCBWorld keeps only boards that were DRV-free after conversion [I].
- Use MGS as a diagnostic of human-likeness, never as an optimization objective: valid alternative routes score low on it [I].
- Add these metrics from the workflow and practitioner research [I]:
  - checklist Critical/Major pass counts ([review-checklist.md](review-checklist.md));
  - convention score ([looks-right-metrics.md](looks-right-metrics.md));
  - blind expert acceptance and review time;
  - edits outside the requested scope;
  - determinism (same inputs → same board hash);
  - human setup minutes;
  - agreement between the agent's predicted and actual outcomes.
- Expose Freerouting's `normalized_score` and optimizer score to the LLM as compact routing feedback [I].

## Conflicts and open questions

- No human-rated aesthetic or "expert acceptability" dataset exists.
- No published score correlates with lab EMC/SI/thermal results; any composite needs calibration on real boards.
- The full Cypress paper is closed-access; its per-design tables are unread.

## Sources

- research notes: [constraints_verification_benchmarks.md § Q3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md)
- research notes: [practitioner_discussions.md § Q2c, Q5 Gaps](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/practitioner_discussions.md)
- corrections: [verification_kicad_and_tools.md § 4 Freerouting](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)

See also: [benchmarks.md](benchmarks.md), [benchmark-plan.md](benchmark-plan.md), [looks-right-metrics.md](looks-right-metrics.md)
