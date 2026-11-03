# kae power copper: widen rails and grounds into free space, ground vias at decoupling pads

**Status:** not finished (smoke test on 10 boards, physics better on all; no A/B through the router yet).
**First published:** 2026-11-02, branch `power-copper` (off `thermal-heatsinks-merge`).

The bridge routes every net at its net-class width and only ever narrows. Over 99 boards of a routing A/B (human layout vs `kae-bridge-main-final`, same placement) the median power-track width was 0.39 mm for the human boards and 0.20 mm for kae, and none of kae's track length was 0.4 mm or wider (human: a median 13.5%). Copper loss was 1.69x, and kae dropped most ground vias (2651 vs 715 over 107 boards). `kae.route.power_copper` is a post-pass on a routed board that changes routing only, on power and ground nets only, and keeps a change only where KiCad's DRC is no worse.

## Idea and how it works

- **Classes** from the physics brief (`kae.circuit.brief`): rails and grounds are widened; switch nodes (role `switch_node`, commutation cells' `sw`/`sw_nets`) never are, since SW copper is an E-field antenna ([power-copper](../../topics/physics/power-copper.md) §1, "pour freely on quiet nodes"). Victims are clock, high-speed, analog and RF nets plus the brief's victim and crystal structures (feedback, sense, divider nodes); antenna parts are kept clear.
- **Widen in place.** Each straight track is sampled every 0.1 mm; at each sample the widest legal half-width is the distance to every foreign item minus its requirement. Runs of equal width (at least 1 mm long; a run is never wider than its narrowest sample) become separate collinear segments, each checked exactly with the critical router's `Space.track_violations` plus the extra gaps below. No track moves, nothing is narrowed, no other net is touched. Ladder 0.3-1.0 mm (area efficiency peaks at the feed width, power-copper §3); a net whose operating current (operating facts `parts.<ref>.I_A`, upper end) needs more gets the IPC-2221 width of 3x that current, up to 3 mm. Highest-current nets go first.
- **Extra spacing.** Grown copper keeps, beyond the board clearance: from ordinary signals 2x the clearance and 2x the signal's width (3W centre to centre); from victims, on its own and the adjacent layers, D = h·sqrt(1/K - 1) with K = 5%, clipped to 0.5-2 mm ([si-fundamentals](../../topics/rules/si-fundamentals.md): express spacing as a crosstalk budget in units of h, not "3W"); 3 mm from antenna pads.
- **Ground vias.** Each SMD ground pad of a capacitor, and each ground pin the brief's decap structures name, without a ground barrel within 1 mm gets one via as close as is legal where the same ground has fill on another layer, with a pad-to-via track ([decoupling-pdn](../../topics/rules/decoupling-pdn.md) PDN-01, LearnEMC's via adjacent to the pad).
- **Stitching.** Ground fill pieces other than a layer's largest that hold ground pads and fewer than 3 barrels get vias 2 mm apart into another layer's ground (`critical.Session.stitch_ground`'s rule).
- **No new pours**: si-fundamentals says ground fill is never a default, and a separate investigation found the task keeps every human zone (refilled ground area 1.003x the human's).
- **DRC gate.** KiCad DRC (zones refilled) on the written board must have no error type and no unconnected count above the input's. A new violation naming an added item reverts it; one that names none reverts changes within 1 mm of its positions; what is left is bisected (16 DRC runs at most). Then the input is kept.

Hook: bridge option `power_copper=True` (off by default) runs it after the repair rounds.

## Results

Smoke test, 10 boards, `kae-bridge-main-final` outputs, physics `tools/research/physics/eval_intent.sh` (`KAE_EM_TOL=1e-4`, intents `compiled-6329e71`). Script: `tools/research/routing/power_copper_smoke.sh`.

| Board | Power length >= 0.4 mm | GND vias | DRC err/unconn | Copper loss | Worst supply.peak | Signal terms |
|---|---|---|---|---|---|---|
| jjhorton pmod-tester | 0 -> 100% | 0 -> 2 | 0/0 -> 0/0 | 141 -> 40 mW | — | — (heat 164 -> 17 K) |
| dream117er paicorea | 0 -> 37% | 8 -> 10 | 0/1 -> 0/1 | 76 -> 58 mW | — | — |
| freetronics secsense | 0 -> 79% | 0 -> 1 | 0/0 -> 0/0 | 2986 -> 873 mW | — | — |
| lenaschimmel bestelampe | 0 -> 66% | 7 -> 30 | 16/0 -> 16/0 | — | 385 -> 137 mV | cable CM 8.2 -> 7.3 mV |
| aifryz sensor-hub | 0 -> 50% | 35 -> 78 | 9/0 -> 9/0 | 52 -> 42 mW | 1.31 -> 1.13 V (VDDA); +BATT 1.31 -> 1.54 V | cable CM 38 -> 36 mV |
| jkiv cm4-carrier | 0 -> 37% | 72 -> 72 | 612/0 -> 612/0 | 780 -> 590 mW | 166 -> 163 mV | emission 61.9 -> 61.8 dBuV/m |
| adafruit metro-m7 | 0 -> 33% | 21 -> 50 | 22/1 -> 22/1 | — | 448 -> 413 mV | cable CM 99 -> 88 mV |
| sparkfun redbot | 0 -> 55% | 9 -> 24 | 133/0 -> 133/0 | 997 -> 552 mW | 2.05 -> 1.35 V | emission 69.2 -> 68.0 dBuV/m |
| greatscottgadgets ubertooth | 0 -> 36% | 12 -> 12 | 37/13 -> 37/13 | — | 293 -> 290 mV | pickup 618 -> 580 uV, emission 40.1 -> 39.4 dBuV/m |
| adafruit magtag | 0 -> 42% | 23 -> 55 | 51/0 -> 50/0 | 43 -> 20 mW | 443 -> 96 mV | emission 92.1 -> 75.0 dBuV/m |

Worse: aifryz `supply.peak` S4 (+BATT pin's own core noise) 1.31 -> 1.54 V while its other supply terms fell 14-41%; redbot's D1 rail drop 22 -> 78 uV (met by a wide margin). The pass took 6-77 s per board, most of it KiCad DRC (planning 2-15 s).

## Width cap sweep, vector growth and current sharing (2026-11-03)

Same 10 boards, same physics. W*n* = track widening capped at *n* mm (`max_width` = `current_cap`); V*n* = vector mode (the free region around each power/ground net's copper on its layer, clipped to an *n* mm corridor, filled with overlapping 0.5 mm track strips; other nets' fills are obstacles). Median after/before ratio over the boards' terms:

| Term (n) | W1 | W2 | W3 | W20 | V3 | V20 |
|---|---|---|---|---|---|---|
| loss.copper (7) | 0.562 | 0.525 | 0.519 | 0.515 | 0.882 | 0.888 |
| drop.rail (20) | 0.693 | 0.678 | 0.668 | 0.667 | 0.918 | 0.916 |
| heat.track (7) | 0.567 | 0.567 | 0.567 | 0.567 | 1.000 | 1.000 |
| supply.peak (35) | 0.865 | 0.865 | 0.864 | 0.865 | 0.905 | 0.910 |
| emission.cable_E (4, field ratio) | 0.902 | 0.908 | 0.906 | 0.907 | 0.934 | 0.988 |
| cable_cm.v (3) | 0.900 | 0.908 | 0.912 | 0.908 | 0.904 | 0.885 |
| pickup.peak (1) | 0.937 | 0.941 | 0.942 | 0.944 | 0.882 | 1.237 |

- **Cap.** Free space, not the cap, limits widening: past 2-3 mm the gains stop. 20 mm is no better than 3 mm on any median and worse on aifryz's loop loss (0.85 vs 0.62) and ubertooth's S1 (x1.04). The default cap is now 3 mm.
- **Vector.** Weaker than widening on 7 of 10 boards: rails may not cut ground pours, and on poured 2-layer boards almost all free space is pour. Better on metro-m7 (0.86 vs 0.90 total), cm4 (0.65-0.70 vs 0.80) and lenaschimmel (0.43 vs 0.49, and DRC errors 16 -> 8). V20 hurt ubertooth (supply.peak up to x4.6, pickup x1.24). Growing into pours (`into_pours`) starved ground thermals on pmod-tester and failed the gate. KiCad zones cannot be used at all: the route-task scorer counts any zone edit as invalid (`bench/src/kaebench/score.py`), so vector copper is written as tracks.
- **Sharing.** Competing power/ground nets split contested room at w ~ I (least sum I^2 R): widening leaves a competing ungrown track its share, and vector mode grows all nets at speeds proportional to current (a weighted Voronoi split by repeated buffering). Examples (W3 shared vs first come): dream117er GND/+5V at equal current, 1.08 mm centre gap: 0.8/0.5 mm vs 1.2/0.4 mm; lenaschimmel +3.3V (354 mA) / +5V (3 mA), 1.5 mm gap: 0.5/0.2 vs 0.5/1.2 mm. Physics totals are the same on the 4 boards tried (few contested spots, small currents).
- **Soldering.** Own SMD pads up to 0.6 mm short side (reflow, or process unknown, which is every compiled intent so far) or 1.6 mm (hand soldering) keep grown copper 0.3 mm away. Same-layer pads fed by copper wider than the pad: 0402 class 1/340 before and 2-3/350 after; 0603-1206 class 0/300 -> 41-54/330 (W1-W3); > 1 mm pads 0 -> 12-15.
- **Gate.** When single-culprit attribution fails, changes are now added back batch by batch (ddmin), and the best no-worse board any check saw is kept. Without this, metro-m7 W2/W3/W20 and magtag V3/V20 fell back to the input.

## Verdict

Not finished. Every board's physics total fell and DRC was never worse, but this is ten boards, one routed attempt each, model-measured physics (no lab measurement), and the router never saw the copper. Next: an A/B through the router's final stage (`power_copper=True`) on the 99-board set with cp1/cpk, and a look at the aifryz +BATT term.

## Code

`kae/src/kae/route/power_copper.py` (`PowerCopper.widen`, `ground_vias`, `stitch`, `run`, `hook`; CLI `python -m kae.route.power_copper IN OUT [--operating F]`), tests `kae/tests/test_route_power_copper.py`, bridge option `power_copper`.
