# BGA / escape routing: exact flow, MCF and SAT formulations

**TL;DR**
- Escape is the most mathematically closed PCB subproblem: single-layer escape = network flow (with **correct diagonal capacity** for 45°), ordered escape = multi-commodity flow or SAT, multi-layer escape with vias = SAT + flow (MonoSAT).
- MonoSAT **proved minimal layer counts** on real BGAs/FPGAs (Xilinx XCVU440, 1755 signals: 4 → 3 layers) in minutes to ~1 h — an infeasibility proof is unique, high-value feedback for stackup/HDI decisions.
- **Pin assignment + escape is polynomial-optimal** (80 buses, >7000 nets in <5 min); bus sequencing O(n log n) — pin/bank/bit swap should be a first-class LLM action.
- Academic escape routers matched or beat Cadence Allegro on industrial cases (B-escape, NCER, Lin DAC'21). Almost none has public code.
- Learned fanout (FanoutNet) helps but is slow; practitioners report tools fall back to sub-spec vias at fine pitch.

## Key facts

**Simultaneous escape routing (Ozdal–Wong line)** [P-abs]
- Separate under-component routing from the intermediate area; SER minimizes intermediate crossings as **longest path with forbidden pairs**; exact polynomial maximal planar solution on one layer + randomized variant; layer assignment = max planar subset per layer ([IEEE 1637740](https://ieeexplore.ieee.org/document/1637740/)).
- + high-speed constraints: −39% vias on industrial cases ([IEEE 1560166](https://ieeexplore.ieee.org/document/1560166/)).

**Bus-aware escape** [P-abs]
| Result | Complexity / scale |
|---|---|
| Bus sequencing as longest common interval sequence (Kong, Yan, Wong, Ozdal ICCAD'07); "no commercial CAD software can provide an automatic solution" | O(n log n) optimal |
| Minimum layers for bus escape (Yan, Kong, Wong ICCAD'09) | optimal |
| Consecutive-layer bus assignment (Ma, Young, Wong DAC'11) | branch-and-bound optimal |
| **Simultaneous pin assignment + escape** (Kong, Yan, Wong ASP-DAC'10) | polynomial optimal; 80 buses, >7000 nets, <5 CPU min ([IEEE 5419881](https://ieeexplore.ieee.org/document/5419881/)) |

**Exact models**
- SAT ordered escape (Luo–Wong ASP-DAC'08; fixed and scaled '09): prior approaches "cannot guarantee to find a routing solution even if one exists" [P-abs].
- **Correct network-flow model** (Yan–Wong DAC'09/TCAD'12): "none of the previous works correctly models the diagonal capacity, which is essential for 45° routing"; first optimal escape algorithm; handles missing pins [P-abs].
- Staggered arrays: LP/ILP orthogonal-side wiring (Ho, Lee, Chang ICCAD'11); flow models guaranteed to find a solution if one exists (Wu–Wong ASP-DAC'13) [P-abs].
- Ordered escape by min-cost **multi-commodity flow** (Jiao–Dong ASP-DAC'16, 100% on tests); multi-capacity ISQED'23 (≤308 pins); **MCMCF-Router (TODAES'24): up to 525 pins, 100% in <810 s** (VP: not "2000+") ([DOI](https://doi.org/10.1145/3695253) [P-abs]).
- LP network-flow SER solving net ordering and escape together (Sattar–Ignjatovic) [P-abs]; two-stage flow ILP for escape + area routing (PeerJ CS 499) [S].

**MonoSAT multi-layer escape** (Bayless, Hoos, Hu ICCAD'16; [PDF](https://www.cs.ubc.ca/labs/isd/Projects/monosat/monosat_bga_iccad2016.pdf) [P])
- Multi-layer escape "cannot be modelled as a pure network flow problem"; practice is greedy layer-by-layer.
- SAT modulo monotonic theories with flow constraints places traces **and** vias simultaneously; 45°/90°; through, blind, buried, any-layer micro-vias; accepts partial solutions; diff pairs by forcing both signals' vias to the same layer.

| Part (blind vias) | Greedy layers | MonoSAT |
|---|---|---|
| TI AM5716 (28×28, 382 signals) | 3 | **2, proven minimal** |
| TI TMS320C | 4 | 3 |
| Xilinx XCVU440 (54×54, 1755 signals) | 4 | **3, proven minimal** (1597 s + 2727 s) |
| TMS320C / AM52E02 (through vias) | 5 | 3 |

Average trace length slightly longer (21.6 vs 20.0 mm). License: MIT, but links GPLv2 code by default — build with `-DGPL=OFF` ([README](https://raw.githubusercontent.com/sambayless/monosat/master/README.md) [P-doc]).

**Negotiated / boundary / full-flow vs commercial** [P-abs]
- NCER (Ma, Yan, Wong ISQED'10): negotiated-congestion escape; NCER and Allegro each fully routed 7/14 industrial cases, 11/14 together ("complementary").
- B-escape (ISPD'10, boundary routing): solved all industrial problems; Allegro completed about half.
- Multiple components sharing buses (Chin–Chen EDAPS'13).
- **Lin, Wang, Kuo, Chen, Li DAC'21**: SER (layer assignment + escape order) → refinement → gridless area routing, length matching and DPs satisfied each stage; completed 7 commercial designs the commercial tool could not complete.
- DP escape methods: [diff-pair routing](diff-pair-routing.md). Package analog: Kubo–Takahashi BGA package global routing determined by via assignment.

**Tools and ML**
- FanoutNet (PPO picks per-pin layer/offset/direction for a negotiated A*): 100% vs Freerouting 81%, ELECTRA 91%, NB-A* 95% on Huawei 6-layer HDI boards, but 245 min ([ML/RL routing](ml-rl-routing.md)).
- Freerouting fanout: "no congestion analysis of any kind", vias "at first feasible location" ([freerouting](freerouting.md)); KRT has BGA/QFN fanout; practitioners: tools fall back to "a smaller, sub-spec via" at fine pitch ([malakaRouter3](https://github.com/Ivshti/malakaRouter3) [P]).
- DQN escape on a 25×26 toy grid (SPIE'25) [S]; learned dual predictions warm-start ε-relaxation MCF, 1.64× faster (IC, [arXiv 2601.20203](https://arxiv.org/abs/2601.20203)) [P-abs].
- Microfluidics/package analogs: PACOR (DME + MCF escape + bounded detours), McDaniel negotiated escape on a biochip PCB, MCMF RDL routing, routability-driven bump assignment ([cross-domain routing](cross-domain-routing-transplants.md)).

## Recommendations for our system
- **Escape is a solver call that may return "impossible"**: flow with correct diagonal capacity for single layer; MonoSAT (`-DGPL=OFF`) or CP-SAT/flow MILP (HiGHS/SCIP) for multi-layer with via-type choices and DP same-layer constraints; feed back a solution or a proof that N layers / this via technology is insufficient [I].
- The LLM chooses via technology, layer budget, DP and bus groupings and **swappable pins** (FPGA banks, MCU alternate functions, DDR DQ bits within a byte lane, connector pins, resistor arrays) from datasheets; an exact pin-assignment + escape solver optimizes within groups; write an ECO back to the schematic [I].
- Untangle twisted buses near escape ([length matching and buses](length-matching-and-buses.md)); lock escape results before bulk routing [I].
- Small windows can also be solved as Numberlink-style SAT/ZDD with vias as bridges ([cross-domain routing](cross-domain-routing-transplants.md)) [I].

## Conflicts and open questions
- No public code for the academic escape routers (except generic MonoSAT; its BGA scripts not found); industrial benchmark sets private.
- Runtimes of minutes to ~1 h on 2000-pin parts are acceptable for planning but not for inner loops.

## Sources
- research notes: [routing_classics_supplement.md § Q3, Q5, Implications](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md); [routing_algorithms.md § Q2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_algorithms.md); [solver_toolbox.md § 1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)

See also: [diff-pair-routing](diff-pair-routing.md) · [length-matching-and-buses](length-matching-and-buses.md) · [solvers/cp-sat-milp-smt](../solvers/cp-sat-milp-smt.md)
