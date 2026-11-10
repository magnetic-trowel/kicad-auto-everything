<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Bus escape (wave 2): where bus lanes die, and ordered escapes for buses

**Status:** diagnosis done 2026-11-10 (stored outputs only); ordered bus escape built (off by default), A/B
`bus-escape-order` pre-registered and queued, no result yet.
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

## 3. Freerouting time on bus nets (proposal, not tested)

The cheapest fix is not to fail: an escape that lets the pin out turns a 1.6 s failure into a 0.26 s route. For what still
fails, a deterministic work cap per connection in pass 1 (expanded doors, not wall time, so runs stay reproducible), with the
cap growing per pass like the existing time limit, would stop one pass-1 failure from costing more than a routed connection
by an order of magnitude. It needs a fork change and its own A/B on the 128 boards; read it against completed passes, since
a cap can also stop searches that would have succeeded.
