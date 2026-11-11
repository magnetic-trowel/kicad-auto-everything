#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# module-clock (PLAN.md, Addendum 3): the module stage with and without its clock fix, and ablations of the fixed
# stage, under J1's restart wrapper, counted-work budgets, one pinned Freerouting build.
#   SHA=<pushed commit> tools/kaeres/experiments/module-escape/setup-clock.sh  (experiment module-clock)
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
C="--max-iters 0 --set module_clock=1"
add "kae modclk M $S7 (restarts)"              "M: staged with the module stage as it was (its clock covers only the part moves)" "--max-iters 0"
add "kae modclk Mclock $S7 (restarts)"         "M-clock: M with the module stage keeping its clock and the first route's time from the attempt budget" "$C"
add "kae modclk Mclocklocal $S7 (restarts)"    "M-clock-local: M-clock with decap and crystal modules only, no rails (crit.kinds, crit.rails_joint=none)" "$C --set crit.kinds=decap,crystal --set crit.rails_joint=none"
add "kae modclk Mclocknoguard $S7 (restarts)"  "M-clock-noguard: M-clock without the modules' guard pours (crit.guards=[])" "$C --set crit.guards=[]"
add "kae modclk Mclocknorails $S7 (restarts)"  "M-clock-norails: M-clock without the rail copper (crit.rails_joint=none)" "$C --set crit.rails_joint=none"
