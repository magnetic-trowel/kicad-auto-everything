#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
cd "$(dirname "$0")"
PY=${PY:-python3}
OUT=results/results_sa.jsonl
run(){ timeout 1500 $PY sa_place.py "$@" >> $OUT 2>>results/errors_sa.log || echo "{\"failed\": \"$*\"}" >> $OUT; }
run 30 0.5 10 --polish-time 20
run 30 0.1 10 --polish-time 20
run 100 0.5 60 --polish-time 60
run 100 0.1 60 --polish-time 60
run 300 0.5 120 --polish-time 120
run 300 0.1 120 --polish-time 120
run 1000 0.5 300 --polish-time 240
for s in 1 2; do run 100 0.5 60 --polish-time 30 --seed $s; done
echo DONE >> $OUT
