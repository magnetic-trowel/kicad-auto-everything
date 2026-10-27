#!/bin/sh
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Method launcher inside the kaebench sandbox (runext.sh's --command):
#   xf_run.sh SPEC INPUT OUTPUT BUDGET SEED [run.py options ...]
# The sandbox makes everything but the attempt's work dir (the cwd) read-only, and numba
# only uses a writable cache. Copy the warm cache ($NUMBA_CACHE_DIR, see warm_numba.sh)
# into the work dir so kernels load instead of compiling inside the CPU budget.
set -eu
SPEC=$1 IN=$2 OUT=$3 BUDGET=$4 SEED=$5
shift 5
if [ -d "${NUMBA_CACHE_DIR:-}" ]; then
  cp -r "$NUMBA_CACHE_DIR" "$PWD/numba-cache"
  NUMBA_CACHE_DIR="$PWD/numba-cache"
  export NUMBA_CACHE_DIR
fi
# The venv's own interpreter, so a sandbox that hides it fails here instead of falling
# back to the system Python.
exec "${VIRTUAL_ENV:?source env.sh first}/bin/python" "$(dirname "$0")/../pnr/run.py" "$SPEC" "$IN" "$OUT" --budget "$BUDGET" --seed "$SEED" "$@"
