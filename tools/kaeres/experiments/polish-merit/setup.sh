#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# polish-merit (PLAN.md): loop-polish's P-late (restarts for 70 % of the allowance, then the joint loop's windows on
# the kept board for 30 %) against restarts alone, on the 213 merit boards, counted-work budgets, Freerouting d137fd1.
#   SHA=<pushed commit> tools/kaeres/experiments/polish-merit/setup.sh
set -euo pipefail
cd "$(dirname "$0")/../../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=${SHA:?commit}
S7=${SHA:0:7}
KH='$HOME/.cache/kaebench'
FORK="\$HOME/.cache/kaebench/kae-freerouting-fork-d137fd1/bin/freerouting"
NUMBA=numba-pmerit-$S7
CP="cp -r $KH/$NUMBA numba 2>/dev/null;"
WENV="env KAE_BUDGET=work PYTHONHASHSEED=0 KAE_WORKERS=1"
E="$WENV NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
FIN="$CP $E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
RES="if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else"
INNER="'$CP $RES $E -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ --max-iters 0 --no-modules; fi'"
POL="$CP $E -m kae.joint.cli run @IN@ @OUT@ --start @BEST@ --seed @SEED@ --time @TIME@ --no-modules"
# allowance as loop-polish: 3.15 x 900 s x sqrt(fp/40), now of nominal work; the harness timeout is the 4x wall ceiling
T=$(( 4 * 900 * 315 / 100 ))
wrap() {  # extra restart.py flags
  echo "$WENV KAE_BRIDGE_FREEROUTING=$FORK {py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time \$(( {timeout} / 4 )) --seed {attempt} --parallel 1 --first-s 300 --scale-first --slack 1.15 --resume 0.5 --final '$FIN' $1 --check-placement -- $INNER"
}
common=(--kind joint-fixed --param timeout_s=$T --param timeout_scale=sqrt-fp40 --param timeout_cap_s=57600 --param parallel=1 --code kae=.@$SHA --harness $SHA)
$K method add "kae pmerit restarts $S7" --description "staged + restarts alone, whole allowance (loop-polish's R), counted-work budgets, Freerouting fork d137fd1; polish-merit at $S7" \
  --command "$(wrap "")" "${common[@]}"
$K method add "kae pmerit late $S7" --description "staged + restarts, then the joint loop's windows on the kept board for 30 % of the allowance (loop-polish's P-late), counted-work budgets, Freerouting fork d137fd1; polish-merit at $S7" \
  --command "$(wrap "--finish '$POL' --finish-s \$(( {timeout} * 30 / 400 ))")" "${common[@]}"
