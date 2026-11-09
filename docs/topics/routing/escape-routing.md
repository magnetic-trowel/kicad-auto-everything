# BGA / escape routing: exact flow, MCF and SAT formulations

Scope: survey of escape-routing formulations and academic escape routers vs commercial tools. Not here: Yan–Wong and MonoSAT encoding detail, commercial practice -> [BGA survey](bga-routing-survey.md); certificates -> [certificates](routing-infeasibility-certificates.md).
Keys: escape routing, fanout, simultaneous escape routing, SER, Ozdal–Wong, bus sequencing, longest common interval, pin assignment, ordered escape, multi-commodity flow, MCMCF-Router, SAT escape, Luo–Wong, MonoSAT, proven minimal layers, NCER, B-escape, Lin DAC'21, FanoutNet, staggered arrays, swappable pins

**Results**
1. Escape is the most mathematically closed PCB subproblem: single-layer = network flow (with correct diagonal capacity for 45°); ordered = multi-commodity flow or SAT; multi-layer with vias = SAT + flow (MonoSAT).
2. MonoSAT proved minimal layer counts on real BGAs/FPGAs (Xilinx XCVU440, 1755 signals: 4 → 3 layers) in minutes to ~72 min (1,597 s + 2,727 s). The proof holds only for its discretized escape model (escape signal layers, given via sites and rules), not the whole board; reference planes come on top.
3. Pin assignment + escape is polynomial-optimal (80 buses, >7000 nets in <5 min); bus sequencing O(n log n): pin/bank/bit swap should be a first-class LLM action.
4. Academic escape routers matched or beat Cadence Allegro on industrial cases (B-escape, NCER, Lin DAC'21); almost none has public code.
5. Learned fanout (FanoutNet) helps but is slow; practitioners report tools fall back to sub-spec vias at fine pitch.

## Simultaneous and bus-aware escape

[P-abs]
- Ozdal–Wong SER: separate under-component routing from the intermediate area; minimize intermediate crossings as longest path with forbidden pairs; exact polynomial maximal planar solution on one layer + randomized variant; layer assignment = max planar subset per layer ([IEEE 1637740](https://ieeexplore.ieee.org/document/1637740/)). With high-speed constraints: −39% vias on industrial cases ([IEEE 1560166](https://ieeexplore.ieee.org/document/1560166/)).

| Result | Complexity / scale |
|---|---|
| Bus sequencing as longest common interval sequence (Kong, Yan, Wong, Ozdal ICCAD'07); "no commercial CAD software can provide an automatic solution" | O(n log n) optimal |
| Minimum layers for bus escape (Yan, Kong, Wong ICCAD'09) | optimal |
| Consecutive-layer bus assignment (Ma, Young, Wong DAC'11) | branch-and-bound optimal |
| Simultaneous pin assignment + escape (Kong, Yan, Wong ASP-DAC'10) | polynomial optimal; 80 buses, >7000 nets, <5 CPU min ([IEEE 5419881](https://ieeexplore.ieee.org/document/5419881/)) |

## Exact models

[P-abs]
- SAT ordered escape (Luo–Wong ASP-DAC'08; fixed and scaled '09): prior approaches "cannot guarantee to find a routing solution even if one exists".
- Correct network-flow model (Yan–Wong DAC'09/TCAD'12): "none of the previous works correctly models the diagonal capacity, which is essential for 45° routing"; first optimal escape algorithm; handles missing pins → [BGA survey § 1](bga-routing-survey.md#1-the-exact-single-layer-escape-network-yanwong).
- Staggered arrays: LP/ILP orthogonal-side wiring (Ho, Lee, Chang ICCAD'11); flow models guaranteed to find a solution if one exists (Wu–Wong ASP-DAC'13).
- Ordered escape by min-cost multi-commodity flow (Jiao–Dong ASP-DAC'16, 100% on tests); multi-capacity ISQED'23 (≤308 pins); MCMCF-Router (TODAES'24): up to 525 pins, 100% in <810 s (VP: not "2000+") ([DOI](https://doi.org/10.1145/3695253)).
- LP network-flow SER solving net ordering and escape together (Sattar–Ignjatovic); two-stage flow ILP for escape + area routing (PeerJ CS 499) [S].

## MonoSAT multi-layer escape

Bayless, Hoos, Hu ICCAD'16 ([PDF](https://www.cs.ubc.ca/labs/isd/Projects/monosat/monosat_bga_iccad2016.pdf) [P]); encoding → [BGA survey § 2](bga-routing-survey.md#2-multi-layer-escape-with-via-sites-monosat-in-detail).
- Multi-layer escape "cannot be modelled as a pure network flow problem"; practice is greedy layer-by-layer.
- SAT modulo monotonic theories with flow constraints places traces and vias simultaneously; 45°/90°; through, blind, buried, any-layer micro-vias; accepts partial solutions; diff pairs by forcing both signals' vias to the same layer.

| Part (blind vias) | Greedy layers | MonoSAT |
|---|---|---|
| TI AM5716 (28×28, 382 signals) | 3 | **2, proven minimal** |
| TI TMS320C | 4 | 3 |
| Xilinx XCVU440 (54×54, 1755 signals) | 4 | **3, proven minimal** (1597 s + 2727 s) |
| TMS320C / AM52E02 (through vias) | 5 | 3 |

Average trace length slightly longer (21.6 vs 20.0 mm). Licence MIT, but links GPLv2 code by default: build with `-DGPL=OFF` ([README](https://raw.githubusercontent.com/sambayless/monosat/master/README.md) [P-doc]).

## Academic routers vs commercial

[P-abs]
- NCER (Ma, Yan, Wong ISQED'10): negotiated-congestion escape; NCER and Allegro each fully routed 7/14 industrial cases, 11/14 together ("complementary").
- B-escape (ISPD'10, boundary routing): solved all industrial problems; Allegro completed about half.
- Multiple components sharing buses (Chin–Chen EDAPS'13).
- Lin, Wang, Kuo, Chen, Li DAC'21: SER (layer assignment + escape order) → refinement → gridless area routing; length matching and DPs satisfied each stage; completed 7 commercial designs the commercial tool could not.
- DP escape → [diff pairs](diff-pair-routing.md). Package analogue: Kubo–Takahashi BGA package global routing determined by via assignment.

## Tools and ML

- FanoutNet: PPO picks per-pin layer/offset/direction for a negotiated A*; 100% vs Freerouting 81%, ELECTRA 91%, NB-A* 95% on Huawei 6-layer HDI boards, but 245 min → [ML/RL routing](ml-rl-routing.md#fanoutnet).
- Freerouting fanout: "no congestion analysis of any kind", vias "at first feasible location" → [freerouting](freerouting.md); KRT has BGA/QFN fanout; practitioners: tools fall back to "a smaller, sub-spec via" at fine pitch ([malakaRouter3](https://github.com/Ivshti/malakaRouter3) [P]).
- DQN escape on a 25×26 toy grid (SPIE'25) [S]; learned dual predictions warm-start ε-relaxation MCF, 1.64× faster (IC, [arXiv 2601.20203](https://arxiv.org/abs/2601.20203)) [P-abs].
- Microfluidics/package analogues (PACOR, McDaniel, MCMF RDL, bump assignment) → [cross-domain routing](cross-domain-routing-transplants.md#other-physical-design-domains).

## Escape in kae

[I]
- Escape is a solver call that may return "impossible": flow with correct diagonal capacity for single layer; MonoSAT (`-DGPL=OFF`) or CP-SAT/flow MILP (HiGHS/SCIP) for multi-layer with via-type choices and DP same-layer constraints; return a solution or a proof that N layers / this via technology is insufficient.
- LLM chooses via technology, layer budget, DP and bus groupings and swappable pins (FPGA banks, MCU alternate functions, DDR DQ bits within a byte lane, connector pins, resistor arrays) from datasheets; an exact pin-assignment + escape solver optimizes within groups; ECO written back to the schematic.
- Untangle twisted buses near escape → [length matching](length-matching-and-buses.md); lock escape results before bulk routing.
- Small windows: Numberlink-style SAT/ZDD with vias as bridges → [cross-domain routing](cross-domain-routing-transplants.md#puzzles-and-sat).

## Open questions

- No public code for the academic escape routers (except generic MonoSAT; its BGA scripts not found); industrial benchmark sets private.
- Runtimes of minutes to ~1 h on 2000-pin parts suit planning, not inner loops.

## Sources

- [routing_classics_supplement.md § Q3, Q5, Implications](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md); [routing_algorithms.md § Q2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_algorithms.md); [solver_toolbox.md § 1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)
