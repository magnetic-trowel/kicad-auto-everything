# Why autorouted boards get rejected: failure modes and measurable checks

**TL;DR**
- Experts cite: too many vias; wasted space from strict X/Y layer bias; cleanup slower than manual routing; setup complexity ("too many rules can bog it down"); blindness to intent (current, noise, return paths, clocks, analog); and a **bottom-up, one-connection-at-a-time process that clashes with top-down planning**.
- "Ugly" has two causes: **legality/completion failures** (fix with better engines + DRC loops) and **intent failures** (fix with explicit constraints and relational intent from a planner).
- Vendors answered with guided automation (sketch routing, topological maps, flow/bundle planning, byte-lane tuning) that needs a human to draw — an LLM that **generates the sketch/flow plan from schematic semantics** fills exactly that gap.
- Humans optimize structure, not just length: PCBWorld's human boards are longer with more vias than Freerouting's, yet are the gold standard.

## Key facts

**Practitioner and vendor statements**
- Barry Olney (PCB Design, 2015): "the majority will say that they do not use them because they do not work"; early autorouters "added too many vias, wasted space due to the strict XY bias"; a weekend mainframe run "50% complete by Monday morning"; remedy = constraints up front (stackup with uninterrupted return paths, via spans, SI/PI, FPGA pin swapping, placement); "too many rules can also bog it down"; sketch router reuses fanouts and "gloss[es]" routes ([PDF](https://www.icd.com.au/articles/Autorouters_PCBD-Nov2015.pdf) [P]).
- Altium history (2016): no SI guidance, excessive vias, strict X/Y grid, fixing took longer than manual; engineers plan "at 10,000 feet" and sketch buses on paper, autorouters work "from the bottom up, one interconnect at a time"; route-planning tools took longer to configure than manual routing ([article](https://resources.altium.com/p/to-autoroute-or-not-to-autoroute-a-history-of-failed-design-automation) [P/V]).
- Siemens (2015, 2023): "intimidation factor" of setup, cleanup time, too many vias, lack of expert elegance; sketch routing — designer draws a path, reuses existing fanout vias, adds no vias; hug router "push[es], shove[s], and squeak[s]" the last nets ([white paper](https://resources.sw.siemens.com/en-US/white-paper-a-stroke-of-genius-saving-time-and-effort-with-sketch-routing) [P/V]).
- SparkFun forum: router "has no way of knowing what the traces … are designed to do … or how much current"; supplies, grounds and clocks routed manually; "No-one would think of autorouting an analogue circuit"; poor grouping → more vias ([thread](https://community.sparkfun.com/t/whats-wrong-with-autorouters/11623) [P]). Element14: sloppy routing, return-current neglect [S].
- Luzin & Polubasov (Eremex 2009): "numerous bent wires that are easy to explain but not to justify"; uniform per-layer directions cause warpage; long adjacent-layer parallels form "a long film capacitor"; unmeasured: bottlenecks at min clearance, parallel run length, adjacent-layer overlap [P/V].
- Altium Situs docs concede: "If the board contains an area that can not be routed by hand, then it will not be autorouted either"; diff pairs must be routed and locked manually; obeys all rules except Routing Corners; avoid excessive rules [P-doc].
- DeepPCB essay (vendor): routing is "a resource allocation problem wrapped in geometry wrapped in physics"; autorouters "too sophisticated to abandon but too limited to trust"; its "80% completion benchmark" attribution to Altium is unverified [V].
- Cadence: Interconnect Flow Planner bundles; auto-interactive breakout (AiBT), trunk routing (AiTR), delay tuning (AiDT) [S/V].

**Benchmark evidence**
- PCBWorld D3-A: Freerouting WL 156 mm / 0.74 vias vs human 170 mm / 1.18 at CP 0.80 ([PCBWorld](pcbworld.md)); rule-based routers "rarely complete complex production boards end-to-end".
- Freerouting Tier D stress boards only 13.6–18.2% clean ([freerouting](freerouting.md)).
- OmniRouting: LMMs average 69.8–431.3 DRC violations vs 0.8 human; GND routed as traces instead of pours ([LLM evidence](llm-routing-evidence.md)).
- Even AI-router vendors scope out SI-critical classes (DeepPCB: no DDR, length matching, impedance, RF); a competitor says DeepPCB's checks are geometric only [V].
- NVIDIA ISPD'24: PCB design "typically semi-automated or fully manual" [S].

## Recommendations for our system
Score what practitioners complain about, next to completion and DRC [I]:
| Complaint | Check |
|---|---|
| Vias | Via count, via density per dm² (Luzin thresholds), vias per net |
| Layer bias / crosstalk | Adjacent-layer parallel overlap length; long same-direction runs |
| Bottlenecks | Total length of segments at minimum clearance |
| Return current | Reference-plane changes without stitching vias; plane-split crossings |
| Intent | Per-net current vs width; clock and analog keep-outs; GND as pours |
| Cleanup burden | Bends and jogs per net; acute angles |

- Generate the sketch/flow plan from schematic semantics (relations, corridors, priorities) and realize it with engines ([topological](topological-routing.md), [LLM evidence](llm-routing-evidence.md)) [I].
- Keep rule sets minimal and generated per net class; verify that every constraint is load-bearing [I].

## Conflicts and open questions
- No controlled study of human acceptance of autorouted vs manual boards; EEVblog/HN/Reddit not surveyed; Hartley/Ritchey statements not located.

## Sources
- research notes: [routing_classics_supplement.md § Q8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md); [routing_algorithms.md § Q5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_algorithms.md)

See also: [algorithm-families](algorithm-families.md) · [topological-routing](topological-routing.md) · [benchmarks-and-datasets](benchmarks-and-datasets.md)
