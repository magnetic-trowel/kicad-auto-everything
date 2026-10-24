# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Shared environment for the xf experiments. Source it from the worktree root:
#   source tools/research/xf_common/env.sh
# Override XF_PHYS (the physics-engine worktree) and XF_BIND before sourcing if needed.
XF_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
export XF_ROOT
. "$XF_ROOT/bench/.venv/bin/activate"            # also sources the kaebench env.sh (KAE_KICAD_WRAP)
export APPTAINER_BIND="${XF_BIND:-$(dirname "$XF_ROOT")}"   # the KiCad container must see the worktree
export KAE_SRC="${XF_PHYS:-$(dirname "$XF_ROOT")/kae-phys}/kae/src"
export KAE_KICAD_PYTHON="$XF_ROOT/tools/research/xf_common/kicad-python"
export NUMBA_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export NUMBA_CACHE_DIR="$XF_ROOT/kae-work/numba-cache"   # compile once, not per attempt
mkdir -p "$NUMBA_CACHE_DIR"
