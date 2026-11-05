<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# kae taut arcs: every connection pulled to its shortest path in its own topology, with true arcs

**Status:** partial. 12 boards: DRC never worse, copper −2.7 %, corners −56 %; physics better on 9 of 11 boards with taut alone; the power-copper interaction is mixed. Not the default anywhere.
**First published:** 2026-11-04, branch `arc-taut` (off `pad-edge-entry`).

## Design note (written before the code)

### What the repo's docs say, and what that fixes in the design

| Doc | What it says | What it fixes here |
|---|---|---|
| [topological-routing](../../topics/routing/topological-routing.md) | Routers pick a homotopy class, then realize a rubber band (SURF, TopoR); for a fixed topology octilinear is ~5 % longer than any-angle | Keep the router's topology and realize it optimally; expect single-digit gains |
| [rule-genealogy-routing-style-dfm](../../topics/physics/rule-genealogy-routing-style-dfm.md) R01-R04, R35; [myths-and-contested](../../topics/rules/myths-and-contested.md); [hv-and-manufacturing-physics](../../topics/physics/hv-and-manufacturing-physics.md) | Corners and 45° are physics-neutral below ~10 GHz; curves cost nothing at a fab; "keep 45° for editability"; round pulsed power copper | **Conflict with the brief**, which asks for arcs: they stand as a style choice (45° is kept for editability, not physics). R35 asks for arcs on power copper |
| [diff-pairs](../../topics/rules/diff-pairs.md) | Rounded corners do not remove skew; outer leg +1.57 p per corner; uncoupled ≤ 1.14 mm | Tighten a pair only as a pair (legs offset from one centreline, end headings kept, so skew = D × net turning is unchanged), else leave it |
| [length-matching-and-buses](../../topics/routing/length-matching-and-buses.md) | Length is tuned after routing; meanders are explicit rules | Length/skew-ruled and meandered nets are never shortened |
| [si-fundamentals](../../topics/rules/si-fundamentals.md) | K = 1/(1+(D/h)²); spacing in units of h, never "3W" | Victims keep min(power copper's `victim_gap`, the input's distance) |
| [kae-power-copper](kae-power-copper.md) | Brief classes, extra gaps, sharing, necks; "rails may not cut ground pours"; gate with attribution and ddmin | Same classes (imported); other nets' fills stay obstacles; widening along arcs reuses the sampling, runs and necks |
| [kae-pad-edge-entry](kae-pad-edge-entry.md) | Entry ≤ 10° off the normal; acute entries come from 45° runs into pad corners | Superseded by the user's rule D (below): ends on the long centre line, square crossing, tangent arc before it |
| [power-copper (physics)](../../topics/physics/power-copper.md) | "Width trades one parasitic for another; only length lowers all of them" | Length is the objective; switch nodes keep victim gaps |
| [research-gaps](../../topics/physics/research-gaps.md) #15, [autorouter-skepticism](../../topics/routing/autorouter-skepticism.md), [open-source-routers](../../topics/landscape/open-source-routers.md) | Practitioners count bends and acute angles; route-rnd's rubber band "leaves unnecessary curves" | Report corners and acute angles; true KiCad arcs; drop backward wraps |
| [physics-in-the-loop-optimization](../../topics/physics/physics-in-the-loop-optimization.md), [kae-routing-dead-ends](kae-routing-dead-ends.md) | Elastic bands relax a fixed-homotopy path; rip-ups do not pay | Solve the tension-only limit exactly; never rip up a neighbour |

### Outside literature built on

- **Homotopic shortest paths.** Hershberger & Snoeyink, CGTA 4(2):63-97, 1994 ([DOI](https://doi.org/10.1016/0925-7721(94)90010-8)): sleeve of triangles in the universal cover plus the funnel of Lee & Preparata (Networks 14, 1984; Chazelle, FOCS 1982). Also Efrat, Kobourov & Lubiw (CGTA 35, 2006) and Bespamyatnikh (J. Algorithms 49, 2003).
- **Curved obstacles.** Chen & Wang, ACM TALG 11(4), 2015 ([arXiv 1103.3911](https://arxiv.org/abs/1103.3911)): shortest paths are free common tangents plus convex boundary arcs. Also Hershberger, Suri & Yıldız (SoCG 2013); Liu & Arimoto's tangent graphs (IJRR 11, 1992); for discs, Chang, Choi, Kwon, Park & Yap (IJCGA 16, 2006, [pdf](https://cs.nyu.edu/exact/doc/computable.pdf)).
- **Funnel with clearance.** Kallmann, SCA 2010 ([DOI](https://doi.org/10.2312/SCA/SCA10/159-168)); Demyen & Buro, AAAI 2006. **Configuration space:** Lozano-Pérez & Wesley, CACM 1979; offsets with round joins, Wein, CAD 39(6), 2007.
- **Rubber-band routing.** Dai, Dayan & Staepelaere, DAC 1991 ([DOI](https://doi.org/10.1145/127601.127622)); Staepelaere (UCSC-CRL-92-39); route-rnd/libgrbs; TopoR (arcs; "~30 % larger minimum gaps than 45°", vendor); US 6,226,560.

### The design

1. **Configuration space.** Every foreign item is grown by r_item + `Space.need` + w/2. `Space.need` is the bridge's own KiCad rules: net classes, custom rules, pad classes, keepouts, edge. Victim pairs keep min(victim gap, the input's distance). Other nets' fills are obstacles.
2. **Topology.** The free space in a window around the branch is triangulated (GEOS constrained Delaunay). The branch is traced through it and back-and-forth crossings cancel, which gives the universal-cover sleeve. The funnel over that sleeve gives the homotopic shortest polygonal path and the side of each obstacle it touches.
3. **Exact geometry.** Every funnel apex lies on an atom (a grown disc: via, round pad, track end, pad or fill corner). Same-side wraps are joined by outer common tangents, opposite sides by inner ones, with an arc on each atom; a backward wrap is dropped. An obstacle the exact check finds too close adds its nearest atom, and the path is solved again.
4. **Certificate.** A G1 path whose arcs all turn toward their atoms, with every piece legal, is locally shortest. In the simply connected universal cover a locally shortest path is the shortest one. The result is therefore optimal for its homotopy class, relative to KiCad's polygonised pad and fill outlines and the 2.5 µm margin.
5. **Order.** route → pad entry → taut → power copper → DRC gate. Taut runs before power copper because widened copper cannot move, and widening fills the room that tightening frees.
6. **Passes and gate.** Passes repeat until no net shortens by more than 1 µm; arcs are checked sampled (0.2 µm added to the requirement); then KiCad DRC must be no worse.

## How it works (as built)

- **Branches** (`Taut.chains`). Each branch is the tracks of one net and layer between fixed points: pads, vias, ends shared by three or more tracks, width changes. Straight tracks are cut at their interior T-joins first. Skipped: locked tracks (the repair loop locks its joins), length- and skew-ruled nets, and tuning patterns.
- **Pad tails** (`Taut.tails`) follow pad-entry rule D, the user's choice: the end on the pad's long centre line ((L − H)/2 either side of the centre along the long axis; a round or square pad's centre, a stadium's end-circle centres), the crossing within 10° of the normal. Since 2026-11-04 the targets are `pad_entry.centreline_targets` itself, with its overhang test (below):
  - straight to the nearest centre-line point, kept only if the solved crossing is square and adds no copper past the land;
  - square through the long edge; along the axis through the short edge (a width deep for current-carrying copper); radially into a round end;
  - the input's own tail.

  Anchors sit one width outside the outline; the turn there becomes a tangent arc (1.5w, w or w/2), a Dubins-type start. Candidates rank by acute corners (never more than the branch had), square entries, overhanging entries (never more than the input's), then length. Ball grids and via-in-pad keep their tails.
- **Requirements** (`Taut.obstacles`). Where the input keeps a rule with under the 2.5 µm margin, the branch may use the input's own distance, never less than the rule. A branch that already breaks a clearance stays (else cm4 gained 24 clearance errors).
- **Geometry** (`taut_geom`). Topology polygons are inscribed (12 segments per quarter, 3 µm inside the requirement); co-circular vertex runs merge into one atom only when consecutive vertices are ≤ 30° apart, so a rectangle keeps four corner atoms.
- **Pairs** (`tighten_pair`). A section at constant pitch D becomes one centreline grown by D/2 for both nets' rules, its end headings kept; the legs are its exact offsets (arcs at r ∓ D/2). Skew is never worse; both legs are kept or reverted together.
- **Output.** KiCad `(arc start mid end)`, one shared point per joint.
- **Gate** (`run`, `set_kept`). Reverts nets KiCad names or that lie within 1 mm, then 2.5 mm, of a violation; else adds nets back batch by batch, keeping each batch that leaves the board no worse; then tries to recover reverted nets. Nets in conflict with restored copper drop exactly.
- **Power copper on arcs** (`PowerCopper._widen_arc`). The `Space`'s two-chord arcs are replaced by sampled arcs; widening samples every 0.1 mm along the arc with the same constraints, sharing and necks, each run a sub-arc of the same circle, checked exactly.
- **Evaluator fix** (`kae.excite.dc._arc_frame`, separate commit): track currents were sampled on an arc's chord, so heat.track read zero for arcs.

## Results

12 boards: the 10 power-copper smoke boards plus chips-0123 and nekoink, the `kae-bridge-main-final-restarts` outputs with the human project files, not re-routed. DRC: kicad-cli on the re-opened board. Script `tools/research/routing/taut_smoke.sh DIR taut`, table `taut_summary.py`; taut defaults. "+pc": the arc-aware power copper on the taut board.

| Board | DRC err/unconn in → taut → +pc | Signal mm | Corners | Acute | Arcs | Pad entries perp/oblique/acute | Taut s | Pc s |
|---|---|---|---|---|---|---|---|---|
| adafruit magtag | 50/0 → 50/0 → 50/0 | 1671 → 1638 | 545 → 311 | 2 → 3 | 181 | 258/14/8 → 260/11/9 | 96 | 341 |
| adafruit metro-m7 | 22/1 → 22/1 → 22/1 | 1604 → 1523 | 776 → 214 | 4 → 5 | 445 | 325/29/19 → 336/26/11 | 51 | 236 |
| aifryz sensor-hub | 9/0 → 9/0 → 9/0 | 1698 → 1656 | 573 → 234 | 8 → 7 | 338 | 272/113/14 → 314/75/10 | 38 | 21 |
| circuitmonkey chips-0123 | 45/4 → 45/4 → 45/4 | 22 → 22 | 5 → 3 | 0 → 0 | 2 | 9/10/0 → 9/10/0 | 6 | 6 |
| dream117er paicorea | 0/1 → 0/1 → 0/1 | 2145 → 2110 | 474 → 178 | 10 → 7 | 358 | 270/124/10 → 319/72/12 | 45 | 25 |
| freetronics secsense | 0/0 → 0/0 → 0/0 | 423 → 421 | 100 → 3 | 0 → 0 | 94 | 70/1/0 → 70/1/0 | 14 | 9 |
| greatscottgadgets ubertooth | 37/13 → 37/13 → 37/13 | 613 → 586 | 577 → 433 | 22 → 16 | 103 | 348/39/14 → 351/38/12 | 41 | 12 |
| jjhorton pmod-tester | 0/0 → 0/0 → 0/0 | 274 → 265 | 64 → 5 | 0 → 0 | 21 | 42/0/0 → 42/0/0 | 8 | 6 |
| jkiv cm4-carrier | 612/0 → 612/0 → 612/0 | 1279 → 1262 | 255 → 220 | 1 → 1 | 28 | 153/38/6 → 158/33/6 | 12 | 10 |
| lenaschimmel bestelampe | 16/0 → 16/0 → 15/0 | 2047 → 1988 | 487 → 177 | 8 → 4 | 280 | 142/23/7 → 155/13/4 | 65 | 23 |
| sparkfun redbot | 133/0 → 133/0 → 133/0 | 1110 → 1055 | 414 → 58 | 4 → 4 | 299 | 180/27/11 → 189/21/10 | 32 | 18 |
| zephray nekoink | 11/95 → 11/93 → 11/93 | 2361 → 2301 | 1338 → 653 | 26 → 24 | 684 | 715/205/25 → 787/141/19 | 150 | 70 |

- **DRC never worse.** Errors 935 → 935, unconnected 114 → 112 (nekoink: taut copper now runs over a same-net pad); with power copper 934 and 112.
- **Length.** Signal −2.8 % (15.25 → 14.83 m), power −2.6 %, ground −2.2 %, all copper −2.7 %; ends `pad_entry_overlap` inside the edge had given −5.3 % and −4.4 %, rule D keeps them deep. [topological-routing](../../topics/routing/topological-routing.md) estimates about 5 %.
- **Corners.** 5,608 → 2,489 (−56 %; G1 joints not counted, 696 tail turns became arcs). Acute corners 85 → 71, acute entries 114 → 93, oblique 623 → 441. Acute corners rank first: square tails into pads behind the path had made 140-174° hairpins.
- **Optimality.** 1,724 branches carry the certificate (G1, positive wraps, window untouched); 50 needed an inserted atom.
- **Convergence.** Pass 0 gave 593 of 599 mm; ten boards stop after 3 passes, nekoink after 4, magtag oscillates at 1 µm per pass to the 8-pass cap.
- **Branches left as they were** (attempts per pass): 3,786 gained nothing, 861 locked, 701 already broke a clearance, 20 failed the solver or the `Space` check.
- **Diff pairs.** None of the 710 P/N branch pairs was coupled: Freerouting routes the legs independently (at most 17 % of a leg at constant pitch). On a synthetic pair (board test) the pass came out shorter at pitch 0.5 ± 0.02 mm, skew not worse.
- **Gate.** Nets reverted: magtag 17 of 64, ubertooth 8 of 52 (clearances), lenaschimmel 5 of 42 (starved thermals); the rest passed on the first DRC run.
- **Pours.** `refill` (other nets' fills ignored) was shorter on 7 boards (up to 3.3 %), but on 3 the gate reverted 18-38 nets for starved thermals; 19.15 m vs 19.17 m, so `hold` stays.
- **Runtime.** Taut 6-150 s per board; power copper 6-341 s.

### Physics

`eval_intent.sh`, `KAE_EM_TOL=1e-4`, intents `compiled-6329e71`; total mW_eq. "Pc only" is power copper on the input.

| Board | Before | Taut | Taut + pc | Pc only |
|---|---|---|---|---|
| adafruit magtag | 26973 | 26748 | 19049 | 10069 |
| adafruit metro-m7 | 7443 | 7037 | 6328 | 6683 |
| aifryz sensor-hub | 47277 | 46692 | 35463 | 40874 |
| dream117er paicorea | 349 | 357 | 96 | 57 |
| freetronics secsense | 15819 | 15832 | 5648 | 5645 |
| greatscottgadgets ubertooth | 2204 | 2174 | 2136 | 2165 |
| jjhorton pmod-tester | 904 | 903 | 20 | 20 |
| jkiv cm4-carrier | 9931 | 8558 | 7781 | 7976 |
| lenaschimmel bestelampe | 5238 | 5125 | 2165 | 2560 |
| sparkfun redbot | 96539 | 96555 | 79013 | 74512 |
| zephray nekoink | 31369 | 14850 | 11955 | 28666 |

Median after/before ratio per observable (number of terms):

| Observable | Taut | Taut + pc | Pc only |
|---|---|---|---|
| loss.copper | 0.979 (7) | 0.737 (7) | 0.566 (7) |
| drop.rail | 0.977 (5) | 0.315 (5) | 0.317 (5) |
| supply.peak | 0.979 (37) | 0.571 (37) | 0.621 (37) |
| emission.cable_E | 0.999 (5) | 0.918 (5) | 0.965 (5) |
| pickup.peak | 0.889 (3) | 0.920 (3) | 0.940 (3) |
| heat.track | 1.000 (4) | 0.324 (4) | 0.324 (4) |

- **Taut alone: total lower on 8 of 11 boards** (9 since 6dc0927, below; chips-0123 has no intent).
  - Copper loss down by up to 6 % (redbot 997 → 940 mW), rail drop up to 3 % (cm4 D1 420 → 409 mV), supply peaks up to 12 % (metro S0 120 → 106 mV).
  - nekoink's −53 % comes from the 2 connections it closed, not from tightening.
- **Taut alone: worse on 3.**
  - dream117er +2.5 % and redbot +0.02 %: the hottest track's heat.track doubled while loss and drop fell. Its effective width is the 0.25 mm raster cells a 0.25 mm track covers, which flips between 1 and 2 with position: most likely raster noise [I].
  - secsense +0.08 % (copper loss +0.6 %).
- **Taut + pc against pc alone.**
  - Better on 6 boards (metro, cm4, lenaschimmel 2165 vs 2560, ubertooth, nekoink, aifryz 35463 vs 40874), equal on 2.
  - Worse on 3: on magtag the power-copper gate spent its 80 DRC runs on solder-mask-bridge noise and kept 35 of 119 widenings (88 of 115 on the input); on redbot and dream117er, the heat.track rise above.
  - Signal terms are better with taut first: emission 0.918 vs 0.965, pickup 0.920 vs 0.940.

### Tracks wider than the land (2026-11-04)

Taut's copy of rule D had no overhang test; tails now come from `pad_entry.centreline_targets` with its overhang test, neck and land hazard ([kae-pad-edge-entry](kae-pad-edge-entry.md#tracks-wider-than-the-land-2026-11-04)); a necked tail keeps the wide path neck_len + w/2 off the land, pieces at their own widths. No candidate hangs more entries past their lands than the input; one that removes such an entry may be 1 mm + 20 % longer. Reported: `necks`, `overhang_fixed`, `hazards`.

Taut alone against the arc-taut head (e415d23, re-run byte-identical; per board in the [results](../../../bench/results/2026-11-04-taut-pad-wide-6dc0927.md)):

| | Branches improved | Oblique / acute entries | Overhanging entries (input 30) | Necks | Hazards | Copper m | Physics better than before |
|---|---|---|---|---|---|---|---|
| e415d23 | 1,724 | 441 / 93 | 25 | – | – | 19.170 | 8 of 11 |
| 6dc0927 | 1,730 | 438 / 92 | 25 | 0 | 0 | 19.169 | 9 of 11 |

- No track here is wider than its land, so no neck or hazard occurred; a board test necks a 1.0 mm track into two 0.6 mm lands at both ends.
- 9 boards changed; DRC no worse than the base on any. The base had removed the same 6 overhanging entries.
- Worse: metro-m7 one more oblique entry (C7, 13°; pad_entry ends tracks in a near-square land on its centre, taut's copy 0.04 mm off it).
- Physics within 0.2 % of the base on every board; redbot turns from +0.02 % to −0.01 % against the input.

## Verdict

- **Worth adopting as a post-pass before power copper.** DRC never worse, 2 connections closed, copper −2.7 %, corners −56 %, every rewritten branch certified optimal for its homotopy class, physics better on 9 of 11 boards.
- **Before power copper:** better than power copper alone on 6 boards, worse on 3. Fix the power-copper gate's mask-bridge noise (magtag) before making taut + pc the default.
- **Next:** an A/B through the bridge's final stage (cp1/cpk, merit physics); heat.track on a finer pitch; letting locked repair joins move (861 attempts); via sliding.

## Code

- `kae/src/kae/route/taut_geom.py`: `tangent`, `solve_wraps`, `make_obstacle` (atoms), `Mesh.trace` (sleeve), `funnel`, `BranchSpace.solve`.
- `kae/src/kae/route/taut.py`:
  - `Taut.chains`, `tails` (rule D), `obstacles`, `tighten`, `tighten_pair`, `set_kept`, `run`, `board_stats`;
  - CLI: `python -m kae.route.taut run IN OUT [--power-copper] [--pours refill]` and `python -m kae.route.taut stats BOARD`.
- `kae/src/kae/route/arcs.py`: arc geometry, `polyline_violations`, `arc_sexpr`, `fix_space_arcs`.
- `kae/src/kae/route/power_copper.py`: `PowerCopper._widen_arc`.
- `kae/src/kae/excite/dc.py`: `_arc_frame`.
- Tests: `kae/tests/test_route_taut.py`. Scripts: `tools/research/routing/taut_smoke.sh`, `taut_summary.py`, `pad_wide_summary.py`.

