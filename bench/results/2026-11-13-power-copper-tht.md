<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Power copper: necks at through-hole pads (THT), before and after

Rule, sources and exceptions: [kae-power-copper](../../docs/research/routing/kae-power-copper.md#necks-at-through-hole-pads-2026-11-13). Branch `power-copper-tht` (off `physics-determinism`).

**Set-up.** The 12 boards: the 9 of [2026-11-08-finish-overhang](2026-11-08-finish-overhang.md) plus the 3 with the most THT overhang in route-finish-ab stage 2's C arm (pekaso fortitude60, computergeek1507 pi-w-controller, nhatminh2h shvrimps). Input: stage 2's arm A board (method a7157c78c659). `kae.route.cli finish` (1,200 s, the corpus board's rules, the stage's operating facts) with the base code (`physics-determinism` 321762db) and with this branch; then `overhang_diag.py`, `kae.route.taut stats` and the deterministic physics evaluator (`eval_intent.sh`, KAE_EM_TOL 1e-4, intents compiled-9867d0b; base code for both). Summary: `tools/research/routing/pc_tht_summary.py`. One run per board and arm (the evaluator and finish are deterministic). Endstop, gos2022 and pumpbot have no DC terms in either arm (the evaluator reports their copper open for DC).

## Totals

| | base | THT neck |
|---|---|---|
| THT overhang, mm² | 1,612.6 | 211.5 (-87 %) |
| SMD overhang, mm² | 7.8 | 7.4 |
| DRC errors / unconnected | 1,094 / 0 | 1,094 / 0 (no type differs on any board) |
| finish entries kept / planned | 2,267 / 2,271 | 1,906 / 1,910 |
| oblique + acute pad entries | 180 | 180 |
| loss.copper, median ratio (9 boards) | | 1.164 (9 worse) |
| worst drop.rail, median ratio (8) | | 1.092 (6 worse) |
| hottest temp.junction, median ratio (7) | | 1.000 (2 worse) |
| heat.track, median ratio (9) | | 1.000 (3 worse) |
| power part, s (12 boards) | 150 | 150 |

## Per board

| board | THT mm² base → tht | SMD mm² | DRC err/unc base → tht | types differing | kept/entries | loss.copper mW | worst drop.rail mV | hottest Tj °C | heat.track K | THT hazards (tht) |
|---|---|---|---|---|---|---|---|---|---|---|
| computergeek1507-kicad-designs-pi-w-cont | 235.1 → 112.4 | 0.0 → 0.0 | 5/0 → 5/0 | = | 174/174 → 143/143 | 445.4 → 483.3 | 815.20 → 815.50 | 79.95 → 80.01 | 301.40 → 301.40 | {'tht_pad_heatsunk': 8, 'tht_pad_necked': 8} |
| fab-machines-bigfdm-endstop-board | 45.9 → 0.0 | 0.0 → 0.0 | 0/0 → 0/0 | = | 16/19 → 12/15 | - | - | - | - | {'tht_pad_necked': 4} |
| gos2022-hardware-mb02a1-2 | 165.0 → 1.8 | 0.0 → 0.0 | 56/0 → 56/0 | = | 436/436 → 419/419 | - | - | - | - | {'tht_pad_necked': 8} |
| hbend63-mesknecht23-btmessbox | 10.4 → 0.4 | 7.0 → 7.0 | 0/0 → 0/0 | = | 149/149 → 145/145 | 3.7 → 4.0 | 685.90 → 686.10 | 57.63 → 57.81 | 0.41 → 0.42 | {'tht_pad_necked': 2} |
| krzys9876-zx-spectrum-diy-zx2-backplane | 258.7 → 0.0 | 0.0 → 0.0 | 1/0 → 1/0 | = | 26/26 → 22/22 | 277.6 → 345.8 | 110.60 → 144.60 | - | 164.30 → 164.30 | {'tht_pad_necked': 8} |
| ladniy-jiran-breakoff-jiran-hotswap | 16.4 → 0.0 | 0.5 → 0.1 | 107/0 → 107/0 | = | 123/123 → 110/110 | 62.4 → 79.7 | - | 40.89 → 40.89 | 0.01 → 0.01 | {'tht_pad_necked': 5} |
| marksard-keyboards-rhymestone | 9.4 → 4.4 | 0.4 → 0.4 | 370/0 → 370/0 | = | 395/396 → 390/391 | 24.8 → 24.9 | 109.80 → 110.40 | 58.61 → 58.61 | 0.88 → 0.88 | {'tht_pad_necked': 4} |
| nhatminh2h-shvrimps-revised-minh-design | 162.9 → 3.6 | 0.0 → 0.0 | 6/0 → 6/0 | = | 45/45 → 44/44 | 29.1 → 39.4 | 25.72 → 33.47 | 110.60 → 117.90 | 16.57 → 16.57 | {'tht_pad_necked': 8} |
| pekaso-fortitude60-fortitude | 506.8 → 0.0 | 0.0 → 0.0 | 527/0 → 527/0 | = | 462/462 → 224/224 | 113.6 → 164.0 | 120.50 → 174.10 | 49.42 → 49.43 | 13.22 → 13.53 | {'tht_pad_necked': 8} |
| rick0x00-cdjc-cdjc | 103.4 → 75.9 | 0.0 → 0.0 | 20/0 → 20/0 | = | 134/134 → 127/127 | 89.1 → 90.9 | 141.20 → 144.10 | 43.81 → 43.81 | 12.97 → 12.97 | {'tht_pad_heatsunk': 8, 'tht_pad_necked': 8} |
| wose-ferro-dactyl-ferro-dactyl | 65.6 → 0.0 | 0.0 → 0.0 | 2/0 → 2/0 | = | 42/42 → 33/33 | 41.3 → 48.1 | 43.72 → 50.87 | - | 4.52 → 11.35 | {'tht_pad_necked': 8} |
| zenodo-15169175-pumpbot | 32.9 → 13.1 | 0.0 → 0.0 | 0/0 → 0/0 | = | 265/265 → 237/237 | - | - | - | - | {'tht_pad_heatsunk': 8, 'tht_pad_necked': 4} |

## Reading

- **Overhang.** What is left is copper the current needs (`tht_pad_heatsunk` on pi-w-controller, cdjc and pumpbot: 1-15 A rails into terminals) and the routed tracks' own entries. SMD overhang and DRC do not change.
- **Physics cost.** Copper loss rises on every board with physics (median +16 %), the drop on 6 of 8. The neck holds grown copper at the routed width over 0.5 mm, and widening keeps wider copper's edge 0.5 mm off the pad (`neck_half`) and merges runs under 1 mm, so on a short track between two THT pads the whole track can stay narrow. The largest costs are boards whose operating facts give no currents (zx2-backplane: no part currents, +25 % loss; fortitude60, a keyboard: +44 %): there the rule sees 0 A and necks to the routed track while the evaluator's own loads flow through the connector pins. That is the trade-off the `tht_pad_necked` entries put to the commanding LLM (`KAE_THT_WIDE`).
- **First version (not kept).** The THT current came from `net_currents` alone and theta did not mark a part hot. On nhatminh2h a 12 V jack got +12 V's own 0.05 A though an LM7805 passed +5 V's 0.5 A through it, and the LM7805's TO-220 pins lost their copper: loss 29 → 53 mW, heat.track 16.6 → 70.1 K, Tj 110.6 → 124.5 °C. With rail currents through the regulator chain and theta as a hot marker: 39 mW, 16.6 K, 117.9 °C. The totals of that version: THT 182.4 mm², the same medians.
- **Profile** (py-spy, pumpbot, finish 1,200 s): power copper's THT code is under 0.3 % of the finish (`_note_tht` 0.2 %, `_tht_pads` not seen); the power part's time is `_share_room` of the pours (38 %), taut 52 %.
- **Open.** Measure with the evaluator's currents (kae.excite.dc's plan) instead of `net_currents`, so the neck sees the same current as the score; a shorter `neck_len` for THT (relief spokes are 0.25-0.5 mm); an assembly-process switch (no THT neck when the facts say pin-in-paste).
