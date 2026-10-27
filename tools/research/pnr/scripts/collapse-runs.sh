#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Driver as used for the joint place-and-route runs (copied from git-ignored kae-work/).
# Paths are those of the research host; set KAE_SRC for kae.physics.
# collapse_assign harness runs (sequential, -j 1)
REPO="${KAE_REPO:-$(cd "$(dirname "$0")" && git rev-parse --show-toplevel)}"
cd $REPO
source bench/.venv/bin/activate
M=$REPO/tools/research/collapse_assign/collapse.py
run() { name=$1; shift
  kaebench run --adapter x-$name --command "python $REPO/tools/research/pnr/run.py $M:collapse {input} {output} --budget 120 --seed {attempt} $*" \
    --kinds route -k 1 --timeout 840 -j 1 --splits A,B --name $name > kae-work/$name.log 2>&1
}
run collapse-b3 --opt beta=3.0 --opt beta_free=1.0
run collapse-b3-spread --opt beta=3.0 --opt beta_free=1.0 --opt spread=2
run collapse-b3-random --opt beta=3.0 --opt beta_free=1.0 --opt solver=random
touch kae-work/collapse-runs.done
