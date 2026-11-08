#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# A/B of pad-edge entry (kae.route.pad_entry, branch pad-edge-entry): both arms are merge3-ab's
# "kae bridge main final" (restart portfolio, --resume 0.5 --final, budget 900 s x sqrt(footprints/40))
# at the same commit; only the pad_entry setting differs:
#
#   kae bridge final pad-centre   default: grid-router ends snap onto pad centres, no trim
#   kae bridge final pad-edge     KAE_PAD_ENTRY=edge: grid-router ends at the pad edge they approach
#                                 (perpendicular, pad_entry_overlap deep, a width on rails), DSN pin ties
#                                 for Freerouting, and kae.route.pad_trim on the routed board
#
# Boards (pad-edge-ab.boards.txt): a tight WLP (circuitmonkey chips-0123), a BGA with 0.5 mm rings
# (zephray nekoink), a power-heavy board and a 4-layer board with planes; two attempts each.
set -euo pipefail
cd "$(dirname "$0")/../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=${SHA:?commit of pad-edge-entry}
KAE=(--code kae=.@$SHA)
H=(--harness $SHA)
KH='$HOME/.cache/kaebench'
FORK="$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
rs() { local f=$1 sl=$2; shift 2
  echo "{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s $f --scale-first --slack $sl $* --"; }
add() {  # NAME DESCRIPTION ENTRY
  local name=$1 desc=$2 entry=$3
  local CP="cp -r $KH/numba-kaemain-e9889fd numba 2>/dev/null;"
  local E="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_PAD_ENTRY=$entry KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
  local FIN="$CP $E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
  $K method add "$name" --kind route --description "$desc; restart portfolio (tools/kaeres/restart.py)" \
    --command "$(rs 60 1.15 --resume 0.5 --final "'$FIN'") '$CP if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else $E -m kae.route.cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@; fi'" \
    --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=4 "${KAE[@]}" "${H[@]}" --allow-dirty
}
add "kae bridge final pad-centre (restarts)" "kae.route.cli at ${SHA:0:7} (pad-edge-entry), pad_entry=centre; --resume 0.5 --final as merge3-ab" centre
add "kae bridge final pad-edge (restarts)" "kae.route.cli at ${SHA:0:7} (pad-edge-entry), KAE_PAD_ENTRY=edge (pad-edge ends, DSN pin ties, pad_trim); --resume 0.5 --final as merge3-ab" edge
$K exp create pad-edge-ab --method "kae bridge final pad-centre (restarts)" --method "kae bridge final pad-edge (restarts)" \
  --boards @tools/kaeres/experiments/pad-edge-ab.boards.txt --attempts 2 --harness $SHA --kae $SHA \
  --description "pad-edge entry A/B at ${SHA:0:7}: centre vs edge, 4 boards x 2 attempts"
