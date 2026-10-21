#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
cd "$(dirname "$0")"
PY=${PY:-python3}
OUT=results/results_hier.jsonl
run(){ timeout 1500 $PY hier_place.py "$@" >> $OUT 2>>results/errors_hier.log || echo "{\"failed\": \"$*\"}" >> $OUT; }
run 100 0.5 --cluster-time 1 --top-time 20 --lns-time 40 --window 40 --iter-time 2
run 100 0.1 --cluster-time 1 --top-time 20 --lns-time 40 --window 40 --iter-time 2
run 300 0.5 --cluster-time 1 --top-time 30 --lns-time 60 --window 40 --iter-time 2
run 300 0.1 --cluster-time 1 --top-time 30 --lns-time 60 --window 40 --iter-time 2
run 1000 0.5 --cluster-time 1 --top-time 60 --lns-time 120 --window 50 --iter-time 3
run 1000 0.1 --cluster-time 1 --top-time 60 --lns-time 120 --window 50 --iter-time 3
echo DONE >> $OUT
