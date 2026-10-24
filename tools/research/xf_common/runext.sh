#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Run a pnr-engine method as a kaebench joint run (place and route in one output).
#   runext.sh SPEC NAME BUDGET SUITE JOBS [SEEDS=3]
# SPEC = /abs/path/module.py:function (or a methods.py name); BUDGET in CPU seconds;
# SUITE = file with one board id per line; results in $XF_WORK/results/NAME/x-NAME/joint/.
# Run it inside the CPU/memory scope from SETUP.md; it does not cap CPU itself.
set -euo pipefail
[ $# -ge 5 ] || { sed -n 4,9p "$0"; exit 2; }
SPEC=$1 NAME=$2 BUDGET=$3 SUITE=$4 JOBS=$5 SEEDS=${6:-3}
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
SUITE="$(realpath "$SUITE")"
cd "$ROOT"
. tools/research/xf_common/env.sh
ulimit -v 40000000
# The sandbox shows the method only its work dir, plus these read-only paths: the code,
# the physics engine, the warm numba cache, and the venv's base interpreter (a uv-managed
# Python under the home directory, which the sandbox hides: without it `python` silently
# falls back to the system Python and its old packages). Hide everything holding human layouts
# that the harness does not hide itself (it hides $XF_WORK/tasks and results).
PYBASE="$(dirname "$(python -c 'import sys; print(sys.base_prefix)')")"
RO=(--sandbox-ro "$PYBASE" --sandbox-ro "$ROOT" --sandbox-ro "$(realpath -m "$KAE_SRC/../..")" --sandbox-ro "$NUMBA_CACHE_DIR")
HIDE="$XF_WORK/cache:$XF_WORK/phys-cache"
for w in "$ROOT"/kae-work*; do
  [ "$(realpath "$w")" = "$XF_WORK" ] || HIDE="$HIDE:$w"
done
export KAE_SANDBOX_HIDE="$HIDE${KAE_SANDBOX_HIDE:+:$KAE_SANDBOX_HIDE}"
exec kaebench --workdir "$XF_WORK" run --adapter "x-$NAME" "${RO[@]}" \
  --command "exec $HERE/xf_run.sh $SPEC {input} {output} $BUDGET {attempt}" \
  --kinds joint -k "$SEEDS" --timeout $((BUDGET * 6 + 120)) -j "$JOBS" \
  --only "@$SUITE" --name "$NAME"
