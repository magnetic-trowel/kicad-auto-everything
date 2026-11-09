<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# bus-wire-types: soft pre-routes, and pairs-first without walls (pre-registered plan, D1 / X1-X2)

Written 2026-11-09, before any run. Branch `bus-wire-types`. Evidence: `bus/mechanisms.md` findings 3-5, H1, section 5.

## What was checked first
KiCad exports unlocked tracks as `(type route)`. Freerouting's `Wiring.calcFixed` makes anything but `normal`/`shove_fixed`/`fix` a user-fixed item (read in the fork at 2e1125a; run on two boards: wires come back `(type protect)`, unrippable; with `shove_fixed` or `normal` they come back without a type and up to 25 % of the stub length is gone, i.e. ripped or moved). So plane escapes and BGA dog-bones have only ever been walls in Freerouting. KiCad's import does not lock `(type protect)` (the repair rounds and last mile could always rip them).

Two experiments, one commit, interleaved arms (kaeq timed class, k = 1, seed 0, Freerouting fork 2e1125a, bare placement: the benchmark's route task).

## X1 bus-wire-types: are walls what hurt?
Boards: `boards.txt` (select_boards.py, seed `bus-wire-types-2026-11-09`): `bga` ∩ `kae_escape_grid` ∩ `plane_layers`, `usable_route_test`, 30-1500 footprints, one per `repo_family`, first 120 by hash of 327. Extension: the next 120 (rule below).

Arms (`kae.route.cli route`, only these flags differ):
- control: unlocked escape copper as KiCad writes it, `(type route)`
- shove: `--set wire_type=shove_fixed` (rippable, not shoved)
- normal: `--set wire_type=normal`
- plan-route: `--set escape_lay=plan` (the old negative, gecko5 54 -> 241-269, a wall test)
- plan-shove: `--set escape_lay=plan --set wire_type=shove_fixed`

Budgets: 900 s (all arms, `bus-wire-types`) and 300 s (control, shove, normal, `bus-wire-types-300`), because bundling and soft work can cost completion when budget is tight.

Outcomes, read per budget, and separately for boards where the control finishes at least 2 Freerouting passes (`router.report.telemetry.loops`) and where it does not:
- **Open connections** total (KiCad on the re-opened board), each arm against control, 95 % bootstrap over boards.
- cp1, cpk, completion, DRC errors by type, CPU, vias. Stub survival is reported from the arm's `wire_types` and the final copper where available.

Decision, each soft arm at 900 s: **helps** if total opens fall by 5 % or more with the interval excluding 0 (noise: A/A total 2.8 % at 213 boards, about 4 % at 120); **no effect** if the interval lies within +-5 %; **hurts** if opens rise by more than 5 % with the interval excluding 0. Guardrail: DRC errors no worse by the same test. If the 900 s interval straddles the +-5 % edge for a soft arm, run the next 120 boards once and report the combined interval.

plan-route against control re-reads the old negative at n = 120, plan-shove against plan-route is the wall test of the plan.

## X2 diffpair-soft: pairs-first without walls, and the budget confound
Boards: `tools/kaeres/experiments/diffpair-ab/boards.txt`, the 120 boards of `diffpair-ab3` (real pairs, one per family, 30-500 footprints). Own control: arms interleaved at one commit; `diffpair-ab3` (486f2f1, not yet finished) is read for its `TIMED_OUT` share only.

Arms, `--pairs first` unless noted, 900 s (`diffpair-soft`) and 300 s (control, first, first-soft, first-own; `diffpair-soft-300`):
- control: no pairs
- first: pairs routed and locked first, as `diffpair-ab3`
- first-soft: `--set pairs_unlocked=true --set wire_type=shove_fixed --set wire_scope=pairs`: pair copper unlocked in KiCad, rippable reservation in Freerouting
- first-own: `--set pairs_own_budget=true`: the pair stage's time is not taken from the routing budget (its bridge deadline moves by what the pairs took)
- first-after: `--set pairs_stage=after_escapes`: pairs after the plane escapes instead of before them (locked)

Outcomes: as `diffpair-ab3` (`pair_report.py`, `analyze.py`: coupled share on pairs routed in both arms, skew, open connections, DRC by type, cp1, CPU), per budget, and split by whether the control finished 2 passes. Plus **share of pair copper surviving routing** (`report["pairs"]["survival"]`, after Freerouting and final, midpoint within 5 um same net and layer).

Decision: first-soft passes if it meets `diffpair-ab3`'s guardrails (opens within +5 %, DRC within +5 %) with coupled share within 0.1 of `first`. Stop (negative) if survival is below 0.5 of the pair copper at 900 s. first-own and first-after are read against `first`: if the opens gap to control closes to within noise with own budget or the other order, budget and stage order explain the pairs-first cost (finding 3); otherwise it is the walls (finding 5). No default changes from this experiment alone.

## Cost (as information)
About 0.3 CPU-h per board-arm at 900 s, 0.13 at 300 s; X1 about 220 CPU-h, X2 about 270 CPU-h.
