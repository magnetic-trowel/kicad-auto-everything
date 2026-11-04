<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# kae taut arcs: every connection pulled to its shortest path in its own topology, with true arcs

**Status:** partial (RESULTS_STATUS).
**First published:** 2026-11-04, branch `arc-taut` (off `pad-edge-entry`).

## Design note (written before the code)

### What the repo's docs say, and what that fixes in the design

| Doc | What it says | What it fixes here |
|---|---|---|
| [topological-routing](../../topics/routing/topological-routing.md) | Routers pick a homotopy class, then realize a rubber band (SURF, TopoR); for a fixed topology octilinear is ~5 % longer than any-angle | Keep the router's topology and realize it optimally; expect single-digit gains |
| [rule-genealogy-routing-style-dfm](../../topics/physics/rule-genealogy-routing-style-dfm.md) R01-R04, R35 | Corners and 45° are physics-neutral below ~10 GHz; any-angle ≤ 8 % shorter; acid traps are fab legacy; "keep 45° for editability"; round inside corners of pulsed power copper | **Conflict with the brief.** The doc keeps 45° for editability (a cognition cost, not physics or fab); the brief asks for arcs, so arcs stand as a style choice. R35 asks for arcs on power copper |
| [myths-and-contested](../../topics/rules/myths-and-contested.md) | Corners matter for ESD, RF (arcs or 135°), diff pairs, ≥ 10 Gb/s | Arcs are neutral or better everywhere |
| [diff-pairs](../../topics/rules/diff-pairs.md) | Rounded corners do not remove skew; outer leg +1.57 p per corner; uncoupled ≤ 1.14 mm | Tighten a pair only as a pair (legs offset from one centreline, end headings kept, so skew = D × net turning is unchanged), else leave it |
| [length-matching-and-buses](../../topics/routing/length-matching-and-buses.md) | Length is tuned after routing; meanders are explicit rules | Length/skew-ruled and meandered nets are never shortened |
| [si-fundamentals](../../topics/rules/si-fundamentals.md) | K = 1/(1+(D/h)²); spacing in units of h, never "3W" | Victims keep min(power copper's `victim_gap`, the input's distance) |
| [kae-power-copper](kae-power-copper.md) | Brief classes, extra gaps, sharing, necks; "rails may not cut ground pours"; gate with attribution and ddmin | Same classes (imported); other nets' fills stay obstacles; widening along arcs reuses the sampling, runs and necks |
| [kae-pad-edge-entry](kae-pad-edge-entry.md) | Entry ≤ 10° off the normal for a width outside the pad, overlap inside; rails keep centre ends (cutting them raised rail drop 0.1-1.3 %); acute entries come from 45° runs into pad corners | Pad ends are fixed tails along the normal; rails keep their centre and run out through the edge middle |
| [power-copper (physics)](../../topics/physics/power-copper.md) | "Width trades one parasitic for another; only length lowers all of them" | Length is the objective; switch nodes keep victim gaps |
| [hv-and-manufacturing-physics](../../topics/physics/hv-and-manufacturing-physics.md), [rf-geometry](../../topics/physics/rf-geometry.md) | Curves cost nothing at a modern fab; arcs are cosmetic for SI below ~30 ps edges | No fab or SI exception needed |
| [research-gaps](../../topics/physics/research-gaps.md) #15, [autorouter-skepticism](../../topics/routing/autorouter-skepticism.md) | Arcs must survive review; practitioners count bends and acute angles | Report corners and acute angles; write true KiCad arcs ([TM48](../../ideas/physics-first/thermal-hv-mfg.md)) |
| [open-source-routers](../../topics/landscape/open-source-routers.md) | route-rnd's rubber-band sketch "leaves unnecessary curves" | Wraps that would sweep backwards are dropped |
| [physics-in-the-loop-optimization](../../topics/physics/physics-in-the-loop-optimization.md), [kae-routing-dead-ends](kae-routing-dead-ends.md) | Elastic bands relax a fixed-homotopy path; exact local joins pay, rip-ups do not | Solve the tension-only limit exactly; never rip up a neighbour |

### Outside literature built on

- **Shortest paths in a homotopy class.** Hershberger & Snoeyink, "Computing minimum length paths of a given homotopy class", CGTA 4(2):63-97, 1994 ([DOI](https://doi.org/10.1016/0925-7721(94)90010-8)): reduce the path to its sleeve of triangles in the universal cover and run the funnel. Funnel: Lee & Preparata, "Euclidean shortest paths in the presence of rectilinear barriers", Networks 14:393-410, 1984; Chazelle, FOCS 1982. Efrat, Kobourov & Lubiw, "Computing homotopic shortest paths efficiently", CGTA 35(3), 2006; Bespamyatnikh, J. Algorithms 49, 2003.
- **Curved obstacles: tangents and arcs.** Chen & Wang, "Computing shortest paths among curved obstacles in the plane", ACM TALG 11(4), 2015 ([arXiv 1103.3911](https://arxiv.org/abs/1103.3911)): a shortest path is free common tangents plus boundary arcs on convex pieces. Hershberger, Suri & Yıldız, SoCG 2013. Liu & Arimoto, tangent graphs, IJRR 11(4), 1992. Discs: Chang, Choi, Kwon, Park & Yap, "Shortest path amidst disc obstacles is computable", IJCGA 16, 2006 ([pdf](https://cs.nyu.edu/exact/doc/computable.pdf)).
- **Funnel with clearance (discs at vertices).** Kallmann, "Shortest paths with arbitrary clearance from navigation meshes", SCA 2010 ([DOI](https://doi.org/10.2312/SCA/SCA10/159-168)); Demyen & Buro, "Efficient triangulation-based pathfinding", AAAI 2006.
- **Rubber-band routing.** Dai, Dayan & Staepelaere, "Topological routing in SURF: generating a rubber-band sketch", DAC 1991 ([DOI](https://doi.org/10.1145/127601.127622)); Staepelaere's thesis (UCSC-CRL-92-39); Dayan's 1997 thesis; route-rnd/libgrbs; TopoR (arcs, "arcs give ~30% larger minimum gaps than 45°", vendor); US 6,226,560 (optimizing a physical wire's path from a topological wire).
- **Any-angle search** for contrast: Theta* (Nash et al., AAAI 2007) and Anya (Harabor et al., JAIR 2016) find any-angle shortest paths on grids; here the path already exists and only its geometry is solved.
- **Configuration space.** Lozano-Pérez & Wesley, CACM 1979: grow every obstacle by the moving body (the Minkowski sum with a disc of radius gap + w/2) and move a point. Offsets with round joins: Wein, "Exact and approximate construction of offset polygons", CAD 39(6), 2007.

### The design

1. **Configuration space.** For a branch of net n, width w, layer L: each foreign item grown by r_item + need + w/2, with need = `Space.need` (the bridge's KiCad rules: net classes, custom DRC rules, pad classes, keepouts), raised for victim pairs to min(victim_gap, the input's distance). Other nets' fills as KiCad refilled them are obstacles. The board edge is shrunk by edge clearance + w/2.
2. **Topology.** Triangulate the free space in a window around the branch (constrained Delaunay, GEOS), trace the branch through it, cancel back-and-forth crossings (the universal-cover sleeve of Hershberger-Snoeyink) and run the funnel. This gives the homotopic shortest path among the polygonised obstacles and the side of every obstacle it touches.
3. **Exact geometry.** Each funnel apex lies on an atom: a disc (a via, a round pad, a track end, a pad or fill corner, each grown). The atoms in order, with their turn sides, define a path of common tangents and arcs (outer tangents between same-side wraps, inner ones between opposite sides). A wrap whose arc would sweep backwards is dropped. Any piece that the exact check finds too close adds the offending atom and the path is solved again.
4. **Certificate.** A G1 path whose arcs all wrap their atom on the inside of the turn, and whose pieces are all legal, is locally shortest. In a simply connected domain (the universal cover) a locally shortest path is the shortest one, so the result is optimal for its class. The only gap is the polygonised pad and fill outlines (KiCad's own, at most its max error outside the true shape).
5. **Fixed points.** Pads (at a tail one width outside the edge, along the normal), vias, T-joins and branch points, width changes, locked tracks, diff pairs that cannot be tightened as a pair, length-ruled and meandered nets.
6. **Order.** route → pad entry → taut → power copper (arc-aware widening) → DRC gate. Taut first because widening fills the room that tightening frees, and widened copper cannot move.
7. **Passes.** Shortest branches last; iterate until no net shortens by more than ε, logging the decrease per pass.
8. **Gate.** Each piece is checked exactly (arcs sampled with chord error ≤ 0.5 µm, which is added to the requirement). Then whole-board KiCad DRC must be no worse, with the power-copper gate's stepwise revert per branch.

## How it works (as built)

- **Branches** (`taut.Taut.chains`). Per net and layer, the tracks between fixed points: pads, vias, ends shared by three or more tracks, width changes. Straight tracks are first cut at the T-joins on their interior (`_split_tees`) and written back whole while unchanged. Skipped: locked tracks (kae's repair loop locks its joins), nets of a diff pair (KiCad naming or the brief), nets with a `length` or `skew` rule, tuning patterns.
- **Pad tails** (`Taut.tails`). A perpendicular entry (within 10°, one width outside the edge) is kept, a signal's end cut to `pad_entry_overlap` inside the edge. Otherwise each of `pad_entry.approach_targets` is a candidate tail, plus the input's own direction as a fallback; tails are checked exactly. Rails keep their end where it is on the normal through the edge middle. Ball grids and pads with a via in them keep their tails. Every head × tail pair is solved; perpendicular at both ends wins, then fewer acute corners, then length. Where the path leaves an anchor at more than 90°, it starts on an arc tangent to the tail, radius 2w, w or w/2 (`_fillet_anchors`): a Dubins-type start, so no acute corner is made.
- **Requirements** (`Taut.obstacles`). These are the bridge's own `Space.need` (KiCad rules, custom DRC rules, pad classes, keepouts, edge), plus victim gaps. Where the input keeps a rule with less than the 2.5 µm margin (a gap exactly one track wide), the branch may use the input's own distance, measured per item on the input board, never less than the rule. A branch that already breaks a clearance stays as it is. Without that rule, branches on jkiv cm4 slid along items they already violated and KiCad counted 24 more clearance errors.
- **Geometry** (`taut_geom`). The topology uses inscribed polygons, 12 segments per quarter, at the requirement less 3 µm. The exact path keeps requirement + 2 µm + 2 × 0.2 µm arc sampling + 0.1 µm. Pads come from KiCad as polygons; co-circular runs of their vertices (round pads, roundrect corners) merge into one atom only when consecutive vertices are at most 30° apart, so a rectangle's four corners stay four atoms. A start on a triangle edge is located a hair along its first move. The window grows (×2, ×4) when the funnel runs along it.
- **Writing** (`Taut.write`, `arcs.arc_sexpr`). KiCad `(arc (start) (mid) (end))` items. Each joint is one shared point, so KiCad sees the pieces connected. An arc under 0.02 rad becomes its chord, checked again.
- **Power copper on arcs** (`power_copper.PowerCopper._widen_arc`). Arcs enter the `Space` as sampled arcs (`arcs.fix_space_arcs`; the `Space` keeps them as two chords). Each arc is sampled every 0.1 mm along its length. Free half-widths come from the same constraints, so current sharing, victim gaps and neck rule apply unchanged. The same runs become sub-arcs of one circle with shared joints, each checked exactly. Ground vias reach arcs through the sampled geometry.
- **Physics evaluator fix** (`kae.excite.dc._arc_frame`, separate commit). `track_currents` sampled a track at its chord's quarter points; for an arc the chord leaves the copper, so heat.track read zero. It now samples on the arc.

## Results

12 boards: the 10 power-copper smoke boards plus circuitmonkey chips-0123 and zephray nekoink. Inputs are the `kae-bridge-main-final-restarts` outputs with the human project files; there is no re-routing. DRC is kicad-cli on the re-opened board. Script: `tools/research/routing/taut_smoke.sh DIR taut`; table: `taut_summary.py`. Taut uses the defaults (pours held, victims on, pad tails, coupled pairs). "+pc" is the arc-aware power copper on the taut board.

| Board | DRC err/unconn in → taut → +pc | Signal mm | Corners | Acute | Arcs | Pad entries perp/oblique/acute | Taut s | Pc s |
|---|---|---|---|---|---|---|---|---|
| adafruit magtag | 51/0 → 51/0 → 50/0 | 1671 → 1561 | 545 → 281 | 2 → 1 | 281 | 258/14/8 → 258/14/8 | 57 | 346 |
| adafruit metro-m7 | 22/1 → 22/1 → 22/1 | 1604 → 1482 | 776 → 404 | 4 → 4 | 360 | 325/29/19 → 334/28/11 | 42 | 35 |
| aifryz sensor-hub | 9/0 → 9/0 → 9/0 | 1698 → 1601 | 573 → 325 | 8 → 5 | 265 | 272/113/14 → 309/81/9 | 33 | 19 |
| circuitmonkey chips-0123 | 45/4 → 45/4 → 45/4 | 22 → 22 | 5 → 4 | 0 → 0 | 2 | 9/10/0 → 9/10/0 | 6 | 6 |
| dream117er paicorea | 0/1 → 0/1 → 0/1 | 2145 → 2018 | 474 → 268 | 10 → 7 | 257 | 270/124/10 → 271/107/6 | 37 | 24 |
| freetronics secsense | 0/0 → 0/0 → 0/0 | 423 → 403 | 100 → 39 | 0 → 0 | 77 | 70/1/0 → 70/1/0 | 12 | 9 |
| greatscottgadgets ubertooth | 37/13 → 37/13 → 37/13 | 613 → 554 | 577 → 405 | 22 → 10 | 123 | 348/39/14 → 352/34/15 | 28 | 11 |
| jjhorton pmod-tester | 0/0 → 0/0 → 0/0 | 274 → 249 | 64 → 25 | 0 → 0 | 19 | 42/0/0 → 42/0/0 | 7 | 6 |
| jkiv cm4-carrier | 612/0 → 612/0 → 612/0 | 1279 → 1261 | 255 → 255 | 1 → 1 | 2 | 153/38/6 → 156/35/6 | 27 | 12 |
| lenaschimmel bestelampe | 16/0 → 16/0 → 15/0 | 2047 → 2012 | 487 → 394 | 8 → 7 | 84 | 142/23/7 → 142/23/7 | 53 | 21 |
| sparkfun redbot | 133/0 → 133/0 → 133/0 | 1110 → 1019 | 414 → 177 | 4 → 4 | 239 | 180/27/11 → 187/21/10 | 29 | 19 |
| zephray nekoink | 11/95 → 11/93 → 11/93 | 2361 → 2251 | 1338 → 927 | 26 → 24 | 496 | 715/205/25 → 768/159/18 | 125 | 63 |

- **DRC never worse.** Errors stayed at 936 over the 12 boards; unconnected went 114 → 112 (nekoink: taut copper now runs over a same-net pad). With power copper: 934 errors, 112 unconnected. KiCad's `solder_mask_bridge` count moves by ±2 between runs on cm4 (612 / 605 / 607 seen); the gate takes each run as it comes.
- **Length.** Signal −5.3 % (15.25 → 14.43 m), power −1.1 %, ground −1.4 %, all copper −4.4 % (19.70 → 18.84 m). Part of it is copper inside lands (the pad trim's share); the [topological-routing](../../topics/routing/topological-routing.md) estimate for straightening a fixed topology is about 5 %.
- **Corners and acute angles.** Corners fell 5,608 → 3,504 (−38 %); arc-tangent joints are G1 and not counted. Acute corners went 85 → 63, acute pad entries 114 → 90, and oblique entries 623 → 513. No branch gets more acute corners than it had: on redbot, perpendicular tails into pads behind the path first made 140-174° hairpins, so candidates now rank by acute corners first.
- **Optimality.** 1,706 branches carry the certificate: G1, positive wraps, and the window untouched. 51 needed an atom inserted after the exact check and 11 got a Dubins start or end. 123 more were only trimmed (fallback).
- **Convergence.** Pass 0 gave 933 of the 967 mm gained. Pass 1 gave 0.03-28 mm per board, pass 2 nothing. Ten boards stop after 3 passes and nekoink after 4. magtag oscillates at 1 µm per pass up to the 8-pass cap, below the 2 µm requirement margin.
- **Why branches stay.**
  - 4,143 attempts gained nothing: mostly branches already straight between their ends, counted once per pass.
  - 861 were locked: the bridge's repair loop locks its joins.
  - 665 already broke a clearance (cm4 has 249 clearance errors).
  - 8 failed in the solver and 12 failed the final `Space` check.
- **Diff pairs.** 710 P/N branch pairs were tested and none was coupled. Freerouting routes the legs independently: at most 17 % of a leg runs at constant pitch, except cm4's E0_TR1/TR2 at 96 %, and those break a clearance already. The coupled mode is shown on a synthetic pair (board test): shorter, pitch 0.5 ± 0.02 mm, skew not worse.
- **Gate.**
  - lenaschimmel: a starved thermal at J5/J7 could not be attributed; 23 of 43 nets came back, recovery added 1.
  - ubertooth: 3 named clearances; 4 nets came back.
  - cm4: 2 mask bridges; 17 nets came back.
  - Every other board passed on the first DRC run.
- **Power copper on arcs.** 96 arcs were widened over 10 boards, all checked exactly. Ground vias and stitching behaved as on the input.
- **Pours.** With the `refill` variant (other nets' fills ignored), copper was 1.1-3.2 % shorter on 4 boards (secsense −3.2 %, dream117er −2.5 %). On 4 others the gate reverted 18-45 nets for starved thermals, so the total is slightly longer: 18.86 m vs 18.84 m. `hold` stays the default (power copper: "rails may not cut ground pours").
- **Runtime.** Taut took 6-125 s per board: setup 2-29 s, passes 0.1-73 s, the rest KiCad DRC. Power copper took 6-346 s.

PHYSICS_SECTION

