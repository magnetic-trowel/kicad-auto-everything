#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
cd "$(dirname "$0")"
PY=${PY:-python3}
OUT=results/results_ablation.jsonl
run(){ timeout 700 $PY cpsat_place.py "$@" >> $OUT 2>>results/errors.log || echo "{\"failed\": \"$*\"}" >> $OUT; }
# what makes N=300 hard?  (feasibility, 0.5 mm, 300 s)
run 300 0.5 300 --mode feas --nodecap
run 300 0.5 300 --mode feas --rot none
run 300 0.5 300 --mode feas --rot opt2
run 300 0.5 300 --mode feas --util 0.35
run 300 0.5 300 --mode feas --pack-subsolver
run 200 0.5 300 --mode feas
run 150 0.5 300 --mode feas
# seed variance at N=100
for s in 1 2 3; do run 100 0.5 120 --mode feas --seed $s; run 100 0.5 60 --seed $s; done
echo DONE >> $OUT
$PY geom_bench.py 100 300 1000 3000 > results/results_geom.jsonl 2>>results/errors.log
echo DONE >> results/results_geom.jsonl
