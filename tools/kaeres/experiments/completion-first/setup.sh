#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# completion-first (PLAN.md): restart.py --policy completion-first with the module stage as --alt, against the same
# policy without --alt (best of two restart runs), J1's wrapper, counted-work budgets, Freerouting d137fd1.
#   SHA=<pushed commit> tools/kaeres/experiments/completion-first/setup.sh
set -euo pipefail
cd "$(dirname "$0")/../../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=${SHA:?commit}
S7=${SHA:0:7}
KH='$HOME/.cache/kaebench'
FORK="\$HOME/.cache/kaebench/kae-freerouting-fork-d137fd1/bin/freerouting"
NUMBA=numba-cfirst-$S7
CP="cp -r $KH/$NUMBA numba 2>/dev/null;"
WENV="env KAE_BUDGET=work PYTHONHASHSEED=0 KAE_WORKERS=1"
E="$WENV NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
FIN="$CP $E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
RES="if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else"
R_CMD="$CP $RES $E -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ --max-iters 0 --no-modules; fi"
M_CMD="$CP $RES $E -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ --max-iters 0; fi"
# --time = two R allowances of 900 s x sqrt(fp/40) nominal work (= timeout x 9/40); the harness timeout, 8,000 s x
# sqrt(fp/40), is the wrapper's own ceiling (4 x that nominal work) plus about 10 % for its DRCs and physics, never capped
wrap() {  # extra
  echo "$WENV KAE_BRIDGE_FREEROUTING=$FORK {py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time \$(( {timeout} * 9 / 40 )) --seed {attempt} --parallel 4 --first-s 300 --scale-first --slack 1.15 --resume 0.5 --final '$FIN' --check-placement --policy completion-first $1 -- '$R_CMD'"
}
common=(--kind joint-fixed --param timeout_s=8000 --param timeout_scale=sqrt-fp40 --param timeout_cap_s=200000 --param parallel=4 --code kae=.@$SHA --harness $SHA)
$K method add "kae cfirst bestR $S7 (restarts)" --description "best of two restart runs of staged (J1 arm a): --policy completion-first without --alt; at $S7" \
  --command "$(wrap "")" "${common[@]}"
$K method add "kae cfirst CF $S7 (restarts)" --description "completion-first: staged restarts, then the module stage (J1 arm b) if that board is clean, else another restart run; at $S7" \
  --command "$(wrap "--alt '$M_CMD'")" "${common[@]}"
