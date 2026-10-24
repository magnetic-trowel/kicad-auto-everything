#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# usage: run_cplace.sh SPEC RUN_NAME BUDGET_S SUITE_FILE JOBS SEEDS [extra run.py args]
# Same as kae-work/runext.sh, with SEEDS attempts (attempt N runs --seed N, as the
# 3-seed pnr-seq-v5 / pnr-combo-v5 baselines).
cd "$(dirname "$0")/../../.."
source bench/.venv/bin/activate
spec=$1; name=$2; b=$3; suite=$4; j=$5; k=$6; shift 6
kaebench run --adapter "x-$name" --command "python $PWD/tools/research/pnr/run.py $spec {input} {output} --budget $b --seed {attempt} $*" \
  --kinds place --probe self -k "$k" --timeout $((b*6+120)) -j "$j" --only @"$suite" --name "$name" > "kae-work/$name.log" 2>&1
