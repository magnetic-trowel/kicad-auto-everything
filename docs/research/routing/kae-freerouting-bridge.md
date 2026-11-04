# kae bridge: constraint-complete KiCad to Freerouting translation

Scope: defensive publication of the bridge: rule port, DSN translation, no-narrowing settings, hardened runner, incremental routing, runs and verdict. Not here: full constraint-coverage table and Freerouting/KiCad behaviours relied on -> [constraint bridge topic](../../topics/routing/freerouting-constraint-bridge.md).
Keys: kae bridge, bridge.route, rule port, rules.py, EvalRules, strictest(), recursive-descent parser, VT_UNDEFINED, MatchDpSuffix, routing class, clearance matrix, representatives, pin classes, KAE_OBSTACLES, snap_wiring, SNAP_TOL_UM, circumscribe_pins, plane cost, router_share, GRACE_S, KAE_FR_XMX, KAE_FR_SLOTS, StopReason, incremental.route_open, drc_rule_census.py, merit method kae bridge (restarts)

**Status:** worked.
**First published:** 2026-10-23, commit [d28e7de](https://github.com/magnetic-trowel/kicad-auto-everything/commit/d28e7de1e031ceb3475000ab47c777d56ab9a198) on branch `claude/vigilant-mayer-i91rrr` (runner and rule port from [bde4bc4](https://github.com/magnetic-trowel/kicad-auto-everything/commit/bde4bc4ac8f15c6dfe21aee47d4b14a868c0d9da), 2026-10-22).
**Merit method:** engine of **"kae bridge (restarts)"** (`kae.route.cli route`, in `tools/kaeres/experiments/merit-restart.sh` on main). 500-board comparison (merit-500r3 / merit-500r3k): pending.

Freerouting is an inner engine; KiCad's own DRC stays the only judge. The bridge computes every KiCad rule for every pair of items, reduces them to what a Specctra DSN can carry (classes, class-pair clearance matrix, pin classes, keepouts), stops Freerouting from narrowing tracks, and repairs the rest with DRC. Split C (79 boards): clean-on-first-attempt 0.051 (stock Freerouting 2.5.0) → 0.532.

## Idea and how it works

Pipeline `bridge.route(input, output, seed, time_s)`:
1. Export: KiCad (SWIG, `kae/src/kae/board/kicad_scripts/pcbnew_bridge.py`) writes the DSN and a JSON sidecar of what the DSN drops (real per-layer pad copper, holes, local clearances, mask expansion, zone connection, copper graphics, mask openings, edges, rule areas, off-board probe tracks and vias for every net).
2. Plan and translate: `constraints.plan` computes every requirement with the rule port; `translate.apply` rewrites the DSN.
3. Route: Freerouting runs isolated with every relied-on setting on the command line: `automatic_neckdown=false`, `fanout.enabled=false`, `copper_to_edge_clearance_um`, `neck_width_um`, `min_trace_width_um`; gets `router_share` (0.6, or `auto`) of the budget.
4. Import: `translate.fix_session` strips the SES placement (KiCad 10's import would move footprints), quotes net names (bare `|` breaks the import), restores real via diameters, un-snaps coordinates.
5. Repair and last mile: DRC-driven rounds ([repair loop](kae-repair-loop.md)), then exact grid joins ([last mile](kae-last-mile.md)).
- Output written as soon as one routed board exists and replaced only by better ones, so a killed run still leaves its best board.
- `--seed N>0` permutes component, placement and net order in the DSN (`translate.permute`); Freerouting is deterministic in DSN item order, so the seed is the only source of diversity ([restart portfolio](kae-restart-portfolio.md)).
- Locked tracks/vias go in as `(type fix)` and come back byte-identical; zones become planes; zones named `kae-crit:` are hard obstacles ([critical copper](kae-critical-copper.md)).

### Rule port (`rules.py`)

KiCad's `DRC_ENGINE::EvalRules` is not exposed to SWIG, so it is re-implemented for item pairs.
- Resolution order: local pad/footprint clearance override wins (floored at board minimum); else implicit board-setup rule, then net-class rules (larger of the two classes wins), then custom `.kicad_dru` rules in file order, last match wins. Conditions are commutative; the rule's layer must contain the tested layer. A custom winner is final; an implicit clearance is raised to local overrides and the board minimum.
- Conditions: recursive-descent parser for KiCad's expression language: `A.`/`B.` properties, case-insensitive wildcard compares, undefined properties compare false both ways (`VT_UNDEFINED` emulation), numbers with units, `diff_base`/`complement_net` mirroring `MatchDpSuffix`.
- Geometric functions unknowable before routing (`intersectsArea`, `intersectsCourtyard`) evaluated both ways by `strictest()`, keeping the larger minimum and smaller maximum.
- Agreement check (probes off-board, kept alive while queried) → [topic § Effective constraints](../../topics/routing/freerouting-constraint-bridge.md#effective-constraints).

### DSN translation (`constraints.py`, `translate.py`, `specctra.py`)

Full table → [topic § Constraint coverage](../../topics/routing/freerouting-constraint-bridge.md#constraint-coverage). Parameters specific to this implementation:
- Routing classes `kae_<netclass>`; width per layer = net-class opt clamped into [min, max]; via = net-class size raised to diameter, hole and annular minimums; padstack named `Via[0-n]_<D>:<d>_um` in whole µm (Freerouting strips `\.\d+`; KiCad reads the drill from the name).
- Clearance matrix per class pair and layer: track-track, track-via, via-track, via-via; hole clearance through the annular ring; via-via ≥ h2h + (d₁+d₂)/2 − (D₁+D₂)/2; via-only values typed `(clearance v (type wire_via|via_via))` inside the class rule; a diff pair's gap raises its track-track value.
- Representatives (representative pair + one coupled + one uncoupled member pair, strictest kept; detail → [topic § Representatives](../../topics/routing/freerouting-constraint-bridge.md#representatives-whose-rules-a-class-pair-reads)): fix in [36d9589](https://github.com/magnetic-trowel/kicad-auto-everything/commit/36d9589def360c02d9889227a034d14ecb7af64c) raised pin clearances on 5 of 17 `.kicad_dru` boards and class pairs on 2 of 112 (doc only, no suite A/B).
- Pin classes per routing class and layer, raised by hole clearance through the ring, by the solder-mask aperture on outer layers, and by the excess of real per-layer copper over the single DSN shape (directed Hausdorff distance).
- Obstacles (NPTH holes, cut-outs, stray Edge.Cuts shapes, copper graphics and text, mask openings, rule areas, spoke corridors) = keepouts in one virtual component `KAE_OBSTACLES` at the origin; net-carrying copper graphics and `kae-crit:` fills = pins of their net; polygon holes cut open by vertical lines (DSN pins have no holes).
- Edges and layers: outline `copper_to_edge_clearance_um` + via-only band; all-power-layer board rewritten to signal layers; requirements rounded up to 0.1 µm.
- Pin snap: `translate.snap_wiring` moves wiring points within `SNAP_TOL_UM` = 1.5 µm onto the same-net pin centre (recomputed as Freerouting reads it, back side mirrored before rotation); `_unsnap` restores KiCad's coordinates on import ([4e88308](https://github.com/magnetic-trowel/kicad-auto-everything/commit/4e883086fd5da7c90cbec0f41586b1d67644ad94)); 167 of 1,598 locked ends on 10 boards affected; lambdakb critical + bridge 1 open → clean (one board).
- Pad shapes (`--pad-shapes outside`, [cb25340](https://github.com/magnetic-trowel/kicad-auto-everything/commit/cb2534088d7ab75a86de0f321b50016bd325b852)): `circumscribe_pins` substitutes KiCad's ERROR_OUTSIDE outline; default `kicad`; never tested alone.
- Plane cost (`--planes cost`, default since [876f8a9](https://github.com/magnetic-trowel/kicad-auto-everything/commit/876f8a9a159d7a18a8599c2e24f2b9b0f487f935)): inner layers where one net's zones cover ≥ 30% of the outline get trace cost 4× in a Specctra `.rules` file beside the DSN (routing layers 1 preferred / 2 against; outer +0.2 per signal layer beyond two). Hard alternative `(type power)` disables plane-net detection on other layers (canhw: 14 → 58 open).

### No narrowing

Stock 2.5.0 `FoundConnectionInserter.insertFanoutMicroNeckdown` retries blocked segments at 3/4, 3/5, 1/2 of the half-width whenever `isFanout || withNeckdown` (the 0.25 → 0.1874 mm `track_width` cluster); only `fanout.enabled=false` stops it. For fine pitch, `neck_width_um` = max(largest class minimum, narrowest class width) caps retries of failed connections (a 0.64 mm USB class reaches 0.5 mm-pitch pads). The project's Freerouting fork adds `router.min_trace_width_um`, a floor under every neck-down ([4403789](https://github.com/magnetic-trowel/kicad-auto-everything/commit/4403789c3ec9de61b4e5e36ae4453bdf988977c0); installer `tools/research/routing/install_freerouting_fork.sh`).

### Hardened runner (`freerouting.py`)

- Settings merge defaults < `freerouting.json` < DSN < SES < rules < env < CLI, so host leftovers change results: each run gets a private empty `--user_data_path`, a scrubbed environment and explicit settings.
- Deadline = budget less start-up and slot wait; kill only after `GRACE_S` = 45 s; `-mp 1` fallback pass.
- JVM heap capped (`KAE_FR_XMX`, 6g; OOM shows as rc −9); host-wide flock slots (`KAE_FR_SLOTS`, else 60% of cgroup memory over heap + 0.5 GB) limit concurrent JVMs → [hosts](../../topics/routing/last-mile-and-restarts.md#hosts).
- Fork's StopReason (COMPLETED, STAGNATION, TIMED_OUT, MAX_PASSES) parsed from its log ([0865c48](https://github.com/magnetic-trowel/kicad-auto-everything/commit/0865c488a3e90241fb1f2268c56edcf953bda657)).

### Incremental `route_open` (joint loop)

`incremental.route_open` ([93f0f47](https://github.com/magnetic-trowel/kicad-auto-everything/commit/93f0f47504cd945ddf0022dc67bd26ede7b85989)) reuses the translation on a board locked except for a window: ≤ 3 autorouter passes (fork `autorouter.max_passes`), optimizer off, fork `item_order_seed`, deadline 75% of the budget, no repair. No standalone result; serves the [joint loop](../joint/kae-joint-loop.md).

### DRC rule census (diagnostic)

`tools/research/routing/drc_rule_census.py RUN_DIR` groups every attempt's `score/drc.json` by type, rule source parsed from the description, binned actual/required ratio (a cluster just under 1.0 = rounding; far below = a missing constraint) and item kinds. It showed `track_width` ≈ 70% of stock Freerouting errors, incl. 199 on a board whose DSN widths needed no clamping, pointing at neck-downs.

## What we tried

A+B (33 boards) at k = 1, 600 s, stock path vs bridge; fanout off vs `--fanout-first`; plane cost on/off at 10× budgets (crit-v6); full benchmark (all 112 qualified boards), single bridge attempt plus last mile vs stock Freerouting 2.5.0.

## Results

| Measurement | Stock FR | Bridge | Source |
|---|---|---|---|
| A+B, k=1, 600 s: errors / cp1 / completion | 88 / 0.455 / 0.896 | 0 / 0.606 / 0.955 | [topic § Measured effect](../../topics/routing/freerouting-constraint-bridge.md#measured-effect) (doc only; no results file) |
| Rule port agreement, 17 boards with `.kicad_dru` | — | 90,633 / 90,633 checks | same doc [C]; rerun `tools/research/routing/rule_evaluator_agreement.py` |
| Fanout off vs fanout-first, A+B k=1: cp1, errors | — | 0.606 / 0 vs 0.576 / 7 | same doc |
| A+B, 1800 s, k=3, with last mile: cp1 / cpk | 0.455 / — | 0.879 / 1.000 | [full-benchmark-03096d9](../../../bench/results/2026-10-24-full-benchmark-03096d9.md), [03096d9](https://github.com/magnetic-trowel/kicad-auto-everything/commit/03096d9fa4203cb6983f39592438c88410c674b7) |
| Split C (79 boards), 3600 s: cp1 / cpk / completion / errors per board | 0.051 / 0.051 / 0.786 / 31.6 | 0.532 / 0.633 / 0.976 / 0.25 | same |
| All 112 boards: cp1 / cpk | 0.17 / 0.17 | 0.634 / 0.741 | same |
| Plane cost at 10× budgets, C6 inner-plane signal track | — | 292.6 → 9.5 mm (human 109.3) | [crit-v6-10x-1ef5bf1](../../../bench/results/2026-10-25-crit-v6-10x-1ef5bf1.md) |
| Plane cost, bridge cpk A+B / C6 | — | 0.818 → 0.788 / 0.500 → 0.333 | same (k=3, single run) |

- Stock errors on A+B (`track_width` 46, `clearance` 23, `copper_edge_clearance` 14, `starved_thermal` 5) all went to 0. On split C the only remaining bridge errors were 69 `starved_thermal`.
- Caveat: the bridge runs the project's Freerouting fork, the baseline stock 2.5.0. k=10 stock baseline: [qualified-k10-baseline](../../../bench/results/2026-10-22-qualified-k10-baseline.md) (cp1 0.170 on 112 boards).

## Verdict

Worked. Most of stock Freerouting's DRC failures on KiCad boards are translation faults (constraints the router never saw, or neck-downs it was allowed to make), not routing faults. Plane cost is a physics choice costing a little completion; its return-path benefit was not separately quantified. Left: four split-C attempts killed at the harness timeout with no board written (finishing stages overran the budget); diff-pair max gap, uncoupled length, length, skew and via-count rules not translated; same-net hole-to-hole caught only by repair; DRC with refill takes minutes per round on big boards.

Not built (2026-10-21 strategy plan, [strategy candidates](../../topics/routing/strategy-candidates.md), [1b52b9f](https://github.com/magnetic-trowel/kicad-auto-everything/commit/1b52b9f0b63ed6edc150fa75058f874eed95df4c)): R4 fastroute (a Rust Freerouting port) as engine; R7 PNS residual completion through PCBWorld-Engine (pinned to KiCad 9.0.8); R9 own negotiated-congestion router; a learned portfolio selector. R1 "per-split budgets" refuted ([dead ends](kae-routing-dead-ends.md)); R2, R3 and R5 became this bridge, the portfolio and the repair loop.

## Code

`kae/src/kae/route/`: `bridge.py`, `cli.py`, `rules.py`, `constraints.py`, `translate.py`, `specctra.py`, `effective.py` (one rule source for every router that draws copper), `freerouting.py`, `incremental.py`. Entry point: `python -m kae.route.cli route IN OUT --seed N --time S [--planes cost|strict|allow] [--pad-shapes kicad|outside] [--[no-]last-mile] [--rounds N|auto] [--router-share F|auto] [--fanout|--fanout-first]`. Tests: `kae/tests/test_route_*.py`. Scripts: `tools/research/routing/{rule_evaluator_agreement.py,drc_rule_census.py,install_freerouting_fork.sh}`.

## Related

[Repair loop](kae-repair-loop.md), [last mile](kae-last-mile.md), [restart portfolio](kae-restart-portfolio.md), [critical copper](kae-critical-copper.md), [dead ends](kae-routing-dead-ends.md), [joint loop](../joint/kae-joint-loop.md).
