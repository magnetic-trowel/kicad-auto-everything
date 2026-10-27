# kae place: the placer, what works, what did not

**TL;DR**
- `kae place` is a physics-first placer: a quadratic and CP-SAT seed, a numba simulated
  annealer pricing wire length, the [place terms](../physics/place-terms.md) and soft
  silkscreen/label/channel terms, then an exact polygon legality model and a closed loop
  with KiCad's DRC. On split C it is legal on 72/72 boards, with physics 1,410 against
  the human's 4,392 ([ablation](../../../bench/results/2026-10-24-place-physics-ablation-1ef5bf1.md)). [C]
- Its routability matches the human placement on splits A+B (probe cp1 0.909 for both),
  but not on split C: 30/78 boards route clean against 43/78 with one router attempt
  ([pipeline C](../../../bench/results/2026-10-24-pipeline-c-c9c49d6.md)). [C]
- None of the congestion estimates we built predicts which of our placements routes:
  RUDY, routing channels, pad gaps, crossings, corridor overflow, cut capacity and pour
  fragmentation. Probe-select (routing candidates briefly) helps a little on paw3395 and
  costs placement time; it is off. [C]
- The mechanical interface (connectors, mounting, user-facing parts) is held fixed with
  `--fix-class`, using the benchmark's own place-fixed rules ([mech_rules](../../../bench/src/kaebench/kicad_scripts/mech_rules.py)). [C]
- The human gate (the legality model may not flag a human board KiCad accepts) caught
  every model bug we shipped; run it after any change to `kae.place.exact`. [C]

## Pipeline

Source: [`kae/src/kae/place/`](../../../kae/src/kae/place/), entry `kae place IN OUT`
([cli.py](../../../kae/src/kae/cli.py)), stages in [pipeline.py](../../../kae/src/kae/place/pipeline.py).

| Stage | What it does | Module |
|---|---|---|
| Problem | movable and fixed parts (locked, Edge.Cuts carriers, `--fix`), grid rectangles per rotation, outline cover, fixed copper and text, keepouts | `problem.py` |
| Brief | net roles (ground x0.1, power x0.2) and, with physics, structures: decaps, hot loops, crystals, protection chains ([comprehension](../physics/comprehension.md)) | `stubs.py`, `kae.circuit` |
| Macros | each structure's top-K rigid layouts (CP-SAT), protection-order rules of connector chains | `clusters.py` |
| Seed | quadratic placement, connectors anchored to the nearest edge, spreading; CP-SAT floorplan (NoOverlap2D, 4 rotations, macros with their layouts, HPWL + small displacement) on boards up to `FLOORPLAN_MAX_ITEMS`, bisection spread above | `seed.py`, `cpsat.py` |
| Anneal | numba engine (`engine.py`, Python reference `anneal.py`): HPWL, place terms (utilization priced linearly, saturated at 3x budget), legality ramp, displacement, protection order, soft silk/channel grids, label anchors | `engine.py`, `anneal.py` |
| Legalize | windowed CP-SAT, greedy fallback, then the exact model | `legalize.py`, `_fastlegal.py` |
| Exact closed loop | per-part polygon check; repair moves each offender to the nearest grid-free, exactly clean spot, with eviction, re-seed and lookahead escalation | `exact.py` |
| Order pass | puts protection parts back between connector and protected part within a physics bound | `exact.fix_order` |
| Silk pass | moves the smaller part of each silk conflict within +3% physics and +10% local HPWL | `exact.fix_silk` |
| KiCad loop | kicad-cli DRC on the written board; findings become constraints; repair; rewrite; up to 6 rounds | `cli._kicad_loop`, `exact.kicad_feedback` |

Budgets: the pipeline plans to finish in min(0.85·time − 10 s, 20 s + 3 s per movable
part). The annealer counts CPU seconds; CP-SAT counts wall seconds with `--workers` threads.
On split C the median move rate is 11.7k moves/s
([split C sweep](../../../bench/results/2026-10-23-place-split-c-e171267.md)). Each numba
kernel gets the engine's state tuple by value, so every extra field costs move rate: 12
fields cost about 10%. The label and silk data are therefore packed into two arrays. [C]

### Exact legality model

`ExactModel` (exact.py) checks what KiCad's DRC checks for placement, on the parts' real
shapes:
- courtyard overlaps;
- pad clearances with net-class and pad-local overrides;
- `hole_clearance` and `hole_to_hole`;
- copper-to-edge clearance;
- items in rule areas;
- solder-mask bridges, including mask-only apertures and pad openings over zone fills of
  other nets (from KiCad's `drc_test_provider_solder_mask.cpp`);
- footprint copper and mask graphics;
- board-level copper graphics;
- **board copper text as KiCad's glyph outlines** (pcbnew `TransformTextToPolySet`).

The copper-text check was added after pic-programmer's ZIF socket landed on "1=>>"; it
finds the same 4 pads KiCad flags, and nothing on the 21 human boards that carry copper
text. [C]

### KiCad loop: blame rules and safety net

KiCad's DRC report is turned into constraints that the repair honours
(`exact.kicad_feedback`):
- **Pair separations:** a minimum distance between the two parts KiCad names.
- **Avoid geometry:** a part to keep off a board text or graphic, found by its uuid.
- **Edge clearance growth:** the named part's edge clearance grows by 0.05 mm per report.
  Only the part whose copper KiCad reports is blamed; blaming its neighbour left paw3222
  illegal.
- A finding that involves only fixed parts counts as `fixed_only` and is not the placer's.

Two protections around the loop:
- **Retry:** a kicad-cli run killed by a signal (rc < 0, seen on buspirate5) is run again,
  up to 2 times, on a freshly staged copy.
- **Safety net:** the best placement KiCad has judged (fewest placement errors) is kept.
  If the loop ends worse, or on a repair KiCad never judged, that placement is written
  back (`kicad_written_round`).

Since 2026-10-25 a repair round that moves parts also re-runs the silk pass: on a fixed
pic-programmer, 40 evictions had left 18 silk errors.

### Silkscreen

Silk is checked only where the project makes `silk_overlap` / `silk_over_copper` an
error (KiCad's default is a warning).

**What is modelled:**
- other parts' silk and pad mask openings, on KiCad's own glyph outlines fetched from
  pcbnew (`refine_silk_text`);
- glyphs for each quarter turn of the part, fetched separately: KiCad keeps text readable,
  so a part turned by 180° does not show its texts turned (`silk_text_at`). Before this,
  sonde-xilinx's model saw 1 of KiCad's 5 conflicts; it now sees all of them;
- the overlap threshold `SILK_AREA` is 1e-5 mm². KiCad reports overlaps of 5e-4 mm²: a
  glyph stroke over a silk line.

**Measured:**
- The soft annealer term (`w_silk`, default 1) plus the final pass took KiCad's silk
  errors on the 5 silk-error projects from 224 to 13. [C]
- After the turn fix, pic-programmer and sonde-xilinx place silk-clean and route clean.
  [C]

### Board silk labels

[labels.py](../../../kae/src/kae/place/labels.py) infers, from the task input alone, which
part a board-level silk label names:

| Kind | How it is inferred | Human part within 3 mm of the label |
|---|---|---|
| ref | a token equal to a reference | 17% |
| pin | a connector pad's pin function or net | 68% |
| keyword | PWR, ACT, RESET, ON/OFF beside LEDs and switches | 49% |
| row | a row of numbered labels, matched in order to one part family | **100%** (14 parts, 2 boards) |

Measured by [tools/research/place/labels.py](../../../tools/research/place/labels.py). [C]

The annealer term pulls a part's labelled pads to the label, with a dead zone; along a
numbered row the dead zone is a third of the row's pitch, which keeps the row's order. It
is on by default only for **rows**, the one kind at ≥ 90% precision. On noisecard it puts
7 of 12 labelled LEDs at their labels, at +1.7% physics and +52% HPWL, and routing is
unaffected. [C]

### Fixed parts (`--fix`, `--fix-class`)

`--fix REF,...` and `--fix-class connectors,mounting,user` keep parts at their input pose.
Through the problem's held set they become fixed obstacles like locked parts, and their
nets still pull. [fixed.py](../../../kae/src/kae/place/fixed.py) classifies parts with the
benchmark's place-fixed rules (rules 4, task spec 8). `kae/src/kae/place/mech_rules.py` is a
byte-identical copy of the harness's file, and `kae/tests/test_place_fixed.py` fails when they drift. On all
112 boards kae and the harness agree on every part (0 differences). [C]

Counts on the 112 human boards
([tools/research/place/fixed.py](../../../tools/research/place/fixed.py)):

| Class | Parts (A / B / C) | Boards | Deciding rule (most parts) |
|---|---|---|---|
| connectors | 637 (33 / 43 / 561) | 102 | library 375, name 163 |
| mounting | 342 (21 / 42 / 279) | 72 | library 213, all-NPTH 68 |
| user | 407 (9 / 18 / 380) | 61 | name 310 (switches, keyboard keys) |

Parts freed by an explicit rule: test points 313, jumpers 120, programming/debug headers
36, net ties 28, trimmers 9, SIMM sockets 8, IC sockets 6, microphones 5.

Debug headers are freed by name (JTAG, SWD, Tag-Connect, debug, prog...). A header of at
most 20 pads is also freed by its nets: it carries one programming interface plus at most
2 other signals. Two kinds of net are not counted: nets named for two functions
(`SDC0_D2/JTAG_TCK`) and nets on panel or cable connectors.

Rules 4 carry the user's judgement calls: SIMM sockets, microphone headers and pots valued
`..._trim` are free; NPTH-only parts stay fixed as mounting.

**With the interface held at the human pose** (6 boards, 600 s, one routing; parts chosen by the
earlier roles-based classifier, before the switch to the shared rules):

| Board | Unconnected: human / free / fixed |
|---|---|
| sdtv2csi | 0 / 26 / 12 |
| paw3395 | 0 / 11 / 2 |
| scart-duplicator, noisecard, pic-programmer | 0 / 0 / ≤ 1 |
| eurorack-saturation (28 parts fixed) | 0 / 9 / **24** |

Physics stays at or below the human's on all six. [C]

## Validation method: the human gate

[tools/research/place/humangate.py](../../../tools/research/place/humangate.py) reads each
reference board (human poses) into a placement problem. It runs the exact model on every
part and compares each finding type with KiCad's DRC report of the same board. A type kae
reports where KiCad reports none is a false positive: it would make the placer avoid spots
KiCad allows. Silk is gated the same way where it is an error. The gate must stay at
A 13/13, B 20/20, C 79/79 clean.

Every new rule went through it: text knockout margins, mask-only apertures, copper text,
silk glyphs. The same discipline applied to estimates: an estimate that flags human boards
the human routes fine is not used.

## Negative results

**Congestion estimates do not predict our routing failures.** Measurements on paw3395,
badjeff-pmw3610 and siderakb-pmw3610, our placements against the human's, each routed with
3 router seeds:
- **RUDY** (several variants), **pad gaps**, **net crossings**, **pour access**: none
  separates the boards that fail from those that route.
- **Corridor overflow:** 42 of 109 human boards overflow, and those route.
- **Cut capacity:** failed the human validation (human boards above capacity route).
  Not built.
- **Channel term** (`w_chan`, soft halos so tracks fit between neighbouring parts' pads):
  paw3395 went from 11/10/10 unconnected to 9/9/2 at weight 1 and 2/5/3 at weight 3. That
  is a modest gain, and it was not validated on human boards. Off (`CHAN_W = 0`). [C]

**Pour fragmentation** ([pour.py](../../../kae/src/kae/place/pour.py), a diagnostic, not
in the placer):
- **Method:** each net's fill regions (zone, less other copper plus clearance, opened by
  the minimum width), joined across layers by through-hole pads and vias. It counts the
  pieces holding the net's pads and the connections the router must add.
- **Human baseline, pads only:** 334 of 412 pours need nothing.
- **Our placements, pads only:** every paw3395 and siderakb placement, ours and the
  human's, is one piece, because the islands only appear once tracks exist.
- **With a minimum-spanning-tree track estimate:**
  - Human: 54 of 76 small two-layer pours need nothing.
  - paw3395: the w_chan 3 placement is the most split (6 pads stranded) yet routes among
    the best; two unsplit placements route at 3.7 and 6.7 unconnected.
  - siderakb: the estimate points the wrong way.
- **Routed boards:** the human paw3395 is as fragmented as ours. [C]

**Probe-select** (`--probe-select N`) places N candidates and routes each briefly with
`kae.route.bridge` and last mile. It keeps the one with the fewest open connections, within
10% of the best physics. Options: `--probe-parallel P` probes P at once; `--probe-jitter F`
moves later candidates' seed stage by F × the board span.

On paw3395 (finals routed 900 s with 3 router seeds):

| Run | Mean unconnected over 3 router seeds |
|---|---|
| probe-select 3 | 4.7 |
| w_chan 3 + probe-select 3 | 11.0 |
| w_chan 3 + probe-select 3, jitter 0.15 | 7.7 |
| w_chan 3 + probe-select 5, jitter 0.15 | 3.7 |

For comparison: w_chan 3 alone 3.3, human 0.

Why it is off by default:
- A 90–140 s probe reports 7–20 unconnected, and its ranking does not carry over to the
  900 s route.
- Each candidate gets 46–76 s of placement instead of the full budget.
- The physics slack excluded the best-probing candidate.
- Jitter widens the candidates only a little, because the CP-SAT floorplan pulls varied
  seeds back together. [C]

**Connector edge pull:** human boards put USB (100%), barrel (100%) and audio (100%) at the
edge, but headers only 69% and mounting holes 84%. The term was dropped when the user
decided the interface stays fixed. [C]

**Free angles** (`--angles STEP`, parts at any multiple of STEP; CP-SAT stays on right
angles): the paired test tool is
[anglepolish.py](../../../tools/research/place/anglepolish.py), which starts both arms from
the same legal placement. Its numbers are not recorded in `bench/results`. Re-run it before
relying on free angles; the option is off by default.

**Other findings:**
- **pingdevkit's `GetRectangleWidth` assert** is printed by pcbnew's zone fill on the human
  boards too. The split-C score error was the pcbnew process ending, not our writer.
- **Probe DRC errors** on split C: the silk errors were placement errors that survived,
  and are fixed by the turned-glyph model. The others (mask bridge, hole and edge
  clearance) did not appear on the 8 boards re-run locally.

## Open problems

- **Dense sensor boards** (paw3395, badjeff-pmw3610, siderakb-pmw3610): our placements
  put caps in the strips between the sensor's pins and the edge. Freerouting's first pass
  then runs about 500 s, against 13–155 s on the human's. With the connectors fixed,
  paw3395 drops to 2 unconnected on one routing. We have no estimate that predicts these
  failures; the routing probe is the only signal, and it is noisy.
- **Split-C routability:** 15 boards route clean only on the human placement
  ([pipeline C](../../../bench/results/2026-10-24-pipeline-c-c9c49d6.md)). Locally, 4 of
  8 re-run boards routed clean on ours, 2 failed only on silk (now fixed), and 2 failed on
  routing: eurorack (HPWL 0.76× human, crowded) and sdtv2csi (HPWL 1.22×). The 4-way
  routing portfolio may close some of the rest
  ([portfolio](../../../bench/results/2026-10-24-portfolio-ab-0465818.md)).
- **Fixed interface on eurorack:** with 28 parts pinned, the free parts route worse (24
  unconnected) than either free placement or the human's.

## Sources

Results:
- [physics ablation](../../../bench/results/2026-10-24-place-physics-ablation-1ef5bf1.md)
- [routability probe](../../../bench/results/2026-10-24-place-routability-probe-1ef5bf1.md)
- [pipeline A+B](../../../bench/results/2026-10-24-pipeline-ab-c9c49d6.md)
- [pipeline C](../../../bench/results/2026-10-24-pipeline-c-c9c49d6.md)
- [split C sweep](../../../bench/results/2026-10-23-place-split-c-e171267.md)
- [full benchmark](../../../bench/results/2026-10-24-full-benchmark-03096d9.md)

Study tools, under [`tools/research/place/`](../../../tools/research/place/):
- `humangate.py`, `labels.py`, `fixed.py`, `anglepolish.py`, `csweep.py`

Code: `kae/src/kae/place/`.

See also: [place terms](../physics/place-terms.md), [legalization](legalization.md),
[strategy candidates](strategy-candidates.md),
[Freerouting bridge](../routing/freerouting-constraint-bridge.md),
[status 2026-10-25](../architecture/status-2026-10-25.md).
