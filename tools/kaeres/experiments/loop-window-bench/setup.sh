#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# The loop's window bench (PLAN.md, written before any run). One commit for all arms; only the kae.joint.cli
# --set flags differ. No restart wrapper: one run of the loop at its budget B = 900 s x sqrt(fp/40); the harness
# timeout is the budget plus the arm's window extension plus a margin, and --time gets B back from it.
#
#   SHA=<pushed commit> tools/kaeres/experiments/loop-window-bench/setup.sh
set -euo pipefail
cd "$(dirname "$0")/../../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=${SHA:?commit}
S7=${SHA:0:7}
KH='$HOME/.cache/kaebench'
FORK="\$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
NUMBA=numba-loop-exp-$S7
OLD="--set skip_unfixable_drc=0"
LEG="--set legal_time=15 --set replace_time=60 --set replace_share=0.4"
add() {  # NAME F(window budgets beyond B) FLAGS DESCRIPTION
  local name=$1 f=$2 flags=$3 desc=$4
  # timeout_s = 900 x (1 + F + 0.15), and B = timeout x 100 / (115 + 100 F): 900 x sqrt(fp/40) again under the harness scale
  local t=$(( 900 * (115 + 100 * f) / 100 ))
  local div=$(( 115 + 100 * f ))
  local win=""; [ "$f" -gt 0 ] && win="--set window_budget_factor=$f"
  $K method add "$name" --kind joint-fixed --description "$desc; window bench at $S7, no restart wrapper" \
    --command "cp -r $KH/$NUMBA numba 2>/dev/null; env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae} -m kae.joint.cli run {input} {output} --seed {attempt} --time \$(( {timeout} * 100 / $div )) $win $flags" \
    --param timeout_s=$t --param timeout_scale=sqrt-fp40 --param parallel=1 --code kae=.@$SHA --harness $SHA
}
# natural budget (F = 0): the shares under test
add "kae wb ctl $S7"       0 "$OLD"                                                     "natural budget control: defaults before this work (J3 off)"
add "kae wb j2 $S7"        0 "$OLD --set route_share=0.4 --set finish_share=0.1 --set min_iter_s=25" "J2: real shares for the windows, min_iter_s 25"
add "kae wb j5 $S7"        0 "$OLD --set min_iter_s=25"                                 "J5: min_iter_s 25 alone"
add "kae wb j14 $S7"       0 "$OLD --set first_last_mile=1"                             "J14: last mile on the first route"
# window bench (F = 2: the windows get two budgets beyond iteration 0's shares)
add "kae wb w2 ctl $S7"    2 "$OLD"                                                     "windows with a real budget: control (J3 off, old legalizer)"
add "kae wb w2 j3 $S7"     2 ""                                                         "windows with a real budget, J3 on"
add "kae wb w2 j4t $S7"    2 "$OLD $LEG"                                                "windows with a real budget, J3 off, legalizer time and share"
add "kae wb w2 j4 $S7"     2 "$OLD $LEG --set revert_illegal=1"                         "windows with a real budget, J3 off, legalizer time and share, incumbent fallback"
add "kae wb w2 all $S7"    2 "$LEG --set revert_illegal=1"                              "windows with a real budget, J3 + J4"
# where it stops paying: one long run, read as an anytime curve from the iterations' seconds
add "kae wb w4 all $S7"    4 "$LEG --set revert_illegal=1"                              "windows with four budgets, J3 + J4 (anytime curve)"
