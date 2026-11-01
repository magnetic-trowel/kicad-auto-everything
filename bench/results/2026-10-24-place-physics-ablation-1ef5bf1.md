# Placement physics ablation, split C at 1ef5bf1

Run on the shared benchmark host, 2026-10-24, KiCad 10.0.7, spec-5 place tasks, `csweep.py --split C --time 600
-j 18 --workers 2`, seed 0, the same code with and without `--no-physics` (routability and
legality only). Legal means kae's exact model and kicad-cli DRC both pass. Tasks with no movable
part and the six outline-incomplete tasks are held out.

| | physics off | physics on | human placement |
|---|---|---|---|
| legal | 72/72 | 72/72 | — |
| physics, linear sum of budget utilization (71 boards) | 35,380 | **1,410** | 4,392 |
| boards better than human | 11 | 62 | — |
| structures over budget | 1,594 | 463 | 869 |
| protection-order rules broken (252) | not evaluated | 0 | 110 |
| wall median / max (s) | 109 / 275 | 125 / 350 | — |

The physics terms cost no legality and improve physics on 70 of 71 boards; the tie is xerxes,
with 2 movable parts.

Utilization summed per structure kind, off → on: decap 3,907 → 573 (878 structures), ESD
693 → 224 (255), coupling 517 → 14 (114), commutation 464 → 153 (61), antenna 96 → 69 (25),
power path 80 → 15 (21), crystal 72 → 19 (29), thermal 58 → 38 (127).

Largest gains on a decisive structure: pingdevkit half-bridge U1502 17.7 → 2.3 nH; emberone
decap U27 3V3 148.7 → 3.7 nH; kintex-pcie decap U1 +1V0 100.7 → 2.5 nH; video decap BUS1 +3.3V
345.8 → 2.0 nH; fanpico ESD chain J5 123.5 → 5.0 nH; battery-stm32 analog victim 214.5 → 0.0 mV.

Routability is not measured here: the joint runs (place, then route) are the test that the
physics does not cost routing.
