#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# pad_edge_smoke.sh DIR [trim|phys-before|phys-after]
# DIR holds before.kicad_pcb (a routed board) with its .kicad_pro/.kicad_dru; INTENT_DIR holds
# <board>.{intent,operating}.json (board = basename of DIR).
#   trim:        kae.route.pad_trim (DRC-gated) before -> after.kicad_pcb, report DIR/trim.json, and
#                the pad-entry counts of both boards -> DIR/stats.{before,after}.json
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
        --report "$dir/trim.json"
      for t in before after; do $PY -m kae.route.pad_trim stats "$dir/$t.kicad_pcb" > "$dir/stats.$t.json"; done
    ) > "$dir/trim.log" 2>&1
    find "$dir/trim-work" -name "*.kicad_pcb" -delete;;
  phys-before|phys-after)
    t=${mode#phys-}
    INTENT_DIR=${INTENT_DIR:?set INTENT_DIR}
    KAE_RULES_FROM=$dir/before.kicad_pcb bash "$REPO/tools/research/physics/eval_intent.sh" "$dir/$t.kicad_pcb" \
      "$INTENT_DIR/$id.operating.json" "$INTENT_DIR/$id.intent.json" "$dir/phys" "$t";;
  *) echo "unknown mode $mode" >&2; exit 2;;
esac
