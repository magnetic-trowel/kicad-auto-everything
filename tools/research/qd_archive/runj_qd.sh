#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# runj_qd.sh FN NAME BUDGET SUITE JOBS SEEDS -- kae-v7/runj.sh for a qd plug-in (FN in
# tools/research/qd_archive/qd.py), run from the checkout WT (set WT to a frozen
# `git worktree` so edits to the shared checkout's engine cannot reach a running benchmark).
set -e
FN=$1 NAME=$2 BUDGET=$3 SUITE=$4 JOBS=$5 SEEDS=$6
REPO=/home/user/kicad-auto-everything
WT=${WT:-$REPO}
export KAE_SRC=${KAE_SRC_SANDBOX:-$HOME/.cache/kaebench/kae-phys/src}
cd $REPO
source bench/.venv/bin/activate
echo "checkout $WT at $(git -C "$WT" rev-parse --short HEAD), dirty files: $(git -C "$WT" status --short --untracked-files=no | wc -l)"
exec kaebench --workdir kae-v7 run --adapter x-$NAME \
  --command "python $WT/tools/research/pnr/run.py $WT/tools/research/qd_archive/qd.py:$FN {input} {output} --budget $BUDGET --seed {attempt}" \
  --kinds joint -k $SEEDS --timeout $((BUDGET*8+120)) -j $JOBS --only @$SUITE --name $NAME
