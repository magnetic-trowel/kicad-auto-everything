# Freerouting constraint bridge: every KiCad constraint, and how it reaches the router

**TL;DR**
- KiCad's Specctra export carries net class widths and clearances, the outline, pads and zones. It drops the custom rules, local overrides, hole, edge and solder-mask clearances, thermal reliefs and net-carrying copper graphics. Freerouting 2.5.0 also narrows tracks on its own. With the built-in adapter, **all 88** error-level DRC violations on splits A+B were translation losses [C].
- `kae.route` resolves KiCad's DRC rules itself: a port of KiCad's rule engine that agrees with KiCad on **90,633 of 90,633** checks on the 17 corpus boards with a `.kicad_dru` [C]. It writes the result into the DSN as Freerouting's own constructs: net classes, a class-to-class clearance matrix, typed via clearances, pin and keepout clearance classes, and pins.
- What Freerouting cannot hold is enforced after import. KiCad's DRC runs on the result, and a deterministic repair loop widens narrow tracks, draws thermal spokes as tracks, splits planes and rips up and re-routes. A board replaces the output only when it is better.
- On A+B (k=1, 600 s) errors fell from **88 to 0** and clean passes rose from **0.455 to 0.606**. Completion went from 0.896 to 0.955. The price is wall time: 125 s against 13.5 s per board [C].
- The same rules are exposed per net and layer (`kae.route.effective`), so routers that draw copper themselves (`kae.route.critical`) enforce identical numbers.

## Key facts

### Pipeline
`python -m kae.route.cli route IN OUT --seed N --time S` ([bridge.py](../../../kae/src/kae/route/bridge.py)):

1. **Export.** KiCad (SWIG, [pcbnew_bridge.py](../../../kae/src/kae/board/kicad_scripts/pcbnew_bridge.py)) writes the DSN plus what it leaves out: pads with real copper per layer, holes, local clearances, mask expansion, zone connection, copper graphics, mask openings, edges and rule areas. KiCad's engine is also probed on a track and a via of every net on every layer.
2. **Plan.** [constraints.py](../../../kae/src/kae/route/constraints.py) computes each requirement with the rule port ([rules.py](../../../kae/src/kae/route/rules.py)); [translate.py](../../../kae/src/kae/route/translate.py) writes it into the DSN.
3. **Route.** Freerouting runs isolated, with every setting the bridge depends on passed explicitly and a deadline inside the budget ([freerouting.py](../../../kae/src/kae/route/freerouting.py)).
4. **Import.** The session is fixed up (placement stripped, net names quoted, via sizes restored) and imported by KiCad.
5. **Repair.** [repair.py](../../../kae/src/kae/route/repair.py) runs KiCad DRC with zones refilled, as the scorer does, and repairs what it finds.

### Effective constraints
KiCad's `DRC_ENGINE` is not exposed to Python, so the bridge evaluates rules itself. The port follows `EvalRules`:
- Pad or footprint local clearances win, floored at the board minimum.
- Implicit rules come next (board setup, net class clearance and width), then custom rules in file order; the last match wins.
- A net class width is an *opt* whose minimum is the board minimum.
- Undefined properties compare false.
- Geometric functions (`intersectsArea`, `intersectsCourtyard`, ...) are evaluated both ways, keeping the stricter result.

All functions and properties the corpus rule files use are supported [C].

**Validation.** `pcbnew.LoadBoard` initialises the engine with the project's rules. Probe tracks and vias of every net, placed off the board, then report KiCad's width, diameter and drill limits, own clearance and annular ring per layer. KiCad caches net classes by item pointer, so probes must stay alive while they are queried [P]. On all 17 corpus boards with a `.kicad_dru` the port agrees with KiCad on every check: 90,633 checks, 0 mismatches [C: `tools/research/routing/rule_evaluator_agreement.py`].

### Constraint coverage
"Class" means a routing class: nets with the same net class, diff-pair membership, width and via limits and answers to net-specific custom rules share one. Classes are named `kae_<netclass>` and are never Freerouting's default class (see the next section).

| KiCad constraint | Into Freerouting as | After import |
|---|---|---|
| Track width min/opt/max (board, net class, custom rules per layer) | class width per layer = opt clamped into [min, max]; `automatic_neckdown=false`, `fanout.enabled=false`; `neck_width_um` = max(largest min, narrowest class width); `min_trace_width_um` = largest min (the fork's floor for every neck-down) | narrower tracks widened in place when clearances allow, else ripped |
| Copper clearance (board, net class, custom rules on both items, pad/footprint overrides) | `class_class` matrix per layer for every class pair | rip-up and re-route |
| Pad clearance and pad shape | a clearance class per pin, per class and layer, read against a track or via of another net of the class, including the excess of real copper beyond the one shape the DSN carries; with `pad_shapes="outside"`, polygon pins that contain the pad | as above |
| Via diameter, hole size, annular width | one via padstack per class, D ≥ d + 2·annulus, named in whole µm | — |
| Hole clearance | vias: typed `wire_via`/`via_via` clearances raised by hole clearance minus annular ring; pads: through the pad's ring; NPTH: circle keepouts | rip-up |
| Hole-to-hole (net-independent) | via-via ≥ h2h + (d₁+d₂)/2 − (D₁+D₂)/2; pad holes in pin classes | same-net via pairs: rip-up |
| Copper-to-edge (board, custom rules by item type; Edge.Cuts, Margin, footprint edges, slotted NPTH) | outline: `copper_to_edge_clearance_um` (track value); a via-only band where vias need more; cut-outs and stray edges as keepouts in class `kae_edge` | — |
| Solder-mask aperture (expansion + mask-to-copper; tented vias) | pin classes on outer layers, unless `solder_mask_bridge` is ignored or the pad allows bridges | — |
| Solder-mask openings drawn as graphics (exposed copper) | keepouts on their outer copper layer at the mask-to-copper clearance, unless they cover a pad | — |
| Rule areas (no tracks / no vias) | `keepout` / `via_keepout` on their layers | — |
| Copper graphics and texts, no net | keepouts in their clearance class | — |
| Copper graphics with a net | pins of that net, centred inside the copper | — |
| Diff-pair gap (min) | raises the pair's track-track clearance | max gap, uncoupled length: not enforced |
| Thermal relief (gap, spoke width, `min_resolved_spokes`) | — (Freerouting sees a solid plane) | spoke tracks from the pad into fill; else spoke corridors kept clear |
| Zone connectivity (fill cut by other nets) | planes | planes replaced by the fill pieces of the net's main part; then planes dropped |
| Locked tracks and vias (pre-routes) | fixed wiring `(type fix)` | kept byte-identical; never ripped, widened or unlocked |
| Zones named `kae-crit:…` | fill pieces as pins of their net at the zone's clearance (hard obstacles), plus the plane | — |
| Length, skew, via count, `disallow` | not translated (of the 17 corpus rule files one uses `length`, none the others) | reported by DRC |

Plumbing [P]:
- KiCad names DSN layers by their user names ("GND" for In1.Cu); the bridge maps them.
- A board whose copper layers are all "power" exports none as signal; the bridge makes them signal layers, since Freerouting refuses such a board and 2.5.0 hangs.
- Bare net names with `|` fail the whole SES import, so the bridge quotes them.
- See [specctra-freerouting-integration](../kicad/specctra-freerouting-integration.md).

### Freerouting build
The bridge runs the magnetic-trowel fork when installed (`tools/research/routing/install_freerouting_fork.sh`, or `KAE_BRIDGE_FREEROUTING`); kaebench's `freerouting` adapter keeps the upstream 2.5.0 release, so the human-placement baseline is unchanged. The fork adds `router.min_trace_width_um`, a floor under every neck-down (pad necks, the fanout micro-neckdown, neck-width retries) [P: magnetic-trowel/freerouting#2]. Older builds log it as unknown and ignore it.

### Freerouting 2.5.0 behaviour the translation relies on
All [P] in the v2.5.0 source:
- **Narrowing.** Escape insertion retries a blocked segment at 3/4, 3/5 and 1/2 of the class half-width whenever `isFanout || withNeckdown` ([FoundConnectionInserter.java](https://github.com/freerouting/freerouting/blob/v2.5.0/src/main/java/app/freerouting/autoroute/path/FoundConnectionInserter.java) `insertFanoutMicroNeckdown`). This is the 0.25→0.1874 mm and 0.2→0.15/0.12 mm `track_width` cluster. `automatic_neckdown=false` alone leaves it on; only `fanout.enabled=false` stops it in stock 2.5.0.
- **Neck width.** `neck_width_um` retries a *failed* connection with every layer's width capped at that value, over its whole length (`AutorouteConnectionRouter.retryConnectionNecked`). It is legal when the value is at least every class's minimum. It is what lets a 0.64 mm USB class reach 0.5 mm-pitch pads with fanout off.
- **Classes.** A typed clearance (`(clearance v (type wire_via))`) gives a class's vias their own clearance class only when it sits in that class's own rule. The default class's via infos are created before the network is read (`Network.createDefaultViaInfos`), so no net may stay in the default class.
- **Keepouts.** Board-level keepouts are inserted before network classes exist, so a clearance class named there is not found (`Structure.insertKeepout`). The bridge therefore holds every obstacle in one virtual component, placed with `(keepout NAME (clearance_class C))`.
- **Padstack names.** Freerouting deletes `\.\d+` from padstack names (`Library.java`), but KiCad reads a via's drill from its name, so via names use whole µm.
- **Outline.** `copper_to_edge_clearance_um` sets one value for the whole outline (`HeadlessBoardManager`).
- **Planes.** Planes and wiring polygons are conduction areas that are not obstacles: other nets may cross them, like KiCad's refill.
- **Connections.** A trace connects to a pin only at the pin's exact centre, and to a conduction area anywhere inside it (`Trace.getNormalContacts`).
- **Plane layers.** KiCad marks most inner planes "signal", so Freerouting routed traces across them: on six split-C boards it put 781–1,362 mm there, against 282 mm on the human boards. `translate.plane_layers` finds inner layers where one net's zones cover ≥ 30 % of the board. With `planes="cost"` (the default), a `board.rules` file beside the DSN gives Freerouting per-layer trace costs: plane layers cost 4× a routing layer (`autoroute_settings layer_rule`). Freerouting loads that file with the DSN and keeps its costs over its own defaults. The hard alternative, `(type power)`, bans traces there. It also switches off Freerouting's plane-net detection on the remaining layers, and canhw went from 14 to 58 unconnected items. Bridge alone, same build, k = 1 [C]: oasis foreign inner track 127 → 0.6 mm, RET-COV 41 → 85 % (human 84 %); canhw 437 → 51 mm, 46 → 79 % (human 92 %); unconnected items 35 → 32 over four boards.
- **Rounded pads.** KiCad writes roundrect, chamfered and custom pads as polygons whose arc chords lie inside the true outline: 3.9 µm at a 0.25 mm corner radius, 10 µm on oasis's custom pads. Freerouting keeps its clearance from that smaller polygon. With `--pad-shapes outside`, `translate.circumscribe_pins` writes KiCad's own outline for each such pin instead (ERROR_OUTSIDE: it contains the pad and lies at most `max_error` beyond it). The default stays `kicad`. A related plan bug is fixed: the pad's own net no longer stands in for the class's tracks. Before the fix, `A.Net != B.Net` rules never matched, so oasis's +18V pads got 0.15 mm instead of 0.2 mm. The fix changes pin clearances on 5 of the 17 boards with a `.kicad_dru` [C].
- **Rounded wiring.** KiCad writes DSN coordinates with `%.6g`, so at x or y ≥ 100 mm half a micrometre is lost. A locked track ending on a pad centre at 137.2875 mm is written 137288 µm, while the pin centre (placement + pin offset) stays 137287.5. Freerouting then reads the wire as floating. `translate.snap_wiring` moves every wiring point within 1.5 µm of a same-net pin centre onto it, and near-coincident corners onto each other. `fix_session` gives KiCad's coordinates back to any returned point it moved. On lambdakb this turned critical + bridge from 1 unconnected to clean [C]. The repair rounds re-export routed boards and benefit too.
- **Plane nets.** A net with a conduction area covering ≥ 30% of the board is routed as a plane net: items already touching any of its areas are skipped (`DsnFile`, `BatchAutorouter.getAutorouteItems`). A split plane is therefore never re-joined unless the island pieces are left out of the DSN.
- **Fixed wiring.** `(type fix)` items become `SYSTEM_FIXED`; they are never moved and never written to the session (`SesWriter.writeNet`). KiCad's import re-adds its own locked objects.
- **Determinism.** The router is deterministic: open items are routed in the order the DSN created them. `--seed N > 0` therefore permutes component, placement and net order, and every repair round uses a new order.
- **Deadline.** The job clock starts after the JVM has started and the DSN has loaded. At `job_timeout` the watchdog asks the router to stop and waits up to 30 s (`GRACE_PERIOD`) before writing the session. `save_intermediate_stages` writes nothing headless, since no listener is registered. A process killed before that is lost, so the bridge kills only after the grace period and the write. If no session appears, it runs one quick pass (`-mp 1`); failing that, the output is the unrouted input.
- **Settings precedence.** Defaults < `freerouting.json` < DSN < SES < rules < env `FREEROUTING__*` < CLI. A host's leftover config is a hazard, not an observed cause. Every run gets a private `--user_data_path` and a scrubbed environment.

### KiCad behaviour the repair relies on
All [P] in KiCad 10.0:
- **Spokes.** A pad is starved when fill spokes plus manual spokes are below `min_resolved_spokes`. A manual spoke is a track connected to the pad, with one end inside the pad outline grown by gap/2 and the other in the zone's fill ([drc_test_provider_zone_connections.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_test_provider_zone_connections.cpp)). Spokes into an island that connects only to this pad do not count. The repair draws such tracks at the class width, clear of foreign copper, in directions at least 45° apart. For a pad cut off from its zone, it aims only at fill outside the pad's own part of the net.
- **Zone connectivity.** An item connects to a fill piece when an anchor lies inside it or its copper overlaps; pads and vias use their flashed shape ([connectivity_algo.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/connectivity/connectivity_algo.cpp) `checkZoneItemConnection`). The bridge mirrors this to find a net's parts.
- **Refill.** The refill depends on the project's rules, so fills are always computed next to `.kicad_pro`/`.kicad_dru`. Without them, KiCad's defaults apply.

### Measured effect
Splits A+B (33 boards), k=1, 600 s per board, on one shared 4-core host with two boards routed at a time, KiCad 10.0.7, Freerouting 2.5.0. Each run is scored by `kaebench` [C: `kaebench report`, `tools/research/routing/drc_rule_census.py`].

| | built-in adapter | bridge, fanout off | bridge, fanout on the first route |
|---|---|---|---|
| clean pass (cp1) | 0.455 | 0.606 | 0.576 |
| completion | 0.896 | 0.955 | 0.956 |
| DRC errors (all boards) | 88 | 0 | 7 (one board) |
| missing connections | 87 | 39 | 35 |
| wire length / human | 0.898 | 0.929 | 0.908 |
| wall time per board (mean) | 13.5 s | 125 s | 118 s |

The built-in adapter's 88 errors break down as:
- `track_width` 46: Freerouting's narrowing, and widths below the board minimum.
- `clearance` 23: custom and board-minimum clearances absent from the DSN.
- `copper_edge_clearance` 14: footprint Edge.Cuts, custom edge rules.
- `starved_thermal` 5.

With the bridge, no error is left. The 39 missing connections it leaves are of two kinds:
- 26 connections Freerouting found no path for: pad to pad 14, pad to track 6, between track pieces 4, to net-carrying copper arcs 2;
- 13 zone islands it could not join: 11 between zone parts, 1 pad to zone, 1 teardrop.

Fanout on the first route leaves 7 errors, all on one board: a repair round there ran out of router time before it could re-route the narrowed tracks.

Wall time goes mostly to the first route and to repair rounds, each of which runs Freerouting and KiCad's DRC. Rounds that do not improve the board stop after two in a row.

## Recommendations for our system
- **Route through the bridge.** Use `kae.route.cli route` as the general router and as the placement probe (`--probe-command`). Keep the CLI stable. Give attempts seeds 0..k−1, since a seed is a different item order.
- **Share the rules.** Any router that draws copper itself takes its numbers from `kae.route.effective`: `track_width`, `via`, `clearance`, `pad_clearance`, `edge_clearance` and `same_net_via_pitch` per net and layer. Pre-routes enter the bridge as locked tracks and vias. Pours that must stay intact are zones named `kae-crit:…`.
- **Keep fanout off.** Stock 2.5.0 narrows below the minimum with it on. The neck-width retry recovers the cases it was needed for: completion is 0.955 with fanout off against 0.956 with fanout on the first route only. `--fanout-first` stays available; repair rounds then re-route the narrowed tracks without fanout.
- **Score only with KiCad.** Judge a router change only by KiCad DRC on the imported board ([drc-report-and-repair-loop](../kicad/drc-report-and-repair-loop.md)); Freerouting's own score counts a split plane as connected.

## Conflicts and open questions
- **Rules Freerouting cannot route by.** Diff pairs are routed as two nets: the gap minimum holds, the gap maximum and uncoupled length do not. Length, skew and via-count rules are only reported.
- **Same-net hole-to-hole.** Freerouting has no same-net clearance, so hole-to-hole between two vias of one net is caught only by the repair.
- **Unjoined planes and the last mile.** Freerouting sees a plane as one area, so zone islands and pads cut off from their fill stay open. It also misses some legal paths. `--last-mile` (`kae.route.lastmile`) joins what is still open with the critical router's grid search, ripping foreign copper only where it must, and re-routes the ripped nets. Locally (seed 0, 600 s) it took 9 of 13 boards that end with unconnected items down to 2, with 0 errors [C]. The default stays off.
- **Fork patch.** A fork that floors micro-neckdown at the class minimum would allow fanout without narrowing; it is on hold.
- **Big boards.** DRC with refill takes minutes on the largest boards, and every repair round runs it once. The bridge bounds it by its own budget; for the scorer, raise `KAE_DRC_TIMEOUT`.
- **Locked zones.** Locked zones that are not `kae-crit:` stay planes that other nets may cross, as in KiCad. That covers 36 locked zones on 8 of the 112 route tasks, all human pours.

## Sources
- research notes: [verification_kicad_and_tools.md § 4 Freerouting](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
- code: [kae/src/kae/route/](../../../kae/src/kae/route/), tests `kae/tests/test_route_*.py`; scripts [rule_evaluator_agreement.py](../../../tools/research/routing/rule_evaluator_agreement.py), [drc_rule_census.py](../../../tools/research/routing/drc_rule_census.py)
- primary: Freerouting [v2.5.0 source](https://github.com/freerouting/freerouting/tree/v2.5.0); KiCad 10.0 [pcbnew/drc](https://gitlab.com/kicad/code/kicad/-/tree/10.0/pcbnew/drc), [specctra_import_export](https://gitlab.com/kicad/code/kicad/-/tree/10.0/pcbnew/specctra_import_export), [connectivity](https://gitlab.com/kicad/code/kicad/-/tree/10.0/pcbnew/connectivity)

See also: [freerouting](freerouting.md), [specctra-freerouting-integration](../kicad/specctra-freerouting-integration.md), [drc-rule-language-reference](../kicad/drc-rule-language-reference.md), [harness](../verification/harness.md)
