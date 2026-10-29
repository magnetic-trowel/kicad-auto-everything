#!/bin/sh
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# One attempt of a hybrid for restart.py: a pnr method places (and routes) with half the time, its
# copper is stripped as prepare strips a route task's input, and kae's bridge routes that placement
# with the rest of the time.
#   hybrid_attempt.sh SPEC INPUT OUTPUT TIME SEED [run.py options ...]
# Environment (set by the method template):
#   PNR_CODE, PNR_VENV, PNR_NUMBA  pnr checkout, its venv and warm numba cache (xf_run.sh copies it)
#   KAE_PY, KAE_NUMBA              kae's python and warm numba cache, for kae.route.cli
#   HARNESS_CODE                   kaebench (strip-routing)
set -eu
SPEC=$1 IN=$2 OUT=$3 T=$4 SEED=$5
shift 5
t0=$(date +%s)
half=$((T / 2))
mkdir -p pnr
(cd pnr && VIRTUAL_ENV=$PNR_VENV NUMBA_CACHE_DIR=$PNR_NUMBA \
  PYTHONPATH=$PNR_CODE/tools/research/collapse_joint:$PNR_CODE/tools/research/xf_minplus \
  KAE_KICAD_PYTHON=$PNR_CODE/tools/research/xf_common/kicad-python \
  NUMBA_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  sh "$PNR_CODE/tools/research/xf_common/xf_run.sh" "$PNR_CODE/tools/research/$SPEC" "$IN" "$PWD/board.kicad_pcb" \
  "$half" "$SEED" "$@") > pnr.log 2>&1 || echo "pnr exited $?"
if [ ! -s pnr/board.kicad_pcb ]; then
  echo "pnr wrote no board"; tail -20 pnr.log; exit 1
fi
PYTHONPATH=$HARNESS_CODE/bench/src "$KAE_PY" -c \
  "import sys; from kaebench import tools; print(tools.run_ops('strip-routing', sys.argv[1], sys.argv[2]))" \
  pnr/board.kicad_pcb placed.kicad_pcb
for ext in kicad_pro kicad_dru; do  # the task's rules
  [ -f "${IN%.kicad_pcb}.$ext" ] && cp "${IN%.kicad_pcb}.$ext" "placed.$ext"
done
left=$((T - ($(date +%s) - t0)))
[ "$left" -ge 60 ] || left=60
cp -r "$KAE_NUMBA" numba 2>/dev/null || true
echo "pnr placement done after $(( $(date +%s) - t0 ))s; kae bridge gets ${left}s"
exec env NUMBA_CACHE_DIR="$PWD/numba" "$KAE_PY" -m kae.route.cli route placed.kicad_pcb "$OUT" --seed "$SEED" --time "$left"
