<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Zone-aware placement: fixed copper zones as placement facts

Scope: defensive publication of the placer's fixed-zone terms (pull of power pads onto their own net's fixed zones, keep-out of other nets' pads from zones and board mask openings they would bridge): mechanism, A/Bs, verdict. Not here: the board study that proposed it -> [board studies](../joint/board-studies-2611.md); why reused runs mislead -> [host-load drift](../benchmark-drift-2611.md).
Keys: zone-aware placement, kae.place.zones, zone_pull, zone_keepout, fixed zones, pads on own zone, solder_mask_bridge, board mask aperture, fixed_mask, zone-ab, zone-keepout-ab2, place-fixed, joint-fixed

**Status:** partial. The keep-out works and stays on: it removes the solder-mask bridges it targets
(polarfire-som 247 → 38, gecko5 22 → 0 over 3 seeds) with routing unchanged. The pull does what it
says (about twice as many power pads on their own zone) but does not change open connections, so it is
off by default (`zone_pull=0`) and stays as an option.
**First published:** 2026-11-08, branch `place-zone-aware` (term [4e4a7ed](https://github.com/magnetic-trowel/kicad-auto-everything/commit/4e4a7ed15a6735a0f365a5d8539028fde62d920e),
apertures and defaults [e54a590](https://github.com/magnetic-trowel/kicad-auto-everything/commit/e54a590d812e9ed4fb887b58d250c31c47d1c2bc),
recipes [0ed5d35](https://github.com/magnetic-trowel/kicad-auto-everything/commit/0ed5d350920d10a601d233bd49809fa3ca818966)).

## Why

In the place-fixed and joint-fixed tasks the human's copper zones stay where they were while every part
moves, and the placer ignored them. The [board study](../joint/board-studies-2611.md) counted power pads
over their own net's fixed zone: polarfire-som human 404 of 469, kae staged 148–221; gecko5's FPGA left its
+1V2 island; every staged DRC error on gecko5 was a solder-mask bridge between a moved pad and a fixed
outer-layer power island. It estimated +60 to +200 open connections a board from this.

## Mechanism

Two unary annealer terms (`kae.place.zones`), priced on a raster of the zones at ~0.1 mm, read by both
the reference and the compiled annealer:

- **Pull** (`zone_pull`): each pad of a movable part whose net owns a fixed zone on a layer the pad
  reaches (SMD: its own outer layer and inner layers through a via; drilled: all) costs its weight when
  its centre is off that net's fill region, half the weight plus half scaled by the distance, so the
  annealer sees the way. Weights: ground/power 1, signal 0.5, divided by √(the net's eligible pads),
  normalised so all pads off cost `zone_pull` × the seed's wirelength. Nets whose region covers ≥ 90 %
  of the board are solid planes and left out. The seed also anchors such parts toward their zones, and
  packages with ≥ 8 weighted pads on zones are pinned there.
- **Keep-out** (`zone_keepout`): a pad of another net with copper and a mask opening on an outer layer
  costs 0.1 × `zone_keepout` × the share of its 5 sample points (centre, corners) within reach of a fixed
  zone it would bridge. Reach is KiCad's test: `solder_mask_to_copper + the pad's mask expansion` beyond
  the gap the fill keeps.
- **Board mask apertures** (since e54a590): F/B.Mask graphics drawn at board level are in the keep-out
  too. A pad of a net the opening does not already expose (through a fixed zone) costs as above. They
  are not grid obstacles: one net's pads under an opening are legal.

## Results

### zone-ab: pull 3 and keep-out 1 against the base placer

48 merit boards with ≥ 10 movable pads on fixed zones, kae staged with the restart wrapper, 3 seeds.
The base runs on 5 of the boards were reused from an earlier experiment (bga-next-ab), made days apart;
on this host that alone moves results by ~14 % ([drift](../benchmark-drift-2611.md)), so they are
reported apart:

| boards | pairs | open, base → zone | runs fewer / more | sign test p |
|---|---|---|---|---|
| 42, arms run side by side | 122 | 6,841 → 6,627 (−3.1 %) | 30 / 29 | 1.0 |
| 5, base runs reused from days earlier (polarfire-som, sdi-mipi, …) | 15 | 2,439 → 2,680 (+9.9 %) | 1 / 9 | 0.02 |

The first analysis pooled them (+4.7 %) and blamed the pull for the study boards getting worse; that was
the reuse. On the side-by-side boards the pull is neutral.

Pads over their own net's fixed zone (`zones.report`), human / base / zone, 3 seeds:

| board | human | base | zone |
|---|---|---|---|
| polarfire-som | 387 of 465 | 162–197 | 353 |
| sdi-mipi | 264 of 319 | 100–112 | 183–198 |
| nekoink | 196 of 235 | 50–87 | 107–122 |
| gecko5 | 65 of 80 | 4–6 | 54–57 |

### Why the pull cannot pay: open connections are on signal nets

Open connections of the base runs split by net (pcbnew connectivity, matching KiCad's count): nets that
own a fixed zone account for 11–51 of 168–545 per run (polarfire 35–51 of 525–545, sdi-mipi 11–32 of
168–183, nekoink 34–50 of 175–186, gecko5 12–21 of 181–286). The router reaches planes through vias from
wherever the pads are; what stays open is signal nets (gecko5's LED matrix, the FPGAs' ball fields). The
zone runs did not reduce the zone-net share either. The study's premise, pads off their zone ≈ open
connections, was wrong; a pull's upside is bounded by those 11–51.

### The aperture bug

One zone-ab run on polarfire-som was kept with 199 solder_mask_bridge errors: two of the board's four
5.4 mm filled F.Mask circles (mounting-point openings) had parts with many nets under them (U15, U28,
U23). The placer's exact check flagged 17 parts, but only after annealing; the grid deliberately leaves
board apertures out, so the annealer moved parts in and the closing repair ran out of time. Base runs
had 1–7 such bridges. Fixed by pricing apertures in the keep-out (above); test
`test_keepout_prices_pads_in_a_board_mask_aperture`.

### zone-keepout-ab2: keep-out only (with apertures), both arms fresh

The same 48 boards × 3 seeds, the base (7221e4a) and keep-out (0ed5d35, `zone_pull=0`) registered again
as replicates so that both arms of a board ran in the same job:

| | base | keep-out |
|---|---|---|
| open connections (141 pairs, 47 boards) | 11,103 | 11,147 (+0.4 %; runs 38 fewer / 36 more, p = 0.91) |
| boards better / worse / within 2 % | | 12 / 11 / 24 |
| errors per run | 28.6 | 27.0 |
| solder_mask_bridge, all runs | 1,787 | 1,573 |
| polarfire-som / gecko5 bridges | 247 / 22 | 38 / 0 |
| clean runs | 22 | 22 |

The remaining bridges (arvsom 468, edison 435, …) are equal in both arms: they come from parts held
fixed in these tasks, not from placement.

## What did not work

- The pull, as a routing lever: neutral at `zone_pull=3` on 42 side-by-side boards.
- The first keep-out-only run (`zone-keepout-ab`, cancelled) compared against zone-ab's base runs made
  days earlier and read +14 % worse; on boards where the keep-out builds no term at all (aifryz, kestrel,
  undercontrol) the same code was worse too. The fresh replicate showed it was the host, not the code.

## Settings

`zone_pull` (default 0; 3 was tested), `zone_keepout` (default 1), both via `--set` or KAE_ text variables
([router limits](../routing/README.md)). Recipes: `tools/kaeres/experiments/zone-ab.sh`,
`zone-keepout-ab.sh` on `place-zone-aware`.
