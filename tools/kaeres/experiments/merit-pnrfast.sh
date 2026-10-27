#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# The pnr methods of merit-restart.sh on the fast pnr router (branch pnr-fast-router: nearest-pin
# tree growth from the nearby tree, connection-level legalize, stall stop with best-pass restore,
# no hopeless full-grid retries; its default, PNR_FAST=D,L,K,B,R,J). Same wrapper, budgets and
# settings as merit-restart.sh; only the pnr code (and its numba cache) differ, so experiment
# merit-500-pnrfast compares directly with merit-500r on the same boards.
#   HARNESS=<commit> keeps an earlier harness (same method ids).
set -euo pipefail
cd "$(dirname "$0")/../../.."
K="python3 tools/kaeres/kaeres.py"
KAE=(--code kae=.@45efe0066edb2559a32e217664ec1f544c80e790)   # claude/vigilant-mayer-i91rrr
PNR=(--code pnr=.@eaf1719b8c33c5070f5b3875c92ab8723a9771f4)   # pnr-fast-router
KH='$HOME/.cache/kaebench'
FORK="$HOME/.cache/kaebench/kae-freerouting-fork-06d2686/bin/freerouting"
# rs FIRST_S SLACK [restart.py options]: the wrapper; {timeout} is the board-scaled budget
rs() { local f=$1 sl=$2; shift 2
  echo "{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s $f --scale-first --slack $sl $* --"; }
add() {  # NAME KIND BASE_S WRAPPER DESCRIPTION INNER [CODE/PARAM ARGS...]; INNER is single-quoted, since the
         # harness runs the template with sh -c (a ';' in it would end restart.py's command there)
  local name=$1 kind=$2 base=$3 wrap=$4 desc=$5 inner=$6; shift 6
  [ "$kind" = route ] || wrap="${wrap% --} --check-placement --"
  $K method add "$name" --kind "$kind" --description "$desc; restart portfolio (tools/kaeres/restart.py)" \
    --command "$wrap '$inner'" --param timeout_s="$base" --param timeout_scale=sqrt-fp40 --param parallel=4 \
    "${KAE[@]}" "$@" ${HARNESS:+--harness $HARNESS}
}

pnr() {  # NAME KIND SLACK SPEC [run.py options...]; the attempt budget is solver CPU s
  local name=$1 kind=$2 sl=$3 spec=$4; shift 4
  local wrap
  if [ "$name" = "pnr route_only" ]; then wrap="$(rs 100000 $sl --max-attempts 1)"; else wrap="$(rs 120 $sl)"; fi
  add "$name fast (restarts)" "$kind" 900 "$wrap" "pnr engine $spec ${*:+($*) }on the fast router (pnr-fast-router)" \
    "env VIRTUAL_ENV={venv:kae} PYTHONPATH={code:pnr}/tools/research/collapse_joint:{code:pnr}/tools/research/xf_minplus KAE_KICAD_PYTHON={code:pnr}/tools/research/xf_common/kicad-python NUMBA_CACHE_DIR=$KH/numba-pnrfast NUMBA_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 sh {code:pnr}/tools/research/xf_common/xf_run.sh {code:pnr}/tools/research/$spec @IN@ @OUT@ @TIME@ @SEED@ $*" \
    "${PNR[@]}"
}
J=joint-fixed
pnr "pnr route_only" route 100 pnr/methods.py:route_only
pnr "pnr seq" $J 100 pnr/methods.py:seq                      # control: HPWL place, then route
pnr "pnr seq_phys" $J 100 pnr/methods_phys.py:seq_phys
pnr "pnr anneal" $J 100 pnr/methods.py:anneal
pnr "pnr anneal_phys" $J 100 pnr/methods_phys.py:anneal_phys
pnr "pnr repair" $J 100 pnr/methods.py:repair
pnr "pnr negotiate" $J 100 pnr/methods.py:negotiate
pnr "pnr beam" $J 100 pnr_mcts/mcts.py:beam --opt phys_w=2
pnr "pnr combo" $J 100 pnr/methods_combo.py:combo
pnr "pnr combo_full" $J 100 pnr/methods_combo.py:combo_full
pnr "pnr seq_collapse" $J 100 collapse_cplace/methods_cplace.py:seq_collapse --opt w_fv=4 --opt w_x=1 --opt w_ovf=0
pnr "pnr grad_phys" $J 100 pnr_grad/grad.py:grad_phys --opt post=phys
pnr "pnr jc" $J 100 collapse_joint/jc.py:jc
pnr "pnr jc_lv" $J 100 collapse_joint/jc.py:jc_lv
pnr "pnr jc_full" $J 100 collapse_joint/jc.py:jc_full
pnr "pnr xf_h minplus" $J 100 xf_minplus/minplus.py:xf_h
pnr "pnr pjc2 pour maps" $J 100 xf_pour/pjc.py:pjc2
pnr "pnr pjc2_lv_nopol" $J 100 xf_pour/pjc.py:pjc2_lv_nopol
pnr "pnr hjc_press" $J 100 harmonic/hjc.py:hjc_press
pnr "pnr qd" $J 100 qd_archive/qd.py:qd
pnr "pnr jc2_fix" $J 100 collapse_joint/jc2.py:jc2_fix
pnr "pnr jc2_fixmp_lv" $J 100 collapse_joint/jc2.py:jc2_fixmp_lv
