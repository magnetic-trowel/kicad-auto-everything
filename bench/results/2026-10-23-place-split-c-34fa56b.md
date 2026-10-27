# Placement on split C at 34fa56b (closed-loop legality)

Run on the shared benchmark host, 2026-10-23, KiCad 10.0.7, spec-5 place tasks, `csweep.py --split C --time 600
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

## Follow-up (2026-10-24, in ea517f9)

The dcecf28 sweep held at 67/72 but traded its five fixes for four exact-checker false
positives (net-less fiducials and mounting holes over a GND pour, which KiCad passes) and one
real stickhub mask bridge. The mask and edge rules now follow KiCad 10.0's
`drc_test_provider_solder_mask.cpp` and `pad.cpp`, and `tools/research/place/humangate.py`
gates the exact model: on every task, the human placement may produce no finding type that
KiCad's DRC on the reference board does not. It passes 13/13 (A), 20/20 (B) and 79/79 (C).
Locally, all 4 false-positive boards, stickhub and the 12-board regression set are legal with
KiCad clean in round 0; pic-programmer's physics regression (47.3, from false-positive
repairs) is back to 25.0 (human 46.8).

## Split C at fe68468 (the shared benchmark host, 2026-10-24)

Human gate 13/13 (A), 20/20 (B), 79/79 (C). Split C **72/72 legal** (from 67/72 at dcecf28),
every counted board KiCad-verified, no legal → illegal flips; the five flips are the four
false-positive boards and stickhub. Physics ours 1,420 vs human 4,392 (−2.5% vs dcecf28), ours
better on 64 boards, human on 2; pic-programmer 25.3 (human 46.8). Wall median 124 s, max 354 s.
One regression: stickhub breaks 4 protection-order rules (the summary's "4/7" column is ours /
human: the human placement breaks 7 of its 24), and its physics went from 22.2 to 33.4. Cause:
the final repair, clearing the mask bridge, moved J6, C17 and D15 across their chain without
checking order. Fixed by the repair's order guard (a move or eviction may not raise a part's
broken-rule count; in 1ef5bf1): 0 broken on seeds 0, 1 and 2, physics 24.5–29.0 (human 47.1).
