# Length matching, meanders and bus routing

Scope: length-matching algorithms, meander generators and their SI side-effect, bus untangling, contests. Not here: PNS meander internals -> [PNS](kicad-pns-router.md#meander-engine); per-interface meander rules -> [DDR](../rules/interfaces/ddr.md), [USB2](../rules/interfaces/usb2.md), [PCIe](../rules/interfaces/pcie.md).
Keys: length matching, meander, serpentine, trombone, accordion, sawtooth, extension budget, area assignment, BSG-Route, Lagrangian relaxation, CAFE router, MSDTW, speedup effect, self-crosstalk, bus untangling, twisted bus, single detour, ICCAD 2018 Problem B, AiDT, match_group, route_matched

**Results**
1. Academic length matching evolved from Lagrangian-relaxation resource allocation during routing → gridless area assignment (BSG-Route: 88 s vs >1 day) → LP/ILP/flow area assignment for any-direction multilayer boards (2024–26).
2. Tools tune after routing with pattern generators (Altium accordion/trombone/sawtooth; KiCad greedy fill-then-trim), which fails when neighbours have consumed the space.
3. Reserve meander area during planning: area-assignment research, Situs pass design and TopoR trapezoids agree.
4. Dense meanders speed signals up via self-crosstalk (Tseng ICCAD'13): meander pitch/amplitude must be explicit rules from the per-interface rule pack (TopoR's generic "pitch usually ≥3w" is looser than the DDR, USB2 and PCIe packs).
5. Bus untangling is O(n) for one-sided single detours; no ICCAD CAD Contest problem on PCB routing exists (2015–2026).

## Length-matching algorithms (PCB)

[P-abs unless noted]
| Work | Idea | Result |
|---|---|---|
| Ozdal–Wong (ICCAD'03 → TCAD'06) | Lagrangian relaxation allocates extra routing resources around nets during routing; graph model guarantees resources can extend length; shorter nets get resources, longer nets minimization | First to handle minimum-length constraints ([IEEE 4015547](https://ieeexplore.ieee.org/document/4015547/)) |
| Ozdal–Wong single-layer bus (TCAD'06) | Min-area, max-length constraints | Optimal O(A); near-optimal exact bounds O(A log A) |
| Ozdal–Wong two-layer bus (TODAES'06) | One track at a time, net subsets, extension during routing | — |
| **BSG-Route** (Yan–Wong ICCAD'08 → TCAD'09) | General topology, gridless; length matching as area assignment on a bounded-sliceline grid by iterative math programming | 88 s vs "more than one day" for LR ([IEEE 5290341](https://ieeexplore.ieee.org/document/5290341/)) |
| CAFE router (Kohira–Takahashi ASP-DAC'10) | Greedy pin-to-pin extension toward a target length, single-layer grid | — |
| Yan–Chen ISPD'11 obstacle-aware bus | O(mn + s³) | −80.5% CPU, zero length error |
| Zhang et al. ASP-DAC'15 disordered pins | LCS layer assignment, single-commodity flow base routes, R-flip/C-flip adjustment | — |
| J.-T. Yan TCPMT'22 multi-bus | Single-layer, obstacle-aware | +10.7% buses routed; max skew 14.25 → 1.38 |
| **Lin–Guo–Fang TODAES'26** | Any-direction multilayer area assignment: LP → ILP with obstacle "utility constraints" → combinatorial min-weight hierarchical flow, near-optimal by LP primal–dual; allows wire-topology modification; continues Fang DAC'24 MSDTW meandering | ([DOI](https://doi.org/10.1145/3795795)) |
| ACO 2025 | Min/max length, "two-ant synchronized routing" for DPs | Weak venue |

Meander SI side-effect: Tseng, Li, Ho, Schlichtmann ICCAD'13: dense meanders cause a "speedup effect due to crosstalks between the segments of the same wire"; ILP post-processing roughly doubles meander width/spacing even under tight area ([IEEE 6691193](https://ieeexplore.ieee.org/document/6691193/) [P-abs]).

## Pattern generators in tools

- Altium: Accordion (max amplitude, space, miter %, style mitered lines/arcs/rounded; "rounded most compact"), Trombone, Sawtooth (tooth width, min height, angle), inserted per available space, rules and obstacles ([docs](https://www.altium.com/documentation/altium-designer/pcb/high-speed-design/length-tuning) [P-doc]).
- KiCad PNS meander engine: greedy fill with largest collision-free amplitude, then trim; point-to-point only (DP: coupled portions only); master adds chain-level fields → [PNS](kicad-pns-router.md#meander-engine).
- TopoR: arc serpentines inscribed in an adjustable trapezoid, target held within 50 nm; contrasts Specctra's rectangular accordion/trombone; meander pitch "usually not less than 3w"; straight-line approximation for arc-less formats ([TKEA 2009](https://www.tkea.com.ua/index.php/journal/article/view/TKEA2009.4.03) [P]).
- KRT: post-route trombones, DDR4 auto-grouping, time matching. Freerouting: `NetMeanderConstraint` rule model only (0.2–1.0 mm amplitude defaults) [P].
- Cadence Allegro AiDT tunes byte lanes/interfaces; Pegatron reported ~67% less routing time [S/V].

## Bus untangling

[P-abs]
- Yan–Wong ICCAD'07/TODAES'09: real buses are "twisted"; single-detour routing with a necessary-and-sufficient condition and DP including inter-pin capacity.
- Lin, Dong, Chen, Goto ASP-DAC'12: optimal O(n) one-sided single-detour untangling (vs O(n³) DP).
- Two-sided untangling (Yan–Chen DAC'10); internal detours +2.8–3.5% routability (J.-T. Yan TODAES'19).
- Contests: ICCAD 2018 Problem B "Obstacle-Aware On-Track Bus Routing" is an IC problem (winners CU-Bus, Bus_Driver, Fujita/Chang team); DAG-based follow-up (Hsu et al. DAC'19/TCAD'21) found top-3 contest routers had 145%, 158%, 420% higher costs. Contest pages 2015–2026 contain no PCB/board/package problem (2026: LLM netlist exploration, regression bucketing, FloorSet) [P-doc].
- Cross-domain: PACOR microfluidic length-matched escape (DME Steiner + MCF + bounded detours, 100% completion) → [cross-domain routing](cross-domain-routing-transplants.md#other-physical-design-domains).

## Length matching in kae

[I]
- Convert DDR/bus constraints (LLM-read from datasheets) into per-net extension budgets and keep-out meander regions allocated before bulk routing (BSG/LP-style area assignment).
- Route buses with reserved area, then tune with KiCad PNS meanders (point-to-point; check chain-level fields) or KRT trombones.
- Meander rules as explicit LLM-set constraints from the interface rule pack: DDR centre-to-centre ≥5W including serpentines ([DDR](../rules/interfaces/ddr.md)); USB2 meander gap ≥5X with X = max(W, H) ([USB2](../rules/interfaces/usb2.md)); PCIe serpentine segments ≥ max(3W, 3H) ([PCIe](../rules/interfaces/pcie.md)); TopoR's pitch ≥3w only as generic fallback; min corner radius ≥ half width; avoid tight meanders (Tseng); verify by a length-group spread / skew check.
- Untangle buses before routing (O(n) single detour); prefer allowed bit swaps (LLM decision) that remove the twist → [escape](escape-routing.md#escape-in-kae).
- Relation API: `match_group(nets, tol_ps, reserve_area=region)` / `route_matched(nets, tol_class)` → [LLM routing evidence](llm-routing-evidence.md).

## Open questions

- No academic length-matching code is public; Allegro AiDT/AiBT internals undocumented; Taiwan domestic and ISPD contests not checked for PCB problems.

## Sources

- [routing_classics_supplement.md § Q4, Implications](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md); [routing_algorithms.md § Q2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_algorithms.md)
