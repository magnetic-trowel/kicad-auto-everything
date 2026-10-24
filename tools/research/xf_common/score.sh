#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Score kaebench place runs (--probe self): KiCad DRC metrics, seed spread, physics.
#   score.sh RUN [RUN ...]        (run names under kae-work/results/)
# Writes kae-work/score/NAME.md (NAME = the runs joined by '+', or $SCORE_NAME), with
# physics JSON in kae-work/score/NAME-phys/ and its table in kae-work/score/NAME-phys.md.
# PHYS_SUITE (default kae-work/phys10.txt) picks the physics boards; NO_PHYS=1 skips them.
# Run it inside the CPU/memory scope from SETUP.md.
set -euo pipefail
[ $# -ge 1 ] || { sed -n 4,9p "$0"; exit 2; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
cd "$ROOT"
. tools/research/xf_common/env.sh
ulimit -v 40000000
NAME="${SCORE_NAME:-$(IFS=+; echo "$*")}"
mkdir -p kae-work/score
DIRS=()
for r in "$@"; do DIRS+=("kae-work/results/${r#kae-work/results/}"); done
{
  echo "# $NAME"
  echo
  echo "## KiCad DRC (attempt-0 = seed 0; tools/research/pnr/compare.py)"
  echo
  python tools/research/pnr/compare.py "${DIRS[@]}"
  echo
  echo "## Seeds (tools/research/xf_common/seeds.py)"
  echo
  python tools/research/xf_common/seeds.py "${DIRS[@]}"
} > "kae-work/score/$NAME.md"
cat "kae-work/score/$NAME.md"
if [ -z "${NO_PHYS:-}" ]; then
  python tools/research/xf_common/physics_score_xf.py "${DIRS[@]}" \
    --suite "${PHYS_SUITE:-kae-work/phys10.txt}" \
    --out "kae-work/score/$NAME-phys" --md "kae-work/score/$NAME-phys.md"
fi
