# kae last mile: exact grid joins with negotiated rip-up

**Status:** worked (the soft critical tier: partial, thin evidence).
**First published:** 2026-10-24, commit [6195e0b](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6195e0b0588903ef27e5424b04e07093ce5cc802) on branch `claude/vigilant-mayer-i91rrr` (history costs [ba32e1e](https://github.com/magnetic-trowel/kicad-auto-everything/commit/ba32e1e70bf875537826f4679dfc219a03343b14); on by default since [c9c49d6](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c9c49d6bd21128a526a9b1386a56e8ec875068db); soft tier [546ce1d](https://github.com/magnetic-trowel/kicad-auto-everything/commit/546ce1d5c85a51529055c59a7a6685f5c5ecb02b)).

When Freerouting stops (COMPLETED or STAGNATION) with 1-3 items still open, more time does not help. The last mile reloads the board as KiCad sees it, splits each open net into its connected parts and joins them with an exact grid A* router, ripping and re-routing foreign copper PathFinder-style when needed. On splits A+B it takes the bridge from cp1 0.727 to 0.909 and cpk 0.818 to 0.970 at no physics cost.

Part of the merit methods "kae bridge (restarts)" and "kae critical+bridge (restarts)"; the soft tier is the merit method **"kae critical soft (restarts)"** (`kae.route.critical_cli route --last-mile-soft`). Results on the 500-board comparison: pending (merit-500r3 / merit-500r3k running).

## Idea and how it works

What is left open after repair is either a signal connection Freerouting found no path for, or plane-net copper only KiCad sees as cut off (a pad outside its fill, a split-pour island: Freerouting treats a plane as one conduction area). `lastmile.close`:

1. **Parts as KiCad sees them.** Reload the routed board, refill every zone with the project's rules, split each open net into connected parts: pads, vias and fills join what they overlap on a shared layer; a track joins only at its ends. A part counts if it holds a pad, or a fill reached by a track or via. Track-only parts are tails; unreached fill islands are ignored.
2. **Joins.** Each smaller part is joined to the rest by `GridRouter.connect` (below). The search window grows around the part and the nearest other part (`MARGINS` 1, 3, 8 mm), then `WIDE` = 15 mm in every direction. Via costs from `VIA_COSTS`.
3. **Rip-up search.** If plain joins fail, the window's unlocked foreign tracks and vias become soft (`_SoftRouter`): crossing costs `RIP_COST` = 20 per cell, so a 0.25 mm track at 0.2 mm clearance costs as much as an 18 mm detour. Only items the new copper actually violates (`_conflicts`) are ripped, at most `MAX_RIP` = 40 per join.
4. **Negotiated re-route.** A ripped net is re-queued; its copper's rip price becomes `RIP_COST·(1 + HIST_WEIGHT·times)` with `HIST_WEIGHT` = 2, and after `HIST_MAX` = 3 rip-ups it is untouchable. `MAX_JOINS` = 40 per pass. A route whose own vias break same-net via pitch or hole-to-hole is re-searched with dearer vias or refused.
5. **Via in pad.** A pad walled in by its own footprint (a microphone's centre pad) escapes through a via in the pad.
6. **Acceptance.** What stays open goes to a nested repair loop with the new copper locked. Each round (≤ `last_mile_rounds` = 4; skipped above `LAST_MILE_MAX` = 40 open) is accepted only if KiCad DRC on the re-opened board is better with no more errors; the next round starts from that board. It needs a 0-error board, which [rip-errors](kae-repair-loop.md) provides.

**Grid router** (`critical_grid.py`, shared with [critical copper](kae-critical-copper.md)). One cost grid per allowed layer at 0.05 mm (coarsened above 1.5 M cells). A cell is blocked when a track centred there would come closer than R = w/2 + KiCad's requirement (from `effective.py`), plus a margin m = √(R² + res²/2) − R (~2 µm at R = 0.3 mm), which guarantees the straight move between two free neighbouring cells is legal; a flat 0.71-cell inflation would close the 0.2 mm gaps of 0.5 mm-pitch pins. Costs: foreign pour 0.4/cell, ground pour 1.2, a 0.4 mm halo round other nets' pads 0.6, via 1.5 cells (vias only where one fits on every layer). A* over a stack of 8-connected layer grids joined by through vias; a diagonal needs both orthogonal neighbours free; heuristic = octile distance to the target bounding box (admissible since every multiplier ≥ 1); numba kernel with a pure-Python fallback. The cell path becomes polylines whose ends snap to pad centres where legal, string-pulled while exact shapely checks (`track_violations`, 2 µm above each requirement) find nothing; a failing route is refused.

Bugs fixed in [2ec702e](https://github.com/magnetic-trowel/kicad-auto-everything/commit/2ec702ed7c5406b50cdbeb47603f7d01c25e1bf1): an open-count cap of 8 skipped bms-c1; KiCad's DRC report shows `A/B` where the board says `A{slash}B` (now unescaped); rounds trading an open for an error were kept; same-net via pitch was violated.

### Soft critical tier (`--last-mile-soft`)

`critical.soft_critical` passes the critical copper uuids (`soft_fixed`) and a physics guard to the bridge. When only critical copper blocks a join, a last rip-up tier may take it at `SOFT_FACTOR` = 3× the rip price; the ripped critical net is then re-joined by the grid search. The guard is the joint loop's accept rule (`kae.joint.scorecard.accept`): completion and errors never worse; routed physics (`critical_recheck.board_physics`) at most 10 % worse per connection gained; a board that becomes clean is always kept. If the guard rejects, the next round runs without the soft tier.

## What we tried

A+B (33 boards), k = 3, 1800 s, fork heap 2 GB, bridge and critical + bridge each with and without the last mile; six hard split-C boards (C6: libresolar-bms-c1, doorman, bldcm-power, aftonsparv, canhw-processor, oasis-pcb), k = 2, 3600 s; soft tier locally on six A+B boards and on C6.

## Results

| Arm | cp1 | cpk | completion | errors | Source |
|---|---|---|---|---|---|
| A+B bridge | 0.727 | 0.818 | 0.989 | 0 | [last-mile-ab-57487e6](../../../bench/results/2026-10-24-last-mile-ab-57487e6.md), [57487e6](https://github.com/magnetic-trowel/kicad-auto-everything/commit/57487e612dcfaf10b80b6726da7f76f6c32c9d0d) |
| A+B bridge + last mile | **0.909** | **0.970** | 0.999 | 0 | same |
| A+B critical + bridge | 0.667 | 0.697 | 0.970 | 2 starved_thermal | same |
| A+B critical + bridge + last mile | 0.758 | 0.818 | 0.988 | 2 starved_thermal | same |
| C6 bridge → bridge + last mile | 0.50 → 0.50 | 0.50 → 0.833 | 0.982 → 0.993 | 0 | [last-mile-c6-57487e6](../../../bench/results/2026-10-24-last-mile-c6-57487e6.md) |

On A+B the last mile closed 21 of 29 open attempts (90 of 107 joins) and raised boards clean on every attempt from 20 to 29; physics medians against the same arm without it were 1.0. After critical copper it closed only 11 of 31 (121 of 204 joins): locked critical copper blocks the paths. The C6 last-mile arm also had `rounds=auto`, `router_share=auto` and outside pad shapes, so the gain is not the last mile's alone; cp1 was 0.50 in both arms. Offline, the last mile alone took bms-c1 from 27 to 0 open in 25 s (topic doc, one board).

Soft tier (thin): locally paw3222 became clean with better physics (1.857 → 1.699); no help on the pmw3610 boards. C6 at 2ec702e, k = 2: critical + soft 6/12 clean vs bridge + last mile 8/12, 0 errors; it was the only arm to route libresolar-bms-c1 clean (2/2) but failed bldcm-power and aftonsparv. A+B physics medians vs human: decap 0.961, cells 0.877, rail 0.975. No A+B suite cp1/cpk for the soft arm exists. Source: [last-mile-and-restarts.md](../../topics/routing/last-mile-and-restarts.md) and [critical-net-routing.md](../../topics/routing/critical-net-routing.md).

## Verdict

Worked. Freerouting's leftovers are few and local, and many are plane connectivity it cannot see; an exact local router that reasons with KiCad's own connectivity closes them cheaply. Left: siderakb-pmw3610 and badjeff-pmw3610 with critical copper, where every join forces rip-ups that nothing absorbs. The soft tier's evidence is one board; whether its clean-board exemption costs physics on the suite is unmeasured.

## Code

`kae/src/kae/route/lastmile.py` (`close`, `_SoftRouter`, `_join`), `repair._last_mile`, `critical_grid.py`, `critical_kernels.py`, `critical_space.py`, `critical.soft_critical`. On by default in `python -m kae.route.cli route` (`--no-last-mile` disables); `critical_cli route --last-mile-soft` for the soft tier. Tests: `kae/tests/test_route_lastmile.py`, `test_route_critical_grid.py`. Topic doc: [last-mile-and-restarts.md](../../topics/routing/last-mile-and-restarts.md); background: [pathfinder-negotiated-congestion.md](../../topics/routing/pathfinder-negotiated-congestion.md).

## Related

[Repair loop](kae-repair-loop.md), [bridge](kae-freerouting-bridge.md), [critical copper](kae-critical-copper.md), [restart portfolio](kae-restart-portfolio.md), [joint loop](../joint/kae-joint-loop.md) (same accept rule).
