#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# polish-ab: staged control, pair_swap=1, place_margin arms (PLAN.md).
#   SHA=<pushed commit> tools/kaeres/experiments/polish-ab/setup.sh
set -euo pipefail
cd "$(dirname "$0")/../../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=${SHA:?commit}
S7=${SHA:0:7}
KAE=(--code kae=.@$SHA)
H=(--harness $SHA)
KH='$HOME/.cache/kaebench'
FORK="\$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
NUMBA=numba-kae-polish-$S7
CP="cp -r $KH/$NUMBA numba 2>/dev/null;"
E="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
FIN="$CP $E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
RES="if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else"
WRAP="{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s 300 --scale-first --slack 1.15 --resume 0.5 --final '$FIN' --check-placement --"
add() {  # NAME DESCRIPTION EXTRA
  $K method add "$1" --kind joint-fixed --description "$2; staged, restart portfolio --resume 0.5 --final at $S7" \
    --command "$WRAP '$CP $RES $E -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ --max-iters 0 --no-modules$3; fi'" \
    --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=4 "${KAE[@]}" "${H[@]}"
}
add "kae polish control $S7 (restarts)"  "control: staged" ""
add "kae pair swap $S7 (restarts)"       "pair_swap=1: greedy swaps of equal two-pad parts on the physics terms after placement" " --set pair_swap=1"
add "kae margin 0.2 $S7 (restarts)"      "place_margin=0.2 mm" " --set place_margin=0.2"
add "kae margin auto $S7 (restarts)"     "place_margin=-1 (Problem.auto_margin)" " --set place_margin=-1"
