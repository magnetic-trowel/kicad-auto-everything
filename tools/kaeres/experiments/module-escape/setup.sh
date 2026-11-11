#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# module-ablation (PLAN.md): the module stage (J1 arm b) against escape corridors and ablations of its pieces, under
# J1's restart wrapper, counted-work budgets, one pinned Freerouting build.
#   SHA=<pushed commit> tools/kaeres/experiments/module-escape/setup.sh  (experiment module-ablation)
set -euo pipefail
cd "$(dirname "$0")/../../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=${SHA:?commit}
S7=${SHA:0:7}
KH='$HOME/.cache/kaebench'
FORK="\$HOME/.cache/kaebench/kae-freerouting-fork-d137fd1/bin/freerouting"
NUMBA=numba-modesc-$S7
CP="cp -r $KH/$NUMBA numba 2>/dev/null;"
WENV="env KAE_BUDGET=work PYTHONHASHSEED=0 KAE_WORKERS=1"
E="$WENV NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
FIN="$CP $E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
RES="if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else"
# work mode: --time is nominal seconds of work (900 x sqrt(fp/40)); the harness timeout is the wall ceiling, 4 x that
WRAP="$WENV KAE_BRIDGE_FREEROUTING=$FORK {py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time \$(( {timeout} / 4 )) --seed {attempt} --parallel 4 --first-s 300 --scale-first --slack 1.15 --resume 0.5 --final '$FIN' --check-placement --"
add() {  # NAME DESCRIPTION JOINT_FLAGS
  $K method add "$1" --kind joint-fixed --description "$2; J1's restart portfolio, counted-work budgets, Freerouting fork d137fd1, at $S7" \
    --command "$WRAP '$CP $RES $E -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ $3; fi'" \
    --param timeout_s=3600 --param timeout_scale=sqrt-fp40 --param parallel=4 --code kae=.@$SHA --harness $SHA
}
add "kae modesc M $S7 (restarts)"        "M: staged with the module stage (J1 arm b), the control"                       "--max-iters 0"
add "kae modesc Mesc $S7 (restarts)"     "M-esc: M with escape corridors of 1.5 mm out of dense ICs (crit.escape_mm)"   "--max-iters 0 --set crit.escape_mm=1.5"
add "kae modesc Mnoguard $S7 (restarts)" "M-noguard: M without the modules' guard pours (crit.guards=[])"              "--max-iters 0 --set crit.guards=[]"
add "kae modesc Mnorails $S7 (restarts)" "M-norails: M without the rail copper (crit.rails_joint=none)"                "--max-iters 0 --set crit.rails_joint=none"
add "kae modesc Mnojoin $S7 (restarts)"  "M-nojoin: M without the completion and island joins (crit.complete_mm=0, crit.island_mm=0)" "--max-iters 0 --set crit.complete_mm=0 --set crit.island_mm=0"
add "kae modesc Mposes $S7 (restarts)"   "M-poses: the module stage's part moves only, its copper and guards dropped before the first route" "--max-iters 0 --set module_poses_only=1"
