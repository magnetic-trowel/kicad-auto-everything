<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Power copper: necks at through-hole pads (THT), before and after

Rule, sources and exceptions: [kae-power-copper](../../docs/research/routing/kae-power-copper.md#necks-at-through-hole-pads-2026-11-13). Branch `power-copper-tht` (off `physics-determinism`).

**Set-up.**
- **Boards.** The 12 boards: the 9 of [2026-11-08-finish-overhang](2026-11-08-finish-overhang.md), plus the 3 with the most THT overhang in route-finish-ab stage 2's C arm (pekaso fortitude60, computergeek1507 pi-w-controller, nhatminh2h shvrimps).
- **Runs.** Input: stage 2's arm A board (method a7157c78c659). `kae.route.cli finish` (1,200 s, the corpus board's rules, the stage's operating facts) ran once with the base code (`physics-determinism` 321762db, no THT neck) and once with this branch.
- **Measures.** `overhang_diag.py`, `kae.route.taut stats` and the deterministic physics evaluator (`eval_intent.sh`, KAE_EM_TOL 1e-4, intents compiled-9867d0b; base code for both). Summary: `tools/research/routing/pc_tht_summary.py`.
- **Repeats and gaps.** One run per board and arm (finish and the evaluator are deterministic). Endstop, gos2022 and pumpbot have no DC terms in either arm (the evaluator reports their copper open for DC).

## Totals (final rule)

| | base | THT neck |
|---|---|---|
| THT overhang, mm² | 1,612.6 | 850.3 (-47 %) |
| SMD overhang, mm² | 7.8 | 7.8 |
| DRC errors / unconnected | 1,094 / 0 | 1,094 / 0 (no type differs on any board) |
| finish entries kept / planned | 2,267 / 2,271 | 2,054 / 2,058 |
| loss.copper, median ratio (9 boards) | | 1.000 (3 worse: +0.9 to +1.4 %) |
| worst drop.rail, median ratio (8) | | 1.003 (5 worse, at most +1.2 %) |
| hottest temp.junction, median ratio (7) | | 1.000 (1 worse: nhatminh +3.8 °C) |
| heat.track, median ratio (9) | | 1.000 |
| power part, s (12 boards) | 150 | 155 |

## Per board (final rule)

| board | THT mm² base → tht | SMD mm² | DRC err/unc base → tht | types differing | kept/entries | loss.copper mW | worst drop.rail mV | hottest Tj °C | heat.track K | THT hazards (tht) |
|---|---|---|---|---|---|---|---|---|---|---|
| computergeek1507-kicad-designs-pi-w-cont | 235.1 → 88.2 | 0.0 → 0.0 | 5/0 → 5/0 | = | 174/174 → 126/126 | 445.4 → 445.0 | 815.20 → 817.40 | 79.95 → 79.98 | 301.40 → 301.40 | {'tht_pad_kept_wide': 8, 'tht_pad_necked': 8} |
| fab-machines-bigfdm-endstop-board | 45.9 → 0.0 | 0.0 → 0.0 | 0/0 → 0/0 | = | 16/19 → 12/15 | - | - | - | - | {'tht_pad_necked': 4} |
| gos2022-hardware-mb02a1-2 | 165.0 → 137.3 | 0.0 → 0.0 | 56/0 → 56/0 | = | 436/436 → 429/429 | - | - | - | - | {'tht_pad_kept_wide': 8, 'tht_pad_necked': 8} |
| hbend63-mesknecht23-btmessbox | 10.4 → 10.4 | 7.0 → 7.0 | 0/0 → 0/0 | = | 149/149 → 149/149 | 3.7 → 3.7 | 685.90 → 685.90 | 57.63 → 57.63 | 0.41 → 0.41 | {'tht_pad_kept_wide': 2} |
| krzys9876-zx-spectrum-diy-zx2-backplane | 258.7 → 234.6 | 0.0 → 0.0 | 1/0 → 1/0 | = | 26/26 → 26/26 | 277.6 → 277.8 | 110.60 → 111.30 | - | 164.30 → 164.30 | {'tht_pad_kept_wide': 7, 'tht_pad_necked': 1} |
| ladniy-jiran-breakoff-jiran-hotswap | 16.4 → 16.4 | 0.5 → 0.5 | 107/0 → 107/0 | = | 123/123 → 123/123 | 62.4 → 62.4 | - | 40.89 → 40.89 | 0.01 → 0.01 | {'tht_pad_kept_wide': 5} |
| marksard-keyboards-rhymestone | 9.4 → 4.4 | 0.4 → 0.4 | 370/0 → 370/0 | = | 395/396 → 392/393 | 24.8 → 24.8 | 109.80 → 109.80 | 58.61 → 58.61 | 0.88 → 0.88 | {'tht_pad_kept_wide': 2, 'tht_pad_necked': 3} |
| nhatminh2h-shvrimps-revised-minh-design | 162.9 → 153.4 | 0.0 → 0.0 | 6/0 → 6/0 | = | 45/45 → 43/43 | 29.1 → 29.5 | 25.72 → 25.83 | 110.60 → 114.40 | 16.57 → 16.57 | {'tht_pad_kept_wide': 8, 'tht_pad_necked': 3} |
| pekaso-fortitude60-fortitude | 506.8 → 111.1 | 0.0 → 0.0 | 527/0 → 527/0 | = | 462/462 → 353/353 | 113.6 → 114.9 | 120.50 → 121.90 | 49.42 → 49.43 | 13.22 → 13.22 | {'tht_pad_kept_wide': 8, 'tht_pad_necked': 8} |
| rick0x00-cdjc-cdjc | 103.4 → 24.7 | 0.0 → 0.0 | 20/0 → 20/0 | = | 134/134 → 117/117 | 89.1 → 89.9 | 141.20 → 142.40 | 43.81 → 43.81 | 12.97 → 12.97 | {'tht_pad_kept_wide': 8, 'tht_pad_necked': 8} |
| wose-ferro-dactyl-ferro-dactyl | 65.6 → 44.1 | 0.0 → 0.0 | 2/0 → 2/0 | = | 42/42 → 38/38 | 41.3 → 41.3 | 43.72 → 43.72 | - | 4.52 → 4.52 | {'tht_pad_kept_wide': 5, 'tht_pad_necked': 7} |
| zenodo-15169175-pumpbot | 32.9 → 25.5 | 0.0 → 0.0 | 0/0 → 0/0 | = | 265/265 → 246/246 | - | - | - | - | {'tht_pad_kept_wide': 8, 'tht_pad_necked': 8} |

## What changed on the way, and why

| version | change | THT mm² | loss.copper median (worse) |
|---|---|---|---|
| v1 | current: the part's own, or the net's for a part with none; neck on every same-net track within neck_len | 182 | 1.164 (9/9) |
| v2 | + rails through the regulator chain; theta marks a part hot | 212 | 1.164 (9/9) |
| v3 | current from the evaluator's DC plan (`kae.excite.dc.planned_injections`) and a resistive solve of the routed copper (`branch_currents`); neck only on tracks ending in the pad, a 0.25 mm gap for passing tracks | partial run (stopped for v4) | 1.164 (5/5 measured) |
| v4 | + a loss budget: a net's necks add at most 0.2 % of its routed copper loss under the plan | 806 | 1.000 (4/9; zx2-backplane +8.9 %) |
| v5 | + a track that runs through a pad enters it (the zx /5V bus runs straight through a row of 2 A connector pins) | 850 | 1.000 (3/9) |

- **Why the 0.5 mm neck alone did not explain v1-v3.** Per-sample L/w along the input's power tracks (`diag`): on fortitude60 and nhatminh most of the added resistance was the copper the base laid *around* the pad (a 3 mm rail over a 1.7 mm pad carries current past it, which is what the overhang is), then the neck, then the taper round-capped wider copper needs to keep its edge 0.5 mm off the pad (L = neck_len + w/2, up to 2 mm). On zx2-backplane in v4 it was a bus routed through pins it does not end in, which the passing-track gap held at 0.25 mm across each pin. Where current flows through a pad, removing the overhang removes a conductor; only a loss budget keeps that within the noise.
- **nhatminh Tj +3.8 °C.** The LM7805 (theta given) is left alone, but three necked pads near it (bulk capacitors on its input and output) were copper that spread its heat.
- **Profile** (py-spy, pumpbot, v1): power copper's THT code was under 0.3 % of the finish; the DC plan and solve added 5 s over the 12 boards in v5.
- **Open.** The budget is per net and even over its pads; a joint-by-joint budget (high-current pads keep copper, idle pins neck) would neck more. The hazard `tht_pad_kept_wide` puts each pad left wide for loss to the commanding LLM (`KAE_THT_NARROW`).
