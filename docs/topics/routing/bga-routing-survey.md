# BGA and dense-package routing: EDA methods and commercial practice

**TL;DR**
- Escape under a BGA is solved exactly, as a network flow, only when the capacity model is right. The Yan–Wong five-node tile network is the one exact single-layer model: k balls escape legally iff it carries an integral flow of k. It runs in about 1 s on 35×35 arrays, and the min cut names the bottleneck gaps.
- Multi-layer escape with real vias is not a pure flow. A via blocks space on the layers it spans. MonoSAT handles this with SAT plus a max-flow theory and proves minimal layer counts. Its theory solver's conflict clause is a min cut over saturated channels and via-blocked edges, which is the bottleneck explanation we want.
- Closed-form layer bounds exist and take microseconds: the Wang–Shi–Cheng claim 4 inequality, and AMD UG1099's channel estimate. Both are cheap first answers to "how many layers does this need".
- Commercial tools agree on the workflow. They escape the BGA first, with a separate pattern-driven engine, and lock it. Pin swap works on the breakout endpoints. Bundles are planned globally before detail routing. **No vendor publishes an unroutability certificate.** The best report is Altium's list of pads that could not be fanned out.
- The human pattern our boards miss is in vendor guides and practitioner texts: the outer rings route on top with no vias, the next rings go by via to the bottom, and the inner rings go to inner layers, with quadrant dog-bones.

This doc adds to [escape-routing](escape-routing.md), [diff-pair-routing](diff-pair-routing.md), [layer-assignment-and-vias](layer-assignment-and-vias.md) and [length-matching-and-buses](length-matching-and-buses.md). It does not repeat what they say.

## Key facts

### 1. The exact single-layer escape network (Yan–Wong)

Sources: Tan Yan's UIUC thesis "Algorithmic Studies on PCB Routing", 2010, ch. 2 ([PDF](https://www.ideals.illinois.edu/items/18457/bitstreams/66469/data.pdf) [P]); DAC'09 ([DOI](https://doi.org/10.1145/1629911.1630001)); TCAD'12 ([DOI](https://doi.org/10.1109/TCAD.2011.2169258)).

**Capacities.** A tile is the square between 4 balls.
- *O-cap* is the number of wires that fit between two orthogonal neighbours.
- *D-cap* is the number that fit between two diagonal neighbours.
- The model assumes O ≤ D ≤ 2·O.

From pitch p, pad diameter d, width w and spacing s (Wang–Shi–Cheng ICCAD'06 §3.1, [PDF](https://www.cecs.uci.edu/~papers/iccad06/papers/10C_3.pdf) [P]):
- O = ⌊(p − d − s)/(w + s)⌋
- D = ⌊(√2·p − d − s)/(w + s)⌋

For example, 225/100/25/25 µm gives O = 2 and D = 3.

With KiCad's two clearances, track–pad c_tp and track–track c_tt, n tracks fit in a gap g when g ≥ 2c_tp + n·w + (n−1)c_tt. So n = ⌊(g − 2c_tp + c_tt)/(w + c_tt)⌋ [I].

**Network, per tile** [P]:

| Element | Capacity |
|---|---|
| Peripheral nodes N, E, S, W ↔ centre node C | ∞, both directions |
| C (split into an in-node and an out-node) | D − 2⌊O/2⌋ |
| Shortcut edges N–E, E–S, S–W, W–N | ⌊O/2⌋ |
| Inter-tile edges (N of a tile to S of the tile above; E to W of the tile to the right) | O |
| Pin edges: each ball feeds one peripheral node of each of its 4 tiles | 1, one direction |
| Super-source → each ball to escape; each boundary edge → super-sink | 1 |

- Any orthogonal cut crosses one inter-tile edge, so its capacity is O.
- Any diagonal cut crosses two shortcut edges plus C, so its capacity is 2⌊O/2⌋ + (D − 2⌊O/2⌋) = D. That identity is the whole trick.
- Older models (one tile node, or triangulation) made up to 53 D-cap violations on the same cases [P].

**Missing balls.** A depopulated ball becomes a "resource node" of capacity Δ, the extra wires its absence lets through (O = 2, D = 4 gives Δ = 2) [P].

**Multi-layer.** Copy the network once per layer and join a ball to the same ball one layer down with an edge of capacity 1 and cost equal to the via cost. Then binary-search the layer count.
- This ignores the space a via takes on the layers in between.
- It is therefore exact only for via-in-pad, or a via whose space is already reserved [P].

**Results.** 8 industrial arrays from 14×16 to 35×35, 66–225 escaped balls, up to 106 missing balls. There were 0 diagonal violations and each case took ≤ 1.01 s with the CS2 min-cost flow solver. Wire length uses cost 1 on inter-tile edges [P].

**Ordered versus free.** This is *unordered* escape: any ball may leave through any boundary slot. A fixed netlist (pin A must reach pin B) needs multi-commodity flow or ILP. Fang, Hsu and Chang make the same point for pre-assigned flip-chip nets ([TCAD 28(1) 2009](https://doi.org/10.1109/TCAD.2008.2009151) [S]).

### 2. Multi-layer escape with via sites: MonoSAT in detail

Source: Bayless thesis, UBC 2017, §5.3.1 and §6.2 ([PDF](https://www.cs.ubc.ca/labs/isd/Projects/monosat/sam_bayless_thesis_2017.pdf) [P]). [escape-routing](escape-routing.md) has the headline table.

**Grid.**
- Each layer is a node-split grid with capacity 1 on nodes and edges.
- "Large" on-grid nodes are joined by "small" nodes that carry 45° traces.
- No space is reserved in advance for vias.

**Via sites.**
- Each candidate via j has a Boolean `via_j`.
- Each grid node i the via would cover has a Boolean `a_i`, and the clause `via_j → ¬a_i` blocks it.
- Via diameter is simply the size of the blocked set.
- Per layer, two via nodes plus gating literals let a via start, end or pass through.

**Via types.** These are pure clause patterns:
- through: block all layers;
- blind from the top to layer j: block layers 1..j;
- buried: block its span;
- microvia: no extra clauses, adjacent layers only.

**Flow.** One theory atom, maxflow(s, t) ≥ |signals|. Power and ground balls are pre-assigned through-vias to the planes.

**After SAT.** Vias and layers are fixed, then each layer is re-routed by min-cost flow, because the theory supports max-flow only.

**Explanation mechanism.** The flow is evaluated on two graphs:
- G+, with undecided edges treated as present;
- G−, with undecided edges treated as absent.

When G+ falls short, the min cut of an auxiliary graph is turned into a conflict clause: "enable one of these blocked cut edges". That is a named bottleneck [P].

**Scale and results** (23 parts):
- Up to 54×54 balls, 1,755 signals, more than 1 M nodes.
- Runtime from seconds to 8,039 s.
- 12 of the 23 blind-via results are proven minimal.
- Through-via results used up to 2 layers fewer than greedy layer-by-layer flow (3 vs 5) [P].
- Diff pairs were ignored.

**Code.** The solver is MIT-licensed with Python bindings ([repo](https://github.com/sambayless/monosat)). The ICCAD'16 escape router itself is not in it [P].

### 3. Layer lower bounds and layer assignment

| Result | Statement | Use |
|---|---|---|
| Wang–Shi–Cheng ICCAD'06 claim 4 [P] | The smallest k with −2(D+1)(D+2)k² + [4(D+1)n − 10D + 8C]k − n² ≥ 0 bounds the layers for an n×n array, assuming blind vias and p = (D+1)(w+s). Ring-by-ring escape is wasteful. Best openings are isosceles triangles at about 45°. Example: a 35×35 FCPBGA escapes in 3 layers vs 6 ring by ring, and 2 layers is proven impossible | Instant "needs ≥ k layers" message |
| AMD UG1099 [P] | Signals ≈ 60% of balls. Routing channels = 4 × (balls per side − 1). Routes per channel 1 or 2. The layer equation is an image; the table matches layers ≈ 0.6·balls / (channels × routes) [I]. One signal between pads escapes one row per layer (two for the outer row); neck-down gives two (three) ([layer count](https://docs.amd.com/r/en-US/ug1099-bga-device-design-rules/Layer-Count-Estimation-and-Optimization)) | Cross-check; average-channel only, weaker than a ring cut |
| Yan–Wong optimal bus layer assignment (thesis ch. 6) [P] | Buses between two arrays are compatible iff one is above the other on both sides. That relation is a partial order, so min layers = n − max bipartite matching (Dilworth). 16–110 buses; at most 1 layer better than greedy | Bus or byte-lane layer plan |
| Ho–Shih–Chang–Cheng ASP-DAC'13 [S] | Staggered arrays: pick the balls that maximise this layer's escape while leaving room for the next | Heuristic |
| Lei–Mak TCAD'13, TCAD'16 [S] | Constrained FPGA pin assignment + escape with diff pairs on through-via boards; blind-via-aware multi-layer co-optimisation | Closest via-type-aware work; full text not reached |
| MORE-Router+ (Gao, Dong, Cheng, Yu, ISQED'24) [S] | Three ILP stages: bus direction, layer assignment, multi-capacity MCMF detail. 54 buses / 1,602 nets on 50×50 in ≤ 266 s | Bus-level ILP template |

### 4. Diff pairs, between-package buses, variable rules

**Yan–Wu–Ma–Wong ICCAD'10, pair escape** (thesis ch. 3 [P]):
- Two single tracks leave the pins, merge in one tile and run as adjacent tracks to the boundary. Splitting after the merge is illegal.
- Single pair, optimal in O(n² log n):
  - one Dijkstra on the double-track graph from the boundary;
  - a min-cost 2-flow from the two pins to each candidate merge tile;
  - keep the best tile.
- Many pairs:
  - PathFinder finds pin-to-pin paths, and their tiles become merge candidates;
  - min-cost flow picks one merge tile per pair (one flow unit = two tracks);
  - each pair is then re-routed alone.
- Results: 8–60 pairs, grids up to 35×35, 1–453 s.
- The single-pair routine drops straight into a rip-up loop as a "pair maze router".

**Matching-based escape with variable rules** (Liu, Lin, Chen, He, Chen, Chang; [DAC'23](https://doi.org/10.1109/DAC56929.2023.10247781), [TCAD 44(12) 2025](https://doi.org/10.1109/tcad.2025.3569773) [S]):
- Handles variable widths and clearances, neck-down modes and pair pad entry.
- Pipeline:
  1. obstacle-aware projection of pins to the boundary;
  2. a bi-projection graph;
  3. matching-based hierarchical sequencing;
  4. congestion-aware global routing with rip-up;
  5. face-by-face detailed routing.
- Reports 100% with no DRC errors on industrial boards that FreeRouting and Allegro did not finish. This is the closest published match to a real KiCad board; there is no open text.

**Other bus and package work:**
- Wu–Ma–Wong ASP-DAC'13, ILP bus planner: decomposition, escape, layer and global bus routing in one model; 97.4% vs 84.7% for an industrial tool [S].
- The Rectangle Escape Problem (Ma–Young–Wong ASP-DAC'11) [S].
- Twisted-bus untangling ([length-matching-and-buses](length-matching-and-buses.md)).

**Package substrates:**
- Kubo–Takahashi and Tomioka–Takahashi move via sites iteratively in 2-layer BGA packages. The moves cut layer-1 congestion and keep layer-2 wires short, until layer 2 routes 100% ([ASP-DAC'08](https://www.cecs.uci.edu/~papers/aspdac08/pdf/p238_3A-3.pdf) [P]).
- The idea, "use the second layer more by moving vias", is our human-vs-router gap.
- Monotonic routing has a necessary and sufficient condition for parallel netlists (ASP-DAC'06) [S].
- Chip–package–board co-design (Fang–Ho–Chang ICCAD'08 with diff pairs; Lee–Chang DAC'12; Chen et al. ASP-DAC'14 bump assignment) treats ball assignment as a variable [S]. For us that means pin swap, which is an LLM or schematic decision.

### 5. ML, RL and LLM work, 2023–2026

| Work | What | Numbers | Note |
|---|---|---|---|
| GPCB Routing (Chen … Qian, [TCAD 2025](https://doi.org/10.1109/TCAD.2024.3486241), [PDF](https://gc.sjtu.edu.cn/~wkqian/papers/Chen_Tu_Wang_Zheng_Liu_Bai_He_Qian_GPCB_Routing_Generative_Pre-Trained_Transformers_Based_Printed_Circuit_Board_Routing_Method.pdf) [P]) | GPT predicts Yan–Wong-style flow tokens per tile; DRC-masked; A* for leftovers | 8 cases, 26–39 nets, 633–1,095 pins: 100% in 1.4–19 s; Freerouting reported at 28% on these cases | Small synthetic cases; Freerouting not KiCad-scored |
| NeuroEscape (ICCAD'23) [S] | MCTS + neural net, ordered escape | Not reached | — |
| Deng et al. [TODAES 2025](https://doi.org/10.1145/3760776) [S] | MCTS for ordered diff-pair escape | Not reached | — |
| Jiao–Dong [TODAES 2018](https://doi.org/10.1145/3185783) [S] | MCMF ordered escape with pairs and blockages | 100% | Extends ASP-DAC'16 |
| PCBWorld, OmniRouting, PCB-Bench ([PCBWorld](pcbworld.md)) | Benchmarks and environments | LLMs weak at routing | No escape planning |

FanoutNet is covered in [escape-routing](escape-routing.md). No follow-up from the same team was found.

### 6. Commercial practice

| Tool | BGA mechanism | Unroutable reporting |
|---|---|---|
| Allegro PCB Router (SPECCTRA) | `fanout` do-file pass before routing. Options: direction in/out, via share, pin share, pin types, via-in-pad. Users report that later passes move fanout vias back unless they are protected ([edaboard](https://www.edaboard.com/threads/specctra-fanout-problem.19893/) [S]; [Pulsonix wizard](https://www.pulsonix.com/docs/Specctra-Wizard/idh_specctra_wizard_breakout.htm) [P]) | Completion and unrouted counts [S] |
| Allegro AiBT / AiTR, GRE | AiBT plans both ends of a bundle at once (Sequence, Breakout, Trunk Route). Cavium used AiBT + AiTR to decide whether a proposed pin-out needed more layers ([Cadence](https://resources.pcb.cadence.com/i/1310866/3) [V/S]). GRE: bundles and flows, "Plan Spatial" | Flow overflow display [I, unverified] |
| Allegro X AI | Cloud router ([EMA guide](https://www.ema-eda.com/ema-resources/product-guide/reports-and-results-routing/) [P]) | Signal Opens per net; **pre-route audit**: min line width > pad width means breakout DRC errors; neck length must be set; keepouts and static shapes choke routability; constraint regions must not overlap |
| Xpedition Sketch Router | **A BGA escape engine runs first.** Sketch → container → layer-bias map ([US 8,930,868](https://patents.google.com/patent/US8930868B2) [P]). Hug Router finishes. Brochure: "typical completion > 90%" [V] | Not described |
| Mentor breakout patents | [US 8,103,988](https://patents.google.com/patent/US8103988B2): breakout endpoints become pseudo-pins for pin swap [P]. [US 5,757,656](https://patents.google.com/patent/US5757656A) (expired 2015): non-crossing pin-to-via matching by convex-hull common tangents [P] | — |
| Cadence patents | [US 8,510,703](https://patents.google.com/patent/US8510703B1) (expired): triangulated-tile global router with per-cut capacity; via locations chosen globally before detail routing [P]. [US 8,667,454](https://patents.google.com/patent/US8667454B1): breakout-aware FPGA pin assignment; minimum layers by adding layers until bundles route [P]. US 7,013,451 (Teig): routability check of topological routes by capacity and flow per edge [S] | The only certificate-like patent found |
| Altium Fanout | Inner pads dog-bone to vias, escapes walk the layers; option "escape diff pair pads first" ([docs](https://www.altium.com/documentation/altium-designer/pcb-fanout-escape-routes) [P]) | **Report of pads that could not be fanned out, cross-probed** |
| Altium ActiveRoute | Multi-net river route; never adds vias or changes layer; needs BGAs fanned out first ([docs](https://www.altium.com/documentation/altium-designer/activeroute-pcb) [P]) | Unfit connections are left unrouted; completion % |
| Zuken CR-8000 Dragon EX | A strategy area round the BGA: fanout by signal name, GND via, layers, directions ([blog](https://www.zuken.com/en/blog/fanout-design-force-dragon-ex/) [P]) | Not published |
| Quilter | 2026 automated BGA fanout in beta [V]. In Project Speedrun, humans did a partial BGA fanout; 98.7% completion after 15 h, then 26.5 h human cleanup ([blog](https://www.quilter.ai/blog/compiling-an-ai-designed-computer) [P]) | Percentage only |
| DeepPCB | 32k jobs, mean 95.6%; ">500 airwires: expect to fine-tune the last 10–20% manually" ([benchmark](https://deeppcb.ai/pcb-autorouter-benchmark-2026) [P/V]) | Percentage only |

**NCER vs Allegro.** On 14 industrial escapes each fully routed 7, and together 11 [P-abs], so escape engines are complementary ([escape-routing](escape-routing.md)).

**Practitioner doctrine** (Pfeil, Mentor, *BGA Breakouts & Routing*; [PCD&F 2008](https://pcdandf.com/pcdesign/index.php/2008-archive-articles/3555-fanout-patterns-parts-1-2-3-and-4) [P]):
- "The BGA fanout pattern has the greatest impact on route density."
- A quadrant dog-bone (vias angled away from the centre, per quadrant) opens the centre row and column for about 2–3 extra routes per layer.
- Fan out every power and ground ball.
- Blind vias shifted into columns: about +24% edge escapes.
- 1+N+1 microvias in columns: about +36% over a through-via quadrant dog-bone.

A generic channel guide puts it this way: "outer two perimeters without vias on top, the next two on the bottom side, the rest on inner layers" ([embedded.com](https://www.embedded.com/?p=4438466) [S]). That is exactly the layer use our human layouts show and our routes lack.

## Recommendations for our system

1. **Escape as its own deterministic stage, locked before Freerouting.**
   - Build the Yan–Wong network from the board's own rules (§1, with c_tp, c_tt, net-class widths and real pad shapes), one copy per signal layer.
   - The two outer layers are the main resource: the top for outer rings, the bottom via a dog-bone for the next rings.
   - Run min-cost flow (OR-Tools `SimpleMinCostFlow`, Apache-2.0).
   - Decompose the flow into per-ball escape paths, write them as fixed or protected wires in the DSN, then run Freerouting.
   - This replaces the fixed-pattern dog-bone pre-pass on branch `rules-escape` with a capacity-aware one, and gives the min cut as a by-product ([certificates](routing-infeasibility-certificates.md)) [I].
2. **Via sites as variables for multi-layer windows.**
   - Use MonoSAT's clause pattern (§2) in CP-SAT or MonoSAT. Via types come from the board's allowed via types: through always; blind, buried and micro only if the stackup defines them.
   - Add one assumption literal per relaxation, so an UNSAT result names the rules to change [I].
3. **Pre-route audit and per-pad escape report** in the style of Allegro X AI and Altium (§6), given to the LLM before any routing [I].
4. **Pair escape.** The Yan–Wu–Ma–Wong single-pair routine is a pair search in the last mile, and merged pairs count 2 tracks in O/D-cap [I].
5. **Pin swap, later.** Treat breakout endpoints as pseudo-pins (US 8,103,988) so swap optimisation, an LLM decision written back to the schematic, sees escape order, not ball order [I].

## Conflicts and open questions
- The Wang–Shi–Cheng extracted text shows "2p" in the D-cap formula. Only √2·p reproduces their example; we use √2·p.
- The UG1099 layer equation is an image. Our reconstruction matches the table but is unverified.
- No commercial completion rate on BGAs, and no vendor certificate, was found.
- The Liu–Chang DAC'23/TCAD'25 full text, Lei–Mak and NeuroEscape numbers were not reached.

## Sources
- Primary sources are linked inline. Detail from four research passes on 2026-10-31 (academic escape, commercial practice, cross-domain, math).
- Related: [escape-routing](escape-routing.md) · [diff-pair-routing](diff-pair-routing.md) · [layer-assignment-and-vias](layer-assignment-and-vias.md) · [routing-cross-domain-and-math](routing-cross-domain-and-math.md) · [routing-infeasibility-certificates](routing-infeasibility-certificates.md)
