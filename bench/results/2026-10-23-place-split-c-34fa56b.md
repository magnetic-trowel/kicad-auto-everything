# Placement on split C at 34fa56b (closed-loop legality)

Run on sk-tibia, 2026-10-23, KiCad 10.0.7, spec-5 place tasks, `csweep.py --split C --time 600
-j 24 --workers 2`, wall 823 s. Compared with [e171267](2026-10-23-place-split-c-e171267.md) on
the same tasks. Legal means the placer's exact model and kicad-cli DRC on the written board both
pass (a kae verdict, not kaebench's scorer).

| | e171267 | 34fa56b |
|---|---|---|
| legal (tasks with ≥ 1 movable part, outline complete) | 65/72 = 90.3% | **67/72 = 93.1%** |
| wall median / max (s) | 123 / — | 125 / 394 |
| physics, linear sum (70 boards; human 4,392) | 1,417 | 1,447 |
| ours better / human better on physics | 62 / 4 | 63 / 3 |
| protection-order rules broken (252 rules; human 110) | 0 | 0 |
| HPWL new / old, median | — | 1.003 |

Held out: six tasks whose staged footprints carry Edge.Cuts (outline incomplete; 0/6 legal in
both runs) and leomanangka (every footprint locked).

## Flips

- **Illegal → legal (7, all of e171267's failures):** myra-sip-interposer, mitayi-pico-d1,
  sc14cvmdect, goga64-ulk, thetick, beelight, helium.
- **Legal → illegal (5):** all five were "legal" at e171267 only because it never ran KiCad DRC.

| board | KiCad's last verdict | likely cause |
|---|---|---|
| latentred-linecard (614 parts) | solder_mask_bridge 1 | mask apertures of adjacent parts merge; the model does not check mask bridges |
| latentred-pdu | solder_mask_bridge 2 | same; the exact check was clean |
| envopenpico-rp2040 | solder_mask_bridge 10 | same, after an escalation to margin 0 |
| brickpico | copper_edge_clearance 1 | one part's copper against the edge |
| tuxkeychain | clearance 25, shorting_items 7, unchanged by repair | fixed copper in the task input that placed parts land on |

## Caveat

On six legal boards the placer's own grid still lists violators while KiCad finds none
(myra-sip-interposer, sonde-xilinx, sc14cvmdect, goga64-ulk, beelight, helium). Most are parts
without a courtyard, where the grid uses body or pad extents and is stricter than KiCad; this
needs a footprint-by-footprint check before the flips are trusted.
