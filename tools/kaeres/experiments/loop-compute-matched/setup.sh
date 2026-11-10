#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# loop-compute-matched (PLAN.md): joint with two budgets of window time against the staged pipeline under the restart
# wrapper, both on one process lane for the same harness timeout (3.15 x 900 s x sqrt(fp/40)).
#   SHA=<pushed commit> tools/kaeres/experiments/loop-compute-matched/setup.sh
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
# arm W: the window bench's "w2 ctl" recipe, run again side by side (replicate makes its own runs)
$K method add "kae cm joint w2 $S7" --kind joint-fixed \
  --description "joint, natural shares plus two budgets of window time (loop-window-bench w2 ctl), one process; compute-matched pair at $S7" \
  --command "$CP $E -m kae.joint.cli run {input} {output} --seed {attempt} --time \$(( {timeout} * 100 / 315 )) --set window_budget_factor=2 --set skip_unfixable_drc=0" \
  --param timeout_s=$T --param timeout_scale=sqrt-fp40 --param parallel=1 --param replicate=loop-compute-matched --code kae=.@$SHA --harness $SHA
# arm R: J1's staged arm (place + bridge) under the restart wrapper, one attempt at a time, for the same timeout
FIN="$CP $E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
RES="if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else"
WRAP="{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 1 --first-s 300 --scale-first --slack 1.15 --resume 0.5 --final '$FIN' --check-placement --"
$K method add "kae cm staged restarts $S7" --kind joint-fixed \
  --description "staged (place + bridge, J1 arm a) under the restart portfolio, parallel 1, same timeout as joint w2; compute-matched pair at $S7" \
  --command "$WRAP '$CP $RES $E -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ --max-iters 0 --no-modules; fi'" \
  --param timeout_s=$T --param timeout_scale=sqrt-fp40 --param parallel=1 --code kae=.@$SHA --harness $SHA
