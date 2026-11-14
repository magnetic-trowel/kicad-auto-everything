<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Soft pre-routes and pair re-lay with rip-up (2026-11-09)

Keys: wire type, shove_fixed, (type route), USER_FIXED, soft reservation, pairs-first, post pass, priced rip-up, H7, D1, E1

Status: mechanism checked, experiments queued (`bus-wire-types`, `diffpair-soft`, `bus-post-relay`, each also at 300 s). Verdicts pending; this page gets the numbers when they finish.

## 1. Unlocked pre-routes are walls in Freerouting

1. KiCad's Specctra export writes unlocked tracks and vias as `(type route)`, locked ones as `(type fix)`.
2. Freerouting's `Wiring.calcFixed` (fork 2e1125a) maps `shove_fixed` to SHOVE_FIXED, `fix` to SYSTEM_FIXED, `normal` to UNFIXED and anything else to USER_FIXED. A USER_FIXED trace is not routable (`Trace.isRoutable`), so it is never ripped or shoved; SHOVE_FIXED is ripped at normal cost but never shoved or pull-tightened.
3. Run (two boards, the bridge's own DSN, 100 s): with `(type route)` the stubs come back `(type protect)`; with `shove_fixed` or `normal` they come back untyped and less of them survives in place (stub segments surviving: keks 309 / 239 / 235 of 412 for route / shove_fixed / normal; felixheld 715 / 683 / 680 of 837). The control's losses are zero-length pieces inside pads, not rips.
4. KiCad's SES import does not lock `(type protect)` copper (no locked items in the control's output), so the repair rounds and the last mile could always rip escape stubs. The walls exist only inside Freerouting's own routing.
5. So plane escapes, BGA dog-bones, the escape plan laid as copper (`escape_lay=plan`, the gecko5 negative 54 -> 241-269 open) and `critical` soft joins have only been tested as walls inside Freerouting.

Code (branch `bus-wire-types`, off by default, `--set`): `translate.set_wire_types`, `wire_type` (`route`, `shove_fixed`, `normal`), `wire_scope` (`pairs`), `pairs_unlocked`, `pairs_stage` (`after_escapes`), `pairs_own_budget`; the bridge reports `wire_types` and, for pairs first, `pairs.survival` (share of the pair copper still in place after Freerouting and at the end).

Smoke, one board each, 200 s (not evidence, shape only): keks open 100 (control) vs 119 (shove_fixed) vs 121 (normal), soft arms one truncated pass against two; felixheld pairs first 181, own budget 116, after escapes 290, soft pairs 184 with 93 % of the pair copper surviving Freerouting.

## 2. Pair re-lay with priced rip-up (H7)

`pair_route.post_pass` re-laid 0.246 of pairs in `diffpair-ab`. The suspected cause was that it needs a free strip.

Count on the 13 pilot boards' control outputs (93 pairs): a spine priced through other nets' unlocked copper (`lastmile.RIP_COST` per cell) exists for 86 and crosses a median of 2 other nets (deciles 0-5, max 9; median 3.5 items). A free-space spine exists for 84, with a median detour of 1.00. So the spine is rarely what fails; the legs, via sites and fan-ins near the pads are.

`post_pass(rip=True)` (branch `bus-post-relay`): when a pair does not fit, other nets' unlocked tracks and vias within 2 mm of its pads' box are taken out and priced per cell in the spine and fan-in grids; what the new pair breaks a rule against is ripped (at most `max_rip`), the rest restored; the last mile rejoins the ripped nets and KiCad's DRC keeps the board only if it is no worse. Re-lay alone on 6 boards: 16 of 63 pairs without rip, 32 with, ripping a median 8 items on 4 nets per pair.

## 3. Tests (pre-registered)

| Experiment | Boards | Arms | Budgets |
|---|---|---|---|
| `bus-wire-types` | 120 of `bga` ∩ `kae_escape_grid` ∩ `plane_layers`, one per family | control, shove_fixed, normal, plan-route, plan-shove | 900 s; first three also 300 s |
| `diffpair-soft` | `diffpair-ab3`'s 120 | control, first, first-soft, first-own, first-after | 900 s; first four also 300 s |
| `bus-post-relay` | `diffpair-ab3`'s 120 | control, post, post-rip10, post-rip40 | 900 s; control, post, rip40 also 300 s |

Plans and decision rules: `tools/kaeres/experiments/bus-wire-types/PLAN.md`, `tools/kaeres/experiments/bus-post-relay/PLAN.md`. Analysis: `tools/kaeres/experiments/bus-wire-types/analyze.py NAME` (opens and errors against control with bootstrap intervals, split by whether the control finished two Freerouting passes; pass-1 timeouts; pair copper survival), plus `pair_report.py` and `diffpair-ab/analyze.py` for coupling and skew.

## 4. Sources

Bus campaign notes (mechanisms findings 3-5, hybrids H1 and H7; not in the repository); Freerouting fork `Wiring.java`, `SesWriter.java`, `Trace.java`; [kae-pair-routing.md](kae-pair-routing.md).
