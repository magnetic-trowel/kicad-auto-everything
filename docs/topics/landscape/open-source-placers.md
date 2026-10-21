# Landscape: placement engines available (open source and what exists in KiCad)

**TL;DR**
- **No mature, constraint-aware, KiCad-integrated open PCB placer exists.**
  - KiCad has only a 2011–12 autoplacer behind `RunAction`.
  - No PCM plugin is an optimizing autoplacer.
  - Every open AI tool punts on placement [P].
- **Reusable pieces:**
  - **Cypress** (NVlabs, Apache-2.0, ISPD '25): GPU, DREAMPlace-style.
  - **kicad-tools** (MIT): force-directed, GA, CMA-ES.
  - **HierPlace** (MIT).
  - **tscircuit's Sequential Optimal Packing** (documented).
  - **KiCadRoutingTools' placement optimizer** (MIT).
  - **RL_PCB** (MIT, academic) [P].
- **Konnect retired its force-directed and whole-board placers within five weeks.** The force model pulled parts toward board-wide rails, plans did not converge, and they were applied without proof of improvement. The fix: a scorer first, then small explicit moves [P].
- **KRT's lesson:** "The killer isn't the algorithm — it's constraint capture". Refine perturbatively from a seed instead of placing from scratch [P].
- **Cheap proxies cannot rank close candidates.** HPWL correlates with routability at r = −0.92, but at equal crossings routability spans 0.83–0.94. Route the top-k to rank [P].

## Key facts

### Engines
| Engine | License | Mechanism | Notes |
|---|---|---|---|
| **KiCad legacy autoplacer** | GPLv3+ | `ar_autoplacer.cpp` (2011–12, Charras/Hollenbeck) + `spread_footprints.cpp`; actions `pcbnew.Autoplacer.autoplaceSelected` and `…autoplaceOffboard` | Needs Edge.Cuts; skips locked parts; still in master [P] |
| **Cypress** (NVlabs) | Apache-2.0 | GPU analytical placement adapted from DREAMPlace (BSD-3). Abstract: "1-5.9X higher routability … 1-19.7X shorter routed track lengths … up to 492.3X speedup"; benchmark suite "synthesized from real commercial designs" | 55★, 746 commits; DOI 10.1145/3698364.3705346, ISPD '25 pp. 31–41 (confirmed, VK); paper closed-access. Repo: `benchmarks/small-1…small-20`, `pcb-util/kicad_converter.py` + Bookshelf converter, `tuner/`, `dreamplace/`; run `python dreamplace/Placer.py config.json`. `enable_rotation` **defaults to 0**; TOP/BOTTOM kept from input (bottom written `FN`); `/FIXED` supported; **no side-assignment optimization** found. ISPD 2025 Best Paper (per solver_toolbox.md) [P] |
| **kicad-tools** (rjwalters) | MIT | File-based force-directed, evolutionary (GA) and hybrid placers; CMA-ES/Bayesian `kct optimize-placement` (`[placement]` extra) | No KiCad instance needed [P] |
| **KiCadRoutingTools placement optimizer** | MIT | "Placement optimization for routability"; experiments June–Aug 2026 incl. router-in-the-loop repair (`place_route_loop.py`); argues seed refinement beats from-scratch placement | [placement-optimization.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/placement-optimization.md) [P] |
| **KMS `suggest_placement`** | MIT | "Fruchterman-Reingold flavoured" relaxation (DRAFT). Nets attract, overlapping courtyards repel, the outline contains. Power-net name fragments (VBAT, VCC, +3V3) and IC↔decap links weighted. A pin-facing rotation pass tries 0/90/180/270 to minimise pad-level wirelength, then grid snap. Reports pad-level HPWL; dry-run unless `apply=true`; collisions by courtyard AABB | Intended loop: suggest(dry) → `check_courtyard_overlaps` → apply → autoroute best-of-N → `run_drc` [P] ([placement_optimizer.py](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/python/commands/placement_optimizer.py)) |
| **HierPlace v1.1.0** (Dave Vandenbout) | MIT | Hierarchical clustering placement; vendored in KMS `hierarchical_place` | [P] |
| **Konnect placers** (retired) | AGPL-3.0 (reference only) | `score_placement`, `place_decoupling_caps`, `plan_bga_fanout`, union-find `auto_place_from_schematic`, `refine_placement_force_directed`. Constants: `K_SPRING 0.4`, `K_REPEL 80`, `K_WALL 5`, damping 0.85, grid 0.5 mm, patience 4; power nets 3×, diff pairs 5× | Timeline below [P] |
| **kicad-mcp-pro placement** | MIT | Spring embedder: springs, Coulomb repulsion, boundary walls, spiral free-spot search, keepout checks; BGA fanout planner. Tools `pcb_auto_place_by_schematic`, `pcb_auto_place_force_directed`, `pcb_group_by_function`, `pcb_place_decoupling_caps`, `pcb_critique_placement`, `pcb_score_placement` | Konnect's scoring weights originate here [P] |
| **tscircuit Sequential Optimal Packing** (blog, 2026-04-01) | MIT ecosystem | "Sequentially packs chips in the Pack Order. Each time it packs a new chip, it selects the Optimal position based on the Cost Function", searching along the boundary of already-packed parts | Space-minimising packing makes boards "nearly impossible to route"; force-directed is "wildly unpredictable". "LLM loops can easily adapt the design intent representation" (e.g. harden "pack decap with its chip"). tscircuit placement itself is manual `pcbX`/`pcbY`, with flex/grid autolayout in development [P] ([blog](https://blog.autorouting.com/p/sequential-optimal-packing-for-pcb)) |
| **RL_PCB** (Vassallo & Bajada, DATE 2024) | MIT | Each component acts as an RL agent with adaptive rewards | Trained on 6 circuits; Python 3.8, PyTorch 1.13, CUDA 11.7; 71★ [P] |
| **CadMust-Neo** | – | Simulated-annealing KiCad plugin | 29★, created 2026-03 [P] |
| **Domain placers** | various | kicad-kbplacer (keyboards, 543★), kicad-auto-silkscreen (refdes, 37★), PlaceFootprints (by sheet or pattern) | Not general [P] |
| **ALIGN, MAGICAL** (analog IC), **SA-PCB** (OpenROAD project), **DREAMPlace**, **OpenROAD** | BSD-3 | Analog-constraint and VLSI placers | OpenROAD solves a different problem (millions of uniform cells vs tens to hundreds of heterogeneous parts) [P/I] |
| **jagua-rs** / **sparrow** | MPL-2.0 / MIT | Nesting and packing libraries | [P] (licensing.md) |

### PCM placement and reuse plugins (index 2026-10-19)
- Place Footprints 5.0.0 (GPL-2.0, KiCad 10.0–10.1; line, circle or grid).
- Replicate Layout 5.0.1 (GPL-2.0; still built for 10 even though it says the feature is native).
- Save/Restore Layout 4.0.0 (KiCad 9).
- SubLayout 0.2 (BSD-3); HierarchicalPCB 1.1.0 (MIT); Layout Clone 0.3.3 (MIT, IPC).
- Parts Placer 0.1.14 (LGPL-2.1; spreadsheet); Place By Sch 2.2.0 (GPL-3.0).
- KLEPlacement, kbplacer, PosOrient, Snap To Grid.
- **None optimizes** [P] ([packages-v1.json](https://gitlab.com/kicad/addons/repository/-/raw/main/packages-v1.json)).

### Konnect placement timeline
1. **2026-08-26, introduced:** scorer and planners ([668af70](https://github.com/mixelpixx/Konnect/commit/668af70808a754acf4c24c60bfd5dae6d1209a53)).
2. **2026-08-28, locked-part bug:** both planners moved locked footprints because `(locked yes)` was never parsed. A loose text search marked all 15 ecc83 parts locked via nested `(unlocked yes)` ([32c3bbc](https://github.com/mixelpixx/Konnect/commit/32c3bbc93675c022fb01418f35fe96e1c8698ced)).
3. **2026-09-18, force-directed blocked:** "Its global-net spring model can pull one footprint toward every other footprint sharing a board-wide rail, and a non-converged plan previously applied without proving that it improved placement." Plans now need convergence, a strict score improvement (ties don't count), no hard failure or off-board target, and a `max_displacement_mm` ([fd4b8fe](https://github.com/mixelpixx/Konnect/commit/fd4b8fee7296fac012ba0d2608ea49ef4551eadd)).
4. **2026-10-01, retired (#754):** "autonomous whole-board mutation is retired". "Callers should make small, explicit `move_component` operations, read the requested board back after each batch, and run placement scoring and DRC before continuing." Decoupling association now needs a shared **non-ground** net with ≤8 references ("a shared ground rail [is not] proof") ([4ae4048](https://github.com/mixelpixx/Konnect/commit/4ae4048d6496361a5cfef22579ab8e7f599c764f)) [P].

**Konnect `score_placement`** ("the objective judge … The metric lands before any placer exists on purpose"):
- Hard failures: same-side courtyard-bbox overlap; part outside the outline.
- Soft weights: overlap ×20 (cap 40), outside ×20 (cap 40), connector >10 mm from edge ×15 (cap 30), decoupling ×15 (cap 30). The weights are ported from kicad-mcp-pro (MIT).
- The outline is classified `rectangular`/`unproven`/`missing`; unproven containment is skipped "as unproven rather than silently passed", and the planners refuse to plan (#594) [P] ([placement.rs](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/crates/konnect-core/src/tools/placement.rs)).

### Evidence on proxies and placement payoff
- **Cadence US 12,223,248:** 12,000 GA placements of one 350-component board, each via-assigned and autorouted. Correlation with routability: HPWL r = −0.923, normalized crossings r = −0.898. At crossings ≈0.075, routability ranged 0.83–0.94, while rerouting one placement varied by σ ≈ 0.005. "Using HPWL or normalized crossings in the fitness function would lead to sub-optimal PCB component placement" [P] ([USPTO](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12223248)).
- **DeepPCB:** placement time pays back in routing. Details in [deeppcb.md](deeppcb.md) [V].
- **Practitioners:** "A good placement has often autorouted usably well even 30 years ago" [P].
- **No MCP codebase publishes placement-quality numbers** (HPWL, DRC pass rate) on any corpus [P].
- **No placement benchmark exists** [P]. See [measured-tool-comparisons.md](measured-tool-comparisons.md).

## Recommendations for our system
- **Placement is the main build item.** The commercial placement offerings are in [commercial-architecture-patterns.md](commercial-architecture-patterns.md) [I].
- **Build the independent scorer first**, starting from PRO's MIT weights and fixing their known gaps: polygon courtyards, a proven outline, non-ground decap associations, no moves of locked parts. Apply only on strict improvement within a displacement limit [I].
- **Pipeline** [I]:
  1. The LLM produces a floorplan and intent artifacts: rule areas, component classes, DRC, keepouts.
  2. Seed with Sequential Optimal Packing or human-like priors.
  3. Refine with FD, SA or analytical methods (Cypress via Bookshelf, or kicad-tools).
  4. Legalize.
  5. Generate N diverse candidates and rank the top-k by routing (KRT or a Freerouting pass).
- **Make small explicit moves the default LLM edit path** [I].
- **Use KiCad Repeat Layout and Design Blocks for repeated channels** ([../kicad/built-in-automation-features.md](../kicad/built-in-automation-features.md)) [I].
- Placement algorithms themselves (analytical, SA, ML) belong to the `placement/` area.

## Conflicts and open questions
- Cypress paper details are unknown: cost terms, rotation model, benchmark sizes and licence, and which router it was evaluated with.
- Konnect's retirement rationale is qualitative; its commits contain no numbers.

## Sources
- research notes:
  - [existing_tools_and_apis.md § 2, § 4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md)
  - [verification_kicad_and_tools.md § 1 (#22, #28), § 4 (Cypress, KRT)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
  - [kicad_mcp_codebases.md § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md)
  - [patents_and_industry.md § 3 (Cadence data), § 7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/patents_and_industry.md)
  - [solver_toolbox.md § analytical placement](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)
- primary: [NVlabs/Cypress](https://github.com/NVlabs/Cypress), [params.json](https://github.com/NVlabs/Cypress/blob/main/dreamplace/params.json), [RL_PCB](https://github.com/LukeVassallo/RL_PCB)

See also: [open-source-routers.md](open-source-routers.md), [deeppcb.md](deeppcb.md), [quilter.md](quilter.md), [../kicad/mcp-tool-surface-spec.md](../kicad/mcp-tool-surface-spec.md)
