#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Methods and experiments for tools/kaeres/experiments/bus-post-relay/PLAN.md (written before any run).
#   SHA=<pushed commit> bus-post-relay/setup.sh        (from the repository root)
set -euo pipefail
cd "$(dirname "$0")/../../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=$(git rev-parse "${SHA:?commit (pushed)}")
S7=${SHA:0:7}
KH='$HOME/.cache/kaebench'
FORK="\$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
CP="cp -r $KH/numba-kae-dp-$S7 numba 2>/dev/null;"
E_="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
add() {  # NAME DESCRIPTION TIMEOUT EXTRA_FLAGS
  $K method add "$1" --kind route --description "$2" \
    --command "$CP $E_ -m kae.route.cli route {input} {output} --seed {attempt} --time {timeout} $4" \
    --param timeout_s="$3" --code kae=.@"$SHA" --harness "$SHA"
}
for t in 900 300; do
  add "kae bridge pr-control $t $S7" "bus-post-relay control at $S7, ${t} s" $t ""
  add "kae bridge pr-post $t $S7" "pairs re-laid after routing, no rip, at $S7, ${t} s" $t "--pairs post"
  add "kae bridge pr-rip40 $t $S7" "pairs re-laid after routing, priced rip-up of 40 items, at $S7, ${t} s" $t \
    "--pairs post --set pairs_rip=true --set pairs_max_rip=40"
done
add "kae bridge pr-rip10 900 $S7" "pairs re-laid after routing, priced rip-up of 10 items, at $S7, 900 s" 900 \
  "--pairs post --set pairs_rip=true --set pairs_max_rip=10"
HS="--harness $SHA --kae $SHA"
B=@tools/kaeres/experiments/diffpair-ab/boards.txt
m() { echo "--method \"kae bridge $1 $S7\""; }
eval $K exp create bus-post-relay --boards $B --attempts 1 $HS \
  --description "\"E1/H7: pairs re-laid after routing with priced rip-up, 900 s; PLAN.md in tools/kaeres/experiments/bus-post-relay\"" \
  $(m "pr-control 900") $(m "pr-post 900") $(m "pr-rip10 900") $(m "pr-rip40 900")
eval $K exp create bus-post-relay-300 --boards $B --attempts 1 $HS \
  --description "\"E1/H7 at 300 s; PLAN.md in tools/kaeres/experiments/bus-post-relay\"" \
  $(m "pr-control 300") $(m "pr-post 300") $(m "pr-rip40 300")
