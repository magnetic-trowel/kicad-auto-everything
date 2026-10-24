<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Shared setup for the xf experiments

Branch `xf-experiments` (from `claude/keen-wright-mlkjv6`). One worktree on local disk
holds the code, the venv and the git-ignored `kae-work/` (tasks, results, scores). The
physics engine (`kae`, branch `claude/vigilant-mayer-i91rrr`) is a second, detached
worktree beside it named `kae-phys`. Engine and method docs:
[AGENT_BRIEF.md](../pnr/AGENT_BRIEF.md), [joint-pnr-experiments](../../../docs/topics/placement/joint-pnr-experiments.md),
[collapse_joint/RESULTS.md](../collapse_joint/RESULTS.md). The brief's absolute paths
(`/home/user/...`) are from another host; use the worktree root instead.

## Environment

```bash
cd <worktree root>                         # $XF_ROOT
source tools/research/xf_common/env.sh
```

[env.sh](env.sh) activates `bench/.venv` (which sources the kaebench `env.sh`, setting
`KAE_KICAD_WRAP` for KiCad 10.0.7 in Apptainer) and exports:

| Variable | Value | Why |
|---|---|---|
| `APPTAINER_BIND` | parent dir of the worktree | the KiCad container must see boards in it |
| `KAE_SRC` | `<parent>/kae-phys/kae/src` (`XF_PHYS` overrides the worktree) | `pnr/physics.py` imports `kae` from it |
| `KAE_KICAD_PYTHON` | [kicad-python](kicad-python) | one executable that runs KiCad's `python3` (pcbnew) in the container; `run.py`, `physics.py` and `kae` call it |
| `NUMBA_NUM_THREADS`, `OMP_NUM_THREADS`, BLAS threads | 1 | budgets are CPU seconds (`placekit.Clock`); one thread per attempt |
| `NUMBA_CACHE_DIR` | `kae-work/numba-cache` | the router's kernels compile once, not inside every attempt's budget |

The venv has `kaebench` (editable, this branch), `kae` (editable, from `kae-phys`, with
numba), numba, scipy, shapely, ortools, pytest. `kaebench doctor` passes. This branch's
`--command` adapter runs the command with `shell=True` in the attempt's work dir, with no
sandbox, so methods inherit the environment above and can import anything in the venv.

Heavy commands on the shared host go in a CPU/memory scope, and long ones in detached tmux:

```bash
systemd-run --user --scope -p AllowedCPUs=<your cores> -p MemoryMax=32G -p MemoryHigh=28G CMD
tmux new -d -s <tag> 'systemd-run ... CMD > kae-work/<run>.log 2>&1'
```

The scripts below set `ulimit -v 40000000` for KiCad themselves.

## Boards

`kae-work/tasks/` holds all 112 boards of `bench/suites/qualified-kicad-10.0.7.txt`
(manifest `bench/manifests/candidates.jsonl`), prepared by this branch's `kaebench prepare`
(locked footprints stay in place in place tasks). 112/112 qualified: 13 A, 20 B, 79 C.
Nothing was downloaded: [seed_cache.py](seed_cache.py) filled `kae-work/cache/` from the
local board corpus, accepting a board only if its sha256 equals the manifest's
`pcb_sha256` (112/112 matched). Rules, splits and qualification match an independent
network-fetched prepare of the same boards.

| Suite | Boards | Contents |
|---|---|---|
| `kae-work/ab33.txt` | 33 | every qualified A/B board (13 A, 20 B) |
| `kae-work/dev6.txt` | 6 | dev boards (2 A, 4 B), all in ab33 |
| `kae-work/phys10.txt` | 10 | boards with physics structures (1 A, 9 B), all in ab33 |

Place-task input: `kae-work/tasks/<id>/place/input/board.kicad_pcb`.

## Run and score

```bash
kae-work/runext.sh SPEC NAME BUDGET SUITE JOBS [SEEDS=3]
kae-work/score.sh RUN [RUN ...]
```

Both are thin wrappers for [runext.sh](runext.sh) and [score.sh](score.sh) here.

- **runext.sh** runs `kaebench run --adapter x-NAME --command "exec python
  tools/research/pnr/run.py SPEC {input} {output} --budget BUDGET --seed {attempt}" --kinds
  place --probe self -k SEEDS --timeout BUDGET*6+120 -j JOBS --only @SUITE --name NAME`.
  SPEC is `/abs/path/module.py:function`. `exec` makes the method the shell's process, so
  the harness timeout kills it. Results: `kae-work/results/NAME/x-NAME/place/<id>/attempt-<seed>/`.
  The attempt's `work/` (with `pnr.log`) is deleted afterwards; to debug one board, run
  `python tools/research/pnr/run.py SPEC IN OUT_DIR/board.kicad_pcb --budget 60` and read
  `OUT_DIR/pnr.log`.
- **score.sh** writes `kae-work/score/NAME.md` (NAME = the runs joined by `+`, or
  `$SCORE_NAME`), holding three parts:
  - `pnr/compare.py`: seed 0, with legal, clean, completion, length and vias on boards
    that every run completed, and DRC error types;
  - [seeds.py](seeds.py): mean ± sd over seeds and clean best-of-k;
  - physics, via [physics_score_xf.py](physics_score_xf.py): `pnr_phys/physics_score.py`
    on `$PHYS_SUITE` (default phys10), seed 0. It writes `kae-work/score/NAME-phys.md`
    and `NAME-phys/`. `NO_PHYS=1` skips it.

  The wrapper only re-points physics_score's hard-coded work directory at this worktree.
- **Jobs.** Each attempt is one Python thread, plus KiCad DRC threads at scoring. On 24
  cores, use about 20 workers in total (e.g. 4 runs × `-j 5`). A/B boards need little
  memory.

Smoke test (`jc`, budget 10, 1 board): attempt ok, scored by kicad-cli. `score.sh` gave
DRC, seed and physics tables, and the physics engine loaded (human place 10.80, routed 4.95
on paw3395).

## Baselines (ab33, budget 120 CPU-s, 3 seeds)

Runs: `kae-work/results/xf-base-{jc,jc_lv_nopol,combo,combo_lv}-ab33` (4 runs in parallel at
`-j 5`, about 75 min wall in total; mean attempt 101-118 s). Full tables are in
`kae-work/score/baselines.md` (git-ignored). Seed 0 is compared via `compare.py`. Length and
vias are summed over the 23 boards that every run completed. Physics is method/human (gmean)
on phys10, seed 0: "fast" is the place terms total, "routed" is board physics on the real copper.

| Run | Legal | Clean | Completion | Length (mm) | Vias | Clean, 3 seeds | Clean best-of-3 | Fast phys | Routed phys |
|---|---|---|---|---|---|---|---|---|---|
| `jc` | **0.909** | 0.636 | 0.892 | 3105 | 76 | **0.657 ± 0.035** | **0.727** | **1.08** | **0.88** |
| `jc_lv_nopol` | 0.879 | **0.667** | **0.896** | 3152 | 74 | 0.616 ± 0.046 | 0.697 | 2.31 | 1.16 |
| `combo` | 0.818 | 0.545 | 0.893 | **3078** | **59** | 0.566 ± 0.017 | 0.636 | 1.12 | 1.25 |
| `combo_lv` | 0.848 | 0.636 | 0.894 | 3252 | 66 | 0.636 ± 0.000 | 0.667 | 2.82 | 1.18 |

- **Two boards fail in every attempt of every method.** On `azonenberg-dumptruck-emmc-interposer` and
  `pcbcorpus-fyralabs-suzyqboard-suzyqboard` the engine raises "board has no outline" in
  `World`, so the method never runs. They count as not legal, not clean and completion 0, which
  caps ab33 at 31/33 (0.939).
- **Seed spread is about as large as the gaps between methods.** Clean varies by up to 0.05
  between seeds. Compare new methods on the 3-seed mean or best-of-3, not on seed 0 alone.
- **The numbers differ from `collapse_joint/RESULTS.md`, which used one seed, another host and
  another prepare.** That file reports jc fast physics 0.82 and routed 1.05; this setup gives
  1.08 and 0.88. Compare only against the runs above.
- **The DRC errors that remain** are mostly `solder_mask_bridge`, `shorting_items`,
  `starved_thermal`, `items_not_allowed` and `silk_overlap`. See `compare.py`'s
  top-errors column.
