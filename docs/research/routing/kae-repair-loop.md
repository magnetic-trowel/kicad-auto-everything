# kae repair loop: DRC-driven repair rounds after Freerouting

**Status:** worked (enabler; no isolated ablation).
**First published:** 2026-10-23, commit [d28e7de](https://github.com/magnetic-trowel/kicad-auto-everything/commit/d28e7de1e031ceb3475000ab47c777d56ab9a198) on branch `claude/vigilant-mayer-i91rrr` (spokes and fill-piece planes in [6b36f77](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6b36f779771940134a3baaca01538a4df501ef1e); rip-errors in [0465818](https://github.com/magnetic-trowel/kicad-auto-everything/commit/04658186e01f08a079acf025a41b7fb844f1f150)).

After Freerouting's session is imported, `kicad-cli` DRC on the re-opened board names what is wrong, and each error is mapped to a concrete action (widen, rip, draw spokes, re-route against the real fill pieces). The routed copper is then locked and Freerouting routes only what is open, in a new item order. This is why the [bridge](kae-freerouting-bridge.md) ends with 0 DRC errors on the benchmark.

Part of every kae merit method (kae bridge, kae critical+bridge, kae critical soft, kae staged, kae joint loop). Results on the 500-board comparison: pending (merit-500r3 / merit-500r3k running).

## Idea and how it works

Each round (`repair.loop`) runs `kicad-cli pcb drc` with zones refilled, as the scorer does (project files staged beside the board), and maps every error and missing connection (`repair.analyse`):

- **Narrow tracks** are widened in place to the required minimum when the plan's clearances leave room (exact check in `_Space`); otherwise ripped.
- **Other violations** touching router copper rip the items involved. The rip level escalates `items` → whole `nets` → `free` re-route when rounds fail.
- **`starved_thermal`, or a pad cut off from its zone,** gets spoke tracks (`spoke_tracks`): up to `need` straight tracks of the pad's net from inside the pad into the zone fill, clear of foreign copper, shortest first, ≥ 45° apart, at class width. KiCad counts as a spoke any track with one end in the pad outline grown by gap/2 and the other in the fill. Where none fit, the spoke corridors (`constraints.thermal_corridors`) are kept clear of other nets and copper in them is ripped.
- **Zone-split missing connections:** the net's planes in the next DSN are replaced by the fill pieces KiCad actually produced for its main part, holes as windows (`_fill_planes`; `net_clusters` mirrors `connectivity_algo.cpp checkZoneItemConnection`). Freerouting then sees the islands and joins them.
- **Other open nets** are re-routed with their planes dropped (`_drop_planes`).

Then all remaining routing is locked as `(type fix)` wiring, Freerouting routes only what is open in a new DSN item order (`round_seed`, never 0), and the session is imported on top. Boards are ordered by the key (clean, −(errors+unconnected), −unconnected). Since [2ec702e](https://github.com/magnetic-trowel/kicad-auto-everything/commit/2ec702ed7c5406b50cdbeb47603f7d01c25e1bf1) a round is kept only if better and its errors do not rise. Stop on: clean, nothing to do, `FAILS` = 2 non-improving rounds in a row, the round cap (5, or `auto` = 50), or time. Pre-routes are never ripped, widened or unlocked.

**Rip errors before the last mile** (`repair._rip_errors`, `RIP_ERROR_TYPES`). The [last mile](kae-last-mile.md) requires 0 errors, so the unlocked router copper each remaining error names is removed (clearance, hole_clearance, track_width, copper_edge_clearance, shorting_items, hole_to_hole, via_diameter, annular_width, solder_mask_bridge and similar). A starved thermal names only a pad and a zone, so for it the foreign unlocked copper inside that pad's spoke corridors is removed instead. Critical copper and pre-routes are never taken; if errors remain, nothing is done. Motivating bug: on olimex a round with a starved thermal was kept, so the last mile never ran.

## What we tried

Fixed round cap 5 vs `rounds=auto` (50); `router_share=auto` / `repair_reserve_s` (opt-in, reserve time for repair); the keep-only-if-errors-don't-rise rule (2ec702e).

## Results

| Measurement | Value | Source |
|---|---|---|
| Stop reasons, full benchmark split C (single bridge attempt, 79 boards) | no improvement 112, nothing joined 50, round cap 26, time 11 | [full-benchmark-03096d9](../../../bench/results/2026-10-24-full-benchmark-03096d9.md), [03096d9](https://github.com/magnetic-trowel/kicad-auto-everything/commit/03096d9fa4203cb6983f39592438c88410c674b7) |
| libresolar-bms-c1 with cap 5 | still gaining (29 → 15 open) when the cap hit; motivated `rounds=auto` | [last-mile-and-restarts.md](../../topics/routing/last-mile-and-restarts.md) |
| Errors after the bridge (repair included), split C | 0.25 per board, all 69 `starved_thermal` | full-benchmark-03096d9 |

There is no run with repair turned off, so its share of the bridge's gain is not isolated. `router_share=auto` and `rounds=auto` were used together with other changes in one C6 arm ([last-mile-c6-57487e6](../../../bench/results/2026-10-24-last-mile-c6-57487e6.md)) and are not confirmed alone.

## Verdict

Worked as an enabler: KiCad DRC is the only judge, so feeding its findings back as typed actions closes the gap between what the DSN can express and what KiCad checks. Remaining weakness: `starved_thermal` is the one error type it does not reliably fix (69 on split C), and each round costs a full DRC with refill, minutes on big boards.

## Code

`kae/src/kae/route/repair.py` (`loop`, `analyse`, `spoke_tracks`, `net_clusters`, `_fill_planes`, `_drop_planes`, `_rip_errors`, `_last_mile`); `kae/src/kae/route/drc.py` (kicad-cli wrapper and staging); `constraints.thermal_corridors`. Tests: `kae/tests/test_route_repair.py`. Runs inside `python -m kae.route.cli route` (`--rounds N|auto`).

## Related

[Bridge](kae-freerouting-bridge.md), [last mile](kae-last-mile.md), [critical copper](kae-critical-copper.md) (spokes-first).
