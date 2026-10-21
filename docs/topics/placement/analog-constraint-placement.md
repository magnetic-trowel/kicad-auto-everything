# Analog IC constraint placement as a constraint vocabulary (MAGICAL, ALIGN)

**TL;DR**
- Analog flows split constraints into **soft penalties during global placement** and **hard equalities/orders in LP/ILP legalization** — the pattern to copy for LLM-authored PCB constraints.
- **ALIGN's typed JSON schema** (Hard / User / Soft constraints) is a ready vocabulary; PCB proximity rules map to `PlaceCloser`/`Order`/`Align`/`PlaceOnBoundary`, symmetric sub-circuits to `SymmetricBlocks`.
- ALIGN's **constraint-preserving sequence-pair perturbations** guarantee order/symmetry by construction instead of penalizing violations.
- LayoutCopilot is the closest "LLM drives a layout tool" precedent: 93.75% command-generation correctness with a multi-agent pipeline and 11 commands.
- No PCB paper yet reuses symmetry islands or sequence-pair-with-symmetry formulations.

## Key facts

**MAGICAL placer** (Xu et al., ICCAD'19; [PDF](https://yibolin.com/publications/papers/ANALOG_ICCAD2019_Xu.pdf) [P]; [repo](https://github.com/magical-eda/MAGICAL), BSD-3)
- Global placement minimizes f_WL + a·f_OL + b·f_BND + c·f_SYM with nonlinear conjugate gradient; HPWL and max/min smoothed by log-sum-exp; f_SYM mirrors each pair about a shared axis and puts self-symmetric devices on it; weights rise each iteration until penalties fall below thresholds.
- Legalization: plane-sweep horizontal/vertical constraint graphs, one spreading direction per overlapping pair, DFS adds missing edges, transitive reduction, then **LP compaction with topology order + exact symmetry equalities**; LP detailed placement for wirelength.
- Feasibility rule: at most one symmetry constraint per device. Constraint extraction: transistor-pattern library + signal-flow-graph traversal from seed differential pairs (also detects bias-circuit symmetry). Net criticality as net weights. Builds on ISPD'17 and ISPD'19 (device-layer-aware) placers.

**ALIGN placer** ([overview arXiv 2008.10682](https://arxiv.org/pdf/2008.10682), [source](https://github.com/ALIGN-analoglayout/ALIGN-public) [P], BSD-3)
- SA over `SeqPair` (T₀ 0.5, T_min 0.05, α 0.995, 10,000 iterations); "PerturbationNew honors order and symmetry".
- Each sequence pair → coordinates and flips by **ILP** (SYMPHONY or lp_solve; HPWL linearized with absolute-value constraints including pin positions under flips, + area; symmetry-axis, alignment, ordering constraints).
- Small designs: **enumerate all order-consistent sequence pairs** (topological-sort enumerator). Optional pure-ILP placer (SA fallback on timeout) and electrostatic `EA_placer` (FFT density, Nesterov, LSE WL, symmetric force matrix, alignment, ordering, common centroid).
- Based on Ma et al. TCAD 2011 (symmetry + common centroid + general constraints in SP); hierarchical block assembly with multiple aspect-ratio options; ML-assisted hierarchical symmetry extraction under approximate matches; electrical constraints translated to max parasitics/wire limits.

**ALIGN constraint schema** ([constraint.py](https://github.com/ALIGN-analoglayout/ALIGN-public/blob/master/align/schema/constraint.py) [S]; per-hierarchy `<name>.const.json`)
| Kind | Constraints |
|---|---|
| Hard | Order, Align, Spread, AspectRatio, Boundary, SymmetricBlocks, AssignBboxVariables |
| User | AlignInOrder, Floorplan |
| Soft | PlaceCloser, PlaceOnBoundary, CompactPlacement, SameTemplate, PowerPorts/GroundPorts/ClockPorts, DoNotIdentify |

**Other analog methods**
- Symmetry islands / ASF-B*-trees (Lin, Chang, Lin, TCAD'09): each symmetry group placed as one connected island; first to handle 2-D symmetry; HB*-trees co-optimize islands with free modules in linear-time packing; follow-ups add matching and hierarchical proximity groups ([PDF](https://cc.ee.ntu.edu.tw/~ywchang/Papers/tcad09-analog-placement.pdf) [S]).
- Mixed constraint graphs for interactive editing (Gao, DAC'21/TCAD'22); ModuPlace calls them too imprecise for PCBs (adjacent pairs only) [S/P].
- GNN symmetry annotation (ASP-DAC'21), GAT extraction (2023), GNN performance-guided placement (ICCAD'20) [S].
- **LayoutCopilot** (TCAD'25, [arXiv 2406.18873](https://arxiv.org/pdf/2406.18873) [P], VP-corrected): agents for classification, analysis, refinement, adaptation; 11 commands (deviceMove, deviceSwap, arrayAdd, arraySpace, symAdd, netRemove, netReroute, wireWidth, wireSpacing, netPriority, netTopology); abstract suggestions go to the designer, concrete requests compile to commands. Correctness **93.75%** with instructions (Claude-3 96.80%, GPT-4 93.92%, GPT-3.5 90.92%) vs 87.89% without, 79.98% single-agent.
- LLANA: LLM-enhanced Bayesian optimization for constraint generation incl. symmetry; open code ([PDF](https://webarchive.lib.cuhk.edu.hk/20241030001211mp_/http:/www.cse.cuhk.edu.hk/~byu/papers/C241-LLANA.pdf) [S]).
- Multi-level multi-agent RL exploring asymmetric placements (DAC'25 LBR); ACDC 10k-sample synthetic symmetric grid benchmark for LLMs [S].
- Template retargeting: IPRAIL extracts a structural template from a tuned layout and re-applies it under new sizes/rules (0.25 → 0.18 µm op-amps) [S].

## Recommendations for our system
- **Compile every LLM constraint twice**: smooth penalty with LLM-tunable weight in global placement; exact linear constraint in legalization; report infeasible subsets back ([legalization](legalization.md)) [I].
- Base our PCB constraint vocabulary on ALIGN + PCB additions (hard: fixed, on_edge, keepout, side, rot_allowed, inside, clearance; soft: near(pin), ring, align, order, symmetric, group, spread, away_from, loop_compact) — see [LLM-guided placement](llm-guided-placement.md) [I].
- Mapping: decap/crystal/ESD proximity → PlaceCloser/Order/Align/PlaceOnBoundary; differential front ends, half-bridge legs, RF chains → SymmetricBlocks [I].
- Use constraint-preserving SP moves for small module floorplans; enumerate order-consistent SPs for tiny blocks [I].
- Copy LayoutCopilot's intent classifier → analyzer (knowledge base) → refiner (user negotiation) → adapter (KiCad calls / DSL) pattern [I].
- Template retargeting: extract a structural template from datasheet/past layouts and re-run it as a relative-placement program ([scene-layout transplants](scene-layout-transplants.md)) [I].

## Conflicts and open questions
- Ma et al. 2011 and Xu et al. ISPD'19 not read in full.
- How MAGICAL's one-symmetry-per-device rule interacts with PCB parts in multiple groups is untested.

## Sources
- research notes: [placement_algorithms.md § Q2, Q6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/placement_algorithms.md); [cross_domain_ideas.md § Q10](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md); [verification_papers.md § 1 row 23, § 2.11](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)

See also: [llm-guided-placement](llm-guided-placement.md) · [legalization](legalization.md) · [algorithm-families](algorithm-families.md)
