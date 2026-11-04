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

