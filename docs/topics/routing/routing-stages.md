<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Routing stages: what each stage decides, and when each copper change belongs

Scope: the order of kae's routing work, from the plan to the board handed back, and where pad entries, arcs, necks and power copper belong in it.
Keys: pipeline, stage order, pad entry, taut arcs, power copper, necks, DRC gate, restart portfolio, finish stage

**TL;DR**
- **Topology, then shape, then fill.** Decide which way copper goes first: connections, layers, vias. Then fix its shape on that topology: pad entries, tightening, arcs. Last, give the space that is left to fill: wider rails, pours, stitching. Shape keeps a path's homotopy, so it can neither block nor open a connection. Fill uses up space, so done any earlier it would block routing [I].
- **Born right where kae draws copper; finished once where it does not.** kae's grid router (critical copper, escapes, repair joins, last mile) draws rule D entries, necks and an overhang-free final piece directly. Freerouting cannot (its pin connection is the pin centre by construction), so its copper is finished in one new stage on the kept board [M: [pad-edge entry](../../research/routing/kae-pad-edge-entry.md)].
- **Rules live in the plan, not in the passes.** The entry rule, the neck per land and the width a current needs are computed once (`constraints.plan`), and every producer and checker reads that one copy [I].
- **Shape before lock.** Copper that later stages treat as fixed gets its final shape before it is fixed. The taut pass could not touch 861 branches on 12 boards because they were locked critical copper and joins [M: [taut arcs](../../research/routing/kae-taut-arcs.md)].
- **One gate per stage boundary.** Inside a stage every change is checked exactly (`Space`); KiCad's DRC runs once at the end of the stage, on a journal of changes tagged by stage, net and dependency, so a revert is surgical. Today the three post-passes run three DRC gates on the same board [M].
- **Spend once on the kept board** what does not change which attempt wins. Finishing an attempt the portfolio throws away is wasted.

## 1. Principles

| # | Principle | Why | Consequence |
|---|---|---|---|
| P1 | Topology → shape → fill | Shape changes are homotopic, so they leave which connections can be made unchanged; fill consumes the space routing needs | Pad entries and arcs come after the last topology change; power-copper widening comes after them |
| P2 | Born right where we draw | Fixing copper after it is drawn costs a search, a gate and failures (27 "no route", 20 "release point at the pad" for rule D) | `GridRouter` takes pad_entry's targets as goals; the finish stage handles only Freerouting copper |
| P3 | One copy of each rule | Two copies drift (metro-m7: taut's own rule D copy ended tracks 0.04 mm off pad_entry's) | `pad_entry` (targets, overhang, neck width) and `power_copper.current_need` are the only implementations; the plan carries their per-pad results |
| P4 | Shape before lock | Locked copper cannot be finished later | Critical copper is tightened (physics-guarded) before it is locked for Freerouting |
| P5 | Exact check inline, KiCad at boundaries, journaled | KiCad's DRC is the slowest step on big boards; a stage-level revert throws away good changes | A shared change journal; one ddmin gate per stage |
| P6 | Per-attempt work only if it changes the winner | Attempts are ranked by (errors, unconnected); finishing changes neither on 11 of 12 boards | Finish runs in the portfolio's final pass |
| P7 | Physics on shipped shapes | Loops that iterate (joint, retweak) must optimize what will be handed back | Joint quotes use born-right grid copper; the recheck runs after finish |
| P8 | Nothing silent | The LLM must know what could not be done | Every stage emits hazards in the shared schema ([hazards](../architecture/hazards.md)) |
| P9 | Deterministic and cached | The step cache already saves 38–45 % of a warm A/B | Finish is keyed by board hash, code and options |

## 2. The stages

| Stage | What it decides | Today | Change |
|---|---|---|---|
| 0 Placement | Where parts sit; room to escape | Placement session; escape bands off by default | Ask placement to keep room for square approaches and necks (a note, not code here) |
| 1 Plan (`constraints.plan`) | Rules every stage obeys | Classes, clearances, vias, thermal corridors | **Adds** per-pad entry frame and rule (D), neck width per two-terminal land (process, package class, series current), required width per rail branch (`current_need`), arc policy |
| 2 Critical copper (`critical`) | Physics-first copper, locked | Grid routes; ends at pad centre or the edge rule | **Born right:** rule D goals, necks, overhang check. **Tightened before lock:** taut on module and rail copper; a move is kept only if the module's routed physics is no worse |
| 3 Escapes (`lastmile.plane_escapes`, `escape`) | Plane joins, ball-grid dog-bones | Stub plus via per pad the fill misses | Stubs end by rule D. Ground vias at decap and IC ground pads move here from power copper as an A/B arm: reserved before routing instead of fitted afterwards |
| 4 Freerouting | Bulk topology | Unchanged | Unchanged; its centre ends are expected and finished in stage 7 |
| 5 Repair rounds (`repair.loop`) | Fixes DRC errors, re-routes what is open | Unchanged | Grid joins born right. Arm: rule D tails on each import's new Freerouting copper (cheap, exact check only), so repair sees final ends |
| 6 Last mile (`lastmile.close`) | Closes the last opens | Grid router with rip-up | Born right (P2) |
| 7 **Finish** (new, `kae.route.finish`) | Final shape and fill on the kept board | Three post-passes with three gates, power copper off by default, rule D and taut not wired in | (a) rule D tails on Freerouting copper → (b) taut and arcs on all unlocked copper → (c) power copper (widening, zones above 5 A, sharing, necks, stitching) → (d) one journaled DRC gate → (e) hazards |
| 8 Recheck / retweak (`critical_recheck`) | Modules that got worse | On the routed board | On the finished board; a retweak re-runs stage 7 only on the region it ripped |
| 9 Diagnose (`blocked`) and report | Why opens are open; hazards | Unchanged | Unchanged, on the finished board |

**Where the portfolio runs it.** Attempts run stages 1–6. The restart wrapper's final pass (`--final`) on the kept board runs the last mile, then stage 7, with its time reserved from the start (`final_reserve`). A single attempt (`kae.route.cli route`) runs stage 7 at its end when time is left.

### As built (stages 1, 2, 3, 5, 6; branch `rf-plan`)

Where the code differs from the table above, and why [I]:
- **Per pad, not per rail branch.** The plan's rule is `constraints.PadRule`, one per pad routing may end on (`plan.pad_rules`, by DSN pad index): the rule-D call, the neck (`power_copper.land_necks`, which `PowerCopper._necks` calls too), the pad's current and `current_need`. A rail branch's width stays with the critical rails.
- **Rails and grounds: the brief and the names.** The plan takes the physics brief's rails and grounds (built from the board, cached by content) together with the name rules of `pad_entry.current_net`, minus switch nodes. On the 12 pad-entry boards the brief finds 24 rails the names miss (redbot V_BATT, nekoink IPSOUT, ...) and misses 2 (secsense 3V3, VIN); grounds agree [M].
- **The land hazard is raised for two-terminal lands in series with a rail only** (where `neck_rule` drops the neck). IC pins whose current needs more than their land would flag nearly every regulator pin.
- **Mask web.** cm4-carrier's 16 reverts were drawn mask openings over solder jumpers (`Segment of JP1 on B.Mask`), not pad webs: the plan's apertures are other nets' pad openings and the drawn openings that expose this net and another (`pad_entry.mask_ok`).
- **Goals, then the old entry, never a lost connection.** `GridRouter` searches to rule-D approach anchors from release points all round the land; entering a land otherwise costs 2 mm extra. The old entry is taken where no anchor is free, or after 3 anchors fail the exact check (counter `fallback_old_entry`).
- **Module hops rank by the module's physics.** For hops of physics modules (`critical_modules._entry_by_physics`), the router's best rule-D route, the best without its approach at either end, and the old entry are each committed, quoted (`quote`) and taken out; the lowest wins, rule D on a tie. Where the module cannot be quoted before its last hop (decaps, crystals, chains), each candidate is priced by the hop's own term of that physics: microstrip inductance from terminal centre to terminal centre for loops, trace capacitance for crystals, length over width otherwise. An acute entry is kept only where nothing else routes. Fixture, aifryz: 12 modules no worse, 5 better (crystals to −13 %, +BATT decap −10 %), 3 worse by 2–3 % (two decaps whose old entry was acute; Y1, whose hops joined other pads, which a per-hop choice cannot see) [M]. Quoting took 0.16 s.
- **Other lands of the net are obstacles.** Lands of the route's net that are neither source nor target are kept out of the search and of string pulling; a route that finds no way round crosses them after all (`fallback_crossing`).
- **Necked lands stay leaves.** A necked land that already has its track is dropped from the anchors when others remain, so a second route joins its track instead of chaining through the neck (`neck_leaf`). The neck is sized for the land's own current (a decap carries no DC); routing the load current through it would need the downstream current at commit time, which the grid router does not have.
- **Space measures pads from their real copper.** The DSN pin class adds the largest excess of the pad's copper over its DSN shape on every side. Space now uses the real copper with the plain requirement (`plan.pin_exact`); the DSN keeps the padded class for Freerouting. Against KiCad on the 12 bare boards (`rule_port_audit.py`, 2,200 pad tests) too-lax stays 0 and too-strict goes from 234 to 230 (ubertooth 41 to 37). The rest (rectangular pads KiCad accepts 10 µm closer) has no cause found yet [M].
- **Commit sites carry the neck** (`Route.necks`, `seg_w`): `critical_modules.commit` and its re-width, `lastmile._commit`, `em.pnr`.
- **No centre piece for Freerouting on the board.** KiCad, and so the scorer, connects any overlap; only Freerouting needs a pin's centre, and `translate.tie_pins` gives it a fixed DSN tie whenever `pad_entry` is not "centre". Critical copper's `join_at_corners` therefore adds no piece from a rule-D end to the pad centre (counter `pin_ties`); via ends keep theirs.
- **Unchanged:** `pad_reroute` (track anchors) and the escape stage's dog-bones (centre).
- **Arm E** (`escape_ground_vias`, default 0; `KAE_ESCAPE_GROUND_VIAS`) calls power copper's selection and placement (`ground_via_pads`, `lay_ground_vias`) in `lastmile.plane_escapes` and writes the vias and their tracks locked: fixed wiring for Freerouting, and in the bridge's `fixed_uuids`, which the repair loop never rips or unlocks.
- **Settings.** `pad_entry` "centreline" (default; "edge" reads as it) or "centre"; `arc_policy` "arcs" or "keep45" in the plan.

## 3. Why this order, step by step

**Rule D before taut.** Taut keeps each path's homotopy and its fixed end points. The pad entry decides the end point and the last piece, so it has to come first, and taut then tightens up to the approach anchor; its tangent arc replaces the corner D leaves. Both use `pad_entry.centreline_targets` (P3).

**Taut before power copper.** Widening grows copper into the space beside it. Tightened signals sit against their obstacles and leave the free side in one piece, so widening has more room. Widening an untightened route and then tightening it would move the signal into space the rail has just been given. Power copper already reads arcs as arcs (`_widen_arc`).

**Necks are a rule, not a pass.** A neck is where copper must be narrow at a two-terminal land (tombstoning, [DFM limits](../rules/dfm-fab-limits.md)). If only power copper knows it, the grid router, rule D and taut can each draw a wide tail into a small land and power copper has to undo it. In the plan, every producer obeys it; where the current needs more than the land, the plan records a `land_enlarged_by_track` hazard once.

**The last mile before finish.** Closing a connection is worth more than any shape. The last mile can rip unlocked copper, so finishing first would be wasted on what it rips. After finish, nothing changes topology except a retweak, which re-finishes only its region.

**Critical copper is tightened at stage 2, not 7.** It is locked for Freerouting, so later is too late (P4). Tightening it on the near-empty board is also cheaper: there is little in the way. The guard is the module's routed physics (`critical_modules.quote`), not length: shorter is not always lower loop inductance.

**Pours and fills.** Every shape stage holds other nets' refilled copper as obstacles and its own net's fill as free. KiCad refills once, in the gate; the refill can only grow into space a tightened track left.

**Why not finish every attempt.** Ranking is by (errors, unconnected). On the 12 boards finishing changed unconnected on one board (nekoink, 114 → 112) and errors on none, and it costs 30–500 s a board. Arm C (§5) measures whether finishing tails inside the repair rounds closes more; if it does, the cheap part (tails) moves into stage 5.

## 4. Interactions that iterate

| Pair | Interaction | Handling |
|---|---|---|
| Repair ↔ finished copper | A repair rip of a finished item wastes the finish | Finish runs after the last topology change; in arm C a violation on a finished tail reverts that tail to its raw shape before anything is ripped |
| Gate ↔ journal | Power copper widens a track taut moved; reverting the taut change alone leaves a widening on a shape that no longer exists | Each journal entry lists the entries it built on; a revert takes its dependants with it |
| Gate ↔ noisy DRC types | magtag's `solder_mask_bridge` count changes from run to run; power copper's gate spent its budget chasing it | The gate compares violations by identity (type, items, position bucket), not by counts; a type that differs between two runs of the same board is noise and excluded, with a note |
| Rule D ↔ mask bridges | cm4-carrier: 16 of 19 reverts were long-edge approaches into fine-pitch pads | The plan's entry frame includes the mask web: a long-edge approach that leaves less than the board's minimum web is not a candidate, so the gate never sees it |
| Retweak ↔ finish | The retweak rips a module's surroundings and re-routes them | It calls finish on the nets it re-routed, with the rest held |
| Joint loop ↔ shapes | The joint loop quotes candidates on routed copper | The copper it quotes is born-right grid copper, the same shapes the board gets |
| Physics ↔ grid noise | dream117er and redbot heat terms doubled under taut, most likely 0.25 mm raster noise | Before the A/B, a check that rasterizes the same copper at two offsets; if the term moves, the evaluator gets a fix in its own commit |

## 5. Efficiency

- **KiCad DRC runs.** Today, power copper, `pad_trim` and the taut pass (when added) each run a DRC in and out plus ddmin rounds. Finish runs one DRC of its input (reused from the final pass's judgement, which already has it) and one of its output, plus ddmin only when the output is worse.
- **Incremental.** Taut and rule D work per branch; a retweak or an in-loop arm passes the changed nets only.
- **Cache.** Stage 7's output is a deterministic function of the input board, code and options; it goes into the step cache like Freerouting's sessions. A/B arms that differ only after stage 6 share everything before it.
- **Budget.** The final pass reserves time for finish: about one DRC plus taut's measured 6–150 s plus power copper's 6–341 s on the 12 boards. A board too big for its reserve finishes stage (a) and (b) and reports that (c) was skipped.

## 6. What the A/B measures

On the physics set (213 boards with compiled intents), restart portfolio, same budget, same seeds, step cache on:

| Arm | Contents | Shares with |
|---|---|---|
| A | Current router (passes off) | — |
| B | A plus finish on the kept board | A up to stage 6 (fork) |
| C | Plan rules, born-right grid copper, critical copper tightened, plus finish | — |
| D | C plus rule D tails on each import in the repair rounds | C up to stage 4 |
| E | C with decap ground vias in stage 3 instead of power copper | C up to stage 2 |

Reported per arm: cp1 and cpk, completion, errors by type, `clean_strict`, oblique and acute pad entries, overhanging entries, copper length, corners, physics per term against A and against the human layout, hazards raised, and run time per stage. B against A isolates finish; C against B isolates born-right copper and early tightening; D and E answer the two placement-of-work questions.

## 7. Open choices

- **Arcs on 45/90 boards.** `rule-genealogy-routing-style-dfm` R02/R03 keeps 45° for editability. That is an editing reason, not physics or fab. Default: arcs. A plan setting (`arc_policy=keep45`) lets the commanding LLM keep the board's style.
- **Via sliding** in taut is not built; vias stay where the router put them.
- **Coupled diff pairs** are tightened as a pair only when the input pair is coupled; Freerouting's are not, so a pair-aware stage 4 is a separate question ([diff pairs](diff-pair-routing.md)).
