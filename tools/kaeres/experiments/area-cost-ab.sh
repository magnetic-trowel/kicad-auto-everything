#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# A/B of the neutral copper area price (kae.intent.route AREA_COST, the knob route.area_cost) on the route
# task. Each arm is new_board.sh's kae-plain: kae.em.pnr --plain --lock under a neutral intent that differs
# only in the knob, then the Freerouting bridge completes every other net. Widths go as a^-1/2:
#
#   kae-plain area 0.05   the default since 5199c80: about economic for an always-on mains board
#                         (docs/topics/architecture/intent-driven-objectives.md, defaults table)
#   kae-plain area 0.2    the same at about 25 % duty
#   kae-plain area 0.5    near the human widths: implied median 0.64 mW_eq/mm^2 over 147 rail nets >= 0.1 A
#                         on 59 qualified boards (tools/research/physics/area_cost_widths.py)
#
# Deterministic (plain pnr, Freerouting): k = 1. Boards: the qualified-kicad-10.0.7 suite; the 59 with a
# DC-carrying rail net are the ones that can differ. Decides: completion (unconnected), DRC errors by type,
# then copper loss and the hottest track from kae.excite.evaluate on the output (physics eval).
set -euo pipefail
cd "$(dirname "$0")/../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=${SHA:-680c30ebb0c960d2d6f2b240baf2c09e1d648c9e}  # decide-2611 (decide-ab.sh tier 2 calls this)
KAE=(--code kae=.@$SHA)
FORK="$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
arm() {  # AREA
  local a=$1
  $K method add "kae-plain area $a ${SHA:0:7}" --kind route --harness "$SHA" \
    --description "kae.em.pnr --plain --lock under a neutral intent with route.area_cost=$a at ${SHA:0:7}, then the Freerouting bridge (new_board.sh kae-plain)" \
    --command "in={input}; for e in kicad_pro kicad_dru; do [ -f \"\${in%.kicad_pcb}.\$e\" ] && cp \"\${in%.kicad_pcb}.\$e\" mid.\$e; done; env OMP_NUM_THREADS=1 {py:kae} -u -W ignore -m kae.em.pnr {input} \$PWD/mid.kicad_pcb --plain --lock --intent {code:kae}/tools/kaeres/experiments/area-cost-ab/area-$a.json --work \$PWD/work-pnr && env KAE_BRIDGE_FREEROUTING=$FORK {py:kae} -u -W ignore -m kae.route.cli route \$PWD/mid.kicad_pcb {output} --time {timeout}" \
    --param timeout_s=900 --param area_cost=$a "${KAE[@]}"
}
arm 0.05
arm 0.2
arm 0.5
