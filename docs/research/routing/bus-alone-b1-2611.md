<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Bus-alone routing (B1): does a bus fail alone, or lose in contention?

**Status:** decided 2026-11-10 (2,854 boards with the pre-registered extension). Verdict: buses mostly fail alone; escape and pin access first.
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

## Final result (2,854 boards, 16,088 buses of width >= 4, 49,888 bus lanes open in control)

Share of the control's open bus lanes that stay open when the buses are routed alone (board-clustered bootstrap 95% CI):

| cut | boards | control open lanes | also open alone |
|---|---|---|---|
| **pooled** | 2,854 | 49,888 | **66% (62-70%)** |
| bus-alone run finished | 2,614 | 18,845 | 60% (55-64%) |
| both runs finished | 2,287 | 10,496 | 69% (64-73%) |
| bus-alone run hit 900 s | 240 | 31,043 | 70% (64-75%) |
| bus_width.8-15 (full suite) | 1,910 | 13,397 | **60% (54-65%)**; finished 61% (57-66%) |
| bus_width.16-31 (full suite) | 712 | 21,454 | **69% (63-73%)**; finished 60% (50-69%) |
| a BGA/grid or < 0.5 mm end | 854 | 35,331 | 75% (71-79%); finished 73% (67-78%) |
| coarse ends only | 2,401 | 14,557 | 44% (38-49%); finished 42% (36-48%) |

By kind, bus-alone run finished: QSPI 79% (72-85), SD/eMMC 73% (63-82), SPI/I2S 71%, serdes lanes 68% (60-76), RGB 66%, DDR byte 65% (49-78),
DDR address 60%, connector ribbons 58% (51-63), GPIO banks 57% (51-63), unknown 52%, parallel memory 41% (27-54), RGMII/MII 35% (16-56).
Buses: 5,359 fail alone (3,936 with a fine-pitch or BGA end; 2,961 lose every lane), 1,196 lose only in contention, 1,959 in contention or
the control's budget, 7,574 fine.

Two facts found since that bear on the reading:
- The bus-alone runs had more routing layers than the control: removing the planes also turned KiCad power layers into signal layers. So
  "fails alone" is conservative; the true share failing alone is at least this high.
- Lanes die at the pin: in the bus-escape diagnosis, 77% of the lanes open alone have no copper at an end pad.

**Verdict (pre-registered rule):** both extended strata are settled above 50% (8-15: 60%, CI 54-65%; 16-31: 69%, CI 63-73%), as is every
other stratum and the pooled share. Completion on bus-rich boards is mostly an escape and pin-access problem that exists without any other
net on the board. Contention with other nets explains about a third of open bus lanes at most, and it is concentrated on coarse-pitch buses
(44% fail alone there: both matter) and on parallel memory and RGMII groups.

**Direction (bus/CAMPAIGN.md):** unchanged in kind, sharper in order. Escape first: pin-access and ordered escape (E2, E3), soft escape
reservations (D1), BGA work, placement that gives ends room (C2). Contention tools (D5 ghost corridors, D6 macro-negotiation) and the
human-corridor oracle B2 address the minority; restrict B2 and D3 to coarse-end buses (ribbons, GPIO, parallel memory), where contention is
half the story. The stop rule does not fire.

## First look (643 boards, 5,118 buses of width >= 4)

v1 of the method failed in plumbing (all runs `no_output`: the wrapper read the board id from the wrong directory); v2 is the run below.

| stratum | boards | lanes open in control | of those, also open alone (95% CI) | buses: fails alone / contention / contention-or-budget / fine |
|---|---|---|---|---|
| all | 643 | 25,458 | **68%** (62-74%) | 2,352 / 300 / 754 / 1,712 |
| bus_width.8-15 | 98 | 520 | 63% (42-77%) | 70 / 57 / 28 / 267 |
| bus_width.16-31 | 96 | 2,213 | 49% (32-67%) | 187 / 41 / 137 / 264 |
| bus_width.32-63 | 92 | 6,476 | 61% (48-73%) | 552 / 43 / 218 / 175 |
| bus_width.64plus | 36 | 7,896 | 74% (61-87%) | 554 / 20 / 77 / 168 |
| bus_ddr | 94 | 9,953 | 74% (65-82%) | 1,031 / 53 / 218 / 326 |
| bus_kind.parallel_mem | 95 | 2,312 | 79% (65-87%) | 274 / 52 / 67 / 309 |
| bus_kind.connector_ribbon | 94 | 1,468 | 78% (58-90%) | 158 / 18 / 66 / 232 |
| bus_kind.gpio_bank | 99 | 1,992 | 71% (52-84%) | 209 / 42 / 93 / 237 |

Every bus kind sits between 54% (GPIO banks) and 78% (RGB LCD). Of the 2,352 buses that fail alone, 1,939 (82%) have a BGA/grid or < 0.5 mm-pitch end; 1,276 lose every lane, 455 only 1-2 lanes.

**The budget caveat (sensitivity, not pre-registered).** On 128 of 643 boards the bus-alone run itself hit its 900 s deadline, and those boards hold 81% of the control's open bus lanes. There, "alone" is not a clean feasibility test:

| subset | boards | control open lanes | also open alone (95% CI) |
|---|---|---|---|
| bus-alone finished | 515 | 4,828 | 51% (40-60%) |
| both arms finished | 429 | 2,423 | 61% (47-73%) |
| bus-alone timed out | 128 | 20,630 | 72% (64-79%) |

Example of a clean failure: a 2-layer header-to-QFP GPIO board (18 bus nets alone, Freerouting COMPLETED at its 10-pass cap with 12 connections unrouted; the human routed all of them).

Stratum membership by the full suites instead of their `.n100` lists (same 643 boards, more of them count in each width stratum;
reported, not the pre-registered cut): width 8-15 67% (55-76%, 220 boards), 16-31 69% (60-77%, 191), 32-63 60% (47-71%, 97).

### First-look reading

At least 50%: by the rule, completion on bus-rich boards is mostly an escape, pin-access and within-bus problem, not contention with
other nets. Contention alone explains 300 buses (6%), contention or the control's budget 754 more. The width 8-15 and 16-31 strata are
undecided and are being extended. Where the bus-alone run finished, the share is near the threshold (51%), so on ordinary boards both
matter; on large BGA boards the bus nets alone already exhaust Freerouting's budget.

Implications: escape and pin access first (ordered escape and ribbons E2, soft escape reservations D1, BGA work), and Freerouting's
throughput on the bus nets of big boards; contention tools (ghost corridors D5, failure-driven corridors D6) can reach at most the
contention share (about a third of open lanes with budget included). Placement stays a lever (planar ends, pose compiler C2).
Results are for fork 06d2686 at a 10-pass cap. 699 lanes routed in control were open alone (4% of alone opens): Freerouting's
outcome is not monotone in the net set.
Runs and views: kaeq owners `exp-bus-alone-b1-v2`, `busview-bus-alone-b1-v2`; extension `exp-bus-alone-b1-ext`, `busview-bus-alone-b1-ext`.
Finish: `EXP=bus-alone-b1-ext ALONE=dde8f2b756fe tools/kaeres/experiments/bus-alone-b1/followup.sh /var/tmp/eriks/bus-alone`, twice (views, then
analysis over every `runs-*.csv`); writes `out/SUMMARY.md` and `out/buses.csv`.
