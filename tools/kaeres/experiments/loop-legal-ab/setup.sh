#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# loop-legal-ab (PLAN.md): anchoring tight parts against its own control, on the restart wrapper of J1's ladder.
#   SHA=<pushed commit> tools/kaeres/experiments/loop-legal-ab/setup.sh
set -euo pipefail
cd "$(dirname "$0")/../../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=${SHA:?commit}
S7=${SHA:0:7}
KH='$HOME/.cache/kaebench'
FORK="\$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
NUMBA=numba-loop-exp-$S7
CP="cp -r $KH/$NUMBA numba 2>/dev/null;"
E="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
FIN="$CP $E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
RES="if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else"
WRAP="{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s 300 --scale-first --slack 1.15 --resume 0.5 --final '$FIN' --check-placement --"
add() {  # NAME DESCRIPTION JOINT_FLAGS
  $K method add "$1" --kind joint-fixed --description "$2; restart portfolio --resume 0.5 --final at $S7" \
    --command "$WRAP '$CP $RES $E -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ $3; fi'" \
    --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=4 --code kae=.@$SHA --harness $SHA
}
add "kae legal staged ctl $S7 (restarts)"   "staged (J1 arm a), anchor_tight off"  "--max-iters 0 --no-modules --set anchor_tight=0"
add "kae legal staged $S7 (restarts)"       "staged (J1 arm a), anchor_tight on"   "--max-iters 0 --no-modules"
add "kae legal joint ctl $S7 (restarts)"    "full joint (J1 arm d), anchor_tight off" "--set anchor_tight=0"
add "kae legal joint $S7 (restarts)"        "full joint (J1 arm d), anchor_tight on"  ""
