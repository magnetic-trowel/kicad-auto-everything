#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# loop-win batch 1 (PLAN.md), after the smoke has been read: all six arms on seed 0 (loop-win), then R, W0 and Wall
# on seed 1 (loop-win-k2, attempt 1 of the same methods). The smoke's two boards stay (their seed-0 runs are reused).
#   S7=48ffd89 tools/kaeres/experiments/loop-win/submit.sh
set -euo pipefail
cd "$(dirname "$0")/../../../.."
export PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
K="python3 tools/kaeres/kaeres.py"
S7=${S7:?short commit of the methods}
SHA=$(git rev-parse "$S7")
D=tools/kaeres/experiments/loop-win
common=(--harness "$SHA" --kae "$SHA" --env KAE_STEP_CACHE=/var/tmp/$USER/step-cache --reuse-runs)
$K exp create loop-win --boards @$D/boards.txt --attempts 1 "${common[@]}" --description "loop-win batch 1, seed 0 (PLAN.md)" \
  --method "kae lw restarts $S7" --method "kae lw joint ctl $S7" --method "kae lw joint evidence $S7" \
  --method "kae lw joint tabu $S7" --method "kae lw joint exact $S7" --method "kae lw joint all $S7"
$K exp submit loop-win
$K exp create loop-win-k2 --boards @$D/boards.txt --attempts 2 "${common[@]}" --description "loop-win batch 1, seed 1 of R, W0, Wall (PLAN.md)" \
  --method "kae lw restarts $S7" --method "kae lw joint ctl $S7" --method "kae lw joint all $S7"
$K exp submit loop-win-k2
