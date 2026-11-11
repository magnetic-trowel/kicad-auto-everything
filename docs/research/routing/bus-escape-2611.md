<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Bus escape (wave 2): where bus lanes die, and ordered escapes for buses

**Status:** diagnosis done 2026-11-10. Ordered bus escape built (off by default) and tested 2026-11-11 (`bus-escape-order-2`,
133 boards): **did not work.** Laying the escape plan before Freerouting, soft or as walls, ordered or not, leaves more bus lanes
and more connections open than the bridge's default; the order itself changes nothing.
**First published:** 2026-11-10, branch `bus-escape`.
Keys: bus escape, ordered escape, compress line, escape_bus, LDS layer split, bare pad, fails alone, B1 follow-up, Freerouting pass-1 time

## 1. Where lanes die (diagnosis of the bus-alone runs)

Input: the B1 bus-alone outputs (`fr-fork 06d2686 bus-alone v2`, 643 boards; Freerouting with fanout on, only bus nets in the
DSN) and their bus-only views. Script: `tools/research/bus_escape/where_lanes_die.py` (read-only). For every lane open alone
and not open in the human view (17,969 lanes on 265 boards), each open net's copper islands (`kae.bus.copper.NetGraph`), and
for each pad its island's reach past its part's pad field: no copper (**bare**), inside the field, just out (at most 2 mm),
or out.

| lane death (read at the fine end: BGA, grid or < 0.5 mm pitch) | all | bus-alone run finished | timed out |
|---|---|---|---|
| fine end bare: no stub, no via, no route | 68% | 72% | 67% |
| other (no fine end, or the fine end joined): a bare end | 12% | 27% | 10% |
| fine end: a fanout via inside the field, nothing past it | 8% | 0% | 10% |
| fine end: just out of the field (<= 2 mm) | 4% | 0% | 5% |
| escaped at both ends, died in the trunk | 1% | 0.1% | 1% |
| lanes | 17,969 | 2,644 | 15,325 |

- **Lanes die at the pin.** Freerouting leaves nothing of a connection it fails, so "bare" means neither its fanout nor any
  maze search got the pin out. Where the run finished, 97% of failed lanes have a bare end. Only 180 lanes (1%) reached out of
  both end parts; 93% of those still had more than 5 mm to go.
- **Inner rings.** Of bare BGA/grid ends with a detected ring, 9% are on the outer ring; ring 1: 25%, ring 2: 21%, ring 3:
  14%, ring 4 and deeper: 30%. Fine ends: BGA 63%, other grids 23%, QFN 6%, board-to-board connectors 5%.
- **Layers and via technology are not the main story.** 13% of failing lanes are on buses whose pin permutation needs more
  layers than the board has (LDS > copper layers), 44% more than its non-plane layers; but the bus-alone run had every layer
  (planes removed). The human layouts route these lanes with through vias only in 94% of cases (blind or micro vias on 6% of
  lanes, 10% of boards) and 72% use two or more vias per lane: the humans' answer is vias at the pins, which our runs never
  placed.
- **Why 128 boards hit 900 s.** Pass 1 is spent on failures: across bus-alone runs a failed connection costs 1.64 s of pass 1
  and a routed one 0.26 s (least squares, 644 runs); on the time-outs pass 1 took a median 352 s for 201 items (82-740 s, p10-p90),
  against 2.9 s for 35 on finished runs. Fanout took a median 5% of a timed-out run (p90 42%; over a quarter on 26 of 135).
  Freerouting's per-connection limit in pass 1 is 100 s of wall time (`AutorouteConnectionRouter`, doubling per pass). One
  board is a fork bug: bkw777 dip28, 28 items, pass 1 774 s, 776 GB allocated and 5.9 M "Polyline: must contain at least 2
  different points" warnings (none in its control).
- **B1 artefact to note:** removing the other nets' planes turned declared power layers into signal layers ("Layer 'GND' is
  declared as a power layer but no plane is defined for it"), so bus-alone had more routing layers than the control.

So the lever is getting lanes out of their pins (escape and pin access), not the trunk; and the same fix removes most of
Freerouting's pass-1 time on these boards, which is spent proving failures.

## 2. Ordered escape for buses (built, under test)

`--set escape_lay=plan --set wire_type=shove_fixed --set escape_bus=true` (`kae.route.bus_escape`, `escape.plan_grid(order=)`):
bus lanes at a ball grid prefer the side facing the bus's other end, and are split into the fewest chains that keep that
end's pin order (greedy best fit; the count is the permutation's LDS), one layer per chain, the outermost on the ball layer.
The planned escapes end 0.75 pitch past the package edge, so each layer's lanes arrive there as ordered ports (the compress
line) and Freerouting routes the trunk from rippable (`shove_fixed`) copper. Production-safe: detection reads only the
netlist, parts and pin positions. Not done: lateral compression of the ports, fine-pitch rings, via-in-pad (only where
`escape_via_in_pad` and the board's rules allow it), coordinating layers between two grid ends.

Smoke (2 boards): planned escapes were laid short of plan (exact-fit gaps failed a 2 um margin; tracks sharing a gap crossed);
fixed, wren 95 -> 102 of 137 laid. Soft (`shove_fixed`) escape copper mostly does not survive Freerouting: 22% of its track
length was left after a 300 s run, so an arm keeps the bus lanes' ordered escapes as walls (`wire_scope=except_bus`).

A/B: [PLAN.md](../../../tools/kaeres/experiments/bus-escape-order/PLAN.md), experiment `bus-escape-order-2` (133 boards;
control / plan / bus at 900 s and 300 s, buswall at 900 s).

## 3. Result of `bus-escape-order-2` (2026-11-11)

133 boards (B1 boards with a grid-end bus that fails alone), all 266 jobs ok, arms side by side, KiCad 10.0.7, Freerouting
fork 2e1125a, k = 1. Analysis: `tools/kaeres/experiments/bus-escape-order/analyze_{ana,lanes}.py`. Ratios are arm / control,
sums over boards, 95% bootstrap over boards.

**Bus lanes open** (pre-registered primary; grid-end buses, lanes open in the human view excluded), counted from each run's
scoring DRC on the 59 boards whose unconnected list is complete in every arm (under 499 items; the 74 others need the bus-only
views, queued):

| arm vs control | all 59 | control finished 2 passes (50) | control < 2 passes (9) |
|---|---|---|---|
| plan 900 | 1.110 [1.041, 1.305] | 1.238 [1.106, 1.427] | 1.019 |
| bus 900 | **1.112 [1.041, 1.323]** | 1.239 [1.104, 1.444] | 1.022 |
| buswall 900 | 1.145 [1.058, 1.370] | 1.325 [1.181, 1.518] | 1.018 |
| plan 300 | 1.095 [1.037, 1.240] | 1.175 [1.072, 1.333] | 1.022 |
| bus 300 | 1.092 [1.035, 1.237] | 1.176 [1.071, 1.332] | 1.017 |
| bus vs plan, 900 / 300 | 1.002 [0.981, 1.028] / 0.998 [0.984, 1.013] | 1.001 / 1.001 | |
| buswall vs bus, 900 | 1.030 [0.991, 1.095] | 1.069 [0.995, 1.136] | |

**Whole-board open connections** (harness DRC, counted past 499 by pcbnew):

| arm vs control | all 133 | router on time in every arm (73) | control 2 passes (57) |
|---|---|---|---|
| plan 900 | 1.015 [0.888, 1.126] | 1.216 [1.088, 1.403] | 1.277 [1.088, 1.554] |
| bus 900 | 1.052 [0.950, 1.136] | 1.209 [1.077, 1.400] | 1.307 [1.148, 1.552] |
| buswall 900 | 1.064 [0.960, 1.151] | 1.296 [1.173, 1.479] | 1.351 [1.152, 1.643] |
| plan 300 | 1.034 [1.007, 1.063] | 1.076 [0.994, 1.196] | 1.178 [1.076, 1.330] |
| bus 300 | 0.999 [0.935, 1.054] | 1.074 [0.994, 1.192] | 1.185 [1.085, 1.334] |

Mean completion 0.579 (control 900) against 0.513 (plan, bus) and 0.501 (buswall); at 300 s 0.421 against 0.381 and 0.378.
cp1 0.008 / 0 / 0 / 0 (one board, clean only in the control). CPU (method processes) 44.7 / 41.6 / 47.1 / 43.8 h at 900 s.
Boards better / worse than the control on whole-board opens: bus 900 44 / 85, buswall 35 / 95.

**DRC errors by type** (sums, control / plan / bus / buswall at 900 s): clearance 5,758 / 5,245 / 5,747 / 5,744; solder-mask
bridge 5,206 / 5,056 / 5,101 / 5,098; copper-edge 1,604 / 1,555 / 1,543 / 1,561; **starved thermal 951 / 993 / 1,294 / 1,382**;
**hole clearance 277 / 326 / 329 / 353**; the rest (courtyards, outlines, padstacks, silk) are the input's and equal across
arms. The arms that lay escape copper starve more thermal spokes and put more holes too close: the plan's dog-bones and the
plane dog-bones it adds sit in the ball field, where spokes land. Clearance errors are not worse.

**Late router start, reported apart.** On 60 boards the router started after a quarter of the budget in at least one arm; on
57 of them the control did too (pre-route stages: escape plans, plane escapes, zone fills; median start 108 s of 900 in the
control). Those boards carry most of the opens and their arms are within noise of each other; on the 73 boards where every arm
started on time, every arm that lays the plan is 20-30% worse.

**Verdict (pre-registered rule, 900 s, bus vs control): hurts.** Bus lanes open rise 11% with the interval excluding 0, and
whole-board opens rise 21% on the boards where the router started on time (31% where the control finished two passes).
The order has no effect (bus vs plan 1.00), and keeping the ordered escapes as walls is worse again (buswall vs bus +3-7%).
Not merged; `escape_bus` and `wire_scope=except_bus` stay off on the branch.

**Why, as far as the data shows.** Of 14,942 planned escapes 8,581 were laid. Soft escapes are mostly ripped by Freerouting
(22% of their track length survived in the smoke check), so the order cannot reach the trunk; what remains of the laid copper
fixes pins to sides, layers and via sites chosen without the rest of the board, which costs more than the escape gains. The
diagnosis stands (lanes die at the pin), but a pre-laid escape plan is not the fix under Freerouting; the escape has to be
negotiated with the routing (window repair failed the same way: [bga-window-repair](bga-window-repair.md)).

**What would change the verdict.** The bus-only views of the 74 boards with capped DRC lists (queued, kaeq owner
`busview-bus-escape-order-2`) and the bus scorecard (vias per lane; owner `bus-bus-escape-order-2`, evaluator 0ff1f9452b8d)
are still to come; on the whole-board counts those boards show no difference either way, so they can dilute the result but are
unlikely to reverse it. A router that uses the escape as a cost (preferred sites and sides) rather than as copper is untested.

## 4. Freerouting time on bus nets (proposal, not tested)

The cheapest fix is not to fail: an escape that lets the pin out turns a 1.6 s failure into a 0.26 s route. For what still
fails, a deterministic work cap per connection in pass 1 (expanded doors, not wall time, so runs stay reproducible), with the
cap growing per pass like the existing time limit, would stop one pass-1 failure from costing more than a routed connection
by an order of magnitude. It needs a fork change and its own A/B on the 128 boards; read it against completed passes, since
a cap can also stop searches that would have succeeded.
