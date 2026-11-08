#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# eval_intent.sh BOARD.kicad_pcb OPERATING.json INTENT.json OUTDIR [TAG]
# One board through kae's physics evaluator under its operating facts, then scored under its intent:
# OUTDIR/TAG.ev.json (observations), OUTDIR/TAG.status.json (kae.intent status). The board is copied
# with its .kicad_pro/.kicad_dru and upgraded to the current KiCad format first (never edited in place).
set -eo pipefail
board=$1 op=$2 it=$3 out=$4 tag=${5:-board}
source ~/.cache/kaebench/env.sh; export APPTAINER_BIND=${KAE_WORK:-/var/tmp/$USER}
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
T=${KAEQ_CPUS:-4}; export PYTHONPATH=$REPO/kae/src NUMBA_THREADING_LAYER=omp KAE_EM_THREADS=$T OMP_NUM_THREADS=$T OPENBLAS_NUM_THREADS=$T MKL_NUM_THREADS=$T
PY=${KAE_PY:-python3}
ulimit -v ${KAE_EVAL_VMEM_KB:-100000000}
mkdir -p "$out"; w=$out/$tag.work; rm -rf "$w"; mkdir -p "$w"
base=${board%.kicad_pcb}
case "$board" in *.gz) zcat "$board" > "$w/board.kicad_pcb"; base=${board%.kicad_pcb.gz};; *) cp "$board" "$w/board.kicad_pcb";; esac
[ -n "$KAE_RULES_FROM" ] && base=${KAE_RULES_FROM%.kicad_pcb}      # a run's output: the board's own rules
for e in kicad_pro kicad_dru; do [ -f "$base.$e" ] && cp "$base.$e" "$w/board.$e"; done
$KAE_KICAD_WRAP kicad-cli pcb upgrade --force "$w/board.kicad_pcb" >/dev/null 2>&1 || true
t0=$(date +%s)
$PY -u -W ignore -m kae.excite.evaluate "$w/board.kicad_pcb" --pitch 0.25 --max-cells ${KAE_EVAL_MAX_CELLS:-3000000} --intent "$op" -o "$out/$tag.ev.json" > "$out/$tag.ev.txt" 2>&1
$PY -u -W ignore -m kae.intent status "$out/$tag.ev.json" --intent "$it" -o "$out/$tag.status.json" > "$out/$tag.status.txt" 2>&1
echo "eval_s $(( $(date +%s) - t0 ))" >> "$out/$tag.status.txt"
cat "$out/$tag.status.txt" | head -40
