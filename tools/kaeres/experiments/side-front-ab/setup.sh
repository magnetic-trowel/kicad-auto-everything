#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# side-front-ab: staged placement with the human side kept, passives on the front, every flippable SMD on the front
# (see PLAN.md). One commit for all arms; only the pre-step differs.
#
#   SHA=<pushed commit> tools/kaeres/experiments/side-front-ab/setup.sh
set -euo pipefail
cd "$(dirname "$0")/../../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=${SHA:?commit}
S7=${SHA:0:7}
KAE=(--code kae=.@$SHA)
H=(--harness $SHA)
KH='$HOME/.cache/kaebench'
FORK="\$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
NUMBA=numba-kae-side-$S7
CP="cp -r $KH/$NUMBA numba 2>/dev/null;"
E="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
FIN="$CP $E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
RES="if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else"
JOINT="$E -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ --max-iters 0 --no-modules; fi"
wrap() {  # INPUT
  echo "{py:kae} {code:harness}/tools/kaeres/restart.py --input $1 --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s 300 --scale-first --slack 1.15 --resume 0.5 --final '$FIN' --check-placement --"
}
add() {  # NAME DESCRIPTION PRE-STEP
  local pre=$3 input="{input}"
  [ -z "$pre" ] || input='$PWD/flip/board.kicad_pcb'
  $K method add "$1" --kind joint-fixed --description "$2; kae.joint.cli --max-iters 0 --no-modules, restart portfolio --resume 0.5 --final at $S7" \
    --command "$pre $(wrap "$input") '$CP $RES $JOINT'" \
    --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=4 "${KAE[@]}" "${H[@]}"
}
flip() {  # ARM
  echo "mkdir -p flip && PYTHONPATH={code:harness}/tools/research/place {py:kae} {code:harness}/tools/research/place/side_front.py --input {input} --output \$PWD/flip/board.kicad_pcb --arm $1 &&"
}
add "kae side control $S7 (restarts)"  "arm C: human sides (oracle reference)" ""
add "kae side passives $S7 (restarts)" "arm P: two-pad SMD passives flipped to the front before placing (cap 0.70 fill)" "$(flip passives)"
add "kae side rule $S7 (restarts)"     "arm R: every movable SMD part's side by rule, no human side (front first to 0.70 fill)" "$(flip rule)"
