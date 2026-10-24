#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# A/B of the joint placement-routing loop as kaebench `joint` runs, on the benchmark host:
#   arms  staged     kae place, then the bridge (python -m kae.joint.cli run --max-iters 0 --no-modules)
#         joint      the joint loop (module stage, windows, finishing stage)
#         human-fr   the human placement routed by Freerouting (kaebench's human-freerouting)
#         joint-multi  (optional, ARMS=...) the loop with --physics-fidelity multi (PEEC on decisions)
# Defaults: splits A,B (33 boards), k = 2 (seeds 0 and 1), 9000 s per attempt (TIMEOUT; 10x
# the 900 s of the local A/B), -j 20 (each attempt uses ~1-1.5 cores: Python, one Freerouting
# JVM thread, kicad-cli). Every stage stops when it is done or stops improving, never on the
# clock alone: the loop has no iteration cap, more tries per window with a longer budget,
# exhausted windows sampled again under new seeds until two cycles in a row keep nothing
# ("no improvement (cycle k)"), the finishing stage reserved at 20 % of the budget. Clean
# boards stop at once. Worst case per arm = 66 attempts x TIMEOUT / JOBS (~8.3 h).
# Per-stage stop reasons: tools/research/joint/joint_stops.py (printed at the end).
#
#   tools/research/joint/run_joint_ab.sh TAG            # from the repo root, detached:
#   tmux new -d -s joint 'tools/research/joint/run_joint_ab.sh v8 > kae-work/joint-ab-v8.log 2>&1'
#
# Env: WORKDIR (absolute; default $PWD/kae-work), JOBS (20), K (2), TIMEOUT (9000), SPLITS (A,B),
# ARMS ("staged joint human-fr"), KAE_PY (kae/.venv/bin/python), KB (bench/.venv/bin/kaebench).
# The method's code is snapshotted to $WORKDIR/code/kae-joint-TAG (other agents keep editing
# kae/), its numba cache pre-warmed outside the sandbox (read-only inside it).
set -euo pipefail
TAG=${1:?usage: run_joint_ab.sh TAG}
R=$(pwd)
WORKDIR=${WORKDIR:-$R/kae-work}
JOBS=${JOBS:-20}; K=${K:-2}; TIMEOUT=${TIMEOUT:-9000}; SPLITS=${SPLITS:-A,B}
ARMS=${ARMS:-"staged joint human-fr"}
KAE_PY=${KAE_PY:-$R/kae/.venv/bin/python}
KB=${KB:-$R/bench/.venv/bin/kaebench}
export OMP_NUM_THREADS=1
C=$WORKDIR/code/kae-joint-$TAG
if [ ! -d "$C/kae" ]; then
  mkdir -p "$C/.numba_cache"
  cp -r "$R/kae/src/kae" "$C/kae"
  find "$C" -name __pycache__ -prune -exec rm -rf {} +
  # pre-warm the compiled kernels on one place task
  T=$(ls -d "$WORKDIR"/tasks/*/place/input | head -1)
  env PYTHONPATH="$C" NUMBA_CACHE_DIR="$C/.numba_cache" KAE_WORKERS=1 "$KAE_PY" -m kae.joint.cli run \
    "$T/board.kicad_pcb" "$C/warm/out.kicad_pcb" --time 240 --max-iters 1 > "$C/warm.log" 2>&1 || true
fi
TIME=$((TIMEOUT - 40))       # the method's own budget; kaebench's timeout is the hard stop
M="env PYTHONPATH=$C NUMBA_CACHE_DIR=$C/.numba_cache OMP_NUM_THREADS=1 KAE_WORKERS=1 $KAE_PY -m kae.joint.cli run {input} {output} --seed {attempt} --time $TIME"
RUN="$KB --workdir $WORKDIR run --kinds joint --splits $SPLITS -k $K -j $JOBS"
for arm in $ARMS; do
  case $arm in
    staged)   $RUN --timeout "$TIMEOUT" --adapter kae-staged --sandbox-ro "$C" --command "$M --max-iters 0 --no-modules" \
                --name "joint-staged-$TAG" ;;
    joint)    $RUN --timeout "$TIMEOUT" --adapter kae-joint --sandbox-ro "$C" --command "$M" --name "joint-loop-$TAG" ;;
    joint-multi) $RUN --timeout "$TIMEOUT" --adapter kae-joint-multi --sandbox-ro "$C" \
                --command "$M --physics-fidelity multi" --name "joint-multi-$TAG" ;;
    human-fr) $RUN --timeout "$TIMEOUT" --adapter human-freerouting --name "joint-human-fr-$TAG" ;;
    *) echo "unknown arm $arm" >&2; exit 2 ;;
  esac
done
for arm in $ARMS; do
  case $arm in staged) n=joint-staged-$TAG ;; joint) n=joint-loop-$TAG ;; joint-multi) n=joint-multi-$TAG ;;
               human-fr) n=joint-human-fr-$TAG ;; esac
  echo "== $n"; grep "| all" "$WORKDIR/results/$n/report.md" || true
done
A=""
for arm in $ARMS; do
  case $arm in staged) A="$A staged=$WORKDIR/results/joint-staged-$TAG/kae-staged" ;;
               joint) A="$A joint=$WORKDIR/results/joint-loop-$TAG/kae-joint" ;;
               joint-multi) A="$A joint-multi=$WORKDIR/results/joint-multi-$TAG/kae-joint-multi" ;; esac
done
[ -n "$A" ] && "$KAE_PY" "$R/tools/research/joint/joint_stops.py" $A --out "$WORKDIR/results/joint-stops-$TAG.md" || true
# routed physics per arm (module values vs the human layout, rail drops):
#   $KAE_PY tools/research/joint/joint_physics.py --tasks $WORKDIR/tasks --out $WORKDIR/physics-$TAG \
#     --arm staged=$WORKDIR/results/joint-staged-$TAG/kae-staged --arm joint=$WORKDIR/results/joint-loop-$TAG/kae-joint \
#     --arm human-fr=$WORKDIR/results/joint-human-fr-$TAG/human-freerouting
