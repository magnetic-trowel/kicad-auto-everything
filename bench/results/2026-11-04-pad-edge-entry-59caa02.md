# Pad-edge entry on 12 routed boards (branch pad-edge-entry, 59caa02)

Post-passes on the merge3-ab `kae-bridge-main-final` outputs (harness e9889fd, KiCad 10.0.7) with the human project files; no re-routing of whole boards. DRC: kicad-cli on the re-opened board (zones refilled). Entries: segment crossings into a same-net land; oblique = 10-45 deg off the edge normal, acute = more than 45 deg. Physics: `tools/research/physics/eval_intent.sh`, `KAE_EM_TOL=1e-4`, intents compiled-6329e71. Write-up: [kae-pad-edge-entry](../../docs/research/routing/kae-pad-edge-entry.md).

Scripts: `tools/research/routing/pad_edge_smoke.sh DIR trim|reend|phys-<variant>`, `pad_edge_summary.py --variant V --terms`, `pad_entry_compare.py BEFORE NAME=OTHER...`.

## 1. End-only post-pass (`pad_trim`, cut plus re-end, rails cut a width deep)

Counts per land shape (before the pad-complex merge). Kept/planned changes (re-ended).

| Board | Kept/planned (re-ended) | DRC errors | Unconnected | Track mm | Centre/edge ends | Oblique / acute |
|---|---|---|---|---|---|---|
| jjhorton pmod-tester | 34/34 (0) | 0 → 0 | 0 → 0 | 309 → 283 | 42/0 → 8/34 | 0/0 → 0/0 |
| dream117er paicorea | 209/209 (2) | 0 → 0 | 1 → 1 | 2477 → 2344 | 251/153 → 38/296 | 124/10 → 112/8 |
| freetronics secsense | 62/62 (0) | 0 → 0 | 0 → 0 | 584 → 555 | 70/1 → 8/63 | 1/0 → 1/0 |
| lenaschimmel bestelampe | 143/143 (4) | 16 → 16 | 0 → 0 | 2361 → 2280 | 149/23 → 6/166 | 23/7 → 21/5 |
| aifryz sensor-hub | 221/221 (9) | 9 → 9 | 0 → 0 | 1973 → 1866 | 318/81 → 97/302 | 113/14 → 105/13 |
| jkiv cm4-carrier | 94/94 (0) | 612 → 605 | 0 → 0 | 1561 → 1518 | 179/18 → 85/112 | 38/6 → 38/6 |
| adafruit metro-m7 | 287/287 (7) | 22 → 22 | 1 → 1 | 2329 → 2145 | 303/70 → 16/357 | 29/19 → 27/14 |
| sparkfun redbot | 154/154 (6) | 133 → 133 | 0 → 0 | 1517 → 1415 | 190/28 → 36/182 | 27/11 → 23/9 |
| greatscottgadgets ubertooth | 287/287 (6) | 37 → 37 | 13 → 13 | 1177 → 1077 | 341/60 → 54/347 | 39/14 → 33/14 |
| adafruit magtag | 241/241 (2) | 51 → 51 | 0 → 0 | 2144 → 2011 | 250/30 → 9/271 | 14/8 → 12/8 |
| circuitmonkey chips-0123 (WLP) | 8/8 (1) | 45 → 45 | 4 → 4 | 33 → 32 | 9/10 → 1/14 | 10/0 → 6/0 |
| zephray nekoink (BGA) | 373/373 (10) | 11 → 11 | 95 → 95 | 3235 → 3083 | 816/129 → 443/502 | 205/25 → 201/19 |


## 2. Tail re-route (`pad_reroute`, then `pad_trim`)

Counts with touching same-net shapes merged into one land.

| Board | Candidates | Re-routed | Original | trim | re-route | re-route + trim | DRC err/unconn (orig → re-route + trim) | Track mm: orig → trim / re-route + trim | Re-route s |
|---|---|---|---|---|---|---|---|---|---|
| adafruit magtag | 16 | 12 | 14/8 | 14/8 | 9/2 | 9/2 | 51/0 → 51/0 | 2144 → 2042 / 2044 | 15 |
| adafruit metro-m7 | 42 | 37 | 29/19 | 30/17 | 9/3 | 9/3 | 22/1 → 22/1 | 2329 → 2214 / 2214 | 19 |
| aifryz sensor-hub | 124 | 75 | 113/14 | 109/13 | 46/6 | 45/6 | 9/0 → 9/0 | 1973 → 1881 / 1888 | 17 |
| dream117er paicorea | 89 | 78 | 87/5 | 85/5 | 12/2 | 12/2 | 0/1 → 0/1 | 2477 → 2360 / 2380 | 20 |
| freetronics secsense | 1 | 0 | 1/0 | 1/0 | 1/0 | 1/0 | 0/0 → 0/0 | 584 → 564 / 564 | 4 |
| greatscottgadgets ubertooth | 36 | 21 | 39/13 | 37/13 | 26/6 | 26/6 | 37/13 → 37/13 | 1177 → 1112 / 1115 | 10 |
| jjhorton pmod-tester | 0 | 0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 → 0/0 | 309 → 286 / 286 | 3 |
| jkiv cm4-carrier | 40 | 18 | 36/5 | 36/5 | 18/5 | 18/5 | 612/0 → 608/0 | 1561 → 1523 / 1525 | 10 |
| lenaschimmel bestelampe | 28 | 18 | 23/7 | 21/5 | 11/2 | 10/2 | 16/0 → 16/0 | 2361 → 2294 / 2296 | 17 |
| sparkfun redbot | 38 | 11 | 27/11 | 23/9 | 20/8 | 20/7 | 133/0 → 133/0 | 1517 → 1420 / 1422 | 14 |
| circuitmonkey chips-0123 | 2 | 2 | 7/0 | 7/0 | 5/0 | 5/0 | 45/4 → 45/4 | 33 → 33 / 33 | 5 |
| zephray nekoink | 208 | 125 | 205/25 | 204/19 | 95/14 | 94/13 | 11/95 → 11/95 | 3235 → 3127 / 3121 | 63 |
| **total** | 624 | 397 | 581/107 | 567/94 | 252/48 | 249/46 | never worse | 19701 → 18856 / 18889 | 199 |


## 3. Physics, change of the intent's total (mW_eq) against the original, with the two terms that moved most

| Board | Original | trim, rails cut a width deep | trim, rails at centre | re-route + trim, rails into the edge middle | re-route + trim, rails left |
|---|---|---|---|---|---|
| adafruit magtag | 26972.5 | -0.04 % (S3 50.39 mV → 50.35 mV, P1 42.95 mW → 43 mW) | +0.04 % (S3 50.39 mV → 50.44 mV, S4 442.9 mV → 443.3 mV) | +0.06 % (S3 50.39 mV → 50.45 mV, S4 442.9 mV → 443.6 mV) | +0.07 % (S3 50.39 mV → 50.48 mV, S4 442.9 mV → 443.7 mV) |
| adafruit metro-m7 | 7442.9 | +0.02 % (S0 120.3 mV → 121.5 mV, S2 194.7 mV → 194.2 mV) | +0.00 % | +0.06 % (S2 194.7 mV → 194.4 mV, S0 120.3 mV → 120.3 mV) | +0.01 % |
| aifryz sensor-hub | 47275.4 | -0.72 % (S7 1.305 V → 1.297 V, R0 12.81 V → 12.73 V) | -0.61 % (S2 11.49 mV → 11.53 mV, S7 1.305 V → 1.298 V) | +1.12 % (S1 1.114 V → 1.131 V, S4 1.305 V → 1.32 V) | -0.07 % (S2 11.49 mV → 11.53 mV, S7 1.305 V → 1.305 V) |
| dream117er paicorea | 348.7 | +0.47 % (D1 121.8 mV → 121.8 mV) | +0.00 % | +0.38 % (D1 121.8 mV → 122 mV, P1 76.25 mW → 76.32 mW) | +0.38 % (D1 121.8 mV → 122 mV, P1 76.25 mW → 76.32 mW) |
| freetronics secsense | 15818.6 | -0.09 % (P1 2.986 W → 2.97 W, D1 378.6 mV → 379.8 mV) | +0.00 % | +0.00 % | +0.00 % |
| greatscottgadgets ubertooth | 2204.1 | +0.16 % (E3 40.12 dBuV/m → 40.21 dBuV/m, E2 618.3 µV → 621.5 µV) | +0.21 % (E3 40.12 dBuV/m → 40.18 dBuV/m, E2 618.3 µV → 621 µV) | +0.18 % (E3 40.12 dBuV/m → 40.19 dBuV/m, E2 618.3 µV → 620.2 µV) | +0.21 % (E3 40.12 dBuV/m → 40.18 dBuV/m, E2 618.3 µV → 621.1 µV) |
| jjhorton pmod-tester | 904.1 | +0.51 % (D0 122.1 mV → 123.7 mV, P1 140.8 mW → 142.7 mW) | +0.00 % | +0.00 % | +0.00 % |
| jkiv cm4-carrier | 9931.3 | +0.07 % (D1 419.9 mV → 421 mV, M1 71.44 C → 71.46 C) | +0.01 % (M1 71.44 C → 71.46 C, P1 779.8 mW → 780.3 mW) | -0.11 % (S0 166.3 mV → 166.1 mV, M1 71.44 C → 71.46 C) | -0.00 % (M1 71.44 C → 71.46 C, P1 779.8 mW → 779.4 mW) |
| lenaschimmel bestelampe | 5237.8 | +1.43 % (S1 385 mV → 386.2 mV, S0 200.1 mV → 202.8 mV) | +0.11 % (S1 385 mV → 385 mV, S0 200.1 mV → 200.2 mV) | -1.49 % (S0 200.1 mV → 193.5 mV, R0 2.007 V → 1.991 V) | +0.11 % (S1 385 mV → 385 mV, S0 200.1 mV → 200.2 mV) |
| sparkfun redbot | 96538.6 | +0.02 % (S5 206.2 mV → 206.9 mV, P1 997.4 mW → 998.2 mW) | +0.00 % (S5 206.2 mV → 206.9 mV, P1 997.4 mW → 998.2 mW) | +0.02 % (S5 206.2 mV → 206.9 mV, P1 997.4 mW → 998.2 mW) | +0.01 % (S5 206.2 mV → 206.9 mV, P1 997.4 mW → 998.2 mW) |

Columns: `pad_trim --rails width` (the first trim run), `pad_trim` (rails at the centre, the default), `pad_reroute` + `pad_trim` with rail tails into the edge middle (`--rails middle`, the default), and the same with rail tails left (`--rails centre`).


## 4. Rule D against the edge rule

`pad_reroute --target centreline` (rule D) against `--target edge`, both from the original outputs; same code (4 Nov), edge-rule rows re-run for the timing. Entries counted with touching same-net shapes merged; "on centre line" = the inside end within 0.01 mm of the land's long centre line.

| Board | Candidates | Kept: edge / D | Oblique/acute: original / edge / D | On centre line: original / edge / D | DRC err/unconn: original → D | Track mm: original / edge / D | Time s: edge / D |
|---|---|---|---|---|---|---|---|
| adafruit magtag | 16 | 12 / 13 | 14/8 / 9/2 / 8/2 | 254 / 247 / 258 | 51/0 → 51/0 | 2144 / 2144 / 2149 | 17 / 16 |
| adafruit metro-m7 | 42 | 37 / 38 | 29/19 / 9/3 / 8/3 | 313 / 289 / 326 | 22/1 → 22/1 | 2329 / 2326 / 2341 | 22 / 24 |
| aifryz sensor-hub | 124 | 75 / 84 | 113/14 / 46/6 / 37/6 | 316 / 259 / 340 | 9/0 → 9/0 | 1973 / 1961 / 1977 | 20 / 20 |
| dream117er paicorea | 89 | 78 / 74 | 87/5 / 12/2 / 14/4 | 232 / 162 / 237 | 0/1 → 0/1 | 2477 / 2458 / 2475 | 23 / 39 |
| freetronics secsense | 1 | 0 / 1 | 1/0 / 1/0 / 0/0 | 70 / 70 / 71 | 0/0 → 0/0 | 584 / 584 / 585 | 6 / 9 |
| greatscottgadgets ubertooth | 36 | 21 / 29 | 39/13 / 26/6 / 20/4 | 336 / 327 / 352 | 37/13 → 37/13 | 1177 / 1176 / 1184 | 13 / 13 |
| jjhorton pmod-tester | 0 | 0 / 0 | 0/0 / 0/0 / 0/0 | 42 / 42 / 42 | 0/0 → 0/0 | 309 / 309 / 309 | 4 / 4 |
| jkiv cm4-carrier | 40 | 18 / 3 | 36/5 / 18/5 / 33/5 | 178 / 166 / 179 | 612/0 → 612/0 | 1561 / 1559 / 1562 | 12 / 14 |
| lenaschimmel bestelampe | 28 | 18 / 24 | 23/7 / 11/2 / 6/1 | 153 / 137 / 160 | 16/0 → 16/0 | 2361 / 2361 / 2363 | 19 / 19 |
| sparkfun redbot | 38 | 11 / 12 | 27/11 / 20/8 / 20/8 | 191 / 186 / 195 | 133/0 → 133/0 | 1517 / 1514 / 1517 | 15 / 15 |
| circuitmonkey chips-0123 | 2 | 2 / 2 | 7/0 / 5/0 / 5/0 | 5 / 3 / 5 | 45/4 → 45/4 | 33 / 33 / 34 | 6 / 6 |
| zephray nekoink | 208 | 125 / 134 | 205/25 / 95/14 / 89/11 | 832 / 725 / 851 | 11/95 → 11/95 | 3235 / 3210 / 3241 | 74 / 78 |

Rule D outcomes over the 12 boards: candidates 624, fail_final_piece 1, fail_length 2, fail_no_route 27, fail_overlap 4, fail_release_at_pad 20, fail_style 1, rerouted 433, skip_via 136 ; DRC-reverted 19 (cm4-carrier 16, dream117er 3).

Physics, change of the intent total against the original (edge rule: re-route + trim, rails into the edge middle; rule D: re-route only, rails routed like every track):

| Board | Original | Edge rule (re-route + trim) | Rule D |
|---|---|---|---|
| adafruit magtag | 26972.5 | +0.06 % (S3 50.39 mV → 50.45 mV, S4 442.9 mV → 443.6 mV) | +0.02 % (S3 50.39 mV → 50.39 mV, S4 442.9 mV → 443.1 mV) |
| adafruit metro-m7 | 7442.9 | +0.06 % (S2 194.7 mV → 194.4 mV, S0 120.3 mV → 120.3 mV) | +0.12 % (S2 194.7 mV → 194 mV, S0 120.3 mV → 120.2 mV) |
| aifryz sensor-hub | 47275.4 | +1.12 % (S1 1.114 V → 1.131 V, S4 1.305 V → 1.32 V) | +5.07 % (S4 1.305 V → 1.377 V, S7 1.305 V → 1.377 V) |
| dream117er paicorea | 348.7 | +0.38 % (D1 121.8 mV → 122 mV, P1 76.25 mW → 76.32 mW) | -0.00 % |
| freetronics secsense | 15818.6 | +0.00 % | +0.00 % |
| greatscottgadgets ubertooth | 2204.1 | +0.18 % (E3 40.12 dBuV/m → 40.19 dBuV/m, E2 618.3 µV → 620.2 µV) | +0.02 % |
| jjhorton pmod-tester | 904.1 | +0.00 % | +0.00 % |
| jkiv cm4-carrier | 9931.3 | -0.11 % (S0 166.3 mV → 166.1 mV, M1 71.44 C → 71.46 C) | -0.00 % |
| lenaschimmel bestelampe | 5237.8 | -1.49 % (S0 200.1 mV → 193.5 mV, R0 2.007 V → 1.991 V) | -1.74 % (S0 200.1 mV → 193.2 mV, R0 2.007 V → 1.986 V) |
| sparkfun redbot | 96538.6 | +0.02 % (S5 206.2 mV → 206.9 mV, P1 997.4 mW → 998.2 mW) | +0.25 % (S0 2.054 V → 2.057 V, R0 8.745 V → 8.773 V) |


## 5. Tracks wider than the land

`pad_reroute` rule D at 75d1e2b (base; byte-identical to §4's outputs) against rule D with the overhang test, necks and land hazard (c964c3d), both from the original outputs, operating facts of compiled-6329e71 for the pads' currents. `tools/research/routing/pad_edge_smoke.sh DIR rd-TAG`, table `pad_wide_summary.py rd ROOT rdbase rdw`. Overhanging: the entering piece adds more than 2·10⁻⁴ mm² beside or beyond the land (`pad_entry.overhang`), counted by the new `pad_trim.stats` for every version. No target: `fail_no_target` + `fail_no_fit` of the new run. Physics: change of the intent total against the original; boards whose output is byte-identical reuse §4's physics.

| Board | Candidates base/new | Kept base/new | Oblique/acute in / base / new | Overhanging in / base / new | Necks | Hazards | No target | Track Δ mm base/new | DRC err/unconn new (worse vs base) | Physics base / new |
|---|---|---|---|---|---|---|---|---|---|---|
| adafruit magtag | 16/18 | 13/15 | 14/8 / 8/2 / 9/2 | 2 / 2 / 0 | 0 | 0 | 0 | +4.8/+5.1 | 50/0 (none) | +0.02 % / +0.03 % |
| adafruit metro-m7 | 42/43 | 38/39 | 29/19 / 8/3 / 8/3 | 2 / 1 / 0 | 0 | 0 | 0 | +11.9/+12.6 | 22/1 (none) | +0.12 % / +0.12 % |
| aifryz sensor-hub | 124/127 | 84/84 | 113/14 / 37/6 / 37/6 | 6 / 3 / 3 | 0 | 0 | 0 | +4.0/+4.0 | 9/0 (none) | +5.07 % / +5.07 % |
| circuitmonkey chips-0123 | 2/2 | 2/2 | 7/0 / 5/0 / 5/0 | 6 / 6 / 6 | 0 | 0 | 0 | +0.4/+0.4 | 45/4 (none) | – |
| dream117er paicorea | 89/89 | 74/74 | 87/5 / 14/4 / 14/4 | 3 / 2 / 2 | 0 | 0 | 0 | -1.8/-1.8 | 0/1 (none) | -0.00 % / -0.00 % |
| freetronics secsense | 1/1 | 1/1 | 1/0 / 0/0 / 0/0 | 0 / 0 / 0 | 0 | 0 | 0 | +0.4/+0.4 | 0/0 (none) | +0.00 % / +0.00 % |
| greatscottgadgets ubertooth | 36/38 | 29/29 | 39/13 / 20/4 / 20/4 | 7 / 4 / 4 | 0 | 0 | 0 | +7.7/+7.7 | 37/13 (none) | +0.02 % / +0.02 % |
| jjhorton pmod-tester | 0/0 | 0/0 | 0/0 / 0/0 / 0/0 | 0 / 0 / 0 | 0 | 0 | 0 | +0.0/+0.0 | 0/0 (none) | +0.00 % / +0.00 % |
| jkiv cm4-carrier | 40/41 | 3/3 | 36/5 / 33/5 / 33/5 | 1 / 1 / 1 | 0 | 0 | 0 | +0.6/+0.6 | 612/0 (none) | -0.00 % / -0.00 % |
| lenaschimmel bestelampe | 28/29 | 24/24 | 23/7 / 6/1 / 6/1 | 1 / 2 / 2 | 0 | 0 | 0 | +2.0/+2.0 | 16/0 (none) | -1.74 % / -1.74 % |
| sparkfun redbot | 38/40 | 12/14 | 27/11 / 20/8 / 20/8 | 2 / 2 / 0 | 0 | 0 | 0 | -0.3/-0.4 | 133/0 (none) | +0.25 % / +0.26 % |
| zephray nekoink | 208/208 | 134/134 | 205/25 / 89/11 / 89/11 | 0 / 0 / 0 | 0 | 0 | 0 | +6.3/+6.3 | 11/95 (none) | – |
| **total** | 624/636 | 414/419 | 581/107 / 240/44 / 241/44 | 30 / 23 / 18 | 0 | 0 | 0 | +36.0/+36.8 | | |

New outcomes over the 12 boards: candidates 636 (overhang_in 23), rerouted 438, kept 419, DRC-reverted 19, skip_via 138, fail_no_route 31, fail_release_at_pad 20, fail_overlap 5, fail_length 2, fail_style 1, fail_final_piece 1; 202 s (base 183 s). DRC by type no worse than the base on any board (magtag `solder_mask_bridge` 25 → 24, run-to-run noise). The only entry whose track is wider than its land's short side (lenaschimmel IC4 pad 1, a 0.2 mm track into one 0.15 mm shape of a pad that is 0.4 mm wide merged) is not one when the shapes are merged.
