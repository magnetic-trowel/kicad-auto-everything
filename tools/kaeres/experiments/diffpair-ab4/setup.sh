#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# diffpair-ab4 methods (PLAN.md): the bridge with and without differential pairs routed as pairs, after the
# pair-rule and post-budget fixes. One commit for every arm; only flags and budgets differ. Freerouting is the
# pinned fork d137fd1, named explicitly.
#   SHA=<pushed commit> tools/kaeres/experiments/diffpair-ab4/setup.sh
set -euo pipefail
cd "$(dirname "$0")/../../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=$(git rev-parse "${SHA:?commit (pushed)}")
S7=${SHA:0:7}
KH='$HOME/.cache/kaebench'
FORK="\$HOME/.cache/kaebench/kae-freerouting-fork-d137fd1/bin/freerouting"
NUMBA=numba-kae-dp4-$S7
CP="cp -r $KH/$NUMBA numba 2>/dev/null;"
E_="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
add() {  # NAME DESCRIPTION HARNESS_TIMEOUT ROUTER_TIME FLAGS
  $K method add "$1" --kind route --description "$2" \
    --command "$CP $E_ -m kae.route.cli route {input} {output} --seed {attempt} --time $4 $5" \
    --param timeout_s="$3" --code kae=.@"$SHA" --harness "$SHA"
}
OWN="--pairs first --set pairs_own_budget=true"
add "kae bridge dp4-control 900 $S7"  "diffpair-ab4 C: bridge, no pair routing, 900 s, fork d137fd1, at $S7" 900 900 ""
add "kae bridge dp4-control 1080 $S7" "diffpair-ab4 Ct: bridge, no pair routing, 1080 s (time-matched to F/FS), at $S7" 1080 1080 ""
add "kae bridge dp4-first 900 $S7"    "diffpair-ab4 F: pairs first (board's pair rules), own pair budget <= 180 s on top of 900 s, at $S7" 1080 900 "$OWN"
add "kae bridge dp4-firstsoft 900 $S7" "diffpair-ab4 FS: F with only the coupled legs locked, fan-ins shove_fixed, at $S7" 1080 900 \
  "$OWN --set pairs_lock=spine --set wire_type=shove_fixed --set wire_scope=pairs"
add "kae bridge dp4-post 900 $S7"     "diffpair-ab4 P: pairs re-laid after a full 900 s route and repair, own 240 s, kept if no worse, at $S7" 1140 900 "--pairs post"
