# Sequential controls: seq, seq_margin, grow

**Status:** `seq` is the control; `seq_margin` did not work; `grow` did not work alone (useful inside beam search).
**First published:** 2026-10-24, commit [44831ff](https://github.com/magnetic-trowel/kicad-auto-everything/commit/44831ff3f802b1758b9c1299e0ae0b212d581f9a) on branch `claude/keen-wright-mlkjv6`.

Scope: the place-for-length-then-route baselines every joint method is compared with, and two simple routing-aware variants. Not here: v7 `seq` numbers -> [combo.md](combo.md#results); physics variant `seq_phys` -> [physics-objective.md](physics-objective.md).
Keys: seq, control, seq_margin, grow, grow_phys, growth order, ripple legalizer, best-response HPWL descent, idea 6

## Idea and how it works

### seq (control)
1. Mechanical parts (no nets) go to the farthest free spots first.
2. Other parts placed greedily in growth order (most-connected first), each at its best legal HPWL pose from `Kit.legal_map` × `hpwl_map`; a ripple legalizer evicts smaller overlapped parts (bounded depth) when a part has no legal spot.
3. Best-response HPWL coordinate descent: each part in turn jumps to its best legal HPWL pose.
4. PathFinder routes everything ([engine.md](engine.md)).

### seq_margin (control: "is it just room?")
`seq` with each part's keep-out grown a priori by a margin scaling with its pin count.

### grow (idea 6: place one part, route it, next)
Parts in growth order; for each, K candidate poses scored by actually routing the nets the part completes and re-routing nets its pads now block; keep the best, place the next. `grow_phys` adds `phys_w` · Δphysics to the candidate score.

## What we tried

v5 era (ab33, place tasks with the self probe, 120 CPU-s, **1 seed**; `seq` also 3 seeds); v7: `seq` as control of every joint run, 3 seeds ([eras](README.md#eras-and-caveats)).

## Results

v5, ab33, seed 0 ([drc-v5-ab33.md](../../../tools/research/pnr/results/drc-v5-ab33.md), [drc-objectives-v5.md](../../../tools/research/pnr/results/drc-objectives-v5.md)):

| run | legal | clean | completion | length mm (boards) | vias |
|---|---|---|---|---|---|
| seq | 0.788 | 0.545 | 0.863 | 3327 (21) | 54 |
| grow | 0.788 | 0.545 | 0.861 | 3274 (21) | 35 |
| grow_phys | 0.758 | 0.515 | 0.850 | 3253 (21) | 49 |
| seq (20-board length set) | 0.788 | 0.545 | 0.863 | 3117 (20) | 40 |
| seq_margin | 0.727 | 0.545 | 0.860 | 3703 (20) | 43 |

- `seq`, 3 seeds (v5): clean 0.545 / 0.545 / 0.576, completion 0.863 / 0.850 / 0.854 ([seeds-v5-ab33.md](../../../tools/research/pnr/results/seeds-v5-ab33.md)).
- Place physics (phys10, v5) × human: `grow` 7.35, `seq_margin` 4.30; `seq` → [physics-objective.md](physics-objective.md#results).
- `seq_margin`: +19% copper vs `seq` on the same 20 boards; fails dense boards. On harness v3 it had shown clean 0.49 vs 0.39 at +29% copper, which did not survive the legality fixes ([scorecard.md](../../ideas/original/scorecard.md)).

## Verdict

- `seq`: reference point; its v7 numbers are the bar for every v7 page. Merit arm (control).
- **seq_margin: no merit.** Room alone does not make placements routable; it costs copper and legality on dense boards.
- **grow: no merit alone.** Greedy commit-as-you-go routes the same as `seq`: the router repairs what the placement order would have avoided. Its step, with alternatives kept across steps, is what makes [beam search](tree-search.md) work.

## Code

[`tools/research/pnr/methods.py`](../../../tools/research/pnr/methods.py): `seq`, `seq_margin`, `grow`; [`methods_phys.py`](../../../tools/research/pnr/methods_phys.py): `grow_phys`. Run: `run.py tools/research/pnr/methods.py:seq IN OUT --budget 120 --seed 0`.

## Related

[engine.md](engine.md), [tree-search.md](tree-search.md), [forces-and-fields.md](forces-and-fields.md).
