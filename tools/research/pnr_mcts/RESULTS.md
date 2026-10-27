<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Tree search over grow-style place-and-route (tag `mcts`, ideas 7 and 8)

## Idea
`methods.grow` is one greedy path through a tree. Levels are parts (growth order) and
branches are candidate poses scored by real routing. Here the tree is searched with beam
search and with AlphaGo-style UCT (MCTS routing: He & Bao 2020).

## Mechanism (`mcts.py`, `fastcand.py`)
- **Node switching**: a node keeps its poses plus a shallow copy of the routes; path arrays
  are never mutated, so nodes can share them. `switch` diffs states and moves or re-stamps
  only what changed, in 0.1–0.5 ms. One expansion (place, then 4 PathFinder iterations)
  takes 2–90 ms, so re-playing a path would cost 2–3 orders of magnitude more.
- **`fastcand`** returns the same candidates as `Kit.candidates` 4–6× faster. It skips the
  FFT legal map: cells are taken in HPWL order and tested for legality one by one in numba.
- **`beam`** (B=4, K=6 per rotation): a child's score is its routed cost plus a look-ahead
  (greedy HPWL of the next 2 parts, ×1.3, with a penalty when a part has no legal spot).
  The 2 best final boards get a full PathFinder.
- **`mcts`**: rolling-horizon UCT. Each part gets an equal CPU slice, then the root commits
  to a child.
  - Progressive widening ceil(1.5·N^0.5), with a fading prior from the child's routed cost.
  - Rollout: greedy HPWL placement, then 3 PathFinder iterations.
- **`grow_wide`**: the greedy ablation (same score, K=24).
- **`phys_w`** adds phys_w × the kae.physics place terms to every node score, with unplaced
  parts parked at the board centre. Parts left unplaced go through the engine's ripple
  legalizer.

## Results
Engine v5, 120 CPU-s, seed 0. Machine load was 9–14 on 4 cores, so wall time ≈ 2–3× CPU.

**All 33 boards** (beam and grow_wide with phys_w=2; the term is zero on the 23 boards with
no physics structure). Length is summed over the 21 boards where every run completed.

| run | legal | clean | completion | length | vias | wall s |
|---|---|---|---|---|---|---|
| pnr-seq-v5 | 0.788 | 0.545 | 0.863 | 3327 | 54 | 58 |
| pnr-grow-v5 | 0.788 | 0.545 | 0.861 | 3274 | 35 | 74 |
| mcts-grow_wide-ab33-p2-v5 | 0.788 | 0.515 | 0.868 | 3278 | 42 | 83 |
| **mcts-beam-ab33-p2-v5** | **0.818** | 0.545 | **0.891** | **3012** | **32** | 192 |

Beam against grow_wide, per board: completion better on 5 boards, worse on 2; shorter on 16
of 22, longer on 6.

**dev6** (phys_w=0), with length summed over the 3 boards every run completed:

| run | completion | length |
|---|---|---|
| seq | 0.904 | 624 |
| grow_wide | 0.953 | 631 |
| beam | 0.954 | 554 |
| mcts | 0.963 | 541 |

Clean: 0.667 for all.

**Physics on the 10 boards that have structures** (`physics_score.py`, ×human, geometric mean):

| run | place φ | capped-u | routed |
|---|---|---|---|
| pnr-seq-v5 | 4.05 | 1.45 | 1.39 |
| pnr-grow-v5 | 7.35 | 1.77 | 1.37 |
| pnr-seq_phys-v5 | 1.52 | 1.20 | 1.26 |
| grow_wide p2 | 2.45 | 1.32 | 1.22 |
| **beam p2** | **0.98** | **1.01** | **1.14** |
| mcts p2 | 1.74 | 1.17 | 1.18 |

(grow_phys/anneal_phys v5 unfinished.)

## What failed
- **More greedy candidates do nothing.** K=24 scored the same as K=6, and grow_wide runs
  out of candidates long before its budget (83 s wall). The gain comes from keeping
  alternatives *across* steps.
- **MCTS gets too few rollouts.** Dense boards allow only about 8–10 iterations per part.
  The first version committed on rollout value alone and lost to greedy on paw3395. The
  routed-cost prior fixed that, but MCTS still trails beam on legality and physics at about
  1.6× its wall time.
- **Clean rate did not move.** Its failures come from engine pad-clearance gaps, thermal
  spokes and DRC types the score never sees. Beam's denser boards also produce more
  `silk_overlap` (52 vs 28).

## Verdict: **merit (moderate)**
At equal CPU, search width beats greedy on the same objective:
- completion +2.3 points;
- wire −8 %, with fewer vias;
- legal +3 points;
- with the physics term, place φ 0.98 vs 2.45 × human, the best of every run measured.

It does not raise clean. Evidence: one seed, 33 boards, 10 of them with physics structures.

**Next step:** run beam with phys_w=2 over 3 seeds against grow_phys and anneal_phys.
Then branch on which part goes next, and add the DRC-failure types to the node score.
