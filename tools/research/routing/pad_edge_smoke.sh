#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# pad_edge_smoke.sh DIR [trim|reend|rd[-TAG]|phys-before|phys-after|phys-reend|phys-TAG]
# DIR holds before.kicad_pcb (a routed board) with its .kicad_pro/.kicad_dru; INTENT_DIR holds
# <board>.{intent,operating}.json (board = basename of DIR).
#   trim:        kae.route.pad_trim --no-reend (DRC-gated cut along each track's axis) before ->
#                after.kicad_pcb, report DIR/trim.json, pad-entry counts -> DIR/stats.{before,after}.json
#   reend:       kae.route.pad_trim (cut, and oblique entries re-ended perpendicular) before ->
#                reend.kicad_pcb, report DIR/reend.json (stats_in/stats_out inside), then its physics
#   rd[-TAG]:    kae.route.pad_reroute (rule D, DRC-gated) before -> TAG.kicad_pcb (default rd), report
#                DIR/TAG.json; operating facts from INTENT_DIR when set (pad currents: necks, hazards)
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
  rd|rd-*)
    t=${mode#rd-}; [ "$mode" = rd ] && t=rd
    op=(); [ -n "$INTENT_DIR" ] && [ -f "$INTENT_DIR/$id.operating.json" ] && op=(--operating "$INTENT_DIR/$id.operating.json")
    ( ulimit -v 40000000; export PYTHONPATH=$REPO/kae/src
      $PY -m kae.route.pad_reroute "$dir/before.kicad_pcb" "$dir/$t.kicad_pcb" --workdir "$dir/$t-work" \
        --report "$dir/$t.json" "${op[@]}"
    ) > "$dir/$t.log" 2>&1
    find "$dir/$t-work" -name "*.kicad_pcb" -delete;;
  phys-*)
    t=${mode#phys-}
    INTENT_DIR=${INTENT_DIR:?set INTENT_DIR}
    KAE_RULES_FROM=$dir/before.kicad_pcb bash "$REPO/tools/research/physics/eval_intent.sh" "$dir/$t.kicad_pcb" \
      "$INTENT_DIR/$id.operating.json" "$INTENT_DIR/$id.intent.json" "$dir/phys" "$t";;
  *) echo "unknown mode $mode" >&2; exit 2;;
esac
