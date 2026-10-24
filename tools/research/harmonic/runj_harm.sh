#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# runj_harm.sh SPEC NAME BUDGET SUITE JOBS SEEDS -- kae-v7/runj.sh with
# KAE_SRC pointing at a copy of the kae physics sources in the kaebench tool cache (the
# default KAE_SRC is under /tmp, which the sandbox replaces; the tool cache stays readable).
set -e
SPEC=$1 NAME=$2 BUDGET=$3 SUITE=$4 JOBS=$5 SEEDS=$6
export KAE_SRC=${KAE_SRC_SANDBOX:-/root/.cache/kaebench/kae-phys/src}
cd /home/user/kicad-auto-everything
source bench/.venv/bin/activate
exec kaebench --workdir kae-v7 run --adapter x-$NAME \
  --command "python $PWD/tools/research/pnr/run.py $SPEC {input} {output} --budget $BUDGET --seed {attempt}" \
  --kinds joint -k $SEEDS --timeout $((BUDGET*8+120)) -j $JOBS --only @$SUITE --name $NAME
