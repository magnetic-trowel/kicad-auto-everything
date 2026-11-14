#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# cf-windows (PLAN.md): completion-first (CF) against CF-W, where a board left open after phase 1 gets the joint
# loop's windows on that board (--open-alt) instead of a second restart run. J1's wrapper, counted work, d137fd1.
#   SHA=<pushed commit> tools/kaeres/experiments/cf-windows/setup.sh
set -euo pipefail
cd "$(dirname "$0")/../../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=${SHA:?commit}
S7=${SHA:0:7}
KH='$HOME/.cache/kaebench'
FORK="\$HOME/.cache/kaebench/kae-freerouting-fork-d137fd1/bin/freerouting"
NUMBA=numba-cfw-$S7
CP="cp -r $KH/$NUMBA numba 2>/dev/null;"
WENV="env KAE_BUDGET=work PYTHONHASHSEED=0 KAE_WORKERS=1"
E="$WENV NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
FIN="$CP $E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
RES="if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else"
R_CMD="$CP $RES $E -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ --max-iters 0 --no-modules; fi"
# the alternative is M-clock: the module stage keeping its clock (module-escape PLAN, Addendum 3)
M_CMD="$CP $RES $E -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ --max-iters 0 --set module_clock=1; fi"
# --time = two R allowances of 900 s x sqrt(fp/40) nominal work (= timeout x 9/40); the harness timeout, 8,000 s x
# sqrt(fp/40), is the wrapper's own ceiling (4 x that nominal work) plus about 10 % for its DRCs and physics, never capped
wrap() {  # extra
  echo "$WENV KAE_BRIDGE_FREEROUTING=$FORK {py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time \$(( {timeout} * 9 / 40 )) --seed {attempt} --parallel 4 --first-s 300 --scale-first --slack 1.15 --resume 0.5 --final '$FIN' --check-placement --policy completion-first $1 -- '$R_CMD'"
}
common=(--kind joint-fixed --param timeout_s=8000 --param timeout_scale=sqrt-fp40 --param timeout_cap_s=200000 --param parallel=4 --code kae=.@$SHA --harness $SHA)
POL="$CP $E -m kae.joint.cli run @IN@ @OUT@ --start @BEST@ --seed @SEED@ --time @TIME@ --no-modules"
$K method add "kae cfw CF $S7 (restarts)" --description "completion-first: staged restarts, then M-clock if that board is clean, else another restart run; cf-windows at $S7" \
  --command "$(wrap "--alt '$M_CMD'")" "${common[@]}"
$K method add "kae cfw CFW $S7 (restarts)" --description "CF-W: completion-first, but a board left open after phase 1 gets the joint loop's windows on that board (--open-alt) instead of another restart run; cf-windows at $S7" \
  --command "$(wrap "--alt '$M_CMD' --open-alt '$POL'")" "${common[@]}"
