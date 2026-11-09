#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# bus-pose-ab (PLAN.md, written before any run): the pose compiler's arms against the same kae staged
# control, one placement, one route (no restart portfolio), Freerouting fork as the bridge's engine,
# 900 s x sqrt(fp/40). One commit for all arms; only --set flags differ.
#   SHA=<pushed commit> tools/kaeres/experiments/bus-pose-ab/setup.sh
set -euo pipefail
cd "$(dirname "$0")/../../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=${SHA:?commit}
S7=${SHA:0:7}
KAE=(--code kae=.@$SHA)
H=(--harness $SHA)
KH='$HOME/.cache/kaebench'
FORK="\$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
NUMBA=numba-kae-buspose-$S7
CP="cp -r $KH/$NUMBA numba 2>/dev/null;"
E="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
one() {  # NAME DESCRIPTION FLAGS
  $K method add "$1" --kind joint-fixed --description "$2; one placement, one route (kae.joint.cli --max-iters 0 --no-modules) at $S7" \
    --command "$CP $E -m kae.joint.cli run {input} {output} --seed {attempt} --time {timeout} --max-iters 0 --no-modules $3" \
    --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=1 "${KAE[@]}" "${H[@]}"
}
one "kae bus-pose control $S7"      "control: bus pose compiler off"                                   ""
one "kae bus-pose final-planar $S7" "final pass, planarity first (legal turns; other nets priced)"     "--set bus_pose=final"
one "kae bus-pose final-length $S7" "final pass, length first"                                         "--set bus_pose=final --set bus_pose_mode=length"
one "kae bus-pose seed-final $S7"   "pose at the seed and held, then the final pass, planarity first"  "--set bus_pose=seed"
# Numba cache warmed once (warm-numba.sh at $SHA) and the experiment created (PLAN.md):
# python3 tools/kaeres/kaeres.py exp create bus-pose-ab --method "kae bus-pose control $S7" --method "kae bus-pose final-planar $S7" \
#   --method "kae bus-pose final-length $S7" --method "kae bus-pose seed-final $S7" --boards @tools/kaeres/experiments/bus-pose-ab/boards.txt \
#   --attempts 3 --harness $SHA --kae $SHA --description "..."
