#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# ab_run.sh MODE BOARD [TAG]: route (plain | physv) or take the human board (human), then evaluate and DRC it.
# Runs the code of the kaeq snapshot it is started in (cwd = repo root).
source ~/.cache/kaebench/env.sh; export APPTAINER_BIND=${KAE_WORK:-/var/tmp/$USER}; ulimit -v 100000000   # address space runs well ahead of RSS (factor caches, threads)
T=${KAEQ_CPUS:-8}; export PYTHONPATH=$PWD/kae/src NUMBA_THREADING_LAYER=omp KAE_EM_THREADS=$T OMP_NUM_THREADS=$T OPENBLAS_NUM_THREADS=$T MKL_NUM_THREADS=$T
PY=${KAE_PY:-python3}             # the venv with kae's dependencies
set -eo pipefail          # a crash inside a pipe (the evaluation into tee) fails the job
mode=$1; board=$2; tag=${3:-r4}; d=$(dirname $board)
echo "code $(git rev-parse --short HEAD 2>/dev/null) mode $mode board $board"
# intake: a board in an older KiCad format is upgraded once, in place, its original (and project files)
# kept beside it; never a board of the read-only corpus. Locked: a board's jobs may start together.
case "$board" in "$HOME"/kae-boards/*) echo "a corpus board: copy it out before routing it"; exit 2;; esac
CUR=${KAE_BOARD_VERSION:-20260206}
(
  flock 9
  v=$(grep -m1 -o '(version [0-9]*' "$board" | grep -o '[0-9]*')
  if [ -n "$v" ] && [ "$v" -lt "$CUR" ]; then
    base=${board%.kicad_pcb}
    [ -f "$base.orig.kicad_pcb" ] || cp "$board" "$base.orig.kicad_pcb"
    for e in kicad_pro kicad_dru; do if [ -f "$base.$e" ] && [ ! -f "$base.orig.$e" ]; then cp "$base.$e" "$base.orig.$e"; fi; done
    $KAE_KICAD_WRAP kicad-cli pcb upgrade --force "$board" >/dev/null
    echo "intake: upgraded $board from format $v to $(grep -m1 -o '(version [0-9]*' "$board" | grep -o '[0-9]*') (original kept)"
  fi
) 9>"$board.lock"
case "$mode" in
human) out=$board ;;
plain) out=$d/plain_$tag.kicad_pcb; $PY -u -W ignore -m kae.em.pnr $board $out --plain ;;
physv) out=$d/physv_$tag.kicad_pcb; $PY -u -W ignore -m kae.em.pnr $board $out --verify ;;
esac
$PY -u -W ignore -m kae.excite.evaluate $out --pitch 0.25 -o $d/ev_${mode}_$tag.json | tee $d/ev_${mode}_$tag.txt
if [ "$mode" != human ]; then
  $KAE_KICAD_WRAP kicad-cli pcb drc --refill-zones --format json --severity-error -o $d/drc_${mode}_$tag.json $out
  python3 -c "import json,collections,sys; v=json.load(open(sys.argv[1])); c=collections.Counter(x['type'] for x in v.get('violations',[])); print('drc', dict(c), 'unconnected', len(v.get('unconnected_items',[])))" $d/drc_${mode}_$tag.json
fi
