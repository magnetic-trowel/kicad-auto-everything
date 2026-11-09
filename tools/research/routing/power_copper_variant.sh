#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# power_copper_variant.sh DIR NAME [power_copper options...]
# One variant of kae.route.power_copper on DIR/before.kicad_pcb (with its project files), then its
# physics: DIR/var/NAME/{after.kicad_pcb, pc.json, pc.log, phys/after.*}. INTENT_DIR as in
# power_copper_smoke.sh; the operating facts are passed to the pass.
set -eo pipefail
dir=$(cd "$1" && pwd) name=$2; shift 2; id=$(basename "$dir")
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
INTENT_DIR=${INTENT_DIR:?set INTENT_DIR}
source ~/.cache/kaebench/env.sh; export APPTAINER_BIND=${KAE_WORK:-/var/tmp/$USER}
export KAE_EM_TOL=${KAE_EM_TOL:-1e-4}
out=$dir/var/$name; rm -rf "$out"; mkdir -p "$out"
t0=$(date +%s.%N)
( ulimit -v 40000000; PYTHONPATH=$REPO/kae/src ${PC_PY:-python3} -m kae.route.power_copper "$dir/before.kicad_pcb" "$out/after.kicad_pcb" \
    --operating "$INTENT_DIR/$id.operating.json" --workdir "$out/work" --report "$out/pc.json" "$@" ) > "$out/pc.log" 2>&1
echo "pass_s $(echo "$(date +%s.%N) - $t0" | bc)" >> "$out/pc.log"
rm -rf "$out/work"
[ -n "$NO_PHYS" ] && exit 0
bash "$REPO/tools/research/physics/eval_intent.sh" "$out/after.kicad_pcb" "$INTENT_DIR/$id.operating.json" \
  "$INTENT_DIR/$id.intent.json" "$out/phys" after
