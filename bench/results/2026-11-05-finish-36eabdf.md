<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Finish stage (one journaled gate) against the three gated passes chained (branch rf-finish, 36eabdf)

The 12 boards of [pad-edge entry](2026-11-04-pad-edge-entry-59caa02.md): the merge3-ab `kae-bridge-main-final` outputs with their human project files (harness e9889fd, KiCad 10.0.7); nothing is re-routed whole. Operating facts from intents compiled-6329e71 for every pass in both arms.

- **chain**: today's passes one after the other, each with its own KiCad gate: `pad_reroute` (rule D) → `taut run` → `power_copper`.
- **finish**: `python -m kae.route.finish` (same three passes with their gates off, then one journaled gate). It ran its own DRC of the input here; in the restart wrapper it reuses the judge's (one run fewer per board).

Script: `tools/research/routing/finish_smoke.sh DIR chain|finish|phys-TAG`, table `finish_summary.py`. DRC: kicad-cli on the written board (zones refilled). Entries: perpendicular / oblique (10-45°) / acute (> 45°). Length: all copper. DRC runs: KiCad DRC invocations of the passes (chain: each gate's input and rounds; finish: input, output, noise run, attribution, recovery, ddmin).

## Per board

| board | DRC err/unconn in → chain → finish | types differing (chain / finish) | entries perp/obl/acute in → chain → finish | length mm | arcs | DRC runs chain / finish | s chain (tails+taut+pc) | s finish (tails+taut+pc+gate) | finish kept/entries, noise |
|---|---|---|---|---|---|---|---|---|---|
| adafruit-adafruit-magtag-pcbs- | 50/0 → 51/0 → 51/0 | solder_mask_bridge 24→25 / solder_mask_bridge 24→25 | 258/14/8 → 262/30/11 → 270/26/5 | 2144 → 2135 → 2114 | 182 / 358 | 53 / 11 | 220 (17+73+129) | 92 (6+49+6+31) | 127/238, solder_mask_bridge |
| adafruit-adafruit-metro-m7-wit | 22/1 → 22/1 → 22/1 | = / = | 325/29/19 → 368/23/3 → 368/23/3 | 2329 → 2248 → 2248 | 446 / 446 | 49 / 13 | 269 (21+64+184) | 95 (10+30+10+44) | 252/334 |
| aifryz-sensor-hub-sensor-hub | 9/0 → 9/0 → 9/0 | = / = | 272/113/14 → 365/54/7 → 365/54/7 | 1973 → 1958 → 1958 | 341 / 341 | 6 / 2 | 64 (16+34+14) | 47 (9+26+6+6) | 291/291 |
| circuitmonkey-chips-0123-class | 45/4 → 45/4 → 45/4 | = / = | 9/10/0 → 12/11/0 → 12/11/0 | 33 → 39 → 39 | 3 / 3 | 6 / 2 | 17 (6+6+5) | 6 (2+1+1+3) | 20/20 |
| dream117er-paicorea-main | 0/1 → 0/1 → 0/1 | = / = | 270/124/10 → 334/58/11 → 335/57/11 | 2477 → 2435 → 2447 | 311 / 236 | 8 / 9 | 88 (27+43+18) | 89 (6+30+4+49) | 124/164 |
| freetronics-secsense-secsense | 0/0 → 0/0 → 0/0 | = / = | 70/1/0 → 71/1/0 → 71/1/0 | 584 → 582 → 582 | 95 / 95 | 6 / 2 | 23 (6+10+6) | 13 (2+5+2+4) | 64/64 |
| greatscottgadgets-ubertooth-ub | 37/13 → 37/13 → 37/13 | = / = | 348/39/14 → 378/20/4 → 378/20/4 | 1177 → 1135 → 1127 | 216 / 239 | 11 / 5 | 73 (10+55+8) | 52 (5+34+3+9) | 226/228 |
| jjhorton-pmod-pmod-tester | 0/0 → 0/0 → 0/0 | = / = | 42/0/0 → 42/0/0 → 42/0/0 | 309 → 300 → 300 | 21 / 21 | 5 / 2 | 16 (3+8+5) | 9 (1+4+1+3) | 15/15 |
| jkiv-cm4-carriers-cm4-carrier- | 612/0 → 612/0 → 612/0 | = / = | 153/38/6 → 159/32/6 → 172/19/6 | 1561 → 1543 → 1545 | 30 / 31 | 8 / 2 | 30 (11+10+8) | 16 (5+5+2+4) | 61/61 |
| lenaschimmel-bestelampe-contro | 16/0 → 14/0 → 15/0 | starved_thermal 11→9 / starved_thermal 11→10 | 142/23/7 → 169/10/0 → 169/9/0 | 2361 → 2298 → 2284 | 280 / 341 | 11 / 13 | 94 (15+49+30) | 103 (5+24+11+63) | 97/149 |
| sparkfun-redbot-with-optical-e | 133/0 → 133/0 → 133/0 | = / = | 180/27/11 → 194/29/8 → 194/29/8 | 1517 → 1458 → 1458 | 290 / 290 | 6 / 2 | 49 (12+25+13) | 40 (5+16+5+15) | 173/173 |
| zephray-nekoink-pcb-2 | 11/95 → 11/94 → 11/93 | = / = | 715/205/25 → 863/128/12 → 865/128/12 | 3235 → 3237 → 3217 | 438 / 659 | 12 / 11 | 358 (52+253+53) | 351 (34+184+30+102) | 542/544 |

Totals over the 12 boards: **KiCad DRC runs 181 → 74, seconds 1,300 → 912**; DRC by type never worse than the input in either arm (magtag's "in" is the chain's first DRC, 24 `solder_mask_bridge`; finish's own read 25: the same unchanged board reads 24 or 25). Against the chain, finish is equal in errors and unconnected on 10 boards, one unconnected better on nekoink (93 vs 94), one `starved_thermal` worse on lenaschimmel (10 vs 9, both better than the input's 11). magtag: 53 DRC runs and 220 s → 11 and 92 s; its `solder_mask_bridge` set differs between two runs of the same board, which the gate detects and judges by count.

Where the single gate keeps less than the chain: dream117er (124 of 164 entries; arcs 236 vs 311) and lenaschimmel (97 of 149): attribution reverts whole 2.5 mm neighbourhoods, and its 8-run recovery wins only part of them back; the chain's per-pass gates attribute against smaller sets.

## Physics (`eval_intent.sh`, `KAE_EM_TOL=1e-4`)

Totals (mW_eq, the intent's weighted sum), "-" where the queued evaluation had not finished when this was written:

| board | physics total before | chain | finish |
|---|---|---|---|
| adafruit-adafruit-magtag-pcbs- | 24644.6 | 9261.4 | - |
| adafruit-adafruit-metro-m7-wit | 23833.4 | 22622.1 | 22596.4 |
| aifryz-sensor-hub-sensor-hub | 36354.8 | 27505.3 | - |
| circuitmonkey-chips-0123-class | 0.0 | 0.0 | 0.0 |
| dream117er-paicorea-main | 463.8 | 129.2 | - |
| freetronics-secsense-secsense | 15994.1 | 5689.7 | 5683.9 |
| greatscottgadgets-ubertooth-ub | 2438.4 | 2295.7 | 2299.0 |
| jjhorton-pmod-pmod-tester | 926.5 | 21.0 | 21.0 |
| jkiv-cm4-carriers-cm4-carrier- | 9902.7 | 8127.9 | - |
| lenaschimmel-bestelampe-contro | 5224.0 | - | - |
| sparkfun-redbot-with-optical-e | 101910.5 | 71665.0 | - |
| zephray-nekoink-pcb-2 | 28333.2 | 9039.1 | - |

Median finish / chain ratio per observable over the terms both have:

| observable (terms) | finish / chain, median | min | max |
|---|---|---|---|
| drop.rail (1) | 0.997 | 0.997 | 0.997 |
| emission.cable_E (1) | 1.005 | 1.005 | 1.005 |
| heat.track (1) | 1.000 | 1.000 | 1.000 |
| loss.copper (2) | 0.996 | 0.992 | 1.000 |
| supply.peak (6) | 0.999 | 0.952 | 1.031 |

## What the runs changed in the gate

The first full run (magtag first) found four gate faults, each fixed in its own commit before the table above was made:
1. Taut nets planned against each other conflict when only some are reverted (6 new clearance violations): entries of one pass in a clearance-distance conflict are merged.
2. Depth-first ddmin spent the 24-run budget halving taut and never tried power copper: breadth first, then a recovery pass after attribution.
3. Identity by position bucket read pre-existing violations on rewritten tracks, and a via's other partner pad, as new (cm4: 58 of 61 changes reverted at unchanged counts): matching by item coverage at any position, then by a shared item nearby.
4. A check at KiCad's error limit (199) reports a subset chosen by item order: such a type is judged by count; the noise run uses the output's item order.
