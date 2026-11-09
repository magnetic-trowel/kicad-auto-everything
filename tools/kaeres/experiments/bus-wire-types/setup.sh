#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Methods and experiments for tools/kaeres/experiments/bus-wire-types/PLAN.md (written before any run).
#   SHA=<pushed commit> bus-wire-types/setup.sh         (from the repository root, with the commit checked out)
set -euo pipefail
cd "$(dirname "$0")/../../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=$(git rev-parse "${SHA:?commit (pushed)}")
S7=${SHA:0:7}
KH='$HOME/.cache/kaebench'
FORK="\$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
NUMBA=numba-kae-dp-$S7
CP="cp -r $KH/$NUMBA numba 2>/dev/null;"
E_="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
add() {  # NAME DESCRIPTION TIMEOUT EXTRA_FLAGS
  $K method add "$1" --kind route --description "$2" \
    --command "$CP $E_ -m kae.route.cli route {input} {output} --seed {attempt} --time {timeout} $4" \
    --param timeout_s="$3" --code kae=.@"$SHA" --harness "$SHA"
}
for t in 900 300; do
  add "kae bridge wt-control $t $S7" "bus-wire-types control at $S7, ${t} s" $t ""
  add "kae bridge wt-shove $t $S7"   "unlocked escape copper as shove_fixed at $S7, ${t} s" $t "--set wire_type=shove_fixed"
  add "kae bridge wt-normal $t $S7"  "unlocked escape copper as normal wiring at $S7, ${t} s" $t "--set wire_type=normal"
  add "kae bridge dps-first $t $S7" "pairs first, locked at $S7, ${t} s" $t "--pairs first"
  add "kae bridge dps-soft $t $S7"  "pairs first, soft (unlocked, shove_fixed) at $S7, ${t} s" $t \
    "--pairs first --set pairs_unlocked=true --set wire_type=shove_fixed --set wire_scope=pairs"
  # own budget: the bridge keeps --time t for everything but the pair stage, whose time (at most min(180, t/4) s)
  # comes on top, so the harness timeout is t plus that (a method killed at t would be no test)
  own=$(( t / 4 < 180 ? t / 4 : 180 ))
  $K method add "kae bridge dps-own+ $t $S7" --kind route --description "pairs first, own budget (+${own} s) at $S7, ${t} s" \
    --command "$CP $E_ -m kae.route.cli route {input} {output} --seed {attempt} --time $t --pairs first --set pairs_own_budget=true" \
    --param timeout_s="$((t + own))" --code kae=.@"$SHA" --harness "$SHA"
done
add "kae bridge wt-plan-route 900 $S7" "escape plan laid as copper, walls, 900 s at $S7" 900 "--set escape_lay=plan"
add "kae bridge wt-plan-shove 900 $S7" "escape plan laid as copper, shove_fixed, 900 s at $S7" 900 "--set escape_lay=plan --set wire_type=shove_fixed"
add "kae bridge dps-after 900 $S7"     "pairs first, after plane escapes, 900 s at $S7" 900 "--pairs first --set pairs_stage=after_escapes"
HS="--harness $SHA --kae $SHA"
B1=@tools/kaeres/experiments/bus-wire-types/boards.txt
B2=@tools/kaeres/experiments/diffpair-ab/boards.txt
m() { echo "--method \"kae bridge $1 $S7\""; }
eval $K exp create bus-wire-types --boards $B1 --attempts 1 $HS \
  --description "\"X1 D1: soft wire types on BGA plane boards, 900 s; PLAN.md in tools/kaeres/experiments/bus-wire-types\"" \
  $(m "wt-control 900") $(m "wt-shove 900") $(m "wt-normal 900") $(m "wt-plan-route 900") $(m "wt-plan-shove 900")
eval $K exp create bus-wire-types-300 --boards $B1 --attempts 1 $HS \
  --description "\"X1 D1 at 300 s; PLAN.md in tools/kaeres/experiments/bus-wire-types\"" \
  $(m "wt-control 300") $(m "wt-shove 300") $(m "wt-normal 300")
eval $K exp create diffpair-soft --boards $B2 --attempts 1 $HS \
  --description "\"X2 D1: pairs-first soft, own budget, after escapes, 900 s; PLAN.md in tools/kaeres/experiments/bus-wire-types\"" \
  $(m "wt-control 900") $(m "dps-first 900") $(m "dps-soft 900") $(m "dps-own+ 900") $(m "dps-after 900")
eval $K exp create diffpair-soft-300 --boards $B2 --attempts 1 $HS \
  --description "\"X2 D1 at 300 s; PLAN.md in tools/kaeres/experiments/bus-wire-types\"" \
  $(m "wt-control 300") $(m "dps-first 300") $(m "dps-soft 300") $(m "dps-own+ 300")
