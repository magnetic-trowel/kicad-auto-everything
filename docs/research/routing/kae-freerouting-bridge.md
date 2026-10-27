# kae bridge: constraint-complete KiCad to Freerouting translation

**Status:** worked.
**First published:** 2026-10-23, commit [d28e7de](https://github.com/magnetic-trowel/kicad-auto-everything/commit/d28e7de1e031ceb3475000ab47c777d56ab9a198) on branch `claude/vigilant-mayer-i91rrr` (runner and rule port from [bde4bc4](https://github.com/magnetic-trowel/kicad-auto-everything/commit/bde4bc4ac8f15c6dfe21aee47d4b14a868c0d9da), 2026-10-22).

Freerouting is used as an inner engine while KiCad's own DRC stays the only judge. The bridge computes every KiCad rule for every pair of items, reduces them to what a Specctra DSN can carry (classes, a class-pair clearance matrix, pin classes, keepouts), stops Freerouting from narrowing tracks, and repairs what is left with DRC. On the 79 hard boards of split C it takes the clean-on-first-attempt rate from 0.051 (stock Freerouting 2.5.0) to 0.532.

This is the engine of the merit method **"kae bridge (restarts)"** (`kae.route.cli route`, in `tools/kaeres/experiments/merit-restart.sh` on main). The 500-board comparison (experiments merit-500r3 / merit-500r3k) is running. Results on the 500-board comparison: pending.

## Idea and how it works

Pipeline `bridge.route(input, output, seed, time_s)`:

1. **Export.** KiCad (SWIG, `kae/src/kae/board/kicad_scripts/pcbnew_bridge.py`) writes the DSN and a JSON sidecar of what the DSN drops: real per-layer pad copper, holes, local clearances, mask expansion, zone connection, copper graphics, mask openings, edges, rule areas, and off-board probe tracks and vias for every net.
2. **Plan and translate.** `constraints.plan` computes every requirement with the rule port (below); `translate.apply` rewrites the DSN.
3. **Route.** Freerouting runs isolated (runner below) with every relied-on setting on the command line: `automatic_neckdown=false`, `fanout.enabled=false`, `copper_to_edge_clearance_um`, `neck_width_um`, `min_trace_width_um`. It gets `router_share` (0.6, or `auto`) of the budget.
4. **Import.** `translate.fix_session` strips the SES placement (KiCad 10's import would move footprints), quotes net names (a bare `|` breaks the import), restores real via diameters and un-snaps coordinates.
5. **Repair and last mile.** DRC-driven rounds ([repair loop](kae-repair-loop.md)), then exact grid joins ([last mile](kae-last-mile.md)).

The output board is written as soon as one routed board exists and replaced only by better ones, so a killed run still leaves its best board. `--seed N>0` permutes component, placement and net order in the DSN (`translate.permute`): Freerouting is deterministic in DSN item order, so the seed is the only source of diversity ([restart portfolio](kae-restart-portfolio.md)). Locked tracks and vias go in as `(type fix)` wiring and come back byte-identical; zones become planes; zones named `kae-crit:` are hard obstacles ([critical copper](kae-critical-copper.md)).

### Rule port (`rules.py`)

KiCad's `DRC_ENGINE::EvalRules` is not exposed to SWIG, so it is re-implemented for item pairs. Resolution order: a local pad/footprint clearance override wins (floored at the board minimum); else the implicit board-setup rule, then net-class rules (larger of the two classes wins), then custom `.kicad_dru` rules in file order, last match wins; conditions are commutative and the rule's layer must contain the tested layer; a custom winner is final, while an implicit clearance is raised to local overrides and the board minimum. Conditions are parsed by a recursive-descent parser for KiCad's expression language: `A.`/`B.` properties, case-insensitive wildcard compares, undefined properties compare false both ways (`VT_UNDEFINED` emulation), numbers with units, `diff_base`/`complement_net` mirroring `MatchDpSuffix`. Geometric functions unknowable before routing (`intersectsArea`, `intersectsCourtyard`) are evaluated both ways by `strictest()`, keeping the larger minimum and smaller maximum.

Agreement check: `pcbnew.LoadBoard` initialises KiCad's engine with the project rules; probe tracks and vias of every net are placed off-board and KiCad's width, diameter, drill, annular and clearance answers per layer are compared with the port (the probes must stay alive while queried, because KiCad caches net classes by item pointer).

### DSN translation (`constraints.py`, `translate.py`, `specctra.py`)

- **Routing classes.** Nets with the same effective net class, diff-pair membership, width/via limits and answers to net-specific custom rules share a class `kae_<netclass>`. No net stays in Freerouting's default class (its via infos are built before the network is read). Width per layer = net-class opt clamped into [min, max]; via = net-class size raised to the diameter, hole and annular minimums, padstack named `Via[0-n]_<D>:<d>_um` in whole µm (Freerouting strips `\.\d+` from names; KiCad reads the drill from the name).
- **Clearance matrix.** Per class pair and layer: track-track, track-via, via-track, via-via. Hole clearance is taken through the annular ring; hole-to-hole through both drills: via-via ≥ h2h + (d₁+d₂)/2 − (D₁+D₂)/2. Via-only values are typed `(clearance v (type wire_via|via_via))` inside the class rule, the only place Freerouting gives vias their own clearance. A diff pair's gap raises its track-track value.
- **Representatives.** Each class-pair requirement is evaluated on the representative pair, one coupled diff-pair member pair and one uncoupled pair, keeping the strictest. A pad's own net never stands in for a class's tracks (else `A.Net != B.Net` rules never match: oasis +18V pads got 0.15 mm instead of 0.2 mm), and a coupled pair never represents its own classes (KiCad's implicit diff-pair rule gives `X+`/`X−` the gap as clearance). Fix in [36d9589](https://github.com/magnetic-trowel/kicad-auto-everything/commit/36d9589def360c02d9889227a034d14ecb7af64c); it raised pin clearances on 5 of 17 `.kicad_dru` boards and class pairs on 2 of 112 (doc only, no suite A/B).
- **Pin classes.** Each pad gets a clearance class per routing class and layer, raised by hole clearance through the ring, by the solder-mask aperture on outer layers, and by the excess of real per-layer copper over the single DSN shape (directed Hausdorff distance).
- **Obstacles.** NPTH holes, cut-outs, stray Edge.Cuts shapes, copper graphics and text, mask openings, rule areas and spoke corridors become keepouts in one virtual component `KAE_OBSTACLES` at the origin (board-level keepouts are read before classes exist). Net-carrying copper graphics and `kae-crit:` fills become pins of their net; polygon holes are cut open by vertical lines (DSN pins have no holes).
- **Edges and layers.** The outline uses `copper_to_edge_clearance_um`, with a via-only band where vias need more. An all-power-layer board is rewritten to signal layers (Freerouting refuses it; 2.5.0 hangs). Requirements are rounded up to 0.1 µm.
- **Pin snap.** KiCad writes DSN coordinates with `%.6g`, so above 100 mm half a micrometre is lost and a locked track end no longer sits on the pin centre; Freerouting joins wires to pins only at exact centres and reads such pre-routes as floating. `translate.snap_wiring` moves wiring points within `SNAP_TOL_UM` = 1.5 µm onto the same-net pin centre (recomputed as Freerouting reads it, back side mirrored before rotation) and `_unsnap` restores KiCad's coordinates on import ([4e88308](https://github.com/magnetic-trowel/kicad-auto-everything/commit/4e883086fd5da7c90cbec0f41586b1d67644ad94)). 167 of 1,598 locked ends on 10 boards were affected; on lambdakb critical + bridge went from 1 open to clean (one board).
- **Pad shapes** (`--pad-shapes outside`, [cb25340](https://github.com/magnetic-trowel/kicad-auto-everything/commit/cb2534088d7ab75a86de0f321b50016bd325b852)). KiCad's DSN export puts arc chords inside rounded and custom pads (3.9 µm at r = 0.25 mm, 10 µm on oasis custom pads); `circumscribe_pins` substitutes KiCad's ERROR_OUTSIDE outline. Default stays `kicad`; never tested alone.
- **Plane cost** (`--planes cost`, default since [876f8a9](https://github.com/magnetic-trowel/kicad-auto-everything/commit/876f8a9a159d7a18a8599c2e24f2b9b0f487f935)). Inner layers where one net's zones cover ≥ 30 % of the outline get trace cost 4× in a Specctra `.rules` file beside the DSN (routing layers 1 preferred / 2 against; outer +0.2 per signal layer beyond two). The hard alternative `(type power)` disables plane-net detection on other layers (canhw: 14 → 58 open).

### No narrowing

Stock 2.5.0's `FoundConnectionInserter.insertFanoutMicroNeckdown` retries blocked segments at 3/4, 3/5 and 1/2 of the half-width whenever `isFanout || withNeckdown`, which made the 0.25 → 0.1874 mm `track_width` cluster. `automatic_neckdown=false` alone does not stop it; `fanout.enabled=false` does. For fine pitch the bridge sets `neck_width_um` = max(largest class minimum, narrowest class width), so failed connections are retried capped there (a 0.64 mm USB class reaches 0.5 mm-pitch pads). The project's Freerouting fork adds `router.min_trace_width_um` as a floor under every neck-down ([4403789](https://github.com/magnetic-trowel/kicad-auto-everything/commit/4403789c3ec9de61b4e5e36ae4453bdf988977c0); installer `tools/research/routing/install_freerouting_fork.sh`).

### Hardened runner (`freerouting.py`)

Freerouting merges settings defaults < `freerouting.json` < DSN < SES < rules < env < CLI, so host leftovers change results. Each run gets a private empty `--user_data_path`, a scrubbed environment and explicit settings; FR's deadline is the budget less start-up and slot wait, with a kill only after `GRACE_S` = 45 s and a `-mp 1` fallback pass; the JVM heap is capped (`KAE_FR_XMX`, 6g; OOM shows up as rc −9); host-wide flock slots (`KAE_FR_SLOTS`, else 60 % of cgroup memory over heap + 0.5 GB) limit concurrent JVMs. The fork's StopReason (COMPLETED, STAGNATION, TIMED_OUT, MAX_PASSES) is parsed from its log ([0865c48](https://github.com/magnetic-trowel/kicad-auto-everything/commit/0865c488a3e90241fb1f2268c56edcf953bda657)).

### Incremental `route_open` (joint loop)

`incremental.route_open` ([93f0f47](https://github.com/magnetic-trowel/kicad-auto-everything/commit/93f0f47504cd945ddf0022dc67bd26ede7b85989)) reuses the translation on a board locked except for a window: ≤ 3 autorouter passes (fork `autorouter.max_passes`), optimizer off, fork `item_order_seed`, deadline 75 % of the budget, no repair. No standalone result; it serves the [joint loop](../joint/kae-joint-loop.md).

### DRC rule census (diagnostic)

`tools/research/routing/drc_rule_census.py RUN_DIR` groups every attempt's `score/drc.json` by type, rule source parsed from the description, binned actual/required ratio (a cluster just under 1.0 means rounding; far below, a missing constraint) and item kinds. It showed `track_width` is about 70 % of stock Freerouting errors, including 199 on a board whose DSN widths needed no clamping, which pointed at neck-downs.

## What we tried

A+B (33 boards) at k = 1, 600 s, stock path vs bridge; fanout off vs `--fanout-first`; plane-cost on/off at 10× budgets (crit-v6); the full benchmark (all 112 qualified boards) with a single bridge attempt plus last mile against stock Freerouting 2.5.0.

## Results

| Measurement | Stock FR | Bridge | Source |
|---|---|---|---|
| A+B, k=1, 600 s: errors / cp1 / completion | 88 / 0.455 / 0.896 | 0 / 0.606 / 0.955 | [freerouting-constraint-bridge.md](../../topics/routing/freerouting-constraint-bridge.md) "Measured effect" (doc only; no results file) |
| Rule port agreement, 17 boards with `.kicad_dru` | — | 90,633 / 90,633 checks | same doc [C]; rerun `tools/research/routing/rule_evaluator_agreement.py` |
| Fanout off vs fanout-first, A+B k=1: cp1, errors | — | 0.606 / 0 vs 0.576 / 7 | same doc |
| A+B, 1800 s, k=3, with last mile: cp1 / cpk | 0.455 / — | 0.879 / 1.000 | [full-benchmark-03096d9](../../../bench/results/2026-10-24-full-benchmark-03096d9.md), [03096d9](https://github.com/magnetic-trowel/kicad-auto-everything/commit/03096d9fa4203cb6983f39592438c88410c674b7) |
| Split C (79 boards), 3600 s: cp1 / cpk / completion / errors per board | 0.051 / 0.051 / 0.786 / 31.6 | 0.532 / 0.633 / 0.976 / 0.25 | same |
| All 112 boards: cp1 / cpk | 0.17 / 0.17 | 0.634 / 0.741 | same |
| Plane cost at 10× budgets, C6 inner-plane signal track | — | 292.6 → 9.5 mm (human 109.3) | [crit-v6-10x-1ef5bf1](../../../bench/results/2026-10-25-crit-v6-10x-1ef5bf1.md) |
| Plane cost, bridge cpk A+B / C6 | — | 0.818 → 0.788 / 0.500 → 0.333 | same (k=3, single run) |

The stock errors on A+B were `track_width` 46, `clearance` 23, `copper_edge_clearance` 14, `starved_thermal` 5; all went to 0. On split C the only remaining bridge errors were 69 `starved_thermal`. Caveat: the bridge runs the project's Freerouting fork, the baseline stock 2.5.0. The k=10 stock baseline is [qualified-k10-baseline](../../../bench/results/2026-10-22-qualified-k10-baseline.md) (cp1 0.170 on 112 boards).

## Verdict

Worked. Most of stock Freerouting's DRC failures on KiCad boards are translation faults (constraints the router never saw, or neck-downs it was allowed to make), not routing faults. Plane cost is a physics choice that costs a little completion; its return-path benefit was not separately quantified. Left: four split-C attempts were killed at the harness timeout with no board written (finishing stages overran the budget); diff-pair max gap, uncoupled length, length, skew and via-count rules are not translated; same-net hole-to-hole is caught only by repair; DRC with refill takes minutes per round on big boards.

**Not built** (from the 2026-10-21 strategy plan, [strategy-candidates.md](../../topics/routing/strategy-candidates.md), [1b52b9f](https://github.com/magnetic-trowel/kicad-auto-everything/commit/1b52b9f0b63ed6edc150fa75058f874eed95df4c)): R4 fastroute (a Rust Freerouting port) as engine, R7 PNS residual completion through PCBWorld-Engine (pinned to KiCad 9.0.8), R9 our own negotiated-congestion router, and a learned portfolio selector. R1 "per-split budgets" was refuted ([dead ends](kae-routing-dead-ends.md)); R2, R3 and R5 became this bridge, the portfolio and the repair loop.

## Code

`kae/src/kae/route/`: `bridge.py`, `cli.py`, `rules.py`, `constraints.py`, `translate.py`, `specctra.py`, `effective.py` (one rule source shared by every router that draws copper), `freerouting.py`, `incremental.py`. Entry point: `python -m kae.route.cli route IN OUT --seed N --time S [--planes cost|strict|allow] [--pad-shapes kicad|outside] [--[no-]last-mile] [--rounds N|auto] [--router-share F|auto] [--fanout|--fanout-first]`. Tests: `kae/tests/test_route_*.py`. Scripts: `tools/research/routing/{rule_evaluator_agreement.py,drc_rule_census.py,install_freerouting_fork.sh}`. Topic doc: [freerouting-constraint-bridge.md](../../topics/routing/freerouting-constraint-bridge.md).

## Related

[Repair loop](kae-repair-loop.md), [last mile](kae-last-mile.md), [restart portfolio](kae-restart-portfolio.md), [critical copper](kae-critical-copper.md), [dead ends](kae-routing-dead-ends.md), [joint loop](../joint/kae-joint-loop.md).
