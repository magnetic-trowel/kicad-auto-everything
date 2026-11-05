#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# diag_foreign.sh BOARD OLD_SHA: prepare BOARD's route task with the harness at SHA and at OLD_SHA, and
# compare A0's stored output (merge3-ab) with both (diag_foreign.py). Prints to stdout.
set -euo pipefail
b=$1 old=$2
. "$(dirname "$0")/common.sh"
here=$(cd "$(dirname "$0")" && pwd)
ws=${KAEQ_SCRATCH:-$(mktemp -d "/var/tmp/$USER/rfab-diag-XXXXXX")}
rf_env "$ws" "$b"
ulimit -v 40000000
rf_prepare "$ws/new" "$b"
KB_NEW=$KB; KB=$STORE/code/kicad-auto-everything@${old:0:12}.venv/bin/kaebench rf_prepare "$ws/old" "$b"; KB=$KB_NEW
zcat "$(rf_run_dir "$b" A0)/output.kicad_pcb.gz" > "$ws/out.kicad_pcb"
$KAE_KICAD_WRAP python3 "$here/diag_foreign.py" "${OPS:-$CODE/bench/src/kaebench/kicad_scripts}" "$ws/out.kicad_pcb" \
  "$ws/new/w/tasks/$b/route/input/board.kicad_pcb" "$ws/old/w/tasks/$b/route/input/board.kicad_pcb"
