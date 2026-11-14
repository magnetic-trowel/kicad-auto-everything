<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Differential pairs: detection, hazard, report column (E36, 2026-11)

Scope: how kae decides which nets form a pair, whether the pair matters, and the hazard when it was not routed as one. Report and hazard only; nothing here reaches a score. The copper itself is measured by the bus scorecard -> [bus yardstick](bus-yardstick-2611.md). Not here: routing pairs as pairs -> [`kae.route.pair_route`](../../../kae/src/kae/route/pair_route.py); pair physics and rules -> [diff-pairs](../../topics/rules/diff-pairs.md); router survey -> [diff-pair-routing](../../topics/routing/diff-pair-routing.md).
Keys: pair_uncoupled, pair_skew, kae.route.pairs, tier rule, tier interface, pair tier, no_ref_mm, ref_changes, E36, E35

**Status:** built, report-only. **First published:** 2026-11-09, branch `diffpair-report`; rebased on the bus scorecard (2026-11-11) so pairs are measured in one place.

## What a pair is, and when it matters

`kae.route.pairs.detect` starts from KiCad's own suffix rule (`DRC_ENGINE::MatchDpSuffix`, via `kae.route.rules.complement_net`; the board's `diff_pair_gap` rules key on the same match) and adds pairs from the brief's name and class matching. Each pair gets a tier:

| Tier | Evidence | Human pairs coupled >= 50 % |
|---|---|---|
| rule | a `.kicad_dru` rule or a net class asks for it (diff-pair width or gap, class named for pairs, `skew`) | 0.96 |
| interface | a high-speed serial interface from the brief or the class name | 0.95 |
| name | only complementary names | 0.90; pads <= 1.5 mm apart 0.93, farther 0.61 |

Measured on the human layouts of 659 boards with E35's measure (all copper of each leg, partner within 0.5 mm edge to edge; `stage1/geometry/scripts/geom.py`), before the bus scorecard existed (the union of `diffpair_nets`, `diffpair_rules`, `if_usb2`, `if_usb3`, `if_hdmi.tmds_pairs`, `if_mipi`, `if_pcie`, `if_ethernet`, `if_lvds`, n100 sets, 12,746 pairs with both legs routed and at least 3 mm each). Human coupling is the reference: a real pair is one the designer ran together. Numbers per interface: usb2 0.93, usb3 0.98, hdmi 0.91, pcie 0.97, ethernet_mdi 0.93, mipi 0.97, lvds 0.96, serdes 0.96, CAN 0.63, analog 0.80.

The earlier "merit name-matched pairs: human skew 1.0 mm, coupled 0.08" (`stage1/geometry`, E35) is a selection effect, not a detection failure: it covers the 78 of 325 merit name pairs that every arm routed completely, a sample that favours nets easy to route and low in interest (speaker outputs `SPKn+`/`SPKn-`, small analog nets). On all 325 human pairs, the same measurement gives median coupled 0.945 (76 % at or above 0.5); my implementation reproduces E35's numbers exactly on the same pairs (correlation 1.0). Hazards and pair routing act on tiers rule and interface; name-only pairs (the ones that include speaker and analog nets) stay out, even though most pairs whose pads sit together do get coupled by designers.

## What the copper shows

One measure, the bus scorecard's pair rows (`kae.bus.scorecard`, [bus yardstick](bus-yardstick-2611.md)): pad-to-pad skew, coupled share within 3 trace widths (`coupled_3w`), vias per leg, the interface's skew limit (`kae.bus.limits`; USB2 1.27 mm and Ethernet MDI 1.27 mm added here, from the [interface packs](../../topics/rules/interfaces/common.md)). `kae.route.pairs` adds to each row its tier (`tier_of`) and where it runs against its reference plane: `no_ref_mm`, length with no zone on an adjacent copper layer, and `ref_changes`, how often the plane's net changes under it (zone outlines, not fills). A row is measured only when both legs have a pad-to-pad path between two common end parts; other pairs get no hazard.

## Hazards

`pair_uncoupled` (warn): pairs of tier rule or interface, measured, at least 3 mm a leg, with `coupled_3w` below 0.5. `pair_skew` (info): skew above the interface's limit in `kae.bus.limits`. Info, not a warning: those limits are vendor tables (TI's 5 mil for USB3, PCIe, SATA) that many working boards exceed. Fifty boards from `if_usb2` and `if_diffpairs` (one Freerouting output missing): `pair_uncoupled` on 13 of 49 Freerouting outputs and 5 of 50 human layouts; `pair_skew` on 11 and 22. Freerouting's count is low partly because its pairs are often open and so not measured. Before the rebase, with E35's all-copper measure, the same boards gave `pair_uncoupled` on 33 and 14. DRC and the score see neither.

## Report column

The bus scorecard is the report column: `kaeres bus submit|report` (`tools/kaeres/busreport.py`) over an experiment's runs, appended to `kaeres exp report`. Its pair rows now carry `tier`, `no_ref_mm` and `ref_changes`.
