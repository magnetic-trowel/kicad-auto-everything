#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# taut_smoke.sh DIR [taut|pc|phys-TAG]
# DIR holds before.kicad_pcb (a routed board) with its .kicad_pro/.kicad_dru; INTENT_DIR holds
# <board>.{intent,operating}.json (board = basename of DIR).
#   taut:     kae.route.taut run (DRC-gated) before -> taut.kicad_pcb, report taut.json; then the
#             arc-aware power copper on it -> tautpc.kicad_pcb (pc.json), and on the input alone ->
#             pc.kicad_pcb (pcin.json); stats.{before,taut,tautpc,pc}.json; times in times.txt.
#             TAUT_ONLY=1: taut alone. INTENT_DIR set: its operating facts give the pads' currents
#   refill:   taut with other nets' fills ignored (KiCad refills around the moved copper) -> tautr.*
#   phys-TAG: physics of TAG.kicad_pcb (eval_intent.sh) -> DIR/phys/TAG.*
# Summary over many DIRs: tools/research/routing/taut_summary.py.
set -eo pipefail
dir=$(cd "$1" && pwd) mode=${2:-taut} id=$(basename "$dir")
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
source ~/.cache/kaebench/env.sh; export APPTAINER_BIND=${KAE_WORK:-/var/tmp/$USER}
export KAE_EM_TOL=${KAE_EM_TOL:-1e-4}
PY=${TAUT_PY:-python3}
case "$mode" in
  taut)
    ( ulimit -v 40000000; export PYTHONPATH=$REPO/kae/src
      for e in kicad_pro kicad_dru; do [ -f "$dir/before.$e" ] && cp "$dir/before.$e" "$dir/taut.$e"; done
      t0=$(date +%s.%N)
      op=(); [ -n "$INTENT_DIR" ] && [ -f "$INTENT_DIR/$id.operating.json" ] && op=(--operating "$INTENT_DIR/$id.operating.json")
      $PY -m kae.route.taut run "$dir/before.kicad_pcb" "$dir/taut.kicad_pcb" --workdir "$dir/taut-work" --report "$dir/taut.json" "${op[@]}"
      t1=$(date +%s.%N)
      [ -n "$TAUT_ONLY" ] || $PY -m kae.route.power_copper "$dir/taut.kicad_pcb" "$dir/tautpc.kicad_pcb" --workdir "$dir/pc-work" --report "$dir/pc.json"
      t2=$(date +%s.%N)
      [ -n "$SKIP_PCIN" ] || $PY -m kae.route.power_copper "$dir/before.kicad_pcb" "$dir/pc.kicad_pcb" --workdir "$dir/pcin-work" --report "$dir/pcin.json"
      t3=$(date +%s.%N)
      echo "taut_s $(echo "$t1 - $t0" | bc) pc_s $(echo "$t2 - $t1" | bc) pcin_s $(echo "$t3 - $t2" | bc)" > "$dir/times.txt"
      for t in before taut tautpc pc; do [ -f "$dir/$t.kicad_pcb" ] && $PY -m kae.route.taut stats "$dir/$t.kicad_pcb" > "$dir/stats.$t.json"; done
    ) > "$dir/taut.log" 2>&1
    find "$dir/taut-work" "$dir/pc-work" "$dir/pcin-work" -name "*.kicad_pcb" -delete 2>/dev/null || true;;
  refill)
    ( ulimit -v 40000000; export PYTHONPATH=$REPO/kae/src
      for e in kicad_pro kicad_dru; do [ -f "$dir/before.$e" ] && cp "$dir/before.$e" "$dir/tautr.$e"; done
      $PY -m kae.route.taut run "$dir/before.kicad_pcb" "$dir/tautr.kicad_pcb" --pours refill --workdir "$dir/tautr-work" --report "$dir/tautr.json"
      $PY -m kae.route.taut stats "$dir/tautr.kicad_pcb" > "$dir/stats.tautr.json"
    ) > "$dir/tautr.log" 2>&1
    find "$dir/tautr-work" -name "*.kicad_pcb" -delete;;
  phys-*)
    t=${mode#phys-}
    INTENT_DIR=${INTENT_DIR:?set INTENT_DIR}
    KAE_RULES_FROM=$dir/before.kicad_pcb bash "$REPO/tools/research/physics/eval_intent.sh" "$dir/$t.kicad_pcb" \
      "$INTENT_DIR/$id.operating.json" "$INTENT_DIR/$id.intent.json" "$dir/phys" "$t";;
  *) echo "unknown mode $mode" >&2; exit 2;;
esac
