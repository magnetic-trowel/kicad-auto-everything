<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Shared setup for the xf experiments (round 2)

Branch `xf-experiments`, merged with `claude/keen-wright-mlkjv6` at harness score v7, task
spec 6 and pnr engine v6.1. One worktree on local disk holds the code, the venv and the
git-ignored work dirs. The physics engine (`kae`, branch `claude/vigilant-mayer-i91rrr`) is
a second, detached worktree beside it named `kae-phys`. Engine and method docs:
[AGENT_BRIEF.md](../pnr/AGENT_BRIEF.md), [joint-pnr-experiments](../../../docs/topics/placement/joint-pnr-experiments.md),
[collapse_joint/RESULTS.md](../collapse_joint/RESULTS.md). The brief's absolute paths
(`/home/user/...`) are from another host; use the worktree root instead.

**Round 2 changes the protocol.** Methods run as `--kinds joint` tasks: the input is the
place task's input, and one output holds placement and routing. The harness scores both
together (`score_joint_task`), in the kaebench sandbox. Round 1 ran `--kinds place --probe
self` on an older harness, engine and prepare. Its results stay in `kae-work/`, and they
are not comparable with round 2.

## Environment

```bash
cd <worktree root>                         # $XF_ROOT
source tools/research/xf_common/env.sh     # XF_WORK=<root>/kae-work2 unless set
```

[env.sh](env.sh) activates `bench/.venv` (which sources the kaebench `env.sh`, setting
`KAE_KICAD_WRAP` for KiCad 10.0.7 in Apptainer) and exports:

| Variable | Value | Why |
|---|---|---|
| `XF_WORK` | `<root>/kae-work2` (set it before sourcing to override; `<root>/kae-work` is round 1) | kaebench work dir: cache, tasks, results, scores |
| `APPTAINER_BIND` | parent dir of the worktree | the KiCad container must see boards in it |
| `KAE_SRC` | `<parent>/kae-phys/kae/src` (`XF_PHYS` overrides the worktree) | `pnr/physics.py` imports `kae` from it |
| `KAE_KICAD_PYTHON` | [kicad-python](kicad-python) | one executable that runs KiCad's `python3` (pcbnew) in the container |
| `NUMBA_NUM_THREADS`, `OMP_NUM_THREADS`, BLAS threads | 1 | budgets are CPU seconds (`placekit.Clock`); one thread per attempt |
| `NUMBA_CACHE_DIR` | `$XF_WORK/numba-cache` | kernels compile once, not inside every attempt's budget |

Heavy commands on the shared host go in a CPU/memory scope, and long ones in detached tmux:

```bash
systemd-run --user --scope -p AllowedCPUs=<your cores> -p MemoryMax=32G -p MemoryHigh=28G CMD
tmux new -d -s <tag> 'systemd-run ... CMD > $XF_WORK/<run>.log 2>&1'
```

The scripts below set `ulimit -v 40000000` for KiCad themselves.

## Sandbox

kaebench now runs `--command` methods under bubblewrap: no network, a private `/tmp` and
`/var/tmp`, a hidden home directory, and only the attempt's work dir writable.
[runext.sh](runext.sh) makes that work for the pnr engine:

- **Read-only paths.** It passes `--sandbox-ro` for the worktree, `kae-phys`, the numba cache
  and the venv's base interpreter. The interpreter is a uv-managed Python under the home
  directory. Without it, `python` in the sandbox silently runs the system Python 3.10
  (shapely 1.8, numba 0.55), and jc fails in `kae` on `shapely.total_bounds`.
- **Hidden paths.** The harness hides only `$XF_WORK/tasks` and `results`. runext.sh also
  hides `$XF_WORK/cache` and `phys-cache`, and every other `kae-work*` dir in the worktree,
  since they hold human layouts.
- **Numba cache.** The cache is read-only in the sandbox, and numba ignores a read-only
  cache. [xf_run.sh](xf_run.sh) copies it into the attempt's work dir before it starts
  `pnr/run.py` with the venv's interpreter. After a change to jitted code, rebuild the
  cache with [warm_numba.sh](warm_numba.sh) `BOARD SPEC...` (unsandboxed), or the attempts
  compile inside their budget.
- **CPU accounting.** The harness's `cpu_s` column reads about 0 for sandboxed methods, so
  don't use it. Budgets are enforced by the method's own CPU clock.

## Boards

`$XF_WORK/tasks/` holds all 112 boards of `bench/suites/qualified-kicad-10.0.7.txt`
(manifest `bench/manifests/candidates.jsonl`), prepared by [prepare.sh](prepare.sh) with
this branch's harness (task spec 6). All 112 are qualified (`$XF_WORK/qualified.txt`). The
cache was copied from round 1's `kae-work/cache/`, which [seed_cache.py](seed_cache.py)
filled from the local board corpus, sha256-checked against the manifest. Nothing was
downloaded.

| Suite | Boards | Contents |
|---|---|---|
| `$XF_WORK/ab33.txt` | 33 | every qualified A/B board (13 A, 20 B) |
| `$XF_WORK/dev6.txt` | 6 | dev boards (2 A, 4 B), all in ab33 |
| `$XF_WORK/phys10.txt` | 10 | boards with physics structures (1 A, 9 B), all in ab33 |

Joint-task input: `$XF_WORK/tasks/<id>/place/input/board.kicad_pcb`.

**The round-1 "board has no outline" failures are gone.** On
`azonenberg-dumptruck-emmc-interposer` and `pcbcorpus-fyralabs-suzyqboard-suzyqboard`,
part of the board outline is Edge.Cuts drawn inside a connector footprint (J1, P1). The
round-1 prepare moved that footprint in the place input, so the outline no longer closed.
KiCad's `GetBoardPolygonOutlines` then fails even on the untouched input, and the engine's
`World` raised "board has no outline". Task spec 5+ keeps footprints carrying Edge.Cuts in
place, and both boards now load. This was a harness bug, not an engine bug.

## Run and score

```bash
$XF_WORK/runext.sh SPEC NAME BUDGET SUITE JOBS [SEEDS=3]
$XF_WORK/score.sh RUN [RUN ...]
```

Both are thin wrappers for [runext.sh](runext.sh) and [score.sh](score.sh) here.

- **runext.sh** runs `kaebench --workdir $XF_WORK run --adapter x-NAME --command "exec
  xf_run.sh SPEC {input} {output} BUDGET {attempt}" --kinds joint -k SEEDS --timeout
  BUDGET*6+120 -j JOBS --only @SUITE --name NAME`, plus the sandbox options above.
  - SPEC is `/abs/path/module.py:function`.
  - `pnr/run.py` writes the placed and routed board: poses, tracks and vias.
  - Results go to `$XF_WORK/results/NAME/x-NAME/joint/<id>/attempt-<seed>/`.
  - The attempt's `work/` (with `pnr.log`) is deleted afterwards. To debug one board, run
    `python tools/research/pnr/run.py SPEC IN OUT_DIR/board.kicad_pcb --budget 60` and read
    `OUT_DIR/pnr.log`.
- **score.sh** writes `$XF_WORK/score/NAME.md` (NAME = the runs joined by `+`, or
  `$SCORE_NAME`), with three parts:
  - `pnr/compare.py`: seed 0, with legal, clean, completion, length and vias on boards that
    every run completed, and DRC error types.
  - [seeds.py](seeds.py): mean ± sd over seeds and clean best-of-k.
  - Physics over seeds via [physics_score_xf.py](physics_score_xf.py) `--attempt N` and
    [physseeds.py](physseeds.py): `pnr_phys/physics_score.py` on `$PHYS_SUITE` (default
    phys10), seeds `0..PHYS_SEEDS-1` (default 3). It reports fast and routed physics as
    mean ± sd. Per-seed tables are in `NAME-phys-seedN.md`, and JSON in `NAME-phys/seed-N/`.
    `NO_PHYS=1` skips it. `physics_score_xf.py --attempt N` replaces `xf_physmap/phys_seed.py`,
    which still reads round 1's `kae-work`.

  All readers take joint attempts: their score holds placement and routing together. The
  physics wrapper changes only where physics_score looks: the work dir, the attempt, and
  joint harness columns. It never changes how it scores.
- **Jobs.** Each attempt is one Python thread, plus KiCad DRC threads at scoring. On 24
  cores, use about 20 workers in total, e.g. 5 runs × `-j 4`. A/B boards need little memory.

Smoke test (`jc`, budget 20, paw3395, sandboxed): status ok, legal, completion 0.69,
scored by kicad-cli. score.sh gave the DRC, seed and physics tables (fast 0.53, routed 0.53
× human).

## Baselines (ab33, budget 120 CPU-s, 3 seeds, joint)

Runs: `$XF_WORK/results/xf2-base-{jc,jc_lv_nopol,jc_full,combo,combo_lv}-ab33`, made by
[baselines.sh](baselines.sh). The 5 runs ran in parallel at `-j 4` for 58 min wall, and all
495 attempts were ok. Full tables: `$XF_WORK/score/baselines.md` (git-ignored), from
`SCORE_NAME=baselines score.sh <runs>`.

Columns:
- legal, clean and completion are mean ± sd over the 3 seeds.
- Length and vias are summed over the 21 boards that every run and seed completed, then
  averaged over seeds.
- Physics is method/human (gmean) on phys10, mean ± sd over seeds, lower is better. "Fast"
  is the place terms total; "routed" is board physics on the real copper.

| Run | Legal | Clean | Clean best-of-3 | Completion | Length (mm) | Vias | Fast phys | Routed phys |
|---|---|---|---|---|---|---|---|---|
| `jc` | 0.899 ± 0.046 | 0.636 ± 0.052 | **0.727** | 0.926 | 2940 | 45 | **0.92 ± 0.05** | 1.09 ± 0.07 |
| `jc_lv_nopol` | 0.889 ± 0.017 | 0.626 ± 0.063 | **0.727** | **0.929** | 2865 | 50 | 2.46 ± 0.14 | 1.16 ± 0.10 |
| `jc_full` | **0.939 ± 0.000** | **0.667 ± 0.030** | **0.727** | 0.928 | 2915 | 50 | 1.01 ± 0.10 | **1.02 ± 0.12** |
| `combo` | 0.869 ± 0.017 | 0.596 ± 0.035 | 0.667 | 0.919 | 2882 | 36 | 1.43 ± 0.32 | 1.30 ± 0.07 |
| `combo_lv` | 0.859 ± 0.017 | 0.586 ± 0.017 | 0.636 | 0.917 | **2824** | **29** | 3.41 ± 1.03 | 1.34 ± 0.05 |

- **Two boards are never legal, so ab33 legal caps at 31/33 (0.939).** No attempt of any
  method is legal on them, and both causes are in the engine (pnr/):
  - `kicad-demos-ecc83-ecc83-pp-v2`, copper_edge_clearance: a 5.6 mm mounting-hole pad lands
    5 µm across the board edge. The edge rule is 0.01 mm, and the outline is off the
    0.1 mm grid.
  - `pcbcorpus-justbuchanan-oasis-ledboard`, shorting_items and clearance: the board carries
    five 1 mm copper `gr_arc`s with nets on F.Cu. They are board graphics, not tracks, and
    `World` does not treat them as obstacles.
- **Seed spread is still about as large as the gaps between methods.** Clean sd is 0.02 to
  0.06. Compare new methods on the 3-seed mean and best-of-3, never on seed 0 alone.
- **The remaining DRC errors** (seed 0) are mostly:
  - jc variants: `solder_mask_bridge`, `shorting_items`, `starved_thermal`;
  - combo variants: `silk_overlap`.
- **Compare only within round 2.** Round 1 numbers (`kae-work/score/baselines.md`, the
  older version of this file) used place tasks with a self-routing probe, an older engine
  and an older prepare.


## Round 3: engine fixes (pnr commit 4c4330a)

Two engine bugs left two ab33 boards never legal; both are fixed (see the commit and
`tools/research/pnr/test_world.py`): pad-to-edge clearance was checked only at cells inside
the pad (kicad-demos-ecc83), and copper board drawings were not pad obstacles or router
terminals (pcbcorpus-justbuchanan-oasis-ledboard; the board's `.kicad_dru` edge clearance is
now read too). Both boards are now legal. Every earlier run used the old engine; round-3
runs are prefixed `xf3` (baselines `xf3-base-<method>-ab33`, `tools/research/xf_common/baselines.sh xf3`).

Baselines (joint, ab33, budget 120, 3 seeds; `kae-work2/score/baselines-xf3.md`):

| run | seeds | legal | clean | clean best-of-k | completion | length (mm) | vias | fast phys | routed phys |
|---|---|---|---|---|---|---|---|---|---|
| xf3-base-jc-ab33 | 3 | 1.000 ± 0.000 | 0.687 ± 0.017 | 0.758 | 0.935 ± 0.002 | 3521 | 53 | 0.96 ± 0.08 | 1.18 ± 0.08 |
| xf3-base-jc_lv_nopol-ab33 | 3 | 0.990 ± 0.017 | 0.677 ± 0.035 | 0.727 | 0.942 ± 0.003 | 3423 | 58 | 1.92 ± 0.50 | 1.26 ± 0.05 |
| xf3-base-jc_full-ab33 | 3 | 0.990 ± 0.017 | 0.677 ± 0.076 | 0.758 | 0.940 ± 0.003 | 3530 | 60 | 0.92 ± 0.08 | 0.98 ± 0.04 |
| xf3-base-combo-ab33 | 3 | 0.929 ± 0.017 | 0.616 ± 0.035 | 0.697 | 0.929 ± 0.006 | 3554 | 44 | 1.29 ± 0.06 | 1.30 ± 0.05 |
| xf3-base-combo_lv-ab33 | 3 | 0.909 ± 0.030 | 0.606 ± 0.061 | 0.697 | 0.926 ± 0.005 | 3466 | 37 | 3.39 ± 0.24 | 1.42 ± 0.13 |
