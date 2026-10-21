#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
cd "$(dirname "$0")"
# Sequential runs (each uses 4 workers on a 4-core box) -> results.jsonl
PY=${PY:-python3}
OUT=results/results.jsonl
run(){ timeout 700 $PY cpsat_place.py "$@" >> $OUT 2>>results/errors.log || echo "{\"failed\": \"$*\"}" >> $OUT; }
# A: time to first feasible
for n in 30 100 300 1000; do for g in 0.5 0.1; do run $n $g 300 --mode feas; done; done
# B: optimisation, 60 s, variable-size rotation encoding vs two-optional-interval encoding
for n in 30 100 300; do for g in 0.5 0.1; do run $n $g 60 --rot var; run $n $g 60 --rot opt2; done; done
# no-rotation reference
for n in 100 300; do run $n 0.5 60 --rot none; done
# C: two-sided
for n in 100 300; do run $n 0.5 60 --sides 2; done
# D: dedicated packing subsolver
run 300 0.5 60 --pack-subsolver
# E: utilisation stress (feasibility)
for u in 0.55 0.65 0.75; do run 100 0.5 120 --mode feas --util $u; run 300 0.5 300 --mode feas --util $u; done
# F: 1000 parts optimisation 300 s
run 1000 0.5 300
echo DONE >> $OUT
