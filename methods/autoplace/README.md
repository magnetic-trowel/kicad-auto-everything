# autoplace: experimental placer for kaebench place tasks

Research-quality placers that plug into `kaebench run --kinds place --probe freerouting`
through `--command`. Results and interpretation:
[docs/topics/placement/autoplace-experiments-2026-10.md](../../docs/topics/placement/autoplace-experiments-2026-10.md).

| File | What it does |
|---|---|
| `kicad_helper.py` | pcbnew side (KiCad's Python): extract outline, keep-outs, locked and board-level copper/mask obstacles, and each free footprint's rectangle and pad offsets at 0/90/180/270° read from pcbnew; write poses; report unrouted nets |
| `place.py` | solver and driver (numpy, scipy, shapely): `rand`, `greedy`, `sa`, `sa-best`, `sa-loop` |
| `summarize.py` | per-board and aggregate comparison of place runs |

Algorithms:
- `rand`: random poses, then the legalizer.
- `greedy`: connectivity-ordered constructive placement on a grid with 4 rotations.
- `sa`: greedy seed, then simulated annealing on weighted HPWL (pour nets × 0.1, power × 0.3)
  + ratsnest (MST) crossings + overlap/outside penalty, with a √pins escape halo that shrinks as
  the board fills; then the legalizer. Budgets are move counts (1,500 × parts).
- `sa-best`: up to N annealing seeds; each is routed in the loop (Freerouting, 4 passes) and
  DRC'd under the board's own rules; the best by (unrouted, errors, vias, length) wins, stopping
  at the first clean one.
- `sa-loop`: KRT-style repair: re-anneal only the parts on unrouted nets or named in DRC errors,
  failed nets weighted 3×, blamed parts get more halo; keep a round only if it ranks better,
  else revert and widen the move radius.

## Setup

The placer needs a Python with numpy, scipy and shapely that the kaebench sandbox can read
(anything under `KAE_HOME`, plus `--sandbox-ro` for the interpreter):

```bash
uv venv ~/.cache/kaebench/placer-venv --python 3.12
VIRTUAL_ENV=~/.cache/kaebench/placer-venv uv pip install numpy scipy shapely
```

## Run

```bash
PY=~/.cache/kaebench/placer-venv/bin/python
kaebench run --adapter sa --kinds place --probe freerouting -j 8 --timeout 600 \
  --sandbox-ro ~/.local/share/uv/python \
  --command "$PY $PWD/methods/autoplace/place.py --algo sa --input {input} --output {output} --workdir {workdir} --attempt {attempt} --timeout {timeout}" \
  --only @subset.txt --name sa
python methods/autoplace/summarize.py kae-work/results ref sa
```

`--seed N` varies every random choice without changing the probe (the attempt index also
changes the probe's Freerouting pass count). Run batches from a frozen copy of this directory,
since each attempt imports the code when it starts.

## Known gaps

- No mechanical intent: unlocked mounting holes and edge connectors move freely, and
  connectors that overhang the edge in the human design end up inside the board.
- Rectangles only (courtyard bbox ∪ pads ∪ copper graphics); no side changes.
- No regularity (grids of LEDs or switches are scattered).
