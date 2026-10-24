#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Compile a method's numba kernels into $NUMBA_CACHE_DIR before a sandboxed run, which
# can only copy the cache (xf_run.sh). Runs each SPEC once, unsandboxed, on one board.
#   warm_numba.sh BOARD_ID SPEC [SPEC ...]      (budget $WARM_BUDGET, default 40)
# Run it after any change to jitted code (numba re-keys on the source file's mtime).
set -euo pipefail
[ $# -ge 2 ] || { sed -n 4,7p "$0"; exit 2; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE/../../.."
. tools/research/xf_common/env.sh
ulimit -v 40000000
B=$1
shift
IN="$XF_WORK/tasks/$B/place/input/board.kicad_pcb"
for spec in "$@"; do
  d="$XF_WORK/warm/$(basename "${spec//:/-}")"
  rm -rf "$d"
  mkdir -p "$d"
  python tools/research/pnr/run.py "$spec" "$IN" "$d/board.kicad_pcb" --budget "${WARM_BUDGET:-40}" >/dev/null &
done
wait
echo "numba cache: $(find "$NUMBA_CACHE_DIR" -name '*.nbi' | wc -l) kernels"
