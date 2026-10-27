# kae fixed mechanical interface: classifier and baselines

**Status:** worked (classifier); baselines measured, our own fixed-interface results pending.
**First published:** 2026-10-24, commit [e7dd229](https://github.com/magnetic-trowel/kicad-auto-everything/commit/e7dd22905ca8c03c0c16fbc8eaf404b67bb8d420) on branch `claude/vigilant-mayer-i91rrr` (harness rule copy [8932ffc](https://github.com/magnetic-trowel/kicad-auto-everything/commit/8932ffcdd868db1d7b496f001fc6c7252bbdeb51), parity [085f1db](https://github.com/magnetic-trowel/kicad-auto-everything/commit/085f1dbdb48bd6aaf4809612c4aee1389997ad83)).

Moving connectors, mounting holes and user-facing parts makes a placement easier but is not something a designer can accept: the enclosure fixes them. A rule-based classifier marks those footprints as fixed; the benchmark's `place-fixed` and `joint-fixed` task kinds use the same rules. The classifier agrees with the harness on all 112 boards. Under the fixed interface, the human placement routed by stock Freerouting is clean on 17% of boards.

## Idea and how it works

**Classifier** (`place/fixed.py`, `place/mech_rules.py`). Ordered first-match rules give each footprint one class:
- **connector**;
- **mounting**: holes, standoffs, fiducials, footprints with only NPTH pads;
- **user**: switches including key switches, buttons, panel pots and encoders, displays, THT, light-pipe and bar LEDs, buzzers;
- **free**: test points, jumpers, net ties, trimmers (including `_trim` pots), IC and SIMM sockets, SMD LEDs, batteries, debug headers (by name, or by nets: <= 20 pads carrying one programming interface such as JTAG, SWD or ISP plus <= 2 other signals).

Inputs: library nickname and name, value, description, pad nets, pad counts by PTH, NPTH and SMD. `kae place --fix REF,...` or `--fix-class connectors,mounting,user` holds the parts as fixed obstacles; their nets still pull the free parts. `mech_rules.py` is a byte-identical copy of the harness's rules file (rules version 4, task spec 8) with a drift test, so kae and the scorer cannot disagree on what is movable. The decision itself (which classes stay fixed) is recorded in [status-2026-10-25](../../topics/architecture/status-2026-10-25.md).

**Why.** On free-connector tasks our placer looked better than it is: "placer advantage from moving connectors is not real" ([status-2026-10-25](../../topics/architecture/status-2026-10-25.md), [kae-staged](../joint/kae-staged.md)). An earlier soft term, a connector edge pull calibrated on human boards, was dropped for the hard rule ([kae-routability-estimators](kae-routability-estimators.md)).

## What we tried

- Classifier parity with the harness on all 112 suite boards.
- An early 6-board test with an earlier roles-based classifier (fixed vs free interface, placement then routing).
- Baselines for the new task kinds at harness [814ba9b](https://github.com/magnetic-trowel/kicad-auto-everything/commit/814ba9b32ec2df099b90a4569425347f769cf9aa): 112 boards, task spec 8, k = 1, 900 s.

## Results

| measure | result | source |
|---|---|---|
| classifier vs harness, 112 boards | 0 differences; 637 connectors (102 boards), 342 mounting (72), 407 user parts (61) | [kae-place](../../topics/placement/kae-place.md) |
| early 6-board test (earlier classifier) | fixed interface helps paw3395 (11 -> 2 open) and sdtv2csi (26 -> 12), hurts eurorack-saturation (9 -> 24 open, 28 parts pinned); physics <= human on all six | same |
| noop placement, `place` / `place-fixed` | legal 0.009 / 0.027 (the 3 boards with 0 movable parts) | [fixed-baselines-814ba9b](../../../bench/results/2026-10-25-fixed-baselines-814ba9b.md) |
| human placement + Freerouting probe, both place kinds | cp1 0.17 (A 0.615, B 0.35, C 0.051); completion 0.809 | same |
| `joint-fixed` reference / human + Freerouting | 1.0 / 0.17 (23.1 errors per board) | same |
| movable footprints per task | median 49.5 (`place`) vs 42 (`place-fixed`) | same |

Our own fixed-interface runs (`fixed-place-d0bdb9d`, `joint-{staged,loop,human-fr,pf}-fixed-d0bdb9d`) were queued and have no results on the branch. They are replaced by the merit methods "kae staged (restarts)" and "kae joint loop (restarts)" on `joint-fixed` (`tools/kaeres/experiments/merit-restart.sh`); the 500-board comparison (experiments merit-500r3 / merit-500r3k) is running. Results on the 500-board comparison: pending.

## Verdict

The classifier worked and is now part of the benchmark definition. The baselines show the fixed-interface task is hard for stock tools (0.17 cp1 for the human placement with Freerouting). Whether our placer and the joint loop beat that under a fixed interface is measured only by the pending merit runs.

## Code

- `kae/src/kae/place/{fixed,mech_rules}.py`; study tool `tools/research/place/fixed.py`; test `kae/tests/test_place_fixed.py`.
- Run: `PYTHONPATH=kae/src python -m kae.cli place IN OUT --fix-class connectors,mounting,user`.

## Related

[kae-placer](kae-placer.md), [kae-staged](../joint/kae-staged.md), [kae-joint-loop](../joint/kae-joint-loop.md).
