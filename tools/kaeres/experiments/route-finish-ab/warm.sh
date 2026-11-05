#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# warm.sh [BOARD...]: warm ~/.cache/kaebench/numba-rf-<SHA7> for the arms' code: kae.route.cli route (with
# escape ground vias and import tails, so their kernels compile too), lastmile and finish on each board's
# route task, with the frozen kae venv, so no arm compiles inside its time budget. Every arm copies this
# cache at the start of each attempt. Default boards: a small two-layer board and a ball-grid board.
#   SHA=... kaeq submit --owner rf-ab --prio 5 --cpus 2 --mem 8G --timeout 2h -- bash warm.sh
set -euo pipefail
. "$(dirname "$0")/common.sh"
boards=("$@"); [ ${#boards[@]} -gt 0 ] || boards=(freetronics-secsense-secsense aifryz-sensor-hub-sensor-hub)
mkdir -p "$NUMBA"
export NUMBA_CACHE_DIR=$NUMBA OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK
ok=0
for b in "${boards[@]}"; do
  ws=$(mktemp -d "/var/tmp/$USER/rfab-warm-XXXXXX")
  rf_env "$ws" "$b"
  ( ulimit -v 40000000
    rf_prepare "$ws" "$b"
    in=$ws/w/tasks/$b/route/input/board.kicad_pcb op="--set operating=$OPSRC/$b.operating.json"
    cd "$ws"
    KAE_ESCAPE_GROUND_VIAS=1 "$KPY" -m kae.route.cli route "$in" route.kicad_pcb --seed 0 --time 240 $op --set import_tails=true > route.log 2>&1
    "$KPY" -m kae.route.cli lastmile "$in" route.kicad_pcb lm.kicad_pcb --seed 0 --time 60 $op > lastmile.log 2>&1
    "$KPY" -m kae.route.cli finish "$in" lm.kicad_pcb fin.kicad_pcb --time 300 $op > finish.log 2>&1
    ! grep -l Traceback ./*.log ) && ok=$((ok + 1)) || echo "$b: warm run failed ($ws)" >&2
  echo "$b: warmed ($ws)"
done
du -sh "$NUMBA"
[ "$ok" -gt 0 ]
