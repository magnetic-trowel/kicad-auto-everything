#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Every method that had merit (or partial merit) in the earlier experiments, plus both Freerouting
# baselines, each run the same fair way: tools/kaeres/restart.py wraps the method in a restart
# portfolio (4 differently seeded attempts at a time on a doubling schedule; the first wave grows
# with sqrt(footprints / 40); the harness's order (legal, clean, unconnected, new DRC errors)
# picks the best and the first clean one stops the run), with a budget of
# 900 s x sqrt(footprints / 40) (at least 900 s, at most 4 h). restart.py measures the work
# (CPU over all processes, restarts, peak memory). Placement methods run on the fixed-interface
# kinds (place-fixed, joint-fixed), the headline task (docs/topics/architecture/status-2026-10-25.md
# on claude/vigilant-mayer-i91rrr).
# Settings follow the experiments that showed merit (audit 2026-10-26):
# - kae: staged is --max-iters 0 --no-modules; one CPU (OMP_NUM_THREADS=1 KAE_WORKERS=1), a warm
#   numba cache, the bridge's Freerouting pinned; the bridge may overrun its --time a little.
# - pnr: engine of keen-wright db10e58 (v6.4, a superset of xf-experiments) with anytime output
#   (branch pnr-anytime: the board is written whenever it improves, a fully routed state ends the
#   attempt, routing and repair keep to the budget); budgets are solver
#   CPU s; their routing (PathFinder) runs outside that clock and they write only at the end,
#   so an attempt is killed only by the overall deadline (slack 100), never at a multiple of its budget.
# - beam with phys_w 2 and seq_collapse with w_fv 4, w_x 1, w_ovf 0, as benchmarked.
# - pnr route_only is deterministic: one attempt. autoplace sa-loop plans its own rounds from
#   one budget (tested at 1200 s): one attempt, 1200 s base; its in-loop router and the probe
#   are kae's bridge.
# - Freerouting: the attempt index sets its pass count (its only variation), first wave 240 s.
# - kae portfolio is left out: it is kae bridge in this same wrapper.
#   HARNESS=<commit> keeps an earlier harness (same method ids).
set -euo pipefail
cd "$(dirname "$0")/../../.."
K="python3 tools/kaeres/kaeres.py"
KAE=(--code kae=.@45efe0066edb2559a32e217664ec1f544c80e790)   # claude/vigilant-mayer-i91rrr
PNR=(--code pnr=.@1ff1b688ec6560c80895e4b25d146c9c3b487295)   # pnr-anytime (keen-wright db10e58 + anytime output, stop when routed, budget-faithful)
KH='$HOME/.cache/kaebench'
FORK="$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"   # fork 06d2686 + kae-speed (same output, faster)
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

fr() { add "$1 (restarts)" route 900 "$(rs 240 1.3)" "$2 through kaebench's adapter" \
  "env PYTHONPATH={code:harness}/bench/src {py:kae} {code:harness}/tools/kaeres/fr_attempt.py --binary $3 --input @IN@ --output @OUT@ --seed @SEED@ --time @TIME@"; }
fr "freerouting 2.5.0" "Freerouting v2.5.0 release" "$HOME/.cache/kaebench/freerouting-2.5.0-linux-x64/bin/freerouting"
fr "fr-fork kae-speed" "magnetic-trowel/freerouting 06d2686 + kae-speed 2e1125a (same output, faster)" "$FORK"

KENV="cp -r $KH/numba-kae numba 2>/dev/null; env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
add "kae bridge (restarts)" route 900 "$(rs 60 1.15)" "kae.route.cli: bridge + last mile" \
  "$KENV -m kae.route.cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@"
add "kae critical+bridge (restarts)" route 900 "$(rs 60 1.15)" "kae.route.critical_cli: critical copper, then the bridge" \
  "$KENV -m kae.route.critical_cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@"
add "kae critical soft (restarts)" route 900 "$(rs 60 1.15)" "kae.route.critical_cli --last-mile-soft (only clean result on libresolar-bms-c1; thin)" \
  "$KENV -m kae.route.critical_cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@ --last-mile-soft"
add "kae staged (restarts)" joint-fixed 900 "$(rs 300 1.15)" "kae.joint.cli --max-iters 0 --no-modules: kae place, then the bridge" \
  "$KENV -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ --max-iters 0 --no-modules"
add "kae joint loop (restarts)" joint-fixed 900 "$(rs 300 1.15)" "kae.joint.cli: module stage, windows with last mile, finishing bridge" \
  "$KENV -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@"

pnr() {  # NAME KIND SLACK SPEC [run.py options...]; the attempt budget is solver CPU s
  local name=$1 kind=$2 sl=$3 spec=$4; shift 4
  local wrap
  if [ "$name" = "pnr route_only" ]; then wrap="$(rs 100000 $sl --max-attempts 1)"; else wrap="$(rs 120 $sl)"; fi
  add "$name (restarts)" "$kind" 900 "$wrap" "pnr engine $spec ${*:+($*) }(docs/ideas/original/scorecard.md)" \
    "env VIRTUAL_ENV={venv:kae} PYTHONPATH={code:pnr}/tools/research/collapse_joint:{code:pnr}/tools/research/xf_minplus KAE_KICAD_PYTHON={code:pnr}/tools/research/xf_common/kicad-python NUMBA_CACHE_DIR=$KH/numba-anyt NUMBA_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 sh {code:pnr}/tools/research/xf_common/xf_run.sh {code:pnr}/tools/research/$spec @IN@ @OUT@ @TIME@ @SEED@ $*" \
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

# autoplace on the newer branch: --router kae routes its candidates with kae's bridge. Its
# placements are scored through the same restart-wrapped kae bridge as the probe (Freerouting
# routes only 0.17 of human placements clean on the qualified boards, so it cannot tell placements apart).
PROBE="$(rs 60 1.15) '$KENV -m kae.route.cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@'"
add "autoplace sa-loop kae (restarts)" place-fixed 1200 "$(rs 100000 1.2 --max-attempts 1)" "methods/autoplace place.py --algo sa-loop --router kae (plans its own rounds; one attempt); probe: kae bridge with restarts" \
  "cp -r $KH/numba-kae numba 2>/dev/null; env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK PYTHONPATH={code:ap}/bench/src {py:kae} {code:ap}/methods/autoplace/place.py --algo sa-loop --router kae --input @IN@ --output @OUT@ --workdir \$PWD --attempt @SEED@ --seed @SEED@ --timeout @TIME@" \
  --code ap=.@eb395651b95ead5a8575befff9527bc2b91e9f12 --param probe=kae-bridge --param "probe_command=$PROBE"   # autoplace-kae-router
