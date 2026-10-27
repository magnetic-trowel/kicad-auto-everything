#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Driver as used for the joint place-and-route runs (copied from git-ignored kae-work/).
# Paths are those of the research host; set KAE_SRC for kae.physics.
REPO="${KAE_REPO:-$(cd "$(dirname "$0")" && git rev-parse --show-toplevel)}"
cd $REPO; source bench/.venv/bin/activate
for spec in "seq|pnr-seq-v5|x-pnr-seq-v5" "$PWD/tools/research/pnr/methods_combo.py:combo|pnr-combo-v5|x-pnr-combo-v5"; do
  IFS='|' read m name ad <<< "$spec"
  kaebench run --adapter "$ad" --command "python $PWD/tools/research/pnr/run.py $m {input} {output} --budget 120 --seed {attempt}" \
    --kinds place --probe self -k 3 --timeout 840 -j 2 --only @kae-work/ab33.txt --name "$name" > kae-work/$name-k3.log 2>&1
done
