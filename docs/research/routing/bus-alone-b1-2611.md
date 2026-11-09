<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Bus-alone routing (B1): does a bus fail alone, or lose in contention?

**Status:** running (queued 2026-11-09). Pre-registered: [PLAN.md](../../../tools/kaeres/experiments/bus-alone-b1/PLAN.md).
**First published:** 2026-11-09, branch `bus-alone-b1`.
Keys: bus-alone, fails alone, contention, B1, bus campaign, DSN net filter

## Mechanism

Freerouting (fork 06d2686, the stored `fr-fork master` control's jar, flags and 900 s budget) routes only the lane nets of every
bus of width >= 4 (kae.bus bare-board detector; matrices excluded). A wrapper drops all other nets from the DSN (their pins stay
as obstacles without a net, their planes go). Opens are read by `kicad-cli` on a bus-only view of each output (non-bus pads
lose their net, non-bus copper is removed), for the bus-alone run, the stored control and the human layout; the view matches
the harness DRC exactly on bus nets where the harness list is not capped.

Boards: union of the `.n100` suites `bus_width.8-15` and up, `bus_ddr`, `bus_kind.parallel_mem`, `.connector_ribbon`, `.gpio_bank`:
673 boards, 670 with at least one bus of width >= 4. 224 of 670 stored controls hit their deadline.

## Results

Pending: kaeq owners `exp-bus-alone-b1` (runs), `busview-bus-alone-b1` (views). `tools/kaeres/experiments/bus-alone-b1/followup.sh WORK`
queues the remaining views and writes `WORK/out/SUMMARY.md`.
