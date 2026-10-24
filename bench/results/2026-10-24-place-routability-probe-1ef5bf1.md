# Placement routability probe, splits A+B at 1ef5bf1

Run on sk-tibia, 2026-10-24, KiCad 10.0.7. Each placement is routed by the same router, kae's
bridge as the kaebench probe (Freerouting fork, 1800 s, heap 2 GB), and scored by kaebench.
33 boards, k = 2. Place tasks freshly prepared at task spec 6.

| placement | legal | probe cp1 | probe cpk | completion mean / min | probe DRC errors |
|---|---|---|---|---|---|
| kae place (physics) | 64/66 | 0.758 | **0.788** | 0.970 / 0.600 | silk_overlap 44, silk_over_copper 5, copper_edge_clearance 2, clearance 1 |
| kae place --no-physics | 65/66 | 0.758 | **0.788** | 0.974 / 0.679 | silk_overlap 44, silk_over_copper 4, copper_edge_clearance 1 |
| human | 66/66 | 0.727 | **0.788** | 0.984 / 0.818 | none |

The physics terms cost no routability on A+B (see the [physics ablation](2026-10-24-place-physics-ablation-1ef5bf1.md)
for what they buy). HPWL relative to human: 0.685 with physics, 0.657 without.

- **Silkscreen** is the systematic loss: the placer does not model silk, and ecc83-pp-v2 routes
  fully on both kae arms but fails on silk alone.
- **paw3222** is illegal on both physics attempts (copper_edge_clearance 1; fixed after this commit
  in 644b268: the edge error was blamed on the wrong part).
- **paw3395** routes worst on ours (9 and 6 unconnected vs 1 and 1 on human); siderakb-pmw3610 5/2
  vs 1/1. oasis-ledboard, xor-2in and tuxkeychain-expansion are clean on ours and not on human.
- **Not scored:** on noisecard both kae placements move D1–D10 away from their printed dB labels
  and SW1 away from its ON/OFF text; the human places each beside its label.

## Follow-up: silkscreen and labels (WIP snapshots up to d8c09e6)

Silk is now checked where the project makes it an error (5 tasks), using KiCad's own glyph
outlines from pcbnew (human placements: 0 conflicts on all five). A final pass moves the smaller
part of each conflict within +3% physics and +10% HPWL. KiCad silk errors on those 5 boards,
local, 600 s: 224 → 71 (ecc83 49 → 3, video 64 → 6, pic-programmer 32 → 7, sonde-xilinx 12 → 1,
complex-hierarchy 67 → 54, where the HPWL cap binds); all legal, KiCad clean. Reference text
cannot be moved: the scorer accepts only footprint poses.

Board-level labels: 91 of 112 tasks carry board silk text. An association inferred from the
task alone (connector-pin labels, numbered rows matched in order to one part family, keywords)
puts the human placement's part within 3 mm on 58–86% of the 354 single-part labels. As an
annealer term (`w_label`, off by default) it brings noisecard's 12 labelled parts from 0 to 8
within 3 mm at weight 3, physics 2.38 → 2.76 (human 3.50), HPWL 170 → 258.
