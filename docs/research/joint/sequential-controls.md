# Sequential controls: seq, seq_margin, grow

**Status:** `seq` is the control; `seq_margin` did not work; `grow` did not work alone (useful inside beam search).
**First published:** 2026-10-24, commit [44831ff](https://github.com/magnetic-trowel/kicad-auto-everything/commit/44831ff3f802b1758b9c1299e0ae0b212d581f9a) on branch `claude/keen-wright-mlkjv6`.

The baselines every joint method is compared with: place for wire length, then route. Two simple
attempts to make the placement routing-aware (spacing margins, routing each part as it is placed)
did not beat the plain control.

## Idea and how it works

### seq (control)
1. Mechanical parts (no nets) go to the farthest free spots first.
2. The other parts are placed greedily in growth order (most-connected first), each at its best legal
   HPWL pose from `Kit.legal_map` × `hpwl_map`. A ripple legalizer evicts smaller overlapped parts
   (bounded depth) when a part has no legal spot.
3. Best-response HPWL coordinate descent: each part in turn jumps to its best legal HPWL pose.
4. PathFinder routes everything ([engine.md](engine.md)).

### seq_margin (control: "is it just room?")
As `seq`, but each part's keep-out is grown a priori by a margin that scales with its pin count, to
leave routing room.

### grow (idea 6: place one part, route it, next)
Parts in growth order. For each part, K candidate poses are scored by actually routing the nets the
part completes, and re-routing nets its pads now block. The best pose is kept and the next part is
placed. `grow_phys` adds `phys_w` · Δphysics to the candidate score
([physics-objective.md](physics-objective.md)).

## What we tried

v5 era: ab33, place tasks with the self probe, engine v5, 120 CPU-s, **1 seed** (`seq` also 3 seeds).
v7 era: `seq` as the control of every joint run, 3 seeds. The eras are not comparable
([engine.md](engine.md#what-we-tried)).

## Results

v5, ab33, seed 0 ([drc-v5-ab33.md](../../../tools/research/pnr/results/drc-v5-ab33.md),
[drc-objectives-v5.md](../../../tools/research/pnr/results/drc-objectives-v5.md)):

| run | legal | clean | completion | length mm (boards) | vias |
|---|---|---|---|---|---|
| seq | 0.788 | 0.545 | 0.863 | 3327 (21) | 54 |
| grow | 0.788 | 0.545 | 0.861 | 3274 (21) | 35 |
| grow_phys | 0.758 | 0.515 | 0.850 | 3253 (21) | 49 |
| seq (20-board length set) | 0.788 | 0.545 | 0.863 | 3117 (20) | 40 |
| seq_margin | 0.727 | 0.545 | 0.860 | 3703 (20) | 43 |

- `seq` over 3 seeds (v5): clean 0.545 / 0.545 / 0.576, completion 0.863 / 0.850 / 0.854
  ([seeds-v5-ab33.md](../../../tools/research/pnr/results/seeds-v5-ab33.md)).
- `seq` in v7 (28 boards, 3 seeds): legal 0.893, clean 0.607 ± 0.036, completion 0.904
  ([v7-baselines.md](../../../tools/research/pnr/results/v7-baselines.md)).
- `grow` place physics 7.35× human vs `seq` 4.05× (phys10, v5).
- `seq_margin`: +19% copper vs `seq` on the same 20 boards in v5; on harness v3 it had shown clean 0.49 vs
  0.39 at +29% copper, which did not survive the legality fixes ([scorecard.md](../../ideas/original/scorecard.md)).
  It fails dense boards; place physics 4.30× human.

## Verdict

- `seq` is the reference point; its v7 numbers are the bar for every v7 page.
- **seq_margin: no merit.** Room alone does not make placements routable; it costs copper and
  legality on dense boards.
- **grow: no merit alone.** Greedy commit-as-you-go routes the same as `seq`; the router repairs what
  the placement order would have avoided. Its step, kept with alternatives across steps, is what makes
  beam search work ([tree-search.md](tree-search.md)).

`seq` is an arm of the merit list (as the control); the 500-board comparison
(`merit-500r3` / `merit-500r3k`) is running. Results on the 500-board comparison: pending.
`seq_margin` and `grow` are not merit arms.

## Code

[`tools/research/pnr/methods.py`](../../../tools/research/pnr/methods.py): `seq`, `seq_margin`, `grow`;
[`methods_phys.py`](../../../tools/research/pnr/methods_phys.py): `grow_phys`. Run as
`run.py tools/research/pnr/methods.py:seq IN OUT --budget 120 --seed 0`.

## Related

[engine.md](engine.md), [tree-search.md](tree-search.md), [forces-and-fields.md](forces-and-fields.md).
