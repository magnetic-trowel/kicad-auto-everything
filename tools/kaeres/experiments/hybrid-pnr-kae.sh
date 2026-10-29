#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Hybrids: a pnr method places, kae's bridge routes (tools/kaeres/hybrid_attempt.sh). In the merit
# comparison pnr placements were compact (about 0.8x human wire on clean boards) but pnr's own router
# cleaned 33 human placements to kae bridge's 49, so pnr's clean counts may understate its placements.
# Each restart attempt: the pnr method (the merit settings, pnr-speed2 7b50773) with half the attempt's
# time, its copper stripped, kae bridge (kae-speed 1650f8e, the merit settings) with the rest. Same
# restart portfolio and budget as the merit methods (joint-fixed, 900 s x sqrt(footprints/40)).
#   HARNESS=<commit> keeps an earlier harness (same method ids).
set -euo pipefail
cd "$(dirname "$0")/../../.."
K="python3 tools/kaeres/kaeres.py"
KH='$HOME/.cache/kaebench'
FORK="$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
CODE=(--code kae=.@1650f8e65f538dd86964eee01007453c6cd9a05f    # kae-speed: the bridge
      --code kb=.@45efe0066edb2559a32e217664ec1f544c80e790     # the venv pnr's numba cache was warmed with
      --code pnr=.@7b50773ff619f0ffcc60b1a303cb2ad8fa7fcd6c)   # pnr-speed2
WRAP="{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s 300 --scale-first --slack 1.5 --check-placement --"
hyb() {  # NAME SPEC [run.py options]
  local name=$1 spec=$2; shift 2
  $K method add "$name + kae bridge (restarts)" --kind joint-fixed \
    --description "hybrid: pnr $spec ${*:+($*) }places with half of each attempt, its copper stripped, kae bridge routes; restart portfolio (tools/kaeres/restart.py)" \
    --command "$WRAP 'env PNR_CODE={code:pnr} PNR_VENV={venv:kb} PNR_NUMBA=$KH/numba-pnrspeed2 KAE_PY={py:kae} KAE_NUMBA=$KH/numba-kaefast HARNESS_CODE={code:harness} OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK sh {code:harness}/tools/kaeres/hybrid_attempt.sh $spec @IN@ @OUT@ @TIME@ @SEED@ $*'" \
    --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=4 \
    "${CODE[@]}" ${HARNESS:+--harness $HARNESS}
}
hyb "pnr pjc2" xf_pour/pjc.py:pjc2
hyb "pnr jc2_fix" collapse_joint/jc2.py:jc2_fix
hyb "pnr combo" pnr/methods_combo.py:combo
