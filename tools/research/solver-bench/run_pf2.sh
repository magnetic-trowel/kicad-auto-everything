#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
cd "$(dirname "$0")"
PY=${PY:-python3}
OUT=results/results_pf2.jsonl
run(){ timeout 1800 $PY pathfinder_bench.py "$@" >> $OUT 2>>results/errors_pf.log || echo "{\"failed\": \"$*\"}" >> $OUT; }
run 50 --engine python
run 50 --engine scipy
run 150 --engine python
run 300 --engine python
run 300 --engine python --layers 4
echo DONE >> $OUT
