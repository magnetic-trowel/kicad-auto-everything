#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# power_copper_smoke.sh DIR before|after
# DIR holds before.kicad_pcb (a routed board) with its .kicad_pro/.kicad_dru; INTENT_DIR holds
# <board>.{intent,operating}.json (board = basename of DIR).
#   before: physics of before.kicad_pcb (eval_intent.sh) -> DIR/phys/before.*
#   after:  kae.route.power_copper before -> after.kicad_pcb (DRC-gated, report DIR/pc.json),
#           then physics of after.kicad_pcb -> DIR/phys/after.*
set -eo pipefail
dir=$(cd "$1" && pwd) mode=$2 id=$(basename "$dir")
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
INTENT_DIR=${INTENT_DIR:?set INTENT_DIR}
source ~/.cache/kaebench/env.sh; export APPTAINER_BIND=${KAE_WORK:-/var/tmp/$USER}
export KAE_EM_TOL=${KAE_EM_TOL:-1e-4}
PCPY=${PC_PY:-python3}
if [ "$mode" = after ]; then
  t0=$(date +%s.%N)
  ( ulimit -v 40000000; PYTHONPATH=$REPO/kae/src $PCPY -m kae.route.power_copper "$dir/before.kicad_pcb" "$dir/after.kicad_pcb" --operating "$INTENT_DIR/$id.operating.json" \
      --workdir "$dir/pc-work" --report "$dir/pc.json" ) > "$dir/pc.log" 2>&1
  echo "pass_s $(echo "$(date +%s.%N) - $t0" | bc)" >> "$dir/pc.log"
fi
bash "$REPO/tools/research/physics/eval_intent.sh" "$dir/$mode.kicad_pcb" "$INTENT_DIR/$id.operating.json" \
  "$INTENT_DIR/$id.intent.json" "$dir/phys" "$mode"
