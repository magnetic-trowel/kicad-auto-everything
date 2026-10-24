#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Run a pnr-engine method as a kaebench place run with self-routed copper.
#   runext.sh SPEC NAME BUDGET SUITE JOBS [SEEDS=3]
# SPEC = /abs/path/module.py:function (or a methods.py name); BUDGET in CPU seconds;
# SUITE = file with one board id per line; results in kae-work/results/NAME/x-NAME/.
# Run it inside the CPU/memory scope from SETUP.md; it does not cap CPU itself.
set -euo pipefail
[ $# -ge 5 ] || { sed -n 4,9p "$0"; exit 2; }
SPEC=$1 NAME=$2 BUDGET=$3 SUITE=$4 JOBS=$5 SEEDS=${6:-3}
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
cd "$ROOT"
. tools/research/xf_common/env.sh
ulimit -v 40000000
SUITE="$(realpath "$SUITE")"
exec kaebench run --adapter "x-$NAME" \
  --command "exec python $ROOT/tools/research/pnr/run.py $SPEC {input} {output} --budget $BUDGET --seed {attempt}" \
  --kinds place --probe self -k "$SEEDS" --timeout $((BUDGET * 6 + 120)) -j "$JOBS" \
  --only "@$SUITE" --name "$NAME"
