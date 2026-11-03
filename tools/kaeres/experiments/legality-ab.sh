#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# A/B of placement legality severities and body relaxation (branch decide-legality; decisions P2/P3 of
# the 2026-11 divergence audit, docs/research/placement/kae-exact-legality.md "Severities", "Bodies").
# kae place, task kind place (and place-fixed), Freerouting probe, score v11 (legal_strict). Arms differ
# only in two kae place flags, at one commit:
#
#   kae place legality old       --severity board  --relax-bodies auto      (the behaviour before the change)
#   kae place legality strict    --severity strict --relax-bodies off       (drawn courtyards everywhere)
#   kae place legality level-c   --severity level_c --relax-bodies off      (new default: courtyards at IPC Level C
#                                                                            where the project waives them)
#   kae place legality escalate  --severity level_c --relax-bodies escalate (bodies freed only when stuck)
#
# Boards (experiments/):
#   legality-ab.boards.txt          113: every merit-500 board whose project downgrades a strict check (26)
#                                   plus 92 corpus boards sampled per waived check (seed 1)
#   legality-ab-relax.boards.txt     52: merit-500 boards over 95% utilization with through-hole parts
#                                   without a courtyard (where relax_bodies 'auto' fires up front)
#   legality-ab-control.boards.txt   40: merit-500 boards that waive nothing and do not trigger it
# Attempts: seeds 0-1 (k = 2). Budget 600 s x sqrt(footprints/40).
# Decide on: legal_strict (primary), legal, probe completion and probe_cp, hpwl_ratio, the place
# report's hazards (body_overlap count), and placement_errors_strict by type. Control: no arm may move.
set -euo pipefail
cd "$(dirname "$0")/../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=${SHA:?commit of decide-legality}
KAE=(--code kae=.@$SHA)
H=(--harness $SHA)
arm() {  # NAME SEVERITY RELAX
  for kind in place place-fixed; do
    $K method add "$1 ($kind)" --kind $kind --param probe=freerouting \
      --description "kae place --severity $2 --relax-bodies $3 at ${SHA:0:7} (decide-legality)" \
      --command "env OMP_NUM_THREADS=1 KAE_WORKERS=4 {py:kae} -m kae.cli place {input} {output} --seed {attempt} --time {timeout} --severity $2 --relax-bodies $3" \
      --param timeout_s=600 --param timeout_scale=sqrt-fp40 "${KAE[@]}" "${H[@]}"
  done
}
arm "kae place legality old" board auto
arm "kae place legality strict" strict off
arm "kae place legality level-c" level_c off
arm "kae place legality escalate" level_c escalate
cat tools/kaeres/experiments/legality-ab.boards.txt tools/kaeres/experiments/legality-ab-relax.boards.txt \
    tools/kaeres/experiments/legality-ab-control.boards.txt | sort -u > /tmp/legality-ab.$$.txt
for kind in place place-fixed; do
  $K exp create legality-ab-$kind --boards @/tmp/legality-ab.$$.txt --attempts 2 \
    --method "kae place legality old ($kind)" --method "kae place legality strict ($kind)" \
    --method "kae place legality level-c ($kind)" --method "kae place legality escalate ($kind)" \
    --description "P2/P3 legality A/B ($kind): severities board/strict/level_c, relax_bodies auto/off/escalate"
done
echo "submit with: $K exp submit legality-ab-place; $K exp submit legality-ab-place-fixed"
