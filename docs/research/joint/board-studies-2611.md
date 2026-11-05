<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Four hard boards taken apart (2026-11)

Scope: four hard boards taken apart: open connections by cause and what to change. Not here: the experiments that test the changes -> [escape bands](../placement/escape-keepouts.md).
Keys: board study, polarfire-som, nekoink, sdi-mipi, gecko5education, fixed zones, zone-aware placement, LED matrix, series arrays, deep BGA rings, Freerouting time

**Status:** worked as a study: it found why kae leaves connections open on these boards and ranked
what to change; the changes are measured elsewhere (zone-aware placement, the BGA window repair).
**First published:** 2026-11-04. Runs: kae staged at 21bc53d (experiment `escape-ab3`), kae's router on the
human placement (`baseline-2611b`), plus one-seed probes; open connections are pcbnew's count.

## Method

For each board, every open connection was located (net, pads, place) from a refilled KiCad DRC and put in
a class: (a) router failure on a routable placement, (b) blocked by the board's rules, (c) made hard or
impossible by our placement, (d) other. Placements were compared with the human's, and hypotheses were
tested with cheap re-routes or re-placements (at most ~6 CPU-hours a board).

## The boards

| board | parts | kae staged, open | same router on the human placement | the gap, mostly |
|---|---|---|---|---|
| polarfire-som (PolarFire SoC module) | 473 | 472–1,386 of ~1,640 | 429 (one 1,500 s attempt) | the router barely leaves the FPGA's ball field; power pads off their fixed planes |
| nekoink (e-ink controller, 0.8 mm BGAs) | 235 | ~160 of ~620 | 95–142 | fixed pours left empty; series arrays scattered; router floor |
| sdi-mipi video converter | 396 | 154–208 of ~1,055 | 115–127 | deep BGA rings the router fails (75–80 % of opens) |
| gecko5education (ECP5 BGA, 6 layers) | 311 | 236–336 of ~1,250 | 25–44 | the 120-LED matrix scattered; the FPGA moved off its fixed core-voltage island |

No open connection on any of them was blocked by a rule (`kae.route.blocked` calls them all congestion),
except 2–5 DDR3 necks on sdi-mipi.

## Findings

1. **The placer ignored the fixed copper zones.** In place-fixed and joint-fixed tasks the human's zones
   stay where they were, but the placer did not look at them. Power pads over their own net's plane:
   polarfire 148–221 of 469 (human 404); nekoink: 32 of 35 local top-layer pours end up with none of
   their net's pads, plane escapes leave 128–153 pads to the router instead of 15; gecko5: the FPGA sat
   off its +1V2 island (25 core balls then need routed escapes instead of 3), and every staged DRC error
   was a solder-mask bridge from other nets' pads under fixed outer-layer zones. Cost: about +60 to +200
   open connections a board at equal routing effort. Addressed by zone-aware placement (branch
   `place-zone-aware`, experiment `zone-ab`).
2. **Arrays get scattered.** gecko5's 12 × 10 RGB LED matrix (with its row resistors, column
   transistors and decoders: 37 % of the connections) was spread over the whole board in four
   rotations, about 165 of 247 opens; locking only the LEDs to the human grid removed about 110. On
   nekoink the series resistor arrays ended 20–30 mm from both their ends. Untested idea: place a
   rows × columns array as one rigid grid, its drivers on its edges; keep series arrays between their
   ends in pin order.
3. **The router fails deep ball-grid rings.** sdi-mipi: 75–80 % of the opens are balls in rings 1–6 of the
   FPGA, on the human placement too ("congestion, a path exists" for 48–58 of ~60 checked). One seed with
   no extra cost on the outer layers left 163 instead of 185 open and doubled bottom-layer track (the
   human uses 3,000 mm there, kae 475–880): worth an A/B. The BGA window repair (`close-bga-region`) aims
   here but rarely gets time on big boards; see [escape-keepouts](../placement/escape-keepouts.md).
4. **Freerouting runs out of time on every big board.** Many short attempts never finish a pass; one
   1,500 s attempt beat the kept one on polarfire (429 vs 1,306). With the uncapped judge (below) the
   restart wrapper can now tell attempts apart; fewer, longer attempts on big boards are untested.
5. **The restart wrapper chose blind on big boards.** Its judge read KiCad's report list, capped at 499:
   all ~150 attempts on polarfire read 499, and 4 of 6 hard and 6 of 8 soft first-round attempts on
   gecko5. Fixed: pcbnew's count past the cap (restart.py and `kae.route.drc`).
6. **Escape bands were not the limit** (the experiment these runs belong to): re-routing polarfire's off
   and hard placements for 1,500 s each left 647 vs 646 open; hard emptied sdi-mipi's strips and still
   left 178–208.
7. Smaller ones: nekoink's U202 has an empty 3.2 mm channel through its middle, and rings counted from
   the outer edge only gave dog-bones that trapped the second column (fixed on `route-bga-next`: rings
   from the nearest open side); LPDDR4 with a 0.80 × 0.65 mm pitch was not recognised as a ball grid;
   the board's smallest via for BGA escapes gave 429 → 386 on polarfire (one seed); hard bands do not
   fit boards above about 70 % utilisation (the legaliser moved parts 1,713 mm against 717).

## What did not work here

On gecko5, locking the FPGA and SDRAM (U6, U9) at the human spots on top of the LEDs barely helped
(273 vs 280); a prototype of the U202 channel escape changed the copper but not the open counts beyond seed noise;
more time alone plateaus (sdi-mipi 154 → 145 with another 1,800 s).
