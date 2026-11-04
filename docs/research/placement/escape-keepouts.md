<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Escape bands: keeping unrelated parts out of BGA and fine-pitch escape strips

**Status:** not finished. The placer side works and is measured; the routing A/B (`escape-ab`, 3 seeds) is queued.
**First published:** 2026-11-01, branch `place-escape-keepouts` (code 0efc1ec, A/B recipe b1bad94).

## Why

About half of the connections our place-and-route runs left open were ones the placement made impossible
(class (c) in [kae-closing-open-connections](../routing/kae-closing-open-connections.md)), typically a
capacitor dropped into the strip a ball grid's or a fine-pitch QFN's escapes need. The placer saw no
difference between that strip and any other free space: RUDY prices a net's box, not the room a package's
pins need to leave it ([kae-routability-estimators](kae-routability-estimators.md)).

## What a band is

`kae.place.escape_band` finds every ball grid (≥ 16 balls on a grid) and every pad ring at ≤ 0.5 mm pitch
(`escape_ring_pitch`), and counts, per side, the signal pads that must escape on the parts' own copper layer:

- **ball grid:** a ball escapes on the surface when its ring is at most the number of tracks that fit
  between two outer balls, the escape planner's own rule (`kae.route.escape.fit`); inner rings go down their
  dog-bones and need no surface room outside the package;
- **pad ring:** every signal pad escapes on the surface;
- ground and power pads go to planes and decaps and count for nothing, so a mostly-power side keeps a
  thin band or none;
- each pad goes to the courtyard edge nearest it, so a connector's single 0.5 mm row escapes away from its
  body (the scan first put half its escapes on the body side).

A side with n escapes gets a band n × (track + clearance) deep, from the board's own default net class
(kae's 0.2 / 0.2 mm only where the board is silent), scaled by `escape_band_scale`, capped at
`escape_band_max_mm` (2.5 mm). Every switch is a `KAE_<NAME>` project text variable or an option
(`kae.route.constraints`). Nothing is written to the board and the router never sees a band.

**Coverage.** Of the 213 merge3-ab merit boards, 67 have such a package (9 with a ball grid); 1 raw board
does not load (smcboard-mono, a parser error before the bands). Most bands hit the 2.5 mm cap.

## What the human placements do with the bands

`tools/research/place/escape_band_cover.py` puts each band on a placed board and lists the parts whose
courtyard overlaps it, as **on-escape** (shares a signal net with the package: series resistors, pull-ups,
ESD, terminations), **decap** (≤ 3 pads, all on the package's ground/power nets, at least one power) or
**other**. The 67 human placements against kae's merit staged placements (`kae-staged-lm-base-resume`,
same boards), full-depth bands:

| sides | | on-escape parts (mm²) | decaps (mm²) | other parts (mm²) | sides with an other part |
|---|---|---|---|---|---|
| 63 ball-grid | human | 102 (346) | 29 (72) | 49 (139) | 18 |
| | kae staged | 67 (274) | 13 (35) | **116 (374)** | 44 |
| 407 pad-ring | human | 400 (767) | 187 (282) | 99 (226) | 57 |
| | kae staged | 312 (897) | 108 (173) | **245 (622)** | 113 |

Two findings, both against a plain keepout:

1. **Humans fill the bands with the package's own parts.** 718 of the 866 parts in human bands are
   on-escape parts or decaps. A band that keeps every part out would push these away: longer stubs on the
   escaping nets and longer decap loops.
2. **kae puts 2.5x as many unrelated parts there as the humans** (361 vs 148; in the ball grids' bands 2.7x
   the area), and fewer of the package's own. The worst boards are the known hard ones: gecko5education
   (163 mm² of unrelated parts), polarfire-som, nekoink, sdi-mipi, arvsom.

(A first pass of this table counted every part sharing any net with the package as related; since nearly
every part shares GND, that hid the unrelated ones. The classes above are the corrected ones.)

## How the placer keeps a band

`escape_band` (default 1):

- **1, soft:** an annealer term on the soft-overlap machinery that silk and routing channels use
  (`kae.place.exact.soft_grid`). Package k's band rectangles are class 2 + k sources; every part on its side
  that is not related to it carries its own body as a class 2 + k target. Related parts sit in the band for
  free; an unrelated one pays `escape_band_w` × overlap / mean part area, as silk does. CP-SAT, the
  legalizer and the exact check do not see it.
- **2, hard:** the package's occupancy grows by the band on its own side (`Problem.set_escape`), so CP-SAT,
  the annealer, the legalizer and the exact check all keep every part out. Legality comes first: the bands
  go before the routing margin when the parts cannot all fit (`pipeline._escalate`), and a locked
  package's bands become fixed obstacles.
- **0:** off.

`escape_fanout=1` (off) also reserves each ball grid's dog-bone via sites on the other side, so no part on
the back covers them; untested.

## Placement smoke

300 s placements (`kae.place.pipeline.place`, no routing) of the three hardest ball-grid boards, two seeds
each; unrelated and own-part area in the full-depth bands, mm² per seed:

| board | human | off | soft w=1 | soft w=4 | hard |
|---|---|---|---|---|---|
| gecko5education, unrelated | 68 | 225, 168 | 87, 138 | 66, 99 | 38, 48 |
| gecko5education, own parts | 206 | 132, 170 | 191, 110 | 203, 98 | 9, 9 |
| nekoink, unrelated | 2 | 52, 63 | 22, 27 | 33, 16 | 9, 16 |
| nekoink, own parts | 119 | 80, 102 | 133, 134 | 96, 131 | 15, 21 |
| sdi-mipi, unrelated | 18 | 43, 48 | 18, 43 | 45, 48 | 0, 0 |
| sdi-mipi, own parts | 63 | 64, 57 | 53, 46 | 55, 56 | 0, 0 |

The soft term roughly halves the unrelated area and keeps the package's own parts as close as the humans
do; a weight of 4 is no better than 1 (within seed noise), so 1 stays the default. The hard band empties
the bands of the package's own parts too. No arm dropped its bands for legality. Placement time: off and
soft w=1 within 3 % of each other, hard up to 10 % and soft w=4 up to 24 % slower (gecko5education). kae suite: 613 passed, 1 failed (the known flaky
`test_router_killed_at_its_deadline_still_yields_a_board`).

## Routing A/B (pending)

`tools/kaeres/experiments/escape-ab.sh`: every arm is merge3-ab's staged arm (merit staged wrapper +
`--screen` + `--final`, 900 s × sqrt(footprints/40), routing from the bare placement of the joint-fixed
task) at the same commit; only `--set escape_band=` differs. Experiment `escape-ab`: off vs soft on the 67
boards, 3 seeds; `escape-ab-hard`: hard on the 9 ball-grid boards, 3 seeds. Harness e87baed, numba cache
warmed for the commit. Metrics: open connections and completion per board and seed, DRC errors beyond the
input's, cp1, and the same-router delta against the bridge on the human placement (merge3-ab).

## Not done

- Partial fanout as frozen copper (dog-bones and edge stubs laid before placement, decaps placed into the
  via gaps on the other side): only the via-site reservation exists (`escape_fanout`). Laying the full
  escape plan before routing made things worse (gecko5 54 → 241 open), so stubs would stay placement-only
  obstacles.
- The joint loop's re-anneal windows do not build the band term.
- Pulling the package's own series parts closer: kae places fewer of them in the band than humans do
  (379 on-escape parts vs the humans' 502); a separate term.
