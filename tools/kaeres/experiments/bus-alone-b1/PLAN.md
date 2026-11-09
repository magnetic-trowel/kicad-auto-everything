<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# bus-alone-b1: can a bus route at all when it is alone?

Pre-registered 2026-11-09, before any result. Part of the bus campaign (`bus/CAMPAIGN.md` B1, `bus/mechanisms.md` X3 and H2):
sorts boards into "fails alone" (ends, escape, pins) and "routes alone, loses in contention", which steers D3-D6 and the
router side of the campaign.

## Question

Route only the bus nets (lane nets of every detected bus of width >= 4 except keyboard matrices; `kae.bus`, bare-board
detection, no human copper) on the placed board, with all other pads as obstacles and no other net routed. Compare with the
same router on the whole board.

## Arms and control

- **Control:** `fr-fork master` (`c55ff7cd5c00`, fork 06d2686, harness 99761c5), the stored per-board run the census used. One
  run per board; never re-seeded (Freerouting is deterministic).
- **bus-alone:** the same fork jar with the same harness, flags, timeout (900 s) and pass schedule, through kaebench's `freerouting`
  adapter. A wrapper binary filters the exported DSN: nets outside the bus list lose their `(net ...)`, class memberships
  and `(plane ...)` entries, their pins stay as obstacles. Both arms start from the bare route task (tracks and vias stripped,
  zones and placement kept). Same task spec: the experiment's harness is 99761c5, so the stored control is on the same task.
- Bus-net list: `busnets/<id>.txt` from `make_busnets.py` (`kae.bus` at the method's kae commit; reads no copper).

## Boards

The union of the `.n100` suites (one board per `repo_family`, `usable_route_test`): `bus_width.8-15`, `bus_width.16-31`, `bus_width.32-63`,
`bus_width.64plus`, `bus_ddr`, `bus_kind.parallel_mem`, `bus_kind.connector_ribbon`, `bus_kind.gpio_bank` (673 boards). Every board in
these suites has at least one target bus. Each suite is analysed as its own stratum; a board can sit in several.

## Measurements

Per board, per arm, from `kicad-cli` on a *bus-only view* of the re-opened output: nets outside the bus list get no net on their
pads and lose their copper, then `pcb drc --severity-all --refill-zones`; the unconnected list is complete (the 499-item cap does not bind with the
other nets gone). The human layout gets the same view. A lane open in the human view is excluded as an artifact of the board.
Per bus: lanes open alone, lanes open in control.

## Classification (decides the campaign)

Per bus (width >= 4, not excluded): **fails alone** if any lane is open in the bus-alone arm; **loses in contention** if no lane is open
alone but one is open in the control; **fine** if neither. A control that hit its deadline (`partial`/`TIMED_OUT`) is labelled
`contention-or-budget`. Per board: **fails alone** if any bus fails alone. Reported per stratum, per bus kind, board-clustered bootstrap 95% CI
(1,000 resamples, seed 1234).

`fails alone` is further split by the end: a failing lane whose either end part is BGA/grid or finer than 0.5 mm pitch counts as `escape`; a
lane open at both ends with neither (fine pins but no room) as `room`. Bus-internal or inter-bus? On a sample of boards that fail alone (`bus-one`):
each failing bus alone, one Freerouting run each, same settings; `fails alone` with all other buses gone counts as `single`, otherwise `inter-bus`.

## Decision rule

Share of lanes open in control that were also open alone, per stratum: **>= 50%** means completion on these boards is mostly an escape/pin/within-bus
problem: the router side concentrates on pin access and escape (E2, E4, D1), and contention tools (D5, D6, ghost corridors) are de-prioritised. **<= 20%**: contention
explains the opens; D3-D6 and placement continue. Between, both matter; report the split. Bootstrap CI straddling a threshold: pre-registered extension to the full suite
of that stratum (one look; effect size tolerance +-10 pp), not an arbitrary continuation.

## What would change the verdict

- A systematic bias in the view (`opens` counted on bus nets only; verified against `summarize_drc` on a smoke board).
- Bus-alone succeeds yet bus lanes only connect by ignoring contention that the control's pads present: pads of non-bus nets stay, so this is not it, but zones on inner layers are removed from the router's view only as far as the control ignores them (Freerouting does not treat foreign planes as obstacles by default in either arm).
- Fork version: results are for 06d2686, not 2e1125a. The diagnosis is about the router class and the bus geometry, not a version comparison; any sign reversal on the shared `fr-fork 2e1125a nomp r11` boards is reported.
- `-mp 10` pass cap applies to both arms.
- Bus nets routed alone get all layers free: an optimistic bound on routability, by design.

## Expected cost (information)

Bus-alone runs are mostly seconds of Freerouting plus export and DRC scoring (~60 s/board, ~2 CPU), 22 CPU-h; views (3 per board) ~15-20 CPU-h. Stored controls are reused. No physics (`KAERES_SKIP_PHYSICS=1`).

## Amendments (before any result)

- 2026-11-09 14:50: a fresh control arm was queued with the experiment (side by side) and withdrawn before any job started: the
  queue put it two days out. The control is the stored `fr-fork master` run, as registered above. Its task was prepared by harness
  99761c5; boards whose route task content changed since (kaeres content records) are reported separately. Control runs that hit the
  deadline (224 of 670 boards in the stored runs) make their buses `contention-or-budget`, never `contention`.
- The bus-one follow-up uses `wrapper/freerouting-one` (attempt N = the N-th failing bus, pass cap reset to 10).
