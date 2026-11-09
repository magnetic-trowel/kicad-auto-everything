# Research: routing BGAs and dense regions to 100%, or proving we can't

Scope: ranked plan for closing open connections in BGA ball fields and proving infeasibility under the board's own rules. Not here: method detail -> [BGA survey](bga-routing-survey.md), [dense-region math](routing-cross-domain-and-math.md), [certificates](routing-infeasibility-certificates.md).
Keys: BGA, dense region, open connections, ring cut, gap cut, C0, C2, C3, C4, C5, Yan–Wong escape planner, MAPF-LNS2 window repair, convergence kit, floating terminals, duality bound, via sites as variables, TritonRoute clips, pair-aware escape, pseudo-pins, rules-escape, work item (1), work item (2)

**Status:** literature and internet survey, 2026-10-31. Nothing implemented or measured; every gain is a hypothesis [I].

Problem: our remaining open connections cluster in the main BGA's ball field and escape ring. Human layouts on the same boards escape ~2× as many balls, use the bottom layer more, route less inside the ball field. Question: which methods close these connections, and when the board's own rules make routing impossible, how to prove it and compute the fixing relaxation.

## What was searched

- EDA literature: ICCAD, DAC, TCAD, ISPD, ASP-DAC, TODAES, ISQED 2000–2026 (Wong, Ozdal, Yan, Kong, Chang, Ho, Lee, Lin, Chen, Dong lines). Read in full: Tan Yan's thesis, Bayless's thesis, Wang–Shi–Cheng ICCAD'06, Luo–Wong ASP-DAC'08, Tomioka–Takahashi ASP-DAC'08, GPCB.
- Commercial: Allegro (SPECCTRA fanout, AiBT, GRE, X AI), Xpedition (Sketch Router), Altium (Fanout, ActiveRoute), Zuken Dragon EX, Quilter, DeepPCB, JITX, Flux; Cadence and Mentor/Siemens patents; AMD UG1099, Intel AN 114 (snippets only), IPC-2226.
- Neighbouring domains: VPR, RWRoute, HUS, nextpnr router2; TritonRoute, WXL, OpenROAD drt, Dr. CU; GRIP, BonnRoute, FastRoute, NTHU-Route, NCTU-GR, CUGR, GPU global routers; InFO/RDL; MAPF-LNS2, CBS symmetry; optical RWA, railway path allocation, robotics braids, quantum and microfluidic wiring.
- Math: disjoint paths (Robertson–Seymour, Schrijver, Cygan et al.); Okamura–Seymour and extensions; flow–cut gaps; the Japanese theorem; Cole–Siegel, Leiserson–Maley, Maley; Schrijver homotopic theorems; channel density and flux; book embedding, circle and permutation graphs; braids.
- Limits: reached only as abstracts [S]: Liu–Chang matching-based escape (DAC'23/TCAD'25), Lei–Mak, NeuroEscape, CRoute, NCTU-GR, Intel AN 114. Nothing fetched from robots-restricted hosts.

## Top 10 ideas, ranked for our case

Ranking: expected effect on a KiCad board under its own DRC rules, with Freerouting plus our numba grid router, against effort.

| # | Idea | Effort | Mechanism | Why |
|---|---|---|---|---|
| 1 | Ring and gap cut certificates from the board's rules (C0) | 3–5 d; new module, extends `kae.route.blocked` | Gap track capacity from board widths/clearances/via sizes ([formula](routing-infeasibility-certificates.md#capacity-model-from-the-boards-own-rules)); for every ring and every row/column cut of each BGA compare nets that must leave vs slots on all layers; add Wang–Shi–Cheng and UG1099 layer estimates as context lines | Microseconds; sound when capacities round up; separates "impossible under rules" from "our search failed"; closed-form relaxation thresholds (track width, clearance, via size, layers). Validate: every human layout passing DRC must pass C0 (also exposes capacity-model bugs) |
| 2 | Escape planner on the Yan–Wong tile network with its min cut (C2) | 1.5–2 w; replaces fixed dog-bone pre-pass on branch `rules-escape`; work item (1) | Five-node network per signal layer, rule-derived capacities, dog-bone via sites blocking; OR-Tools min-cost flow, top layer for outer rings, bottom via dog-bone for next rings; decompose into per-ball escapes written as protected wires before Freerouting, which routes from escape ends → [survey](bga-routing-survey.md#escape-pipeline-for-kae) | Targets "humans escape 2× more balls and use the bottom layer"; exact for single-layer and via-in-pad; min cut = named certificate; relaxation what-ifs rerun in < 1 s |
| 3 | Window repair as MAPF-LNS2, not global PathFinder | 1–2 w; reuses `lastmile.py`/`critical_grid.py` A*, replaces greedy rip-up inside BGA windows; work item (2) | Route all window nets with conflicts allowed; repeatedly re-plan 4–16 conflicting nets picked adaptively (collision-graph components, nets blocking a boxed-in pad, random); lexicographic A* on (conflicts, cost); accept only if conflicting pairs do not rise → [math § 5](routing-cross-domain-and-math.md#5-mapf-beyond-what-we-have) | Monotone progress our region negotiation lacked (a non-standard PathFinder variant: per-net history, every net re-routed each round, 20 rounds; [pathfinder](pathfinder-negotiated-congestion.md), Results 5); on MAPF it solved 300 agents in seconds where prioritized planning with restarts failed |
| 4 | Convergence kit, if PathFinder is kept | 2–4 d on top of 3 or the window router | History-centric costs (nextpnr present 5, history 0.5; or HUS present ×2 → ×1.1, history 1 → 2); connection-based reroute; seeded shuffles; dynamic boxes; best-so-far state; VPR-style log-linear predictor with low floor handing non-converging runs to certificates → [math § 1](routing-cross-domain-and-math.md#1-fpga-routers-convergence-machinery) | Shipped fixes for the oscillation we saw |
| 5 | Floating window terminals | 3–5 d | Each net's border crossing = interval of the border on any allowed layer (one super-terminal); re-stitch outside with the last mile | Fixed crossings inherited from Freerouting can alone make a window infeasible; required for window certificates to be sound for the whole board |
| 6 | Duality lower bound from negotiation prices (C3 for free) | 3–5 d once 3 or 4 exists | After each round, each net's exact cheapest route under current prices (GAMER-style row/column sweeps in numba); Σ costs > Σ prices ⇒ infeasible even fractionally (min-max resource sharing weak duality); prices with largest d·c name the bottleneck; Σ d·Δc ≥ 1 − λ* bounds the needed relaxation | Turns "ran out of iterations" into a proof or "keep going" |
| 7 | Via sites as variables (MonoSAT pattern) in CP-SAT with assumption literals per rule (C5) | 3–5 w; small/residual windows only | Via types from the stackup as blocking clauses, cell exclusivity, per-net flow; UNSAT core over rule literals; MaxSAT or CP-SAT minimizing relaxation literals gives the cheapest fix (e.g. via-in-pad on these balls, or w = 0.09 in the courtyard) | Only exact "why" with minimal relaxation; expensive, run after 1–6 narrow the window |
| 8 | TritonRoute-style clip schedule for large BGAs | 1–2 w; generalizes 3 into tiles | Clips 6–10 ball pitches, offsets shifted per pass; route/DRC/context boxes; pin-access via reservation for every ripped net; decaying marker history; 3×3 cost portfolio on stubborn tiles | When one window is too big to solve whole |
| 9 | Fixed-topology cut test after Freerouting (C4) | 1 w | Cole–Siegel/Schrijver test per layer on the routed topology | C0–C3 pass + C4 fails ⇒ re-topologize (rip up the named nets), not relax rules; picks between 3 and 7; names the cut |
| 10 | Pair-aware escape and swap-aware planning | 1–2 w each | Yan–Wu–Ma–Wong optimal single-pair escape (min-cost 2-flow to a merge tile) as last-mile pair search; merged pairs = one 2-track unit; breakout endpoints as pseudo-pins (US 8,103,988) so LLM pin/bank/bit swaps are evaluated on escape order; LDS and circle-clique bounds show what a swap saves | — |

## Try first

- 1, then 2 (they share the gap-graph builder): 1 answers the controlling LLM's first question with a proof in days, and human layouts check the capacity model for free; 2 attacks the measured cause (too few balls escaped, bottom layer unused) at the stage commercial tools also separate; its min cut is the certificate for work item (1).
- 3 with 4's schedule and 5 (the window reroute): replaces the non-converging PathFinder variant with monotone progress; floating terminals remove a likely source of false infeasibility.

## Related

[escape routing](escape-routing.md) · [PathFinder](pathfinder-negotiated-congestion.md) · [topological](topological-routing.md) · [layer assignment](layer-assignment-and-vias.md) · [strategy candidates](strategy-candidates.md)
