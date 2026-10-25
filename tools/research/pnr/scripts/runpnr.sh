#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Driver as used for the joint place-and-route runs (copied from git-ignored kae-work/).
# Paths are those of the research host; set KAE_SRC for kae.physics.
# usage: runpnr.sh METHOD NAME BUDGET [extra run.py args]
source bench/.venv/bin/activate
m=$1; name=$2; b=$3; shift 3
kaebench run --adapter pnr-$m --command "python $PWD/tools/research/pnr/run.py $m {input} {output} --budget $b --seed {attempt} $*" \
  --kinds place --probe self -k 1 --timeout $((b*6+120)) -j 2 --splits A,B --name $name > kae-work/$name.log 2>&1
