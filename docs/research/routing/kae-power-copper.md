# kae power copper: widen rails and grounds into free space, ground vias at decoupling pads

**Status:** not finished (smoke test on 10 boards, physics better on all; no A/B through the router yet).
**First published:** 2026-11-02, branch `power-copper` (off `thermal-heatsinks-merge`).

The bridge routes every net at its net-class width and only ever narrows. Over 99 boards of a routing A/B (human layout vs `kae-bridge-main-final`, same placement) the median power-track width was 0.39 mm for the human boards and 0.20 mm for kae, and none of kae's track length was 0.4 mm or wider (human: a median 13.5%). Copper loss was 1.69x, and kae dropped most ground vias (2651 vs 715 over 107 boards). `kae.route.power_copper` is a post-pass on a routed board that changes routing only, on power and ground nets only, and keeps a change only where KiCad's DRC is no worse.

## Idea and how it works

- **Classes** from the physics brief (`kae.circuit.brief`): rails and grounds are widened; switch nodes (role `switch_node`, commutation cells' `sw`/`sw_nets`) never are, since SW copper is an E-field antenna ([power-copper](../../topics/physics/power-copper.md) §1, "pour freely on quiet nodes"). Victims are clock, high-speed, analog and RF nets plus the brief's victim and crystal structures (feedback, sense, divider nodes); antenna parts are kept clear.
- **Widen in place.** Each straight track is sampled every 0.1 mm; at each sample the widest legal half-width is the distance to every foreign item minus its requirement. Runs of equal width (at least 1 mm long; a run is never wider than its narrowest sample) become separate collinear segments, each checked exactly with the critical router's `Space.track_violations` plus the extra gaps below. No track moves, nothing is narrowed, no other net is touched. Ladder 0.3-1.0 mm (area efficiency peaks at the feed width, power-copper §3); a net whose operating current (operating facts `parts.<ref>.I_A`, upper end) needs more gets the IPC-2221 width of 3x that current, up to 3 mm. Highest-current nets go first.
- **Extra spacing.** Grown copper keeps, beyond the board clearance: from ordinary signals 2x the clearance and 2x the signal's width (3W centre to centre); from victims, on its own and the adjacent layers, D = h·sqrt(1/K - 1) with K = 5%, clipped to 0.5-2 mm ([si-fundamentals](../../topics/rules/si-fundamentals.md): express spacing as a crosstalk budget in units of h, not "3W"); 3 mm from antenna pads.
- **Ground vias.** Each SMD ground pad of a capacitor, and each ground pin the brief's decap structures name, without a ground barrel within 1 mm gets one via as close as is legal where the same ground has fill on another layer, with a pad-to-via track ([decoupling-pdn](../../topics/rules/decoupling-pdn.md) PDN-01, LearnEMC's via adjacent to the pad).
- **Stitching.** Ground fill pieces other than a layer's largest that hold ground pads and fewer than 3 barrels get vias 2 mm apart into another layer's ground (`critical.Session.stitch_ground`'s rule).
- **No new pours**: si-fundamentals says ground fill is never a default, and a separate investigation found the task keeps every human zone (refilled ground area 1.003x the human's).
- **DRC gate.** KiCad DRC (zones refilled) on the written board must have no error type and no unconnected count above the input's. A new violation naming an added item reverts it; one that names none reverts changes within 1 mm of its positions; what is left is bisected (16 DRC runs at most). Then the input is kept.

Hook: bridge option `power_copper=True` (off by default) runs it after the repair rounds.

## Results

Smoke test, 10 boards, `kae-bridge-main-final` outputs, physics `tools/research/physics/eval_intent.sh` (`KAE_EM_TOL=1e-4`, intents `compiled-6329e71`). Script: `tools/research/routing/power_copper_smoke.sh`.

| Board | Power length >= 0.4 mm | GND vias | DRC err/unconn | Copper loss | Worst supply.peak | Signal terms |
|---|---|---|---|---|---|---|
| jjhorton pmod-tester | 0 -> 100% | 0 -> 2 | 0/0 -> 0/0 | 141 -> 40 mW | — | — (heat 164 -> 17 K) |
| dream117er paicorea | 0 -> 37% | 8 -> 10 | 0/1 -> 0/1 | 76 -> 58 mW | — | — |
| freetronics secsense | 0 -> 79% | 0 -> 1 | 0/0 -> 0/0 | 2986 -> 873 mW | — | — |
| lenaschimmel bestelampe | 0 -> 66% | 7 -> 30 | 16/0 -> 16/0 | — | 385 -> 137 mV | cable CM 8.2 -> 7.3 mV |
| aifryz sensor-hub | 0 -> 50% | 35 -> 78 | 9/0 -> 9/0 | 52 -> 42 mW | 1.31 -> 1.13 V (VDDA); +BATT 1.31 -> 1.54 V | cable CM 38 -> 36 mV |
| jkiv cm4-carrier | 0 -> 37% | 72 -> 72 | 612/0 -> 612/0 | 780 -> 590 mW | 166 -> 163 mV | emission 61.9 -> 61.8 dBuV/m |
| adafruit metro-m7 | 0 -> 33% | 21 -> 50 | 22/1 -> 22/1 | — | 448 -> 413 mV | cable CM 99 -> 88 mV |
| sparkfun redbot | 0 -> 55% | 9 -> 24 | 133/0 -> 133/0 | 997 -> 552 mW | 2.05 -> 1.35 V | emission 69.2 -> 68.0 dBuV/m |
| greatscottgadgets ubertooth | 0 -> 36% | 12 -> 12 | 37/13 -> 37/13 | — | 293 -> 290 mV | pickup 618 -> 580 uV, emission 40.1 -> 39.4 dBuV/m |
| adafruit magtag | 0 -> 42% | 23 -> 55 | 51/0 -> 50/0 | 43 -> 20 mW | 443 -> 96 mV | emission 92.1 -> 75.0 dBuV/m |

Worse: aifryz `supply.peak` S4 (+BATT pin's own core noise) 1.31 -> 1.54 V while its other supply terms fell 14-41%; redbot's D1 rail drop 22 -> 78 uV (met by a wide margin). The pass took 6-77 s per board, most of it KiCad DRC (planning 2-15 s).

## Width cap sweep, vector growth and current sharing (2026-11-03)

Same 10 boards, same physics. W*n* = track widening capped at *n* mm (`max_width` = `current_cap`); V*n* = vector mode (the free region around each power/ground net's copper on its layer, clipped to an *n* mm corridor, filled with overlapping 0.5 mm track strips; other nets' fills are obstacles). Median after/before ratio over the boards' terms:

| Term (n) | W1 | W2 | W3 | W20 | V3 | V20 |
|---|---|---|---|---|---|---|
| loss.copper (7) | 0.562 | 0.525 | 0.519 | 0.515 | 0.882 | 0.888 |
| drop.rail (20) | 0.693 | 0.678 | 0.668 | 0.667 | 0.918 | 0.916 |
| heat.track (7) | 0.567 | 0.567 | 0.567 | 0.567 | 1.000 | 1.000 |
| supply.peak (35) | 0.865 | 0.865 | 0.864 | 0.865 | 0.905 | 0.910 |
| emission.cable_E (4, field ratio) | 0.902 | 0.908 | 0.906 | 0.907 | 0.934 | 0.988 |
| cable_cm.v (3) | 0.900 | 0.908 | 0.912 | 0.908 | 0.904 | 0.885 |
| pickup.peak (1) | 0.937 | 0.941 | 0.942 | 0.944 | 0.882 | 1.237 |

- **Cap.** Free space, not the cap, limits widening: past 2-3 mm the gains stop. 20 mm is no better than 3 mm on any median and worse on aifryz's loop loss (0.85 vs 0.62) and ubertooth's S1 (x1.04). The default cap is now 3 mm.
- **Vector.** Weaker than widening on 7 of 10 boards: rails may not cut ground pours, and on poured 2-layer boards almost all free space is pour. Better on metro-m7 (0.86 vs 0.90 total), cm4 (0.65-0.70 vs 0.80) and lenaschimmel (0.43 vs 0.49, and DRC errors 16 -> 8). V20 hurt ubertooth (supply.peak up to x4.6, pickup x1.24). Growing into pours (`into_pours`) starved ground thermals on pmod-tester and failed the gate. KiCad zones cannot be used at all: the route-task scorer counts any zone edit as invalid (`bench/src/kaebench/score.py`), so vector copper is written as tracks.
- **Sharing.** Competing power/ground nets split contested room at w ~ I (least sum I^2 R): widening leaves a competing ungrown track its share, and vector mode grows all nets at speeds proportional to current (a weighted Voronoi split by repeated buffering). Examples (W3 shared vs first come): dream117er GND/+5V at equal current, 1.08 mm centre gap: 0.8/0.5 mm vs 1.2/0.4 mm; lenaschimmel +3.3V (354 mA) / +5V (3 mA), 1.5 mm gap: 0.5/0.2 vs 0.5/1.2 mm. Physics totals are the same on the 4 boards tried (few contested spots, small currents).
- **Soldering** (superseded by the neck rule below). Own SMD pads up to 0.6 mm short side (reflow, or process unknown, which is every compiled intent so far) or 1.6 mm (hand soldering) keep grown copper 0.3 mm away. Same-layer pads fed by copper wider than the pad: 0402 class 1/340 before and 2-3/350 after; 0603-1206 class 0/300 -> 41-54/330 (W1-W3); > 1 mm pads 0 -> 12-15.
- **Gate.** When single-culprit attribution fails, changes are now added back batch by batch (ddmin), and the best no-worse board any check saw is kept. Without this, metro-m7 W2/W3/W20 and magtag V3/V20 fell back to the input.

## Necks at small lands: tombstoning and manufacturability (2026-11-03)

**What the sources say.**
- **No primary source gives a number for trace width into a chip land.**
  - IPC-7351 (2005) §3.4.6.2: wide conductors "act as a solder thief" and planes "act as a heat sink"; use "a narrow conductor between the land area and the via". §7.6.1 asks for "a short length of copper conductor" to isolate terminations ([IPC-7351 text](https://dn720001.ca.archive.org/0/items/ipc_20220718/IPC-7351%20eng_text.pdf)) [P].
  - AVX: "necking of the conductive path at the component will largely eliminate" drawbridging ([Wicker & Maxwell](https://kyocera-avx.com/docs/techinfo/SurfaceMountCapacitors/soldpad.pdf)) [P].
  - Murata: "bilateral symmetry" ([Murata](https://article.murata.com/article/basics-of-capacitors-6)) [P]. Kyocera: "equal heating to both terminations", 3216 (1206) and smaller ([Kyocera](https://ele.kyocera.com/en/product/capacitor/ceramic/mlcc-handling/mounting-09/)) [P].
- **Numbers come from assembly houses.**
  - Eurocircuits: "the track width to each pad of the component the same width", and that width runs "at least 0.25 mm from the pad edge", "longer is better"; vias ≥ 0.25 mm from the pad ([Eurocircuits](https://www.eurocircuits.com/pcb-assembly-guidelines-tombstoning/)) [S].
  - Suntron (0402): copper exposure on each pad "must be equal (or very close)"; a mask-defined pad on a plane exposes about 65% more area ([Suntron](https://www.globalspec.com/Suntron/ref/FinalTombstone0402Whitepaper.pdf)) [S].
  - Blog ratios such as "within 50% for the first 1 mm" are unsourced ([AtlasPCB](https://www.atlaspcb.com/blog/pcb-tombstoning-prevention-smt/)).
- **Process.**
  - A 192-board reflow DOE saw tombstones on 0402 only, not 0805/1206; nitrogen and fast profiles promote them ([TU Dresden/rehm](https://www.electronics.org/system/files/technical_resource/E10%26S30_02.pdf)) [P].
  - Vapour phase "can exacerbate 0402 and smaller" tombstoning ([I-Connect007](https://iconnect007.com/article/95304/vapor-phase-technology-is-a-viable-solution-but-carries-a-learning-curve/95307/smt?page=2)) [S]; hot plate's slower ramps resist it (IPC-7351 §7.4.6).
  - Coilcraft: avoid an iron on 0201/0402 ([Doc362](https://coilcraft.com/pdfs/Doc362_SolderingSMT.pdf)) [P].
- **Physics.** The surface-tension to gravity torque ratio rises from 2 (1206) to 49 (0201), and what decides the outcome is the wetting lag between the two lands ([hv-and-manufacturing-physics](../../topics/physics/hv-and-manufacturing-physics.md)). A 0.15 × 2 mm neck cut the modelled lag by about 23%, and equal environments remove it.

**The rule** (`neck_rule`, `NECK_TABLE`).
- **Where it applies.** It covers the lands of two-terminal SMD parts. Within `neck_len` = 0.5 mm of the land edge (twice Eurocircuits' 0.25 mm), grown copper is at most the neck width. Beyond that, a capsule may be wider only where its edge stays 0.5 mm off the land (`neck_half`).
- **Balance.** Both lands of a part get the same neck. That equalises what this pass adds; the routed track, which enters at its class width, is unchanged.
- **Neck widths** (our choice, at most the land width; class by land width):

| Process | 0201 | 0402 | 0603-0805 | 1206+ |
|---|---|---|---|---|
| reflow (and unknown, the case on every compiled intent so far) | 0.15 | 0.25 | 0.30 | none |
| vapour phase | 0.15 | 0.25 | 0.30 | 0.50 |
| hand | 0.15 | 0.25 | 0.30 | 0.50 |
| wave (glued chips) | none | none | none | none |

- **Current overrides the neck.** A part in series with a rail (fuse, ferrite, shunt, jumper) keeps the IPC-2221 width of 3× its current. It is not necked at all once that width exceeds the land.
- **Where it does not apply.** A part to ground (a decap) carries no DC and is necked. ICs and parts with more than two terminals are not necked.
- **Cost.** A neck costs 0.3 mm × 0.5 mm at 35 µm ≈ 0.8 mΩ.
- **Vias.** Pad-to-via tracks at necked lands are no wider than the neck.
- **Vector mode.** Grown copper stays 0.5 mm off necked lands.

**Results.** All runs: 10 boards, 3 mm cap, sharing on, final gate.
- **Variants:**
  - W3: widening without necks.
  - N3: widening with necks; ground vias keep their own neck-wide track, via edge ≥ 0.25 mm from the land.
  - NT3: as N3, but the via sits on the land's routed track, so no second entry.
  - NV3: vector mode with necks.
- **Physics** (median after/before):

| Term | W3 | N3 | NT3 | NV3 |
|---|---|---|---|---|
| loss.copper (7) | 0.519 | 0.556 | 0.748 | 0.880 |
| drop.rail (20) | 0.668 | 0.679 | 0.862 | 0.936 |
| heat.track (7) | 0.567 | 0.567 | 0.567 | 1.0 |
| supply.peak (35) | 0.864 | 0.867 | 0.918 | 0.915 |
| emission (4) | 0.906 | 0.921 | 0.926 | 0.935 |
| pickup (1) | 0.942 | 0.943 | 0.943 | 0.858 |

- **Board totals.** N3 is within 0.03 of W3 on every board, and DRC is never worse than the input.
- **NT3 is worse:** magtag 0.87 vs 0.37, loss 0.75 vs 0.56. With one via per land and no second entry, the decap ground loops grow and the ground stitching thins out (via-to-pad distance is the decoupling lever in [decoupling-pdn](../../topics/rules/decoupling-pdn.md)). The default is therefore N3.
- **Tombstone risk** over 260 two-terminal 0201–0805 parts on power/ground nets.

| | before | W3 | N3 | NT3 | NV3 |
|---|---|---|---|---|---|
| lands fed by copper wider than the neck | 0 | 164 | 5 | 5 | 4 |
| parts whose two lands lose heat unequally (copper crossing a circle just outside the land, or a pour, ratio > 2) | 155 | 186 | 151 | 155 | 152 |

  With necks the pass adds no imbalance; the 151–155 are the routing's and the pours' own.
- **Gate.** A wider (2.5 mm) spatial attribution is tried before ddmin, and the DRC budget is 80. Before this, magtag reverted 88 changes under the budget; now it reverts 6.
- **Zones switch.** `--mode vector --vector-out zones` writes each vector piece as a KiCad zone: priority above the layer's zones, solid pad connection, thermal reliefs when hand soldered. Necked lands sit outside the zone outline (0.5 mm), so a solid connection never reaches them. On dream117er it wrote 31 zones, and the gate kept 28. Strips stay the default until route tasks may add zones.

## Necks at through-hole pads (2026-11-13)

**Why.** Route-finish-ab stage 2 (213 boards) measured copper overhanging plated through-hole (THT) pads at 4,085 mm² with finish, 168 without and 1,037 in the human layouts ([report](../../../bench/results/2026-11-11-route-finish-ab.md), branch `route-finish-ab`): power copper ran 2-3 mm rails straight into screw-terminal, header and connector pads.

**What the sources say.**
- A THT joint is made by a wave, a selective nozzle or an iron, which must heat the barrel against the copper's drain. "Reliefs remain physics for hand and wave soldering of THT pins" ([hv-and-manufacturing-physics](../../topics/physics/hv-and-manufacturing-physics.md)); a relief cuts the joint's drain 1.8-4.2× ([derivation-audit](../../topics/physics/derivation-audit.md) D7). Checklist THM-01: reliefs on plane connections "except heat-sinking or high-current pads" ([checklist](../../topics/verification/checklist-full-thermal-routing-assembly-test.md)); pcb-cooling rule 15: reliefs on THT pads except heat-carrying pins, solid above ~3 A ([pcb-cooling](../physics/pcb-cooling.md)).
- IPC-2222 §9.1.2 sizes a relief's webs together at 60% of the land diameter ("divide 60% of the minimum land area diameter by the number of webs", quoted on the [KiCad developers' list](https://archive.lists.launchpad.net/kicad-developers/msg06584.html)) [S]. We found no IPC-7251 clause on track width into a THT land.

**The rule** (`neck_rule(..., tht=True)`, `land_necks(..., tht_current=)`, the SMD neck's code).
- **Where.** Within `neck_len` (0.5 mm) of a plated THT pad of a power or ground net, on a track that *ends in* the pad. A track that only passes the pad keeps a relief-like gap (`tht_gap`, 0.25 mm) from it and is not narrowed along its run.
- **Width.** No wider than the routed track or the IPC-2221 width of 3× the current in the entering track, whichever is wider.
- **Current.** It comes from the physics evaluator's DC plan (`kae.excite.dc.planned_injections`: rails, regulators, loads and feeds at the typical point) and a resistive solve of the net's routed copper (`branch_currents`), so a feed pin or a pad in a chain carries what flows through it.
- **Loss budget.** The necks of a net add at most `tht_loss_frac` (0.2 %) of the net's copper loss under that plan, counting I²R over the neck and the taper that round-capped wider copper needs to keep its edge off the pad (L = neck_len + w/2). Within a net the pads neck cheapest first (cost I² × entries × L × (1/w − 1/w_full)) while the budget lasts, so idle and light pins neck and the busiest keep their copper. A pad whose budget width exceeds a relief's webs keeps its copper (`tht_pad_kept_wide`, info).
- **Heat paths.** THT pads of any net within a hot part's spreading radius keep their copper (`tht_pad_kept_wide`). The radius is where the part's dissipation holds an infinite board fin (`kernels.fin_point`; 1 oz layers at 50 % fill) `tht_heat_dK` (20 K) above ambient (λ ≈ 27 mm on 2-layer 1 oz; [pcb-cooling](../physics/pcb-cooling.md): copper within 1.5-2 λ is what cools a part). P comes from the facts' P_sustained_W or the DC plan's linear-regulator drop; a part with theta or a heat sink and no P keeps only its own pads.
- **No plan.** Connector pins keep their copper (`tht_pad_kept_wide`); other parts' pads take their own current.
- **Heat-sunk.** If the current needs more than a relief's webs (0.6 × the land), the copper stays wide and `tht_pad_heatsunk` (warn, assembly) says so.
- **Process.** The rule holds in every declared process: THT parts on a reflow board are still wave, selective or hand soldered.

**Exceptions**, each with its reason:
- mounting holes, heat sinks, mechanical parts, fiducials (brief part kinds) and board-only footprints: no solder joint;
- parts the operating facts give at least `heat_min_W` (P_sustained_W), a part heat sink or a thermal resistance (theta_jb/jc/ja: the compiler gives one where a part's heat matters, e.g. an LM7805's TO-220 pins): spreading copper is wanted (pcb-cooling, thermal_vias);
- pads touching a fill of their own net: the zone's own connection (relief or solid) sets the drain, and the plane dominates any track;
- pads or parts in the `tht_wide` setting.

**Settings** (constraints.DEFAULTS; project text variable, then opts, then env): `KAE_THT_NECK` on|off (board-wide), `KAE_THT_WIDE` refs or ref.pad, comma-separated (`J1, J3.2`), kept wide; `KAE_THT_NARROW`, necked even without a plan or over the loss budget. Every pad the neck actually holds back is in the report's hazards as `tht_pad_necked` (info, assembly), one entry per part (at most 8, the rest in one entry) with the pad, net, planned width with and without the neck, current, and the setting that keeps it wide. Results: [2026-11-13-power-copper-tht](../../../bench/results/2026-11-13-power-copper-tht.md).

## Verdict

Not finished. Every board's physics total fell and DRC was never worse, but this is ten boards, one routed attempt each, model-measured physics (no lab measurement), and the router never saw the copper. Next: an A/B through the router's final stage (`power_copper=True`) on the 99-board set with cp1/cpk, and a look at the aifryz +BATT term.

## Code

`kae/src/kae/route/power_copper.py` (`PowerCopper.widen`, `ground_vias`, `stitch`, `run`, `hook`; CLI `python -m kae.route.power_copper IN OUT [--operating F]`), tests `kae/tests/test_route_power_copper.py`, `kae/tests/test_route_power_copper_tht.py`, bridge option `power_copper`.
