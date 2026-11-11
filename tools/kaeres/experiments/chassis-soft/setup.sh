#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# chassis-soft (PLAN.md): staged, + module stage, + module stage with its copper rippable, all under J1's restart wrapper
# at the same allowance (900 s x sqrt(fp/40), --parallel 4).   SHA=<pushed commit> tools/kaeres/experiments/chassis-soft/setup.sh
set -euo pipefail
cd "$(dirname "$0")/../../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=${SHA:?commit}
S7=${SHA:0:7}
KH='$HOME/.cache/kaebench'
FORK="\$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
NUMBA=numba-chassis-$S7
CP="cp -r $KH/$NUMBA numba 2>/dev/null;"
E="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
FIN="$CP $E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
RES="if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else"
WRAP="{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s 300 --scale-first --slack 1.15 --resume 0.5 --final '$FIN' --check-placement --"
add() {  # NAME DESCRIPTION JOINT_FLAGS
  $K method add "$1" --kind joint-fixed --description "$2; J1's restart portfolio at $S7" \
    --command "$WRAP '$CP $RES $E -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ $3; fi'" \
    --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=4 --code kae=.@$SHA --harness $SHA
}
add "kae chassis R $S7 (restarts)"      "R: staged, no module stage (J1 arm a)"                          "--max-iters 0 --no-modules"
add "kae chassis M $S7 (restarts)"      "M: staged with the module stage, its copper locked (J1 arm b)"  "--max-iters 0"
add "kae chassis Msoft $S7 (restarts)"  "M-soft: module stage, its copper rippable on the first route (shove_fixed)" "--max-iters 0 --set module_soft=1"
