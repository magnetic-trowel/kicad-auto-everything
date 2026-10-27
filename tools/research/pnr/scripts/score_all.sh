#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Driver as used for the joint place-and-route runs (copied from git-ignored kae-work/).
# Paths are those of the research host; set KAE_SRC for kae.physics.
# usage: kae-work/score_all.sh OUT_NAME RUN_DIR...   -> kae-work/score/<OUT_NAME>.md
REPO="${KAE_REPO:-$(cd "$(dirname "$0")" && git rev-parse --show-toplevel)}"
# DRC (legal, clean, completion, length, vias) + fast physics (place terms) + full routed
# physics, both as ratios to the human board on the boards with physics structures.
cd $REPO; source bench/.venv/bin/activate
out=$1; shift
mkdir -p kae-work/score
S=${KAE_SRC:-$HOME/.cache/kaebench/kae-phys/src}
{ echo "## DRC (all 33 boards)"; python tools/research/pnr/compare.py "$@" | head -$(( $# + 4 ));
  echo; echo "## Physics (boards with physics structures; fast = place terms, routed = full recheck on copper)";
  PYTHONPATH=$S KAE_KICAD_PYTHON=/usr/bin/python3 python tools/research/pnr_phys/physics_score.py "$@" \
    --suite tools/research/pnr/suites/mcts-phys10.txt --out kae-work/score/$out-phys --md kae-work/score/$out-phys.md > kae-work/score/$out-phys.log 2>&1;
  sed -n 1,12p kae-work/score/$out-phys.md; } > kae-work/score/$out.md
cat kae-work/score/$out.md
