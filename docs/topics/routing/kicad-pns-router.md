# KiCad PNS push-and-shove router: internals and how to script it

Scope: PNS API, walkaround/shove/optimizer internals, meander engine, IPC/CLI access, PCBWorld-Engine bindings. Not here: DP algorithms -> [diff pairs](diff-pair-routing.md); PCBWorld results -> [PCBWorld](pcbworld.md).
Keys: PNS, push-and-shove, PNS::ROUTER, ROUTER_IFACE, NODE, Branch, line placer, walkaround, shove, springback, SH_OK, optimizer, COST_ESTIMATOR, Finish, RouteSelected, Autoroute, meander engine, MEANDER_SETTINGS, IPC API, RunAction, kicad-python, ExportSpecctraDsn, qa/tools/pns, PCBWorld-Engine, checkpoint/restore, determinism

**Results**
1. PNS is not a path searcher: it is a local walkaround/shove engine needing waypoints, layer choices and order from a planner. Its "Autoroute/Finish" is ≤5 `Move()` calls toward the nearest ratsnest anchor.
2. KiCad has no global autorouter: `pcbnew/autorouter/` holds only the footprint autoplacer.
3. The stock IPC API has no route/shove RPC (only `RunAction`, item CRUD and, from KiCad 11, Specctra DSN export / SES import).
4. PCBWorld-Engine (GPLv3) exposes PNS to Python via pybind11 (~90 module calls; the paper's L3 wrapper exposes 58 step-level APIs; checkpoint/restore, deterministic loops); vendorable under GPL-3.0-or-later but pinned to KiCad 9.0.8.
5. PNS is the right geometric realizer, repair and smoothing engine; its DP gateway placer and meander engine are reusable for pairs and tuning.

## Router API

`PNS::ROUTER`, [pns_router.h](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_router.h) [P].
- Routing: `StartRouting(p, item, layer)`, `Move(p, item)`, `FixRoute(p, item, forceFinish, forceCommit)`, `Finish()`, `ContinueFromEnd`, `UndoLastSegment`, `CommitRouting`, `StopRouting`.
- Session: `SwitchLayer`, `ToggleViaPlacement`, `FlipPosture`, `SetOrthoMode`, `ToggleCornerMode`.
- Dragging: `StartDragging(p, item|itemset, mode)` with DM_CORNER/SEGMENT/VIA/FREE_ANGLE/ARC/COMPONENT/BLOCK.
- Settings: `SetMode` (ROUTE_SINGLE, ROUTE_DIFF_PAIR, TUNE_SINGLE, TUNE_DIFF_PAIR, TUNE_DIFF_PAIR_SKEW), `UpdateSizes`, `LoadSettings`, `GetNearestRatnestAnchor`.
- ROUTER_IFACE host abstraction: world sync, item add/update/remove, visibility/flashing, `Commit`, `ImportSizes`, `StackupHeight`, `GetRuleResolver`, length/delay calculators (`CalculateRoutedPathLength`, `CalculateRoutedPathDelay`, `CalculateLengthForDelay`), layer mapping; lets PNS run outside pcbnew (Horizon EDA, PCBWorld-Engine).
- NODE ([pns_node.h](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_node.h)): spatially indexed world, collision/clearance search, line assembly over joints, lightweight `Branch()`/`Commit()` cloning for recursive optimization and shove springback; `NearestObstacle`, `CheckColliding`, `AssembleLine`.

## Line placer, shove and optimizer

[pns_line_placer.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_line_placer.cpp) [P].
- Walkaround (`rhWalkBase`): initial 45° two-segment line (`buildInitialLine`) → `WALKAROUND::Route` cw and ccw around cached clearance hulls → both optimized (MERGE_SEGMENTS) → shorter collision-free result; iteration limit; early abort when length exceeds an expansion factor ([pns_walkaround.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_walkaround.cpp)).
- Shove (`rhShoveOnly`): walk around solids only (pads cannot be shoved) → `SHOVE` on the new head; line stack; nearest obstacle by kind SOLID → VIA → SEGMENT → HOLE; solids walked around, vias pushed by force vector, segments/arcs re-walked around hull sets at clearance; status SH_OK / SH_INCOMPLETE / SH_TRY_WALK; stops on empty stack, incomplete, time or iteration limit; springback pops branched NODE frames that no longer collide; per-line policies SHP_SHOVE, WALK_FORWARD/BACK, IGNORE, DONT_OPTIMIZE, DONT_LOCK_ENDPOINTS; changed lines re-optimized; falls back to walkaround if shove fails; smart-pads in 45° modes ([pns_shove.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_shove.cpp)).
- Defaults: shove 250 iterations / 1000 ms; walkaround 40 iterations; hug-length threshold 1.5; DP gap pickup ratio 2.5 ([pns_routing_settings.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_routing_settings.cpp)).
- Optimizer: `COST_ESTIMATOR::CornerCost` + MERGE_SEGMENTS, MERGE_OBTUSE, MERGE_COLINEAR, SMART_PADS, FANOUT_CLEANUP, KEEP_TOPOLOGY, PRESERVE_VERTEX, RESTRICT_AREA, LIMIT_CORNER_COUNT; effort OE_LOW/MEDIUM/FULL.
- "Autoroute" is not search: `ROUTER::Finish()` gets the nearest ratsnest anchor, calls `Move(otherEnd)` ≤5 times until the head stops, `FixRoute` only if it reached the anchor on an overlapping layer. `RouteSelected` ("Attempt Finish Selected (Autoroute)", action `pcbnew.InteractiveRouter.Autoroute`) loops over selected items, current layer only, no vias, one undo commit ([pns_router.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_router.cpp); [router_tool.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/router_tool.cpp)).

## Meander engine

[pns_meander.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/router/pns_meander.cpp) [P]; DP gateway placer → [diff pairs](diff-pair-routing.md#tool-support).
- Shapes MT_SINGLE/START/FINISH/TURN/CORNER/ARC/EMPTY; round (90° arc) or chamfer (45°) corners; single/dual-sided.
- `MeanderSegment` greedily fills each base segment alternating sides with maximal meanders passing `CheckFit` (`Fit` steps amplitude max → min); `tuneLineLength` ends the chain at the target and spreads the reduction via `findAmplitudeForLength` (fill, then trim).
- Min corner radius = half width (DDR4 reflection comment). Docs: tuning only point-to-point between two pads; DP tuning only on coupled portions.
- Master adds chain-level `MEANDER_SETTINGS` (pre-existing length from other nets in a logical chain; scope/UI unverified). No area reservation.

## IPC API and CLI

[P]
- `RunAction` by name: "TOOL_ACTIONs are specifically *not* an API", prototyping only; selection, `HitTest`, commit-scoped item CRUD; no route/shove RPC ([editor_commands.proto](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/common/commands/editor_commands.proto)).
- `RunBoardJobExportSpecctraDsn` + `ImportSpecctraSession` "Since: 11.0" (repositions footprints, replaces unlocked tracks/vias); master on 2026-10-14 gained CLI `kicad-cli pcb export specctra` (commit title says "specctra_dsn") and API specctra import/export; latest stable 10.0.7 ([board_commands.proto](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_commands.proto)).
- kicad-python (MIT) main: `get_pad_shapes_as_polygons`, `refill_zones`, `hit_test`, `interactive_move`, `place_footprint_from_library`; `GetPadShapeAsPolygon` RPC.
- Headless replay: `qa/tools/pns` (log player, debug tool, `qa_pns_regressions`).
- Unconfirmed: whether `RunAction("pcbnew.InteractiveRouter.Autoroute")` works headless in KiCad 10/11.
- Board I/O: prefer IPC (kicad-python) and the KiCad 11 DSN/SES round trip; `RunAction` only for prototyping [I].

## PCBWorld-Engine

[repo](https://github.com/LGAI-Research/PCBWorld-Engine) [P].
- Pins upstream KiCad 9.0.8 as a submodule + full-file patches to pns_router, pns_node, pns_shove, pns_walkaround, pns_line_placer, pns_optimizer, pns_topology, pns_kicad_iface, pns_item, pns_joint, pns_mouse_trail_tracer, pns_routing_settings, ratsnest_data, tracks_cleaner, drc_engine, drc_rtree, kiid, … (conflict: PCBWorld paper says engine "unmodified").
- ~8.8k new lines: headless RL router (`pns_rl_router.cpp`, 3.7k), DRC fork, pybind11 module `kicad_rl_router`.
- Calls: `set_routing_mode`, `set_corner_mode`, `set_track_width`, `start_route`, `move`, `fix_route`, `finish`, `cancel_route`, `undo_last_segment`, `flip_posture`, `set_via_placement`, `switch_layer`, `start_drag`/`fix_drag`, `run_drc`, `run_drc_incremental`, `get_drc_violations_by_net`, `get_ratsnest`, `get_unrouted_count`, `get_tracks`/`vias`/`pads`, `checkpoint`/`restore`/`restore_incremental`, `optimize_all_lines` (v1.1.0), `lock_net`, `delete_routing_of_nets`, `set_shove_iter_limit`, `save`.
- Determinism: items ordered by geometry with UUID tie-break; shove/walkaround bounded by iteration limits, not wall-clock; seedable KIID. DRC: uncapped per-type counts; R-tree leak fixed.
- Runs as a child process over a Unix socket ("never combined into one distributable" with the BSD env). Maintenance cost across KiCad 10/11 unknown.

## PNS in kae

[I]
- PNS (PCBWorld-Engine-style binding, vendored under GPL-3.0-or-later) as realizer + repair + smoothing: planner supplies waypoints, layer switches, order; then `optimize_all_lines`.
- Search over PNS: beam search or MCTS over (waypoint candidate, walk/shove mode, layer switch) for the hardest residual connections; reward = ΔDRC + Δunrouted − λ·Δlength; uses checkpoint/restore and deterministic loops.
- DPs via the gateway placer from planner-chosen waypoints (LLM gives corridor and side-of-obstacle relations, never coordinates); tuning via the meander engine after area was reserved; check chain-level fields.

## Open questions

- KiCad's plans for first-class routing RPCs unknown.

## Sources

- [routing_algorithms.md § Q2, Q4, Implications](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_algorithms.md); [routing_classics_supplement.md § Q4, Q5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md); [solver_toolbox.md § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md); [verification_papers.md § 1 row 9](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
