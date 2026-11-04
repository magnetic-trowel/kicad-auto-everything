#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# pad_edge_smoke.sh DIR [trim|reend|phys-before|phys-after|phys-reend]
# DIR holds before.kicad_pcb (a routed board) with its .kicad_pro/.kicad_dru; INTENT_DIR holds
# <board>.{intent,operating}.json (board = basename of DIR).
#   trim:        kae.route.pad_trim --no-reend (DRC-gated cut along each track's axis) before ->
#                after.kicad_pcb, report DIR/trim.json, pad-entry counts -> DIR/stats.{before,after}.json
#   reend:       kae.route.pad_trim (cut, and oblique entries re-ended perpendicular) before ->
#                reend.kicad_pcb, report DIR/reend.json (stats_in/stats_out inside), then its physics
#   phys-before: physics of before.kicad_pcb (eval_intent.sh) -> DIR/phys/before.*
#   phys-after:  physics of after.kicad_pcb -> DIR/phys/after.*
# Summary over many DIRs: tools/research/routing/pad_edge_summary.py.
set -eo pipefail
dir=$(cd "$1" && pwd) mode=${2:-trim} id=$(basename "$dir")
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
source ~/.cache/kaebench/env.sh; export APPTAINER_BIND=${KAE_WORK:-/var/tmp/$USER}
export KAE_EM_TOL=${KAE_EM_TOL:-1e-4}
PY=${TRIM_PY:-python3}
case "$mode" in
  trim)
    ( ulimit -v 40000000; export PYTHONPATH=$REPO/kae/src
      $PY -m kae.route.pad_trim trim "$dir/before.kicad_pcb" "$dir/after.kicad_pcb" --workdir "$dir/trim-work" \
        --report "$dir/trim.json" --no-reend
      for t in before after; do $PY -m kae.route.pad_trim stats "$dir/$t.kicad_pcb" > "$dir/stats.$t.json"; done
    ) > "$dir/trim.log" 2>&1
    find "$dir/trim-work" -name "*.kicad_pcb" -delete;;
  reend)
    ( ulimit -v 40000000; export PYTHONPATH=$REPO/kae/src
      $PY -m kae.route.pad_trim trim "$dir/before.kicad_pcb" "$dir/reend.kicad_pcb" --workdir "$dir/reend-work" \
        --report "$dir/reend.json"
    ) > "$dir/reend.log" 2>&1
    find "$dir/reend-work" -name "*.kicad_pcb" -delete
    exec bash "$0" "$dir" phys-reend;;
  phys-before|phys-after|phys-reend)
    t=${mode#phys-}
    INTENT_DIR=${INTENT_DIR:?set INTENT_DIR}
    KAE_RULES_FROM=$dir/before.kicad_pcb bash "$REPO/tools/research/physics/eval_intent.sh" "$dir/$t.kicad_pcb" \
      "$INTENT_DIR/$id.operating.json" "$INTENT_DIR/$id.intent.json" "$dir/phys" "$t";;
  *) echo "unknown mode $mode" >&2; exit 2;;
esac
