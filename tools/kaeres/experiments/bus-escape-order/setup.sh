#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Methods and experiments for tools/kaeres/experiments/bus-escape-order/PLAN.md (written before any run).
#   SHA=<pushed commit> bus-escape-order/setup.sh [smoke]   (from the repository root, with the commit checked out)
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
D=tools/kaeres/experiments/bus-escape-order
add() {  # NAME DESCRIPTION TIMEOUT EXTRA_FLAGS
  $K method add "$1" --kind route --description "$2" \
    --command "$CP $E_ -m kae.route.cli route {input} {output} --seed {attempt} --time {timeout} $4" \
    --param timeout_s="$3" --code kae=.@"$SHA" --harness "$SHA"
}
PLAN="--set escape_lay=plan --set wire_type=shove_fixed"
for t in 900 300; do
  add "kae bridge be-control $t $S7" "bus-escape-order control (bridge defaults) at $S7, ${t} s" $t ""
  add "kae bridge be-plan $t $S7"    "escape plan laid as shove_fixed copper at $S7, ${t} s" $t "$PLAN"
  add "kae bridge be-bus $t $S7"     "escape plan as shove_fixed copper, bus lanes as ordered ribbons at $S7, ${t} s" $t \
    "$PLAN --set escape_bus=true"
done
add "kae bridge be-buswall 900 $S7" "ordered bus escapes kept as walls (rest of the plan soft) at $S7, 900 s" 900 \
  "$PLAN --set escape_bus=true --set wire_scope=except_bus --set unlock_imported=true"
HS="--harness $SHA --kae $SHA"
m() { echo "--method \"kae bridge $1 $S7\""; }
SFX=""
EXP=${EXP:-bus-escape-order}
BOARDS=@$D/boards.txt
if [ "${1:-}" = smoke ]; then SFX="-smoke"; BOARDS=@$D/smoke.txt; fi
eval $K exp create $EXP$SFX --boards $BOARDS --attempts 1 $HS \
  --description "\"wave 2 bus escape: ordered bus escapes vs plan vs bridge, 900 s; PLAN.md in $D\"" \
  $(m "be-control 900") $(m "be-plan 900") $(m "be-bus 900") $(m "be-buswall 900") \
  $(m "be-control 300") $(m "be-plan 300") $(m "be-bus 300")
