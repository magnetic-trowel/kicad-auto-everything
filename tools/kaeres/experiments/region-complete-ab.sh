#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Does the BGA window repair have merit when no stage competes for time? One kae.route.cli attempt with 6x the
# usual budget (5400 s x sqrt(fp/40)), so every stage stops by its own convergence: Freerouting on completion or
# stagnation, the repair rounds after non-improving rounds (rounds=auto lifts the cap of 5), the window repair
# when its windows run out (up to 50), the last mile when a round joins nothing. The router's own log is
# archived (adapter.log), so each run shows which stage stopped by the clock. The kae bridge on the human
# placement, the 10 merit ball-grid boards, 2 seeds:
#
#   complete region off   --set region=0 --set rounds=auto
#   complete region on    --set rounds=auto, up to 80 % of the time after round 0 and 50 windows for the repair
set -euo pipefail
cd "$(dirname "$0")/../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=${SHA:?commit}
KH='$HOME/.cache/kaebench'
FORK="$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
CP="cp -r $KH/numba-kae-bga-${SHA:0:7} numba 2>/dev/null;"
E_="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
single() {  # NAME SET
  $K method add "$1" --kind route --description "kae.route.cli $2 at ${SHA:0:7} (route-bga-next); one attempt, 6x budget, stages run to convergence" \
    --command "bash -c \"$CP $E_ -m kae.route.cli route {input} {output} --seed {attempt} --time {timeout} $2\"" \
    --param timeout_s=5400 --param timeout_scale=sqrt-fp40 --code kae=.@$SHA --harness $SHA
}
single "kae bridge complete region off" "--set region=0 --set rounds=auto"
single "kae bridge complete region on" "--set rounds=auto --set region_reserve=1000000 --set region_reserve_frac=0.8 --set region_windows=50"
