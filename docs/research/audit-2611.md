<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Whole-codebase bug audit (2026-11)

Scope: the whole-codebase bug audit of 2026-11: method, what was wrong per area, what it changed. Not here: per-board results -> [post-audit baselines](routing/post-audit-baselines.md).
Keys: bug audit, utilization double count, relax_bodies, 499 cap, uncapped unconnected, restart judge, task spec 9, score v9, decap_pairs, regulator_vout, static analysis, profiling

**Status:** worked. About 50 confirmed bugs fixed with a regression test each; the post-audit baselines
improve kae staged (−4.6 % open, physics −13 % on load-stable boards; [post-audit-baselines](routing/post-audit-baselines.md)).
**First published:** 2026-11-04. The fixes reached main through branch `place-escape-keepouts` (21bc53d,
merged with `thermal-heatsinks-merge`, PR #24).

## Why

Three bugs found one at a time on a single small board (circuitmonkey chips-0123) each skewed hours of
benchmark runs: the placer's utilization counted a part's overlapping rectangles twice (a 53 %-full board
read 101 %, so it dropped every courtyard-less body and put a capacitor under an SMD electrolytic), a
12-ball wafer-level BGA was taken for a pad ring, and the router could not leave a tight ball at all. So
the whole codebase was audited at once instead.

## How

Seven read-only auditors, one per area, on a frozen copy (b96ee0c): critical router; bridge, rules and
escape planner; placer; physics and EM; board model and circuit comprehension; evaluator, joint loop and
intent; benchmark harness, scoring, restart wrapper and kaeres. Each finding had to be reproduced or
proven by arithmetic on the code and was labelled CONFIRMED or PLAUSIBLE. Static analysis ran beside it:
ruff's bug rules (545 findings, 192 in product code), vulture and pyright (209 errors); a triage found 2
real bugs among them, the rest false positives (closures used within their own loop iteration, numpy
stub noise). Four fixers then worked on separate branches from the same commit (router, placer and
loader, physics inputs, harness and scoring), each fix with a test that fails before it; the scoring
fixes are separate commits that say which results they change.

## What was wrong, by area

**Benchmark harness and scoring** (score v8, v9):
- A project that sets the unconnected check to "ignore" scored every output as fully routed, an empty
  one included (3 qualified boards). Now pcbnew's count, at start and end (score v8).
- The restart wrapper's judge ran DRC with `--severity-error`, missing unconnected items set to
  "warning"; and it read KiCad's report list, which stops at 499, so on big boards it chose between
  attempts blind (polarfire-som: a 206 s attempt kept with 1,306 open where a 1,500 s one leaves 429).
- kaeres looked up existing runs without the task id (a run on an older task spec counted as done);
  report means were over each method's own subset of boards; command methods lost their output when
  the harness timed them out while Freerouting kept its partial result; place-task physics was
  measured on an unrouted board; the off-board check read graphics from every layer as the outline.
- A locked part nudged by under 1 µm passed the placement check and failed the routing one (score v9).

**Placer:**
- Pad inflation ignored the board's minimum clearance; the exact check's mask-bridge prefilter added
  two lists instead of two maxima; a macro's whole outline had to fit one cover rectangle; the compiled
  annealer's legality total went stale after a hash overflow.
- The reference and compiled annealers were checked against each other: 3,000 random moves on 4
  boards agreed to 7e-13.

**Routers:**
- The escape certificate crashed when its LP did not solve, discarding the BGA's escape plan on every
  restart; the critical router counted a connection as routed with no copper where two tight pads'
  escapes met; planes on renamed copper layers were never dropped in repair rounds (24 of 400 corpus
  boards); the same-net via spacing tolerance had its sign inverted; thermal spokes were tried in a
  mirrored y frame.

**Physics inputs and evaluators:**
- The routed-board recheck paired every unpaired decap with the IC's first power pin (C9 on helios
  priced at 6 mm instead of 0.9 mm); regulator voltages were read from footprint sizes and current
  ratings (a TPS7A20285, 2.85 V, read as 1.0 V); a voltage suffix alone made signal nets rails
  (SCK_3V); a missing module value was priced below the cap; intent "min" limits were judged at the
  best corner; an evaluation with no observations scored perfect; inductor, ferrite and via losses were
  not heat; the physics router's A* heuristic was inadmissible and priced hops with one island's current.

**Board loader:** zones inside a footprint took its uuid before uuids were made unique; zero-width
circles and rectangles that pcbnew fills were dropped.

## What it changed

- Task spec 9 (castellated edge pads and 4UCONN connectors are fixed in place-fixed tasks), score v8
  and v9: earlier place-fixed / joint-fixed results and physics numbers are not comparable with later
  ones; [post-audit-baselines](routing/post-audit-baselines.md) re-runs the reference methods.
- kaeres now refuses an experiment whose methods prepare boards with a harness of another task spec
  (a Freerouting method pinned to an old harness had run every job and written nothing).

## Performance, measured alongside

py-spy profiles of kae staged and the bridge on three board sizes: Freerouting (a separate Java process)
takes 40–72 % of wall time, the placer 25–40 %, the last mile 11–29 %. No easy speedup: caching the last
mile's cost rasters would hit 12 % of requests and save about 1 % (measured by instrumenting a run); the
compiled annealer's time shows as Python only because py-spy cannot see into numba.

## Left

The PLAUSIBLE findings not confirmed; wideband evaluations emit no intent observations (they now get no
score instead of a perfect one); solder-mask bridges are not a placement error type (no evidence they
come from placement).
