<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# ripupmemory-ab: upstream RipupMemory on oscillating boards

Pre-registered 2026-11-09, before any run. Upstream `847e7dae3` records rip-ups by (ripper net, ripped net, pass)
and keeps a rerouted net from ripping back the net it was moved for; a pair that still fails twice is retired,
so nothing is held back for ever. Ledger: R12 lists it for a rebase; the brief asks for a cherry-pick only if an
A/B on oscillating boards supports it. Commit `061507e5d` on the fork's branch `fr-ripupmemory`: one trivial
conflict (`AutoroutePassRunner`).

## Arms (kaeres methods; one Freerouting run per board per arm, 900 s, 1 thread, no `-mp` cap)
| Arm | Method |
|---|---|
| control | `fr-fork 2e1125a nomp ra` |
| ripup memory | `fr-fork 061507e5d nomp ra` |

## Boards
`boards.txt`: 55 merit boards whose fork 2e1125a run (R11) oscillates: at least 4 sign flips in the unrouted
count across passes, and still unrouted at the end. The selection is on the control's behaviour on purpose: the
mechanism only exists there. Harness 7f17a5d, task spec 11.

## Noise
Freerouting is deterministic on boards that finish inside the job timeout: paired differences are real; timed-out
boards move with wall clock and are reported apart.

## Decision rule
Cherry-pick into the fork if, on the boards that finish, opens fall by at least 5 % in total (paired sign test p
< 0.05), cp1 is not lower, and DRC errors are not higher by more than 2 % with no error type (at least 30 errors)
worse by more than 25 %. Then check the routes' Freerouting telemetry: pass count and CPU must not rise sharply
(at most 1.3x CPU median). Otherwise it stays out until the 2.6.0 rebase.
