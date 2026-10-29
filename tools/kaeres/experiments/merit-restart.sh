#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Every method that had merit (or partial merit) in the earlier experiments, each run the same
# fair way: tools/kaeres/restart.py wraps the method in a restart portfolio (4 differently seeded attempts at a time on a doubling schedule; the first wave grows
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
#   attempt, routing and repair keep to the budget) and the fast router of pnr-fast-router
#   (its default, PNR_FAST=D,L,K,B,R,J), plus pnr-speed2 (placement legal maps by summed-area
#   table instead of FFT, the same maps; pad cells as cached arrays); budgets are solver
#   CPU s; their routing (PathFinder) runs outside that clock and they write only at the end,
#   so an attempt is killed only by the overall deadline (slack 100), never at a multiple of its budget.
# - (until pruned) beam ran with phys_w 2 and seq_collapse with w_fv 4, w_x 1, w_ovf 0, as benchmarked.
# - pnr route_only is deterministic: one attempt. autoplace sa-loop plans its own rounds from
#   one budget (tested at 1200 s): one attempt, 1200 s base; its in-loop router and the probe
#   are kae's bridge.
# - Freerouting is not wrapped: it is deterministic (the attempt index only picks one of 8 pass
#   counts), so restarts repeated identical runs (one board: 129 attempts, one result). The
#   reference is plain Freerouting 2.5.0 from the fr-baseline campaign (one run per board).
# - kae portfolio is left out: it is kae bridge in this same wrapper.
# - Pruned 2026-10-29 (near-duplicates of a kept method, or inferior with no unique clean board; on 159
#   boards no pnr method cleaned a board that kae or autoplace did not, and pnr clean sets overlapped
#   0.97-1.0): kae critical soft (a flag of critical+bridge); pnr combo_full, jc_lv, jc2_fixmp_lv,
#   pjc2_lv_nopol (settings of combo, jc, jc2_fix, pjc2); xf_h minplus (its maps are in jc2_fix); anneal,
#   beam, seq, seq_phys (their ideas run inside anneal_phys and combo); seq_collapse, jc_full, qd,
#   negotiate (did not work in research; jc refines negotiate). docs/research keeps every idea.
#   HARNESS=<commit> keeps an earlier harness (same method ids).
set -euo pipefail
cd "$(dirname "$0")/../../.."
K="python3 tools/kaeres/kaeres.py"
KAE=(--code kae=.@45efe0066edb2559a32e217664ec1f544c80e790)   # claude/vigilant-mayer-i91rrr
PNR=(--code pnr=.@7b50773ff619f0ffcc60b1a303cb2ad8fa7fcd6c)   # pnr-speed2: pnr-anytime 957a37f (keen-wright db10e58 + anytime output + the fast router) + exact summed-area legal maps
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

# the kae methods and autoplace run kae-speed (45efe00 + faster critical grid + one pcbnew worker per
# process, same outputs) with its own warm numba cache; pnr keeps 45efe00's venv
KAE_BASE=("${KAE[@]}")
KAE=(--code kae=.@1650f8e65f538dd86964eee01007453c6cd9a05f)   # kae-speed

KENV="cp -r $KH/numba-kaefast numba 2>/dev/null; env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
add "kae bridge (restarts)" route 900 "$(rs 60 1.15)" "kae.route.cli: bridge + last mile" \
  "$KENV -m kae.route.cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@"
add "kae critical+bridge (restarts)" route 900 "$(rs 60 1.15)" "kae.route.critical_cli: critical copper, then the bridge" \
  "$KENV -m kae.route.critical_cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@"
add "kae staged (restarts)" joint-fixed 900 "$(rs 300 1.15)" "kae.joint.cli --max-iters 0 --no-modules: kae place, then the bridge" \
  "$KENV -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ --max-iters 0 --no-modules"
add "kae joint loop (restarts)" joint-fixed 900 "$(rs 300 1.15)" "kae.joint.cli: module stage, windows with last mile, finishing bridge" \
  "$KENV -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@"

pnr() {  # NAME KIND SLACK SPEC [run.py options...]; the attempt budget is solver CPU s
  local name=$1 kind=$2 sl=$3 spec=$4; shift 4
  local wrap KAE=("${KAE_BASE[@]}")
  if [ "$name" = "pnr route_only" ]; then wrap="$(rs 100000 $sl --max-attempts 1)"; else wrap="$(rs 120 $sl)"; fi
  add "$name (restarts)" "$kind" 900 "$wrap" "pnr engine $spec ${*:+($*) }(docs/ideas/original/scorecard.md)" \
    "env VIRTUAL_ENV={venv:kae} PYTHONPATH={code:pnr}/tools/research/collapse_joint:{code:pnr}/tools/research/xf_minplus KAE_KICAD_PYTHON={code:pnr}/tools/research/xf_common/kicad-python NUMBA_CACHE_DIR=$KH/numba-pnrspeed2 NUMBA_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 sh {code:pnr}/tools/research/xf_common/xf_run.sh {code:pnr}/tools/research/$spec @IN@ @OUT@ @TIME@ @SEED@ $*" \
    "${PNR[@]}"
}
J=joint-fixed
pnr "pnr route_only" route 100 pnr/methods.py:route_only
pnr "pnr anneal_phys" $J 100 pnr/methods_phys.py:anneal_phys
pnr "pnr repair" $J 100 pnr/methods.py:repair
pnr "pnr combo" $J 100 pnr/methods_combo.py:combo
pnr "pnr grad_phys" $J 100 pnr_grad/grad.py:grad_phys --opt post=phys
pnr "pnr jc" $J 100 collapse_joint/jc.py:jc
pnr "pnr pjc2 pour maps" $J 100 xf_pour/pjc.py:pjc2
pnr "pnr hjc_press" $J 100 harmonic/hjc.py:hjc_press
pnr "pnr jc2_fix" $J 100 collapse_joint/jc2.py:jc2_fix

# autoplace on the newer branch: --router kae routes its candidates with kae's bridge. Its
# placements are scored through the same restart-wrapped kae bridge as the probe (Freerouting
# routes only 0.17 of human placements clean on the qualified boards, so it cannot tell placements apart).
PROBE="$(rs 60 1.15) '$KENV -m kae.route.cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@'"
add "autoplace sa-loop kae (restarts)" place-fixed 1200 "$(rs 100000 1.2 --max-attempts 1)" "methods/autoplace place.py --algo sa-loop --router kae (plans its own rounds; one attempt); probe: kae bridge with restarts" \
  "cp -r $KH/numba-kaefast numba 2>/dev/null; env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK PYTHONPATH={code:ap}/bench/src {py:kae} {code:ap}/methods/autoplace/place.py --algo sa-loop --router kae --input @IN@ --output @OUT@ --workdir \$PWD --attempt @SEED@ --seed @SEED@ --timeout @TIME@" \
  --code ap=.@54be03254b821394bc218ecb9a9d71c7914d5e70 --param probe=kae-bridge --param "probe_command=$PROBE"   # autoplace-kae-router
