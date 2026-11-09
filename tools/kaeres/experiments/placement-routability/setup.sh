#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Methods of the placement-routability experiments (PLAN.md, written before any run). One commit for all arms;
# only the --set flags differ. SHA=<pushed commit> XING=<mm per crossing> setup.sh
set -euo pipefail
cd "$(dirname "$0")/../../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=${SHA:?commit}
XING=${XING:?mm per crossing}
S7=${SHA:0:7}
KAE=(--code kae=.@$SHA)
H=(--harness $SHA)
KH='$HOME/.cache/kaebench'
FORK="\$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
NUMBA=numba-kae-routab-$S7
CP="cp -r $KH/$NUMBA numba 2>/dev/null;"
E="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
one() {  # NAME DESCRIPTION FLAGS: one placement, one route (no restarts)
  $K method add "$1" --kind joint-fixed --description "$2; one placement, one route, at $S7" \
    --command "$CP $E -m kae.joint.cli run {input} {output} --seed {attempt} --time {timeout} --max-iters 0 --no-modules $3" \
    --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=1 "${KAE[@]}" "${H[@]}"
}
one "kae routab control $S7"  "control: knobs off"                                ""
one "kae routab untangle $S7" "untangle pass after legalization (J70)"            "--set place_untangle=1"
one "kae routab xing $S7"     "crossing term in the annealer, $XING mm/crossing"  "--set place_w_xing=$XING"
one "kae routab chan1 $S7"    "routing-channel term, w_chan 1 (J46)"              "--set place_w_chan=1"
one "kae routab chan3 $S7"    "routing-channel term, w_chan 3 (J46)"              "--set place_w_chan=3"
FIN="$CP $E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
RES="if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else"
WRAP="{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s 300 --scale-first --slack 1.15 --resume 0.5 --final '$FIN' --check-placement --"
add() {  # NAME DESCRIPTION FLAGS: the restart chassis (J1's staged arm)
  $K method add "$1" --kind joint-fixed --description "$2; restart portfolio (tools/kaeres/restart.py) --resume 0.5 --final at $S7" \
    --command "$WRAP '$CP $RES $E -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ --max-iters 0 --no-modules $3; fi'" \
    --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=4 "${KAE[@]}" "${H[@]}"
}
add "kae history control $S7 (restarts)"      "place-history control: knobs off"                  ""
add "kae history cong30 $S7 (restarts)"       "place_w_cong=30, no history (J6 control for RUDY)" "--set place_w_cong=30"
add "kae history cong30 hist $S7 (restarts)"  "place_w_cong=30 and routing history across attempts (J6)" "--set place_w_cong=30 --set place_history=../phist"
