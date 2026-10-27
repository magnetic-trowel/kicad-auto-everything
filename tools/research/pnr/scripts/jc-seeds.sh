#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Driver as used for the joint place-and-route runs (copied from git-ignored kae-work/).
# Paths are those of the research host; set KAE_SRC for kae.physics.
REPO="${KAE_REPO:-$(cd "$(dirname "$0")" && git rev-parse --show-toplevel)}"
cd $REPO; source bench/.venv/bin/activate
kaebench run --adapter x-jcollapse-jc-ab33-v3 --command "python $PWD/tools/research/pnr/run.py $PWD/kae-work/jc-snap/jc_v3.py:jc {input} {output} --budget 120 --seed {attempt} " \
  --kinds place --probe self -k 3 --timeout 1200 -j 2 --only @kae-work/ab33.txt --name jcollapse-jc-ab33-v3 > kae-work/jc-seeds.log 2>&1
