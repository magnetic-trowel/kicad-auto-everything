<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Differential pairs: detection, hazard, report column (E36, 2026-11)

Scope: how kae decides which nets form a pair, whether the pair matters, and what the routed copper shows. Report and hazard only; nothing here reaches a score. Not here: routing pairs as pairs -> [`kae.route.pair_route`](../../../kae/src/kae/route/pair_route.py); pair physics and rules -> [diff-pairs](../../topics/rules/diff-pairs.md); router survey -> [diff-pair-routing](../../topics/routing/diff-pair-routing.md).
Keys: pair_uncoupled, pair_skew, kae.route.pairs, tier rule, tier interface, coupled share, pair_report, E36, E35

**Status:** built, report-only. **First published:** 2026-11-09, branch `diffpair-report`.

## What a pair is, and when it matters

`kae.route.pairs.detect` starts from KiCad's own suffix rule (`DRC_ENGINE::MatchDpSuffix`, via `kae.route.rules.complement_net`; the board's `diff_pair_gap` rules key on the same match) and adds pairs from the brief's name and class matching. Each pair gets a tier:

| Tier | Evidence | Human pairs coupled >= 50 % |
|---|---|---|
| rule | a `.kicad_dru` rule or a net class asks for it (diff-pair width or gap, class named for pairs, `skew`) | 0.96 |
| interface | a high-speed serial interface from the brief or the class name | 0.95 |
| name | only complementary names | 0.90; pads <= 1.5 mm apart 0.93, farther 0.61 |

Measured on the human layouts of 659 boards (the union of `diffpair_nets`, `diffpair_rules`, `if_usb2`, `if_usb3`, `if_hdmi.tmds_pairs`, `if_mipi`, `if_pcie`, `if_ethernet`, `if_lvds`, n100 sets, 12,746 pairs with both legs routed and at least 3 mm each). Human coupling is the reference: a real pair is one the designer ran together. Numbers per interface: usb2 0.93, usb3 0.98, hdmi 0.91, pcie 0.97, ethernet_mdi 0.93, mipi 0.97, lvds 0.96, serdes 0.96, CAN 0.63, analog 0.80.

The earlier "merit name-matched pairs: human skew 1.0 mm, coupled 0.08" (`stage1/geometry`, E35) is a selection effect, not a detection failure: it covers the 78 of 325 merit name pairs that every arm routed completely, a sample that favours nets easy to route and low in interest (speaker outputs `SPKn+`/`SPKn-`, small analog nets). On all 325 human pairs, the same measurement gives median coupled 0.945 (76 % at or above 0.5); my implementation reproduces E35's numbers exactly on the same pairs (correlation 1.0). Hazards and pair routing act on tiers rule and interface; name-only pairs (the ones that include speaker and analog nets) stay out, even though most pairs whose pads sit together do get coupled by designers.

## What the copper shows (`kae.route.pairs.measure`)

Per pair: skew (difference of the two legs' total copper length), coupled share (share of the legs' length within 0.5 mm edge to edge of the other leg on the same layer, E35's definition), vias on each leg, layers used, length with no plane on an adjacent layer, and how often the plane under the pair changes net.

## Hazards

`pair_uncoupled` (warn): pairs of tier rule or interface, both legs routed, at least 3 mm per leg, with coupled share below 0.5. `pair_skew` (warn): skew above the loosest published limit for the interface (`pairs.SKEW_LIMIT_MM`, sources in [interfaces](../../topics/rules/interfaces/common.md)). Fifty boards from `if_usb2` and `if_diffpairs` (one Freerouting output missing): `pair_uncoupled` on 33 of 49 Freerouting outputs and 14 of 50 human layouts; `pair_skew` on 17 and 8. DRC and the score see neither.

## Report column

`tools/kaeres/pair_report.py NAME` measures every method's attempt-0 output and the human board, writes `experiments/NAME/pairs.csv` and `PAIRS.md`; `kaeres exp report` appends `PAIRS.md` to the report. Boards whose human layout has no pair of tier rule or interface contribute nothing.
