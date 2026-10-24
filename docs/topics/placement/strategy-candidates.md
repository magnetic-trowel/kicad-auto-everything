# Placement strategy candidates for kaebench

**TL;DR**
- Build a shared geometry kit, then a constructive seed + CP-SAT legalizer, slot/orientation clean-up, multi-seed SA, and router-probe-in-the-loop repair. Repair is the strategy most likely to matter [I].
- Cypress is time-boxed; an analytical placer is gated; RL and diffusion are out for now.
- Fix the place-track defects in [dev-eval-plan](../verification/dev-eval-plan.md) (H1, H2, H7, H11, H12) before trusting any number.

## Key facts


All of these plug in through `--command` in three steps:
1. a stdlib extractor runs in the KiCad container (pcbnew → JSON);
2. the solver runs in the venv (OR-Tools, numpy, shapely);
3. a pcbnew writer sets pose, orientation and flip.

Pad positions always come from pcbnew, never from our own rotation maths ([transform-math-pitfalls](../kicad/transform-math-pitfalls.md)).

**Baselines first:**
- B0 `noop` and B1 `reference` + probe;
- B2 random start + our legalizer (measures the legalizer alone);
- B3 [pyplacer](https://github.com/ajokela/pyplacer) (BSD-3);
- B4 kicad-tools (MIT) force-directed, GA and CMA-ES;
- B5 Cypress (P5 below).

| ID | Strategy | Reuse (licence) | Effort | Expected [tag] | Kill |
|---|---|---|---|---|---|
| P0 | Geometry kit: courtyard per rotation, pads, nets, locks, sides, Edge.Cuts polygon, keep-outs; writer verified pad-by-pad | own | 3–4 d | Prerequisite | — |
| P1 | Constructive core-IC + satellites seed (satellites share a non-ground net), cluster macros, CP-SAT floorplan, then NoOverlap2D legalization on a 0.25–0.5 mm grid | `tools/research/solver-bench/` (own), OR-Tools (Apache-2.0) | 4–6 d | legal@1 ≥ 0.95 on A+B [I]; hierarchical CP-SAT legal at N ≤ 1,000 in 71–294 s [M] | legal@1 < 0.9 after two fix rounds means the kit is wrong |
| P2 | Slot assignment (Hungarian) and 4-rotation clean-up, with decap rings that leave escape channels | scipy (BSD-3) | 1–2 d | Shuffling interchangeable parts drops designer clean-route from 0.56 to 0.31–0.39 [P] | Probe completion changes < 0.02 |
| P3 | Multi-seed SA. Wirelength by net class (GND/power × 0.1–0.2), escape halo, crossing term, **displacement-from-seed** term; the attempt index is the seed | `sa_place.py` (own); pyplacer terms | 4–6 d | SA beat monolithic CP-SAT on wirelength by a median of about 20% [M] | Probe completion < P1 + 0.05 on A+B, or HPWL falls while probe completion also falls |
| P4 | Router-probe-in-the-loop repair: fast route (KRT, about 1–3 s), map failed endpoints to blocking parts, re-solve the window with LNS, accept only strict improvement, 10–30 rounds | [KRT](https://github.com/drandyhaas/KiCadRoutingTools) `place_route_loop` (MIT) | 5–8 d | KRT: tigard 13 → 2 failures [P]. Pre-route proxies rank pairs of placements correctly only 0.59–0.75 of the time [P] | < 10% median gain over P3 with extra seeds at equal time, or inner-probe gains don't transfer to the Freerouting probe (Spearman < 0.5) |
| P5 | Cypress adapter with our own KiCad → Bookshelf converter (theirs ignores Edge.Cuts), rotation on, then P1 legalization | [NVlabs/Cypress](https://github.com/NVlabs/Cypress) (Apache-2.0) | 5–8 d, **time-boxed to 3 d for a CPU build** | Independent routed ratio 0.33 vs human 1.00 [P]; reference row, possibly a seed for C | No CPU build in 3 d, or doesn't beat P3 on C |
| P6 | Own analytical global placer (weighted-average WL, pairwise overlap, outline SDF, orientation relaxation) | torch / jax | 8–12 d | Cypress ablation: crossings 0.31 → 0.27 with orientation [P] | Gate: P3 can't finish > 300-part boards in 15 min |
| P7 | Weight tuning (MOTPE) on a 40-board train set, evaluated on val | Optuna (MIT) | 3–4 d | Cypress was tuned this way [P] | Held-out gain < 2 points of probe completion |

**Placement-specific prerequisites** (Phase 0/1 additions):
- **Mechanical anchors:** `--keep-anchors` for mounting holes and edge connectors, or an `anchor_displacement` metric. Otherwise a routability probe rewards moving connectors to the centre.
- **Signal-only HPWL**, never used for ranking.
- **KRT as a second probe.** Freerouting's floor effect on C (0.04 on human placements) makes `probe_cp` meaningless there. Use probe completion normalised by the human placement's probe.

**Not now:** RL or diffusion placers. SA beat Circuit Training on 17/17 proxy-cost comparisons [P].


## Sources

See [dev-eval-plan § Sources](../verification/dev-eval-plan.md#sources).

See also: [dev-eval-plan](../verification/dev-eval-plan.md), [harness](../verification/harness.md)
