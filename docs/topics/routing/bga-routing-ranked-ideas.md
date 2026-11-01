# Research: routing BGAs and dense regions to 100%, or proving we can't

**Status:** literature and internet survey, 2026-10-31. Nothing here is implemented or measured yet. Every gain below is a hypothesis [I].

The question: our remaining open connections cluster in the main BGA's ball field and escape ring. Human layouts on the same boards:
- escape about 2× as many balls;
- use the bottom layer more;
- route less inside the ball field.

Which methods would close these connections? And when a board's own rules make routing impossible, how do we prove it and compute the relaxation that would fix it?

| Doc | Contents |
|---|---|
| [bga-routing-survey](bga-routing-survey.md) | EDA escape models in implementable detail: Yan–Wong network, MonoSAT encoding, layer bounds, diff-pair and variable-rule escape, ML 2023–26. Commercial tools, patents and vendor rules |
| [routing-cross-domain-and-math](routing-cross-domain-and-math.md) | Convergence in FPGA routers, VLSI detailed routing, global routing, RDL, MAPF-LNS2 and other domains; disjoint-paths, Okamura–Seymour, river-routing and homotopy theory |
| [routing-infeasibility-certificates](routing-infeasibility-certificates.md) | Capacity model from KiCad rules; a six-tier certificate ladder; relaxations as KiCad edits; reporting to the LLM |

Placement: these docs assume they sit next to the existing `docs/topics/routing/` docs and link them by sibling path.

## What was searched

**EDA literature.**
- ICCAD, DAC, TCAD, ISPD, ASP-DAC, TODAES and ISQED, 2000–2026: the Wong, Ozdal, Yan, Kong, Chang, Ho, Lee, Lin, Chen and Dong lines.
- Read in full: Tan Yan's thesis, Bayless's thesis, Wang–Shi–Cheng ICCAD'06, Luo–Wong ASP-DAC'08, Tomioka–Takahashi ASP-DAC'08 and GPCB.

**Commercial practice.**
- Tools: Allegro (SPECCTRA fanout, AiBT, GRE, X AI), Xpedition (Sketch Router), Altium (Fanout, ActiveRoute), Zuken Dragon EX, Quilter, DeepPCB, JITX and Flux.
- Patents from Cadence and Mentor/Siemens.
- Vendor guides: AMD UG1099, Intel AN 114 (snippets only) and IPC-2226.

**Neighbouring domains.**
- VPR, RWRoute and HUS, nextpnr router2; TritonRoute, its WXL variant, OpenROAD drt and Dr. CU.
- GRIP, BonnRoute, FastRoute, NTHU-Route, NCTU-GR, CUGR and GPU global routers; InFO and RDL routing.
- MAPF-LNS2 and CBS symmetry reasoning.
- Optical RWA, railway path allocation, robotics braids, quantum and microfluidic wiring.

**Math.**
- Disjoint paths: Robertson–Seymour, Schrijver, Cygan et al.
- Okamura–Seymour and its extensions; flow–cut gaps; the Japanese theorem.
- Cole–Siegel, Leiserson–Maley and Maley; Schrijver's homotopic theorems.
- Channel density and flux; book embedding, circle and permutation graphs; braids.

**Limits.**
- Several primary texts were reached only as abstracts and are tagged [S]: the Liu–Chang matching-based escape (DAC'23/TCAD'25), Lei–Mak, NeuroEscape, CRoute, NCTU-GR and Intel AN 114.
- Nothing was fetched from robots-restricted hosts.

## Top 10 ideas, ranked for our case

Ranking basis: expected effect on a KiCad board under its own DRC rules, with Freerouting plus our numba grid router, against the effort.

1. **Ring and gap cut certificates from the board's rules (C0).** Effort 3–5 days; new module, extends `kae.route.blocked`.
   - Compute each gap's track capacity from the board's own widths, clearances and via sizes (formula in [certificates](routing-infeasibility-certificates.md#capacity-model-from-the-boards-own-rules)).
   - Then compare, for every ring and every row or column cut of each BGA, the nets that must leave against the slots available on all layers.
   - It costs microseconds and is sound when capacities round up.
   - It separates boards that are impossible under their rules from boards where our search failed, which is the first thing the controlling LLM needs.
   - Its relaxation thresholds (track width, clearance, via size, layers) are closed-form.
   - Validate it at once: every human layout that passes DRC must pass C0. That also exposes bugs in our capacity model.
   - Add the Wang–Shi–Cheng and UG1099 layer estimates as context lines.
2. **Escape planner on the Yan–Wong tile network, with its min cut (C2).** Effort 1.5–2 weeks; replaces the fixed dog-bone pre-pass on branch `rules-escape`, and is work item (1).
   - Build the five-node network per signal layer with capacities from the rules, and treat dog-bone via sites as blocking.
   - Run OR-Tools min-cost flow with the top layer for outer rings and the bottom layer, through a dog-bone, for the next rings, as humans and vendor guides do.
   - Decompose the flow into per-ball escapes, write them as protected wires before Freerouting, and let Freerouting route from the escape ends.
   - It directly targets "humans escape 2× more balls and use the bottom layer", it is exact for single-layer and via-in-pad escape, and the min cut is a named certificate.
   - Relaxation what-ifs are reruns that take under a second.
3. **Window repair as MAPF-LNS2, not global PathFinder.** Effort 1–2 weeks; reuses the `lastmile.py` and `critical_grid.py` A*, and replaces greedy rip-up inside BGA windows. This is work item (2).
   - Route every window net with conflicts allowed.
   - Then repeatedly re-plan 4–16 conflicting nets, picked adaptively from collision-graph components, the nets blocking a boxed-in pad, and random nets. Use lexicographic A* on (conflicts, cost).
   - Accept only moves that do not raise the number of conflicting pairs.
   - This gives the monotone progress our generic PathFinder lacked. On MAPF instances where prioritized planning with restarts failed, it solved 300 agents in seconds.
4. **Convergence kit, if PathFinder is kept.** Effort 2–4 days on top of item 3 or the planned window router.
   - History-centric costs: nextpnr's constant present weight 5 and history 0.5, or the HUS switch from present ×2 to ×1.1 and history 1 to 2.
   - Connection-based reroute, seeded shuffles, dynamic boxes, best-so-far state.
   - A VPR-style log-linear predictor with a low floor, which stops non-converging runs and hands them to the certificates.
   - These are shipped fixes for exactly the oscillation we saw.
5. **Floating window terminals.** Effort 3–5 days.
   - Fixed border crossings inherited from Freerouting can make a window infeasible by themselves.
   - Model each net's crossing as an interval of the border on any allowed layer (one super-terminal), then re-stitch outside with the last mile.
   - It is also required for window certificates to be sound for the whole board.
6. **Duality lower bound from negotiation prices (C3 for free).** Effort 3–5 days once item 3 or 4 exists.
   - After each negotiation round, compute each net's exact cheapest route under the current prices. GAMER-style row and column sweeps in numba suit this.
   - If Σ costs exceeds Σ prices, the window is infeasible even fractionally (min-max resource sharing weak duality).
   - The prices with the largest d·c name the bottleneck, and Σ d·Δc ≥ 1 − λ* bounds the relaxation needed.
   - This turns "ran out of iterations" into a proof or into "keep going".
7. **Via sites as variables (MonoSAT pattern) in CP-SAT, with assumption literals per rule (C5).** Effort 3–5 weeks; small or residual windows only.
   - Encode via types from the stackup as blocking clauses, cell exclusivity and per-net flow.
   - UNSAT gives a core over rule literals. MaxSAT, or CP-SAT minimising relaxation literals, gives the cheapest fix, for example via-in-pad on these balls or w = 0.09 in the courtyard.
   - This is the only exact "why" with a minimal relaxation, but it is expensive. Use it after items 1–6 have narrowed the window.
8. **TritonRoute-style clip schedule for large BGAs.** Effort 1–2 weeks; generalises item 3's window into tiles.
   - Clips 6–10 ball pitches wide with offsets shifted per pass.
   - Route, DRC and context boxes; pin-access via reservation for every ripped net.
   - Decaying marker history, and a 3×3 cost portfolio on stubborn tiles.
   - Use it when one window is too big to solve as a whole.
9. **Fixed-topology cut test after Freerouting (C4).** Effort 1 week.
   - Run the Cole–Siegel/Schrijver test per layer on the routed topology.
   - If rules-level tiers C0–C3 pass and C4 fails, the fix is re-topologising (rip-up the named nets), not relaxing rules.
   - It tells the pipeline which of items 3 and 7 to run, and names the cut.
10. **Pair-aware escape and swap-aware planning.** Effort 1–2 weeks each.
    - Yan–Wu–Ma–Wong's optimal single-pair escape routine (min-cost 2-flow to a merge tile) as a pair search in the last mile. Merged pairs count as one 2-track unit in capacities.
    - Treat breakout endpoints as pseudo-pins (US 8,103,988), so that LLM-chosen pin, bank or bit swaps are evaluated on escape order.
    - Use the LDS and circle-clique layer bounds to show what a swap saves.

## Try first

- **1, then 2:** they share the gap-graph builder.
- **3 with 4's schedule and 5:** the window reroute.

Reasons:
- Item 1 is days of work and answers the controlling LLM's first question with a proof. The human layouts give a free check that the capacity model is sound.
- Item 2 attacks the measured cause, too few balls escaped and the bottom layer unused, at the stage commercial tools also treat separately. Its min cut is the certificate for work item (1).
- Item 3 replaces the PathFinder that did not converge with a loop whose progress is monotone, and floating terminals remove a likely source of false infeasibility.

## Related

[escape-routing](escape-routing.md) · [pathfinder-negotiated-congestion](pathfinder-negotiated-congestion.md) · [topological-routing](topological-routing.md) · [layer-assignment-and-vias](layer-assignment-and-vias.md) · [strategy-candidates](strategy-candidates.md)
