# Quantifying "looks right": layout regularity and convention metrics

**TL;DR**
- "Looks right" means concrete regularities:
  - like parts in one orientation, pin-1s aligned, memories in a matrix;
  - parts and labels on grids and straight lines; text in at most two directions;
  - compact power loops; tight, ordered decoupling;
  - short, uncrossed airwires; traces leaving pad centres;
  - identical channel layouts.
- Every one of these heuristics can be computed from a KiCad board and netlist. The metric definitions below are proposals and are uncalibrated.
- Neatness is necessary but not sufficient. Neat long parallel runs cause crosstalk, so every neatness term must be paired with a coupling penalty.
- HPWL and crossings alone "are indifferent between a sensible layout and a scattered one" (KRT), so convention and intent metrics are needed on top.
- No dataset links aesthetics to SI/EMC outcomes or reviewer acceptance, so weights need calibration on expert-rated boards.

## Key facts

Tags: [P] primary; [I] inference. Practitioner quotes: [P/C] community opinion.

### Source heuristics

- **Olney:**
  - "Similar types of components should be aligned on the board in the same orientation".
  - "orient pin 1 on all IC components the same".
  - Memory chips "in a clearly defined matrix".
  - Grid of 100 mil for large parts and 25 mil for chip parts.
  - Flag nets "longer than the Manhattan length or spiral around the board three times" [P].
- **SparkFun:**
  - Frame on a 0.1" grid at (0,0); "All parts are placed on a 0.005" grid. If possible, use a .05" grid".
  - "Route with straight lines and 45 degree corners only … T-intersections are okay".
  - "Traces should enter and exit center of pad".
  - "Makes sure labels are on a straight line" ([SparkFun](https://learn.sparkfun.com/tutorials/how-to-sell-your-widget-on-sparkfun/designing-for-sparkfun-manufacture)) [P].
- **Checklist repos:**
  - grosdode: polarized parts "in the same direction or in a repeatable pattern".
  - jnoss and henrikh: legend in one or two directions; designators ordered by layout; traces exit pad ends.
  - Pikafu: 5 mil origin grid; caps' power nets facing the same way [P].
- **Altium (Harris):** "All designators are only in one or two orientations"; "Each designator is close to and clearly identifies the associated component" [P].
- **Flux:** 90° corners are not an SI issue below ~25 GHz on a 20.5 mil trace. Bend style is a DFM/aesthetic question [P]. That holds for single-ended nets below about 2 Gb/s; bend rules still apply to differential pairs and ≥10 Gb/s nets ([../rules/myths-and-contested.md](../rules/myths-and-contested.md)).
- **Practitioners:**
  - Two 45° turns, not "10~30 small ones".
  - Any-angle output is painful to re-route by hand.
  - "random thick traces" are a red flag.
  - "'which way is up' is an unsolved problem".
  - "readability is king!!" [P/C].

### Proposed metrics

| Heuristic (sources) | Metric | Computation (KiCad board + netlist) |
|---|---|---|
| Consistent orientation (grosdode, jnoss, henrikh, Olney) | Orientation entropy per part class | H = −Σ p(θ) log p(θ) over {0, 90, 180, 270} for same-footprint parts within a block; for polarized parts, fraction in the modal direction |
| Pin-1 alignment (Olney) | Pin-1 direction agreement | Fraction of ICs whose pin-1 vector matches the board's modal direction |
| Grid alignment (grosdode, Pikafu, SparkFun, Olney) | Grid-snap ratio | Fraction of footprint origins on grid g (25/50/100 mil or 1/1.27 mm) within ε; separately for vias and 0.1" headers |
| Rows/columns (KiCad align tools, SparkFun labels) | Collinearity score | Clusters of equal x or y centres among same-class parts or labels |
| Minimal, uncrossed airwires (KiCad GS, KiCad forum) | HPWL + crossing count | Half-perimeter or MST wirelength per net; pairwise MST-edge crossings |
| No scenic routes (Olney, Altium) | Manhattan ratio | Routed length ÷ Manhattan (or MST) length per net; flag outliers |
| Compact power loops (Feranec, TI) | Hot-loop area; SW-node area | Polygon area through role-tagged loop pads; SW-net copper area |
| Decap tightness and order (azonenberg, Pikafu, Feranec, UWARG) | Distance and rank order | Cap-pad to IC-pin path length; Spearman correlation of estimated mounting inductance (package, via count, via-to-pad distance) vs distance. Value order ("smallest closest") is CONTESTED, so score it only behind the contested-rule selector ([../rules/decoupling-pdn.md](../rules/decoupling-pdn.md)) |
| Text orientation (henrikh, jnoss, Altium) | Text-direction count | Number of readable directions (target ≤2); bottom text mirrored |
| Geographic designators (henrikh, jnoss) | Rank correlation | Spearman correlation of designator number vs row-major position per prefix |
| Pad-exit style (jnoss, grosdode, SparkFun) | Off-centre/side-exit count | Track endpoints not at pad centre, or attaching on the long side between same-net adjacent pins |
| Neatness vs crosstalk (Olney) | Parallel-run length | Coupled length between non-pair nets on the same or adjacent layers (kicad-happy grid method) |
| Channel symmetry (KiCad multichannel) | Layout congruence | RMS pose deviation of target vs reference channels after the isomorphism map |
| Signal flow (Pikafu, henrikh) | Flow monotonicity | Fraction of inter-block edges pointing "forward" from input to output connectors |
| Clean geometry (practitioners) | Turn count / wiggle; any-angle fraction | Bends per routed length; fraction of non-45° segments [I] |
| Power-width foresight (practitioners) | Width consistency on power nets | Min/max width along each power net vs declared current [I] |
| Orientation conventions (practitioners) | Connector edge-facing; "up" consistency | Connector mating face toward board edge; text/part "up" agreement [I] |

### Existing implementations (tool heuristics, not standards)

kicad-happy ([methodology_pcb.md](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/scripts/methodology_pcb.md)) [P]:
- decap proximity: a C within 10 mm of a U, sharing a net, on the same side;
- tombstoning copper ratio min/max (<0.3 high, 0.3–0.6 medium);
- a trace-proximity grid for coupling length;
- per-net layer-transition analysis.

KiCad supports regularity directly with Align/Distribute and multichannel Repeat Layout [P].

## Recommendations for our system

- **Compute these metrics in T0** (microseconds per move) as a "convention score". Use it as a soft objective and as a review diagnostic, never as a gate ([evaluation-stack.md](evaluation-stack.md)) [I].
- **Pair every neatness term with a coupling-length penalty** [I].
- **Make thresholds and targets a per-company style profile**: grids, allowed angles, orientation conventions, silk rules. Quilter: "'looks right' varies by company" [I].
- **Calibrate weights against expert-rated boards** via blind review ([benchmark-plan.md](benchmark-plan.md)) [I].

## Conflicts and open questions

- Kleinstein says readability is unnecessary if the board works; Phil's Lab and Quilter say convention decides acceptance. This trade-off is unquantified.
- There is no empirical study of aesthetics vs measured performance or reviewer acceptance, and no human-rated aesthetics dataset.

## Sources

- research notes: [expert_workflow_and_checklists.md § Q6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md)
- research notes: [practitioner_discussions.md § Q4a](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/practitioner_discussions.md)
- research notes: [constraints_verification_benchmarks.md § Q3 (KRT critique)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md)

See also: [../workflow/what-good-looks-like.md](../workflow/what-good-looks-like.md), [quality-metrics.md](quality-metrics.md)
