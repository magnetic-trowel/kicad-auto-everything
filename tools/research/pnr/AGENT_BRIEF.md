# Brief for agents building joint place-and-route approaches

Goal: test whether a *structurally different* approach to placing and routing a PCB
**simultaneously or interleaved** has merit. Build it on the shared grid engine in
`tools/research/pnr/`, run it on real boards, and report honestly (a clear "no merit"
is a useful result).

## Read first (short)
- `docs/ideas/original/joint-pnr.md` — the 42-idea catalog (your idea is one of them).
- `research_notes/joint-pnr/literature-survey.md` — mechanisms from other fields.
- The engine: `world.py`, `router.py`, `placekit.py`, `methods.py` in `tools/research/pnr/`.

## The engine in one screen
- `World(data, g=0.1)`: grid (0.1 mm cells) per copper layer. Clearance via "halo" stamps:
  `occT[net, layer, y, x]` / `occV[...]` per-net counts, `DT`/`DV` = number of distinct
  nets per cell; foreign nets at a cell for net n = `DT - (occT[n] > 0)`. `world.hist` is the
  PathFinder history cost. `world.court[side]` counts courtyard (+pad keep-out) coverage.
- Parts: `world.parts[i]` (`.locked`, `.side`, `.pads`, `.area`), pose = `(cx, cy, ri)` origin
  cell + rotation index (0/90/180/270). `world.place(i, cx, cy, ri)`, `world.unplace(i)`,
  `world.pose`, `world.part_raster(part, ri)` (cached cell offsets: pads `cu`/`hT`/`hV`,
  `court`), `world.pad_world(i, k)`, `world.hpwl()`, `world.net_pins[net] = [(part, pad)]`.
- `Router(world)`: `route_net(n, hard=False)`, `rip(n)`, `pathfinder(nets=None, iters=30)`
  (negotiated congestion, then `legalize`: conflicted nets re-routed hard or dropped),
  `routes[n]` = list of (k,3) int arrays of (layer, y, x) cells, `unrouted[n]`, `stats()`,
  `export()`. Output copper is always legal by construction (KiCad DRC confirms).
- `Kit(world, router)` (placekit.py): `legal_map(i, ri)` (bool map of legal origins via FFT),
  `overlap_map`, `hpwl_map(i, ri)` (HPWL of the part's nets for every origin), `candidates`,
  `snapshot/restore` of routes, `reroute(nets)`, `total_cost()` (routed mm + 2 mm/via + a
  perimeter per unrouted connection), `movable()`.
- `methods.py` has the controls and the first joint methods: `seq` (HPWL place, then route —
  the control to beat), `seq_margin`, `grow`, `anneal`, `tension`, `negotiate`, `bloat`,
  `repair`. Reuse helpers (`_place_fixed`, `place_mechanical`, `growth_order`,
  `greedy_place`, `descent`) instead of re-writing them.
- A method is `fn(world, seed=0, budget=300, log=print, **kw) -> Router`; it must place every
  movable part (legal placement) and leave routes in the router.

## Run and score (KiCad DRC is the only judge)
```bash
source bench/.venv/bin/activate          # in /home/user/kicad-auto-everything
# one board, quick:
python tools/research/pnr/run.py /abs/path/to/your_module.py:your_fn IN.kicad_pcb OUT_DIR/board.kicad_pcb --budget 60
# through the harness (place tasks, self-routed copper scored by kicad-cli):
kae-work/runext.sh /abs/path/to/your_module.py:your_fn <tag>-dev6-v1 120 kae-work/dev6.txt 1
python tools/research/pnr/compare.py kae-work/results/pnr-seq-v3 kae-work/results/<tag>-dev6-v1
```
Task inputs: `kae-work/tasks/<id>/place/input/board.kicad_pcb`. Suites: `kae-work/dev6.txt`
(6 dev boards), `kae-work/ab33.txt` (all 33 qualified A+B boards). Per-attempt artifacts:
`kae-work/results/<run>/x-<run>/place/<id>/attempt-0/` (`attempt.json`, `adapter.log`,
`probe/score/drc.json`). Metrics: `legal` (placement), `clean` (legal + copper fully
connected + no DRC errors), `completion`, routed length, vias.

Baselines (same engine, same boards): `kae-work/results/pnr-seq-v3` (place-then-route
control), `pnr-grow-v3`, `pnr-anneal-v3`, ... (a batch is running; use what exists), and
`pnr-route-v3` (the human placement routed by the same router: A clean 0.85, B 0.50).

## Rules
- Do NOT edit anything in `tools/research/pnr/` or `bench/` (a benchmark batch is running
  from them). Put your code in `tools/research/pnr_<tag>/` (new files, SPDX header
  `GPL-3.0-or-later`, match the style of the existing lab code). Import the engine with
  `sys.path.insert(0, "/home/user/kicad-auto-everything/tools/research/pnr")`.
- Never change scoring. No git commits or pushes; the lead commits.
- CPU: the machine has 4 cores and a batch already uses them. Develop on one board at a
  time and dev6 with `-j 1`; a final all-33 run may use `-j 2` with budget 120 s. Time-budgeted
  methods see less CPU under load: say so when comparing.
- Run names start with your tag (`<tag>-...`). Long runs: `tmux new -d -s <tag> '...'`.

## Deliverable
`tools/research/pnr_<tag>/RESULTS.md` (<= 700 words): the idea and its source domain, the
mechanism as built, what you tried (including what failed), a table vs `pnr-seq-v3` on the
same boards (legal, clean, completion, length, vias, time), and a verdict: merit / no merit /
inconclusive, with the next step you would take. Your final message: the same, shorter.
