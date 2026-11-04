#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Does the dense-window repair (kae.route.region, close-bga-region) pay when it gets time? The kae bridge on the
# human placement (route task: the router alone), 900 s x sqrt(fp/40), the 10 merit ball-grid boards
# (escape-ab-grid.boards.txt), 3 seeds. Arms differ only in the repair's time (repair.region_reserve):
#
#   restart wrapper (--resume 0.5 --final), as the merit bridge:
#     region-reserve 0      --set region_reserve=0   the repair only when the rounds leave it 120 s (before e67ec8e)
#     region-reserve auto   default                  time in proportion to the opens at dense packages, <= 50 %
#     region-reserve max    up to 80 % of the time after round 0, up to 10 windows
#   one attempt with the whole budget (no restarts: the repair's best chance at long windows):
#     single region-reserve 0, single region-reserve max
#
# The user's instruction: give the repair every chance to show merit; speed comes later.
# Method and experiment harness: the same commit (SHA).
set -euo pipefail
cd "$(dirname "$0")/../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=${SHA:?commit}
KAE=(--code kae=.@$SHA)
H=(--harness $SHA)
KH='$HOME/.cache/kaebench'
FORK="$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
CP="cp -r $KH/numba-kae-bga-${SHA:0:7} numba 2>/dev/null;"
E_="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
FIN="$CP $E_ -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
rs() { echo "{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s 60 --scale-first --slack 1.15 --resume 0.5 --final '$FIN' --"; }
arm() {  # NAME SET
  $K method add "$1" --kind route --description "kae.route.cli $2 at ${SHA:0:7} (route-bga-next); restart --resume 0.5 --final; restart portfolio (tools/kaeres/restart.py)" \
    --command "$(rs) '$CP if [ \"\$KAE_RESUME\" = 1 ]; then $E_ -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@ $2; else $E_ -m kae.route.cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@ $2; fi'" \
    --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=4 "${KAE[@]}" "${H[@]}"
}
MAX="--set region_reserve=1000000 --set region_reserve_frac=0.8 --set region_windows=10"
single() {  # NAME SET: one kae.route.cli attempt with the whole budget
  $K method add "$1" --kind route --description "kae.route.cli $2 at ${SHA:0:7} (route-bga-next); one attempt, the whole budget" \
    --command "bash -c \"$CP $E_ -m kae.route.cli route {input} {output} --seed {attempt} --time {timeout} $2\"" \
    --param timeout_s=900 --param timeout_scale=sqrt-fp40 "${KAE[@]}" "${H[@]}"
}
arm "kae bridge region-reserve 0 (restarts)" "--set region_reserve=0"
arm "kae bridge region-reserve auto (restarts)" ""
arm "kae bridge region-reserve max (restarts)" "$MAX"
single "kae bridge single region-reserve 0" "--set region_reserve=0"
single "kae bridge single region-reserve max" "$MAX"
