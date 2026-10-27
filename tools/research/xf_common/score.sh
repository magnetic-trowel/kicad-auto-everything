#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Score kaebench joint runs (or place runs with --probe self): DRC metrics, seeds, physics.
#   score.sh RUN [RUN ...]        (run names under $XF_WORK/results/)
# Writes $XF_WORK/score/NAME.md (NAME = the runs joined by '+', or $SCORE_NAME), with
# physics per seed in $XF_WORK/score/NAME-phys/seed-N/ (tables NAME-phys-seedN.md).
# PHYS_SUITE (default $XF_WORK/phys10.txt) picks the physics boards, PHYS_SEEDS (default 3)
# how many seeds; NO_PHYS=1 skips physics. Run it inside the CPU/memory scope from SETUP.md.
set -euo pipefail
[ $# -ge 1 ] || { sed -n 4,9p "$0"; exit 2; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
cd "$ROOT"
. tools/research/xf_common/env.sh
ulimit -v 40000000
W="$XF_WORK"
NAME="${SCORE_NAME:-$(IFS=+; echo "$*")}"
mkdir -p "$W/score"
DIRS=()
for r in "$@"; do DIRS+=("$W/results/$(basename "$r")"); done
PH="$W/score/$NAME-phys"
phys() {  # seed
  python tools/research/xf_common/physics_score_xf.py --attempt "$1" "${DIRS[@]}" \
    --suite "${PHYS_SUITE:-$W/phys10.txt}" --out "$PH/seed-$1" --md "$W/score/$NAME-phys-seed$1.md" \
    > "$PH/seed-$1.log" 2>&1 || echo "physics seed $1 failed: see $PH/seed-$1.log"
}
if [ -z "${NO_PHYS:-}" ]; then
  mkdir -p "$PH"
  phys 0                                   # builds the reference briefs the other seeds copy
  for ((s = 1; s < ${PHYS_SEEDS:-3}; s++)); do phys "$s" & done
  wait
fi
{
  echo "# $NAME"
  echo
  echo "## Summary (tools/research/xf_common/table.py; mean ± sd over seeds, physics on $(basename "${PHYS_SUITE:-$W/phys10.txt}"), lower is better)"
  echo
  python tools/research/xf_common/table.py "$([ -z "${NO_PHYS:-}" ] && echo "$PH" || echo -)" "${DIRS[@]}"
  echo
  echo "## KiCad DRC (attempt-0 = seed 0; tools/research/pnr/compare.py)"
  echo
  python tools/research/pnr/compare.py "${DIRS[@]}"
  echo
  echo "## Seeds (tools/research/xf_common/seeds.py)"
  echo
  python tools/research/xf_common/seeds.py "${DIRS[@]}"
  if [ -z "${NO_PHYS:-}" ]; then
    echo
    echo "## Physics over seeds on $(basename "${PHYS_SUITE:-$W/phys10.txt}") (tools/research/xf_common/physseeds.py)"
    echo
    echo "Method/human gmean ratios (lower is better). Per-seed detail: $NAME-phys-seedN.md."
    echo
    python tools/research/xf_common/physseeds.py "$PH"
  fi
} > "$W/score/$NAME.md"
cat "$W/score/$NAME.md"
