<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Escape bands: keeping unrelated parts out of BGA and fine-pitch escape strips

**Status:** did not work. The bands do what they say (soft halves unrelated parts in the strips), but on the routing A/B (63 merit boards × 3 seeds) they leave open connections unchanged, and hard is worse on ball grids. `escape_band` is off by default since this result; both modes stay as options.
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

## Routing A/B

`tools/kaeres/experiments/escape-ab.sh`: every arm is merge3-ab's staged arm (merit staged wrapper +
`--screen` + `--final`, 900 s × sqrt(footprints/40), routing from the bare placement of the joint-fixed
task) at the same commit (21bc53d, after the code audit); only `--set escape_band=` differs. Experiments
`escape-ab3` (off vs soft, 65 boards, 3 seeds) and `escape-ab3-hard` (hard, the 10 ball-grid boards, 3
seeds). Earlier runs `escape-ab`, `escape-ab2` are void (the methods ran the restart wrapper from a harness
without `--resume`; then pre-audit code). Open connections are pcbnew's count past KiCad's 499 cap. Pairs
are (board, seed); a run the queue froze for memory counts unless it also hit its deadline (none did).

| comparison | pairs | open connections | per board (3-seed means) | errors / run |
|---|---|---|---|---|
| off vs soft, all boards | 188 | 12,096 → 13,099 (+8.3 %); pairs 57 fewer, 57 more, 74 equal | 22 better, 19 worse, median ±0 % | 39.5 → 38.2 |
| off vs soft, pad rings only | 158 | 6,422 → 6,327 (−1.5 %), sign test p = 0.76 | 19 better, 15 worse | 37.1 → 36.1 |
| off vs soft, ball grids | 30 | 5,674 → 6,772 (+19 %), polarfire-som most | 3 better, 4 worse, median +0.8 % | 52.2 → 49.7 |
| off vs hard, ball grids | 30 | 5,674 → 6,286 (+11 %) | 3 better, 3 worse | 52.2 → 55.5 |

Why, from four board studies (polarfire-som, nekoink, sdi-mipi, gecko5education):

- The strips are not what limits these boards. Re-routing the off and hard placements of polarfire for
  1,500 s each left 647 vs 646 open. Hard emptied sdi-mipi's strips in two seeds and still left 178 and
  208 open; gecko5's hard arm clears the BGA's ring (3 parts within 3 mm vs 32) with no change in opens.
- What does limit them: the router on deep ball-grid rings (75-80 % of sdi-mipi's opens, also on the human
  placement), fixed copper zones the placer ignored (power pads off their planes: polarfire 148-221 of 469
  vs the human's 404), scattered arrays (gecko5's 120-LED matrix: ~165 opens), and Freerouting's time on
  big boards. Those are what the next experiments target (zone-aware placement, `zone-ab`).
- Hard bands do not fit dense boards: at 76 % courtyard utilisation the legaliser moves parts 1,713 mm
  (off: 717 mm) and the placer then drops the bands, keeping the worse spread.
- The restart wrapper read KiCad's capped DRC list (499) as the open count, so on the big boards its
  choices between attempts were blind in both arms; fixed since (7221e4a), after these runs.

### The ball-grid router changes (`bga-next-ab`)

Branch `route-bga-next` (c5f328a): the BGA window repair from `close-bga-region` merged, one shared
small-ball-grid test (3 × 3 sites and up) for router and placer, and escape rings counted from the nearest
open side, an empty channel inside the grid included (nekoink U202). Against its base (7221e4a), kae staged,
the 10 ball-grid boards × 3 seeds: 26 pairs, open 5,270 → 5,526 (+4.9 %), pairs 9 fewer and 10 more,
per board 2 better and 4 worse; errors 51.5 → 49.6 per run. No gain. On a big board the window repair
rarely runs at all: it needs 120 s after the repair rounds, which on nekoink run to the last mile's
90 s reserve (Freerouting took 694 of 1,200 s).

## Not done

- Partial fanout as frozen copper (dog-bones and edge stubs laid before placement, decaps placed into the
  via gaps on the other side): only the via-site reservation exists (`escape_fanout`). Laying the full
  escape plan before routing made things worse (gecko5 54 → 241 open), so stubs would stay placement-only
  obstacles.
- The joint loop's re-anneal windows do not build the band term.
- Pulling the package's own series parts closer: kae places fewer of them in the band than humans do
  (379 on-escape parts vs the humans' 502); a separate term.
