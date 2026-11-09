#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# diffpair-ab: routes differential pairs as pairs first against the bridge alone (see PLAN.md, written before any
# run). One commit for both arms; the only difference is --pairs first.
#   SHA=<pushed commit> tools/kaeres/experiments/diffpair-ab/setup.sh
#   warm the numba cache (numba-kae-dp-${SHA:0:7}, a route run with --pairs first on a small board), then
#   kaeres exp create diffpair-ab-smoke --method "kae bridge dp-control <sha7>" --method "kae bridge dp-pairs <sha7>" \
#      --boards <3 boards from boards.txt> --attempts 1 --harness $SHA --kae $SHA; kaeres exp submit diffpair-ab-smoke; read runs; then
#   kaeres exp create diffpair-ab --method ... --boards @tools/kaeres/experiments/diffpair-ab/boards.txt --attempts 1 --harness $SHA --kae $SHA
#   kaeres exp submit diffpair-ab; kaeres exp install-timer diffpair-ab
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
add() {  # NAME DESCRIPTION EXTRA_FLAGS
  $K method add "$1" --kind route --description "$2" \
    --command "$CP $E_ -m kae.route.cli route {input} {output} --seed {attempt} --time {timeout} $3" \
    --param timeout_s=900 --code kae=.@"$SHA" --harness "$SHA"
}
add "kae bridge dp-control $S7" "diffpair-ab control: kae.route.cli at $S7, no pair routing" ""
add "kae bridge dp-pairs $S7"   "diffpair-ab arm: kae.route.cli --pairs first at $S7 (kae.route.pair_route)" "--pairs first"
