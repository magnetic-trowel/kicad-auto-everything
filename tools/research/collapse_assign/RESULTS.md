# Layer collapse as a routing method: results

Idea: [layer-collapse](../../../docs/ideas/original/layer-collapse.md), steps 1, 3 and 5.
Code: `collapse.py` (method), `lifted.py` (placement objective), `analyze.py`,
`placement_study.py`. Engine: `tools/research/pnr` v5, unchanged.

## Method

1. **Lift:** each net is A*-routed alone on one virtual layer (the engine's `astar`
   with `nl=1`), with static blocks and pads only.
   - A cell is hard-blocked if every layer has a foreign pad halo (through-hole pads).
   - It costs +1 if only some layers do (SMD), and those layers are recorded as
     forbidden.
   - The **spread** variant adds 2 rounds of single-layer negotiation, with other
     lifted nets priced at 0.5 per halo. Crossings stay cheap and shared corridors do
     not.
2. **Conflicts:** lifted centrelines closer than the track halo conflict. Paths are cut
   into runs of constant signature (the conflicting nets plus the forbidden layers).
   Runs are the variables.
3. **Assign:** the Hadlock/Pinter via-minimization energy.
   - 10 per layer change between runs or at a junction, and per run end on an SMD pad
     of another layer.
   - 1000 per conflict left on one layer, or per run on a forbidden layer.
   - 5 per plane-net run off its plane layers (4-layer boards).

   CP-SAT solves it exactly, one model per component (Boolean variables at L=2,
   one-hot at L=4). Core search proved the optimum on **33/33** boards (≤ 24 s). The
   heuristic is L-state Potts annealing.
4. **Realize:** within 1 mm of a net's lifted path, every non-assigned layer gets +β in
   `hist` while that net routes (β=3 on critical runs, 1 on free runs). Then the
   engine's `pathfinder(40)` and `legalize` run.

## Route tasks vs `pnr-route-v5`

33 A/B tasks, k=1, KiCad 10.0.7. Clean is cp1 (= cpk). Errors and vias are totals.

| run | A clean | B clean | all | completion | unconnected | errors | vias | length (mm) |
|---|---|---|---|---|---|---|---|---|
| pnr-route-v5 | 0.846 | 0.50 | 0.636 | 0.924 | 66 | 13 | 173 | 8116 |
| collapse-b3 (exact) | 0.769 | 0.50 | 0.606 | 0.937 | 57 | 25 | 186 | 8413 |
| collapse-b3-spread | 0.769 | 0.50 | 0.606 | 0.922 | 68 | 22 | 168 | 8214 |
| collapse-b3-random (control) | **0.923** | 0.50 | 0.667 | 0.917 | 73 | 11 | 193 | 8352 |

The **random-assignment control** (same prior, random layer per run) does at least as
well as the exact assignment. Every variant reshuffles the same marginal boards:
pcbcupid's starved_thermal vanishes under random; dumptruck completion spans
0.52–0.78.

New A failure in both collapse runs: oasis-ledboard, 11 `copper_edge_clearance` errors
on a circular edge (an engine edge-model artifact).

**Predicted vs realized vias:** exact optimum 523 vias + 594 unresolved conflicts
(pure) and 379 + 57 (spread), against 186 and 168 realized vias. Mean per-board error
is 10.2 and 6.4 vias. The router does not keep the lifted shapes: at 2 mm per via it
detours.

## The conflict graph on real boards

- **Size:** median 12 nets, 86 runs and 44 conflict edges (max 26 / 451 / 513).
- **Net graph:** planar on 18/33 boards (25 with spread), bipartite on 11 (12), max
  clique median 4, up to 13.
- **Run conflict graph:** bipartite on only 13/33 (23 with spread). That is the number
  of boards whose 2-layer collapse needs no reshaping.
- **Junctions:** degree ≤ 3 on 32/33 boards, but the full run graph is planar on only
  18 (23). The planar max-cut reduction therefore does not apply in general, and CP-SAT
  replaced it.
- **Corridor sharing:** most pure-lift conflicts are shortest paths sharing a gap
  between pads, not crossings. Spread removes 90% of the unresolved conflicts and 62%
  of the conflict edges.
- **Potts vs exact:** Potts reaches the optimum on 9/33 boards (14 with spread). It
  leaves similar unresolved counts but 62% more vias (849 vs 523), because single-site
  moves cannot flip run chains.

## Lifted conflicts as a placement objective

219 placements: human, plus pnr-seq-v5 and pnr-combo-v5 attempts 0–2, each re-routed by
the same engine. The table shows the mean within-board Spearman ρ, with KiCad-probe
values in brackets:

| predictor | vias | length | len + 2·vias + 20·unrouted |
|---|---|---|---|
| HPWL | 0.15 (0.22) | 0.59 (0.61) | 0.51 |
| lift forced vias | 0.48 (0.43) | 0.49 | 0.42 |
| spread forced vias | **0.54** (0.53) | 0.45 | 0.40 |
| spread cost (lift length + 2·vias + 5·unresolved) | 0.37 | **0.84** (0.83) | **0.85** |

- Nothing predicts unrouted connections (ρ ≈ 0).
- Human placements carry more forced vias: 17.2, against 10.0 (seq) and 10.6 (combo).
  Realized vias show the same order: 5.2, 4.8 and 4.3.
- API: `lifted.lifted_conflicts(world)`; `LiftedConflicts(world).update([pi],
  [old_box])` re-lifts only affected nets (matches a full recompute). Median
  0.1–0.24 s, about one engine PathFinder on these small boards.

## Verdict

- **Routing method: no merit.** The exact layer assignment does no better than a
  random prior. The lifted geometry predicts 2.8× the realized vias, and its conflicts
  are mostly corridor sharing.
- **Placement objective: inconclusive, positive signal.** Spread forced vias and spread
  cost rank placements better than HPWL (ρ 0.54 vs 0.15 for vias, 0.85 vs 0.51 for
  routed cost).

**Next step:** use `LiftedConflicts.update` as the move cost in `anneal`/`descent`, in
place of HPWL. Test it on larger boards, where a PathFinder per move is too slow, and
compare against `pnr-seq-v5`.
