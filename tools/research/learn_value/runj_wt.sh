#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# runj_wt.sh WT SPEC NAME BUDGET SUITE JOBS SEEDS -- kae-v7/runj.sh, but the method (run.py,
# engine, plug-in) comes from a frozen git worktree WT, so edits in the shared checkout
# cannot leak into a long run. SPEC is relative to WT (e.g. tools/research/learn_value/lv_jc.py:jc_value).
REPO="${KAE_REPO:-$(cd "$(dirname "$0")" && git rev-parse --show-toplevel)}"
set -e
WT=$1 SPEC=$2 NAME=$3 BUDGET=$4 SUITE=$5 JOBS=$6 SEEDS=$7
cd $REPO
source bench/.venv/bin/activate
echo "worktree $WT at $(git -C "$WT" rev-parse --short HEAD), dirty files: $(git -C "$WT" status --short | wc -l)"
exec kaebench --workdir kae-v7 run --adapter x-$NAME \
  --command "python $WT/tools/research/pnr/run.py $WT/$SPEC {input} {output} --budget $BUDGET --seed {attempt}" \
  --kinds joint -k $SEEDS --timeout $((BUDGET*8+120)) -j $JOBS --only @$SUITE --name $NAME
