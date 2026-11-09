# Freerouting constraint bridge: every KiCad constraint, and how it reaches the router

Scope: mechanism reference for `kae.route` bridge: rule port, constraint coverage table, Freerouting 2.5.0 and KiCad 10 behaviours it relies on, representatives, measured effect at k=1. Not here: provenance, full-benchmark runs and verdict -> [research: kae bridge](../../research/routing/kae-freerouting-bridge.md); repair rounds -> [research: repair loop](../../research/routing/kae-repair-loop.md); last mile -> [last mile and restarts](last-mile-and-restarts.md).
Keys: kae.route, bridge, rule port, rules.py, EvalRules, effective constraints, kae.route.effective, constraints.py, translate.py, routing class, kae_<netclass>, class_class matrix, pin clearance class, KAE_OBSTACLES, neck_width_um, min_trace_width_um, automatic_neckdown, fanout.enabled, insertFanoutMicroNeckdown, plane cost, planes=cost, pad_shapes outside, snap_wiring, plane nets, type fix, representatives, starved_thermal, min_resolved_spokes, GRACE_PERIOD, settings precedence

**Results** ([C])
1. KiCad's Specctra export carries net-class widths and clearances, outline, pads, zones; it drops custom rules, local overrides, hole, edge and solder-mask clearances, thermal reliefs and net-carrying copper graphics. Freerouting 2.5.0 also narrows tracks on its own. With the built-in adapter, all 88 error-level DRC violations on splits A+B were translation losses.
2. `kae.route` resolves KiCad's DRC rules itself: a port of KiCad's rule engine agreeing with KiCad on 90,633 of 90,633 checks on the 17 corpus boards with a `.kicad_dru`. It writes the result into the DSN as Freerouting's own constructs (net classes, class-to-class clearance matrix, typed via clearances, pin and keepout clearance classes, pins).
3. What Freerouting cannot hold is enforced after import: KiCad DRC on the result, a deterministic repair loop (widen narrow tracks, draw thermal spokes, split planes, rip up and re-route), then the last mile (exactly checked grid joins). A board replaces the output only when better and with no more errors.
4. A+B (k=1, 600 s): errors 88 → 0, clean passes 0.455 → 0.606. With last mile, k=3: cp1 0.909, cpk 0.970, 0 errors ([results](../../../bench/results/2026-10-24-last-mile-ab-57487e6.md)). Restart portfolio: 99/99 clean attempts ([results](../../../bench/results/2026-10-24-portfolio-ab-0465818.md)).
5. The same rules are exposed per net and layer (`kae.route.effective`), so routers drawing copper themselves (`kae.route.critical`) enforce identical numbers.

### Pipeline

`python -m kae.route.cli route IN OUT --seed N --time S` ([bridge.py](../../../kae/src/kae/route/bridge.py)):
1. Export: KiCad (SWIG, [pcbnew_bridge.py](../../../kae/src/kae/board/kicad_scripts/pcbnew_bridge.py)) writes the DSN plus what it leaves out (pads with real copper per layer, holes, local clearances, mask expansion, zone connection, copper graphics, mask openings, edges, rule areas); KiCad's engine is probed on a track and a via of every net on every layer.
2. Plan: [constraints.py](../../../kae/src/kae/route/constraints.py) computes each requirement with the rule port ([rules.py](../../../kae/src/kae/route/rules.py)); [translate.py](../../../kae/src/kae/route/translate.py) writes it into the DSN.
3. Route: Freerouting runs isolated, every relied-on setting passed explicitly, deadline inside the budget ([freerouting.py](../../../kae/src/kae/route/freerouting.py)).
4. Import: session fixed up (placement stripped, net names quoted, via sizes restored), imported by KiCad.
5. Repair: [repair.py](../../../kae/src/kae/route/repair.py) runs KiCad DRC with zones refilled, as the scorer does, and repairs what it finds → [repair loop](../../research/routing/kae-repair-loop.md).

### Effective constraints

KiCad's `DRC_ENGINE` is not exposed to Python, so the bridge ports `EvalRules`:
- Pad or footprint local clearances win, floored at the board minimum.
- Then implicit rules (board setup, net class clearance and width), then custom rules in file order; last match wins.
- A net class width is an opt whose minimum is the board minimum. Undefined properties compare false.
- Geometric functions (`intersectsArea`, `intersectsCourtyard`, ...) evaluated both ways, stricter result kept.
- All functions and properties the corpus rule files use are supported [C]. Parser and resolution detail → [research page § Rule port](../../research/routing/kae-freerouting-bridge.md#rule-port-rulespy).
- Validation: `pcbnew.LoadBoard` initializes the engine with the project's rules; probe tracks and vias of every net, placed off the board, report KiCad's width, diameter and drill limits, own clearance and annular ring per layer. KiCad caches net classes by item pointer, so probes must stay alive while queried [P]. 17 boards with `.kicad_dru`: 90,633 checks, 0 mismatches [C: `tools/research/routing/rule_evaluator_agreement.py`].

### Constraint coverage

Class = routing class: nets with the same net class, diff-pair membership, width and via limits and answers to net-specific custom rules share one; named `kae_<netclass>`, never Freerouting's default class.

| KiCad constraint | Into Freerouting as | After import |
|---|---|---|
| Track width min/opt/max (board, net class, custom rules per layer) | Class width per layer = opt clamped into [min, max]; `automatic_neckdown=false`, `fanout.enabled=false`; `neck_width_um` = largest min, or the narrowest class width if no rule sets one (only when some class is wider); `min_trace_width_um` = largest min (the fork's floor for every neck-down) | Narrower tracks widened in place when clearances allow, else ripped |
| Copper clearance (board, net class, custom rules on both items, pad/footprint overrides) | `class_class` matrix per layer for every class pair: strictest of the representative pair, a coupled and an uncoupled member pair | Rip-up and re-route |
| Pad clearance and pad shape | Clearance class per pin, per class and layer, read against a track or via of another net of the class, incl. the excess of real copper beyond the one DSN shape; with `pad_shapes="outside"`, polygon pins containing the pad | As above |
| Via diameter, hole size, annular width | One via padstack per class, D ≥ d + 2·annulus, named in whole µm | — |
| Hole clearance | Vias: typed `wire_via`/`via_via` clearances raised by hole clearance minus annular ring; pads: through the pad's ring; NPTH: circle keepouts | Rip-up |
| Hole-to-hole (net-independent) | via-via ≥ h2h + (d₁+d₂)/2 − (D₁+D₂)/2; pad holes in pin classes | Same-net via pairs: rip-up |
| Copper-to-edge (board, custom rules by item type; Edge.Cuts, Margin, footprint edges, slotted NPTH) | Outline: `copper_to_edge_clearance_um` (track value); a via-only band where vias need more; cut-outs and stray edges as keepouts in class `kae_edge` | — |
| Solder-mask aperture (expansion + mask-to-copper; tented vias) | Pin classes on outer layers, unless `solder_mask_bridge` is ignored or the pad allows bridges | — |
| Solder-mask openings drawn as graphics (exposed copper) | Keepouts on their outer copper layer at mask-to-copper clearance, unless they cover a pad | — |
| Rule areas (no tracks / no vias) | `keepout` / `via_keepout` on their layers | — |
| Copper graphics and texts, no net | Keepouts in their clearance class | — |
| Copper graphics with a net | Pins of that net, centred inside the copper | — |
| Diff-pair gap (min) | Raises the pair's track-track clearance | Max gap, uncoupled length: not enforced |
| Thermal relief (gap, spoke width, `min_resolved_spokes`) | — (Freerouting sees a solid plane) | Spoke tracks from pad into fill; else spoke corridors kept clear |
| Zone connectivity (fill cut by other nets) | Planes | Planes replaced by the fill pieces of the net's main part; then planes dropped |
| Locked tracks and vias (pre-routes) | Fixed wiring `(type fix)` | Kept byte-identical; never ripped, widened or unlocked |
| Zones named `kae-crit:…` | Fill pieces as pins of their net at the zone's clearance (hard obstacles), plus the plane | — |
| Length, skew, via count, `disallow` | Not translated (of 17 corpus rule files one uses `length`, none the others) | Reported by DRC |

Plumbing [P]: KiCad names DSN layers by user names ("GND" for In1.Cu), bridged by a map; a board whose copper layers are all "power" exports none as signal, so the bridge makes them signal (Freerouting refuses such a board and 2.5.0 hangs); bare net names with `|` fail the whole SES import, so names are quoted → [specctra-freerouting-integration](../kicad/specctra-freerouting-integration.md).

### Freerouting build

The bridge runs the magnetic-trowel fork when installed (`tools/research/routing/install_freerouting_fork.sh`, or `KAE_BRIDGE_FREEROUTING`); kaebench's `freerouting` adapter keeps upstream 2.5.0, so the human-placement baseline is unchanged. The fork adds `router.min_trace_width_um`, a floor under every neck-down (pad necks, fanout micro-neckdown, neck-width retries) [P: magnetic-trowel/freerouting#2]; older builds log it as unknown and ignore it.

### Freerouting 2.5.0 behaviour the translation relies on

All [P] in the v2.5.0 source.
| Behaviour | Fact | Bridge response |
|---|---|---|
| Narrowing | Escape insertion retries a blocked segment at 3/4, 3/5, 1/2 of the class half-width whenever `isFanout \|\| withNeckdown` ([FoundConnectionInserter.java](https://github.com/freerouting/freerouting/blob/v2.5.0/src/main/java/app/freerouting/autoroute/path/FoundConnectionInserter.java) `insertFanoutMicroNeckdown`): the 0.25→0.1874 mm and 0.2→0.15/0.12 mm `track_width` cluster. `automatic_neckdown=false` alone leaves it on | `fanout.enabled=false` (the only stop in stock 2.5.0) |
| Neck width | `neck_width_um` retries a failed connection with every layer's width capped there over its whole length (`AutorouteConnectionRouter.retryConnectionNecked`); legal when ≥ every class's minimum | Lets a 0.64 mm USB class reach 0.5 mm-pitch pads with fanout off |
| Classes | A typed clearance `(clearance v (type wire_via))` gives a class's vias their own clearance class only inside that class's own rule; default class's via infos are created before the network is read (`Network.createDefaultViaInfos`) | No net stays in the default class |
| Keepouts | Board-level keepouts inserted before network classes exist, so a clearance class named there is not found (`Structure.insertKeepout`) | All obstacles in one virtual component, `(keepout NAME (clearance_class C))` |
| Padstack names | Freerouting deletes `\.\d+` from padstack names (`Library.java`); KiCad reads a via's drill from its name | Via names in whole µm |
| Outline | `copper_to_edge_clearance_um` sets one value for the whole outline (`HeadlessBoardManager`) | Via-only band where vias need more |
| Planes | Planes and wiring polygons are conduction areas, not obstacles (other nets may cross, like KiCad's refill) | — |
| Connections | A trace connects to a pin only at its exact centre, to a conduction area anywhere inside (`Trace.getNormalContacts`) | Corner/centre joins → [critical routing](critical-net-routing.md#keeping-critical-copper-out-of-the-routers-way) |
| Plane layers | KiCad marks most inner planes "signal", so Freerouting routed 781–1,362 mm of traces across them on six split-C boards (human 282 mm) | `translate.plane_layers` finds inner layers where one net's zones cover ≥ 30% of the board; `planes="cost"` (default) writes a `board.rules` beside the DSN pricing traces there at 4× (`autoroute_settings layer_rule`), which Freerouting keeps over its defaults. Hard alternative `(type power)` on every plane layer also disables plane-net detection on other layers (canhw: 14 → 58 open). Default `plane_strict_share="odd"`: odd seeds write inner layers ≥ 80% filled by one net as `(type power)`, even seeds none; restarts try both ([why](../../research/routing/kae-closing-open-connections.md): z280 59 → 12 open, heypcb kestrel worse). Costs cut plane-layer signal track ~30-fold on split C at a small cpk cost ([10x sweep](../../../bench/results/2026-10-25-crit-v6-10x-1ef5bf1.md)) |
| Rounded pads | KiCad writes roundrect, chamfered and custom pads as polygons whose arc chords lie inside the true outline: 3.9 µm at 0.25 mm corner radius, 10 µm on oasis custom pads | `--pad-shapes outside`: `translate.circumscribe_pins` writes KiCad's ERROR_OUTSIDE outline (contains the pad, ≤ `max_error` beyond); default stays `kicad` |
| Rounded wiring | KiCad writes DSN coordinates `%.6g`: at ≥ 100 mm half a micrometre is lost; a locked track ending on a pad centre at 137.2875 mm is written 137288 µm while the pin centre stays 137287.5, so Freerouting reads the wire as floating | `translate.snap_wiring` moves wiring points within 1.5 µm of a same-net pin centre onto it; `fix_session` restores KiCad's coordinates. lambdakb: critical + bridge 1 open → clean [C] |
| Plane nets | A net with a conduction area covering ≥ 30% of the board is routed as a plane net: items already touching any of its areas are skipped (`DsnFile`, `BatchAutorouter.getAutorouteItems`); a split plane is never re-joined unless island pieces are left out of the DSN | Repair replaces planes by fill pieces |
| Fixed wiring | `(type fix)` → `SYSTEM_FIXED`: never moved, never written to the session (`SesWriter.writeNet`); KiCad's import re-adds its own locked objects | — |
| Determinism | Deterministic: open items routed in DSN creation order | `--seed N > 0` permutes component, placement and net order; every repair round uses a new order |
| Hosts | Every JVM grows toward its heap cap (`KAE_FR_XMX`); runs take host-wide slots; slot wait counts against the deadline | → [last mile and restarts § Hosts](last-mile-and-restarts.md#hosts) |
| Deadline | Job clock starts after JVM start and DSN load; at `job_timeout` the watchdog asks the router to stop and waits up to 30 s (`GRACE_PERIOD`) before writing; `save_intermediate_stages` writes nothing headless (no listener); a process killed earlier is lost | Kill only after grace period and write; no session → one quick pass (`-mp 1`); else output = unrouted input |
| Settings precedence | Defaults < `freerouting.json` < DSN < SES < rules < env `FREEROUTING__*` < CLI | Private `--user_data_path`, scrubbed environment per run |

### Representatives: whose rules a class pair reads

Each requirement is evaluated on a representative net of each class [C]:
- A pad's own net never stands in for a class's tracks; otherwise `A.Net != B.Net` rules never match (oasis +18V pads got 0.15 mm instead of 0.2 mm; Freerouting routed 30 µm inside the rule). Fix changes pin clearances on 5 of 17 boards with a `.kicad_dru`.
- A coupled diff pair never stands in for its two classes: KiCad gives nets named `X+`/`X−` the diff-pair gap as clearance (implicit "diff pair" rule). On bms-c1, /BAT− and /BAT+ represented Default_2 × HV, so the pair got 0.25 mm; Freerouting laid /BAT− 0.28 mm from a /PACK+ via where KiCad wants HV's 0.3 mm. Each class pair now also evaluates one coupled and one uncoupled member pair, keeping the strictest; `effective.clearance` keeps a net's complement out of its class's value. Changed 2 of 112 boards, all upward.

### KiCad behaviour the repair relies on

All [P] in KiCad 10.0.
- Spokes: a pad is starved when fill spokes + manual spokes < `min_resolved_spokes`. A manual spoke = track connected to the pad with one end inside the pad outline grown by gap/2 and the other in the zone's fill ([drc_test_provider_zone_connections.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_test_provider_zone_connections.cpp)); spokes into an island connecting only to this pad do not count. Repair draws such tracks at class width, clear of foreign copper, ≥ 45° apart; for a pad cut off from its zone it aims only at fill outside the pad's own part of the net.
- Zone connectivity: an item connects to a fill piece when an anchor lies inside it or its copper overlaps; pads and vias use their flashed shape ([connectivity_algo.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/connectivity/connectivity_algo.cpp) `checkZoneItemConnection`); the bridge mirrors this to find a net's parts.
- Refill depends on the project's rules: fills always computed next to `.kicad_pro`/`.kicad_dru`, else KiCad's defaults apply.

### Measured effect

Splits A+B (33 boards), k=1, 600 s per board, one shared 4-core host, two boards at a time, KiCad 10.0.7, Freerouting 2.5.0; scored by `kaebench` [C: `kaebench report`, `tools/research/routing/drc_rule_census.py`]. Doc-only result (no results file).

| | built-in adapter | bridge, fanout off | bridge, fanout on the first route |
|---|---|---|---|
| clean pass (cp1) | 0.455 | 0.606 | 0.576 |
| completion | 0.896 | 0.955 | 0.956 |
| DRC errors (all boards) | 88 | 0 | 7 (one board) |
| missing connections | 87 | 39 | 35 |
| wire length / human | 0.898 | 0.929 | 0.908 |
| wall time per board (mean) | 13.5 s | 125 s | 118 s |

- Built-in adapter's 88 errors: `track_width` 46 (Freerouting's narrowing), `clearance` 23 (custom and board-minimum clearances absent from the DSN), `copper_edge_clearance` 14, `starved_thermal` 5.
- Bridge's 39 missing connections: 26 Freerouting found no path for, 13 zone islands; the last mile now closes both kinds.
- Repair-round keep/stop rules and stop reasons → [repair loop](../../research/routing/kae-repair-loop.md). Freerouting reports its own stop (`autorouter_stop`: COMPLETED, STAGNATION, TIMED_OUT); at 10× budgets it was never the clock ([10x sweep](../../../bench/results/2026-10-25-crit-v6-10x-1ef5bf1.md)).

### Using the bridge

- Route through the bridge: `kae.route.cli route` as general router and placement probe (`--probe-command`); keep the CLI stable; attempts get seeds 0..k−1 (a seed is a different item order).
- Share the rules: any router drawing copper takes numbers from `kae.route.effective` (`track_width`, `via`, `clearance`, `pad_clearance`, `edge_clearance`, `same_net_via_pitch` per net and layer); pre-routes enter as locked tracks and vias; pours that must stay intact are zones named `kae-crit:…`.
- Keep fanout off: stock 2.5.0 narrows below the minimum with it on; the neck-width retry recovers the needed cases (completion 0.955 fanout off vs 0.956 fanout on first route only). `--fanout-first` stays available; repair rounds then re-route the narrowed tracks without fanout.
- Score only with KiCad DRC on the imported board ([drc-report-and-repair-loop](../kicad/drc-report-and-repair-loop.md)); Freerouting's own score counts a split plane as connected.

## Open questions

- Rules Freerouting cannot route by: diff pairs routed as two nets (gap minimum holds; gap maximum and uncoupled length do not); length, skew, via-count rules only reported.
- Same-net hole-to-hole: Freerouting has no same-net clearance; caught only by repair.
- Unjoined planes: Freerouting sees a plane as one area, so zone islands stay open for it; the last mile joins them.
- Unreproduced clearance error: a Freerouting track 0.19 mm from a 0.3 mm HV custom-polygon pad on bms-c1 with correct DSN shape and pin class → [last mile and restarts](last-mile-and-restarts.md#open-questions).
- Fork patch flooring micro-neckdown at the class minimum would allow fanout without narrowing: on hold.
- Big boards: DRC with refill takes minutes on the largest boards, once per repair round; the bridge bounds it by its own budget; for the scorer raise `KAE_DRC_TIMEOUT`.
- Locked zones that are not `kae-crit:` stay planes other nets may cross (as in KiCad): 36 locked zones on 8 of the 112 route tasks, all human pours.

## Sources

- [verification_kicad_and_tools.md § 4 Freerouting](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
- Code: [kae/src/kae/route/](../../../kae/src/kae/route/), tests `kae/tests/test_route_*.py`; scripts [rule_evaluator_agreement.py](../../../tools/research/routing/rule_evaluator_agreement.py), [drc_rule_census.py](../../../tools/research/routing/drc_rule_census.py)
- Primary: Freerouting [v2.5.0 source](https://github.com/freerouting/freerouting/tree/v2.5.0); KiCad 10.0 [pcbnew/drc](https://gitlab.com/kicad/code/kicad/-/tree/10.0/pcbnew/drc), [specctra_import_export](https://gitlab.com/kicad/code/kicad/-/tree/10.0/pcbnew/specctra_import_export), [connectivity](https://gitlab.com/kicad/code/kicad/-/tree/10.0/pcbnew/connectivity)
- Related: [freerouting](freerouting.md), [drc-rule-language-reference](../kicad/drc-rule-language-reference.md), [harness](../verification/harness.md)
