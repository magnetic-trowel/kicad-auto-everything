#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# loop-polish (PLAN.md): staged + restarts, then the joint loop's windows on the kept board (restart.py --finish),
# within the same total allowance, against staged + restarts alone using all of it.
#   SHA=<pushed commit> tools/kaeres/experiments/loop-polish/setup.sh
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
T=$(( 900 * 315 / 100 ))
FIN="$CP $E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
RES="if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else"
INNER="'$CP $RES $E -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ --max-iters 0 --no-modules; fi'"
POL="$CP $E -m kae.joint.cli run @IN@ @OUT@ --start @BEST@ --seed @SEED@ --time @TIME@ --no-modules --set skip_unfixable_drc=0"
wrap() {  # extra restart.py flags
  echo "{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 1 --first-s 300 --scale-first --slack 1.15 --resume 0.5 --final '$FIN' $1 --check-placement -- $INNER"
}
common=(--kind joint-fixed --param timeout_s=$T --param timeout_scale=sqrt-fp40 --param parallel=1 --code kae=.@$SHA --harness $SHA)
$K method add "kae polish restarts $S7" --description "staged + restarts alone, whole allowance (loop-compute-matched's R, run again); loop-polish at $S7" \
  --command "$(wrap "")" --param replicate=loop-polish "${common[@]}"
$K method add "kae polish late $S7" --description "staged + restarts, then the joint loop's windows on the kept board for 30 % of the allowance; loop-polish at $S7" \
  --command "$(wrap "--finish '$POL' --finish-s \$(( {timeout} * 30 / 100 ))")" "${common[@]}"
$K method add "kae polish half $S7" --description "staged + restarts, then the joint loop's windows on the kept board for 50 % of the allowance; loop-polish at $S7" \
  --command "$(wrap "--finish '$POL' --finish-s \$(( {timeout} * 50 / 100 ))")" "${common[@]}"
