#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# The A/Bs of the 2026-11 "decide" work (branch decide-2611), all at one kae commit, plus an A/A.
# Every arm is a switch that exists at $SHA (CLI flag, --set/--opt key or environment variable);
# the default arm is listed first. The plan, costs and verdicts: decide-ab/README.md.
#
#   decide-ab.sh register TIER     # method add + exp create (TIER 1, 2 or 3); idempotent per method
#   decide-ab.sh exps TIER         # the experiment names of a tier
#
# Tier 1 (safety / legality first, then the A/A):
#   legality-ab-*  P2/P3   kae place --severity level_c|strict|board, --relax-bodies off|escalate|auto
#   copper-ab      C2/RC3  kae critical+bridge --opt rail_over_cap=1 / --opt via_A=1.0 vs default
#   edge-ab        P4      staged kae joint (free interface, kind joint) --set connector_edge=2 (default) vs 1
#   aa-joint       A/A     kae joint loop final under two names (an inert --param), the noise floor
# Tier 2 (cheap): keepupright-ab (K11), area-cost-ab (CI7b), eff-tiebreak-ab (J13)
# Tier 3: placement-decide-staged (P5/P10), placement-decide-joint (J10)
set -euo pipefail
cd "$(dirname "$0")/../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=${SHA:-680c30ebb0c960d2d6f2b240baf2c09e1d648c9e}
S7=${SHA:0:7}
KAE=(--code kae=.@$SHA)
H=(--harness $SHA)
B=tools/kaeres/experiments/decide-ab
LB=tools/kaeres/experiments
KH='$HOME/.cache/kaebench'
FORK="$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
NUMBA=numba-kae-decide-$S7
CP="cp -r $KH/$NUMBA numba 2>/dev/null;"
E="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
FIN="$CP $E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
RES="if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else"

madd() {  # NAME ARGS...: method add, skipped when the name already has this recipe (same id)
  $K method add "$@" 2>&1 | tail -1
}
rs() { local f=$1 sl=$2; shift 2
  echo "{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s $f --scale-first --slack $sl $* --"; }
radd() {  # NAME KIND WRAPPER DESCRIPTION INNER [EXTRA method-add ARGS]
  local name=$1 kind=$2 wrap=$3 desc=$4 inner=$5; shift 5
  [ "$kind" = route ] || wrap="${wrap% --} --check-placement --"
  madd "$name" --kind "$kind" --description "$desc; restart portfolio (tools/kaeres/restart.py)" \
    --command "$wrap '$inner'" --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=4 \
    "${KAE[@]}" "${H[@]}" "$@"
}
staged() {  # NAME KIND SET [EXTRA]
  local n=$1 kind=$2 set=$3; shift 3
  radd "$n" "$kind" "$(rs 300 1.15 --resume 0.5 --screen --final "'$FIN'")" \
    "kae.joint.cli --max-iters 0 --no-modules $set at $S7 (decide-2611); restart --resume 0.5 --screen --final, as merge3-ab's staged arm" \
    "$CP $RES $E -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ --max-iters 0 --no-modules $set; fi" "$@"
}
joint() {  # NAME SET [EXTRA]
  local n=$1 set=$2; shift 2
  radd "$n" joint-fixed "$(rs 300 1.15 --resume 0.5 --final "'$FIN'")" \
    "kae.joint.cli (joint loop) $set at $S7 (decide-2611); restart --resume 0.5 --final, as baseline-2611b's joint loop final" \
    "$CP $RES $E -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ $set; fi" "$@"
}
crit() {  # NAME OPT
  local n=$1 opt=$2
  radd "$n" route "$(rs 60 1.15)" \
    "kae.route.critical_cli route $opt at $S7 (decide-2611), as merit-500r3k's kae critical+bridge" \
    "$CP $E -m kae.route.critical_cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@ $opt"
}
place() {  # NAME KIND SEVERITY RELAX [BASE_S] [ENV]
  local n=$1 kind=$2 sev=$3 relax=$4 base=${5:-600} env=${6:-}
  madd "$n" --kind "$kind" --param probe=freerouting \
    --description "kae place --severity $sev --relax-bodies $relax ${env:+($env) }at $S7 (decide-2611)" \
    --command "$CP env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=4 $env {py:kae} -m kae.cli place {input} {output} --seed {attempt} --time {timeout} --severity $sev --relax-bodies $relax" \
    --param timeout_s=$base --param timeout_scale=sqrt-fp40 "${KAE[@]}" "${H[@]}"
}
exp() {  # NAME BOARDS ATTEMPTS DESCRIPTION METHOD...
  local n=$1 b=$2 k=$3 d=$4; shift 4
  if [ -f "$HOME/kae-baselines/experiments/$n/experiment.json" ]; then echo "exists: $n"; return; fi
  local ms=(); for m in "$@"; do ms+=(--method "$m"); done
  $K exp create "$n" --boards "@$b" --attempts "$k" "${ms[@]}" --harness "$SHA" --kae "$SHA" --description "$d"
}

LEG_ARMS=("old:board:auto" "strict:strict:off" "level-c:level_c:off" "escalate:level_c:escalate")
lname() { echo "kae place legality $1 ($2) $S7"; }

tier1() {
  # ---- P2/P3 legality: place and place-fixed, k = 2 (seeds 0, 1), 600 s x sqrt(fp/40), Freerouting probe
  for kind in place place-fixed; do
    for a in "${LEG_ARMS[@]}"; do IFS=: read -r n sev rel <<< "$a"; place "$(lname "$n" "$kind")" "$kind" "$sev" "$rel"; done
  done
  # Arms per board set (an arm runs only where it can differ from the others):
  #   downgrade (113): place all four; place-fixed old / strict / level-c
  #   relax (52, >95 % full with courtyard-less parts): old / level-c / escalate, both kinds
  #   control (40, waive nothing, no relaxation): old / level-c, place only
  exp legality-ab-place-down $LB/legality-ab.boards.txt 2 \
    "P2/P3 (decide-legality) on the 113 boards whose project downgrades a strict check: severities board/strict/level_c, relax auto/off/escalate; kae place at $S7, k=2" \
    "$(lname old place)" "$(lname strict place)" "$(lname level-c place)" "$(lname escalate place)"
  exp legality-ab-place-relax $LB/legality-ab-relax.boards.txt 2 \
    "P3 on the 52 merit boards over 95% utilization with courtyard-less parts: relax auto/off/escalate; kae place at $S7, k=2" \
    "$(lname old place)" "$(lname level-c place)" "$(lname escalate place)"
  exp legality-ab-place-ctrl $LB/legality-ab-control.boards.txt 2 \
    "P2/P3 control: 40 merit boards that waive nothing and never relax; old vs level-c must not differ; kae place at $S7, k=2" \
    "$(lname old place)" "$(lname level-c place)"
  exp legality-ab-fixed-down $LB/legality-ab.boards.txt 2 \
    "P2 on the 113 downgrade boards, place-fixed (interface locked): board/strict/level_c; kae place at $S7, k=2" \
    "$(lname old place-fixed)" "$(lname strict place-fixed)" "$(lname level-c place-fixed)"
  exp legality-ab-fixed-relax $LB/legality-ab-relax.boards.txt 2 \
    "P3 on the 52 relax boards, place-fixed: relax auto/off/escalate; kae place at $S7, k=2" \
    "$(lname old place-fixed)" "$(lname level-c place-fixed)" "$(lname escalate place-fixed)"

  # ---- C2/RC3 copper: kae critical+bridge restarts, k = 2
  crit "kae critical+bridge decide default $S7 (restarts)" ""
  crit "kae critical+bridge decide rail_over_cap=1 $S7 (restarts)" "--opt rail_over_cap=1"
  crit "kae critical+bridge decide via_A=1.0 $S7 (restarts)" "--opt via_A=1.0"
  exp copper-ab $B/copper.boards.txt 2 \
    "C2/RC3 (decide-copper-thermal): critical+bridge default vs --opt rail_over_cap=1 (C2) vs --opt via_A=1.0 (RC3, the old 1 A/via); crit-v6 A+B (33 qualified) + 6 C + power boards; at $S7, k=2" \
    "kae critical+bridge decide default $S7 (restarts)" "kae critical+bridge decide rail_over_cap=1 $S7 (restarts)" \
    "kae critical+bridge decide via_A=1.0 $S7 (restarts)"

  # ---- P4 connector edge: staged kae on the free-interface joint task, 58 merit boards with a USB,
  # barrel, RJ, video/D-sub or SMA/BNC part (kae.place.edge_check.PIN_KINDS); 1 = hazard only (old placement)
  staged "kae staged decide edge2 $S7 (restarts)" joint ""
  staged "kae staged decide edge1 $S7 (restarts)" joint "--set connector_edge=1"
  # edge-ab (58 merit-213 boards, k=2) was the smoke; edge-ab2 is the run: the 135 merit-500 boards with
  # an unlocked pinned-kind part (decide-ab/edge_boards.py), k=1, for more boards rather than more seeds
  exp edge-ab $B/edge.boards.txt 2 \
    "P4 (decide-placement): connector_edge=2 (pin panel connectors to the edge, default) vs 1 (hazard only, the old placement); staged kae, joint task (free interface), at $S7, k=2" \
    "kae staged decide edge2 $S7 (restarts)" "kae staged decide edge1 $S7 (restarts)"
  exp edge-ab2 $B/edge500.boards.txt 1 \
    "P4 (decide-placement): connector_edge=2 (default) vs 1 (hazard only, the old placement); staged kae, joint task (free interface), 135 merit-500 boards with an unlocked USB/barrel/RJ/video/SMA part, at $S7, k=1" \
    "kae staged decide edge2 $S7 (restarts)" "kae staged decide edge1 $S7 (restarts)"

  # ---- A/A: one recipe under two names (the twin differs only in an inert parameter, so it gets its
  # own method id and runs); the control is also the J10/J13 control
  joint "kae joint decide control $S7 (restarts)" ""
  joint "kae joint decide control twin $S7 (restarts)" "" --param aa=twin
  exp aa-joint $B/merit213.boards.txt 1 \
    "A/A noise floor: kae joint loop final at $S7 under two names (inert --param aa=twin), 213 merit boards, k=1" \
    "kae joint decide control $S7 (restarts)" "kae joint decide control twin $S7 (restarts)"
}

tier1b() {
  # ---- P2/P3 follow-up (2026-11-04): tier 1 showed strict gains most legal_strict (+29 pp) but, without
  # escalation, piles parts into shorts on more boards (13 vs 5); escalate kept shorts at baseline.
  # strict + escalate is the untested combination. Existing arms are reused (same method ids, no reruns).
  for kind in place place-fixed; do place "$(lname strict-esc "$kind")" "$kind" strict escalate; done
  exp legality-ab2-place-down $LB/legality-ab.boards.txt 2 \
    "P2/P3 follow-up: strict + escalate vs the tier-1 arms on the 113 downgrade boards; kae place at $S7, k=2" \
    "$(lname old place)" "$(lname strict place)" "$(lname escalate place)" "$(lname strict-esc place)"
  exp legality-ab2-fixed-down $LB/legality-ab.boards.txt 2 \
    "P2/P3 follow-up, place-fixed: strict + escalate vs old / strict / level-c; kae place at $S7, k=2" \
    "$(lname old place-fixed)" "$(lname strict place-fixed)" "$(lname level-c place-fixed)" "$(lname strict-esc place-fixed)"
}

tier2() {
  # ---- J13 eff_tiebreak: reuses the A/A control's runs
  joint "kae joint decide eff1 $S7 (restarts)" "--set eff_tiebreak=1"
  exp eff-tiebreak-ab $B/merit213.boards.txt 1 \
    "J13 (decide-eval): joint loop eff_tiebreak 0 (default) vs 1; 213 merit boards at $S7, k=1" \
    "kae joint decide control $S7 (restarts)" "kae joint decide eff1 $S7 (restarts)"
  # ---- K11 keep-upright: kae place (pcbnew writer) at 300 s, place task, k = 2
  place "kae place keepupright0 $S7" place level_c off 300 "KAE_WRITER_KEEP_UPRIGHT=0"
  place "kae place keepupright1 $S7" place level_c off 300 "KAE_WRITER_KEEP_UPRIGHT=1"
  exp keepupright-ab $B/merit213.boards.txt 2 \
    "K11 (decide-kicad-io): writer KeepUpright 0 (default) vs 1; kae place 300 s, place task, 213 merit boards at $S7, k=2" \
    "kae place keepupright0 $S7" "kae place keepupright1 $S7"
  # ---- CI7b area cost: area-cost-ab.sh at $SHA, qualified suite, k = 1 (deterministic)
  SHA=$SHA bash tools/kaeres/experiments/area-cost-ab.sh
  exp area-cost-ab2 bench/suites/qualified-kicad-10.0.7.txt 1 \
    "CI7b (decide-intent-circuit): route.area_cost 0.05 / 0.2 / 0.5, kae-plain (pnr --plain --lock + bridge) at $S7, qualified suite, k=1" \
    "kae-plain area 0.05 $S7 v2" "kae-plain area 0.2 $S7 v2" "kae-plain area 0.5 $S7 v2"
}

tier3() {
  staged "kae staged decide control $S7 (restarts)" joint-fixed ""
  staged "kae staged decide cong0 $S7 (restarts)" joint-fixed "--set place_w_cong=0"
  staged "kae staged decide cong10 $S7 (restarts)" joint-fixed "--set place_w_cong=10"
  staged "kae staged decide margin0 $S7 (restarts)" joint-fixed "--set place_margin=0"
  exp placement-decide-staged $B/merit213.boards.txt 2 \
    "P5/P10 (decide-placement): staged kae place_w_cong 30/0/10, place_margin auto/0, one control; 213 merit boards at $S7, k=2" \
    "kae staged decide control $S7 (restarts)" "kae staged decide cong0 $S7 (restarts)" \
    "kae staged decide cong10 $S7 (restarts)" "kae staged decide margin0 $S7 (restarts)"
  joint "kae joint decide bump0 $S7 (restarts)" "--set bump_mm=0"
  joint "kae joint decide rmargin0 $S7 (restarts)" "--set replace_margin=0"
  exp placement-decide-joint $B/joint-open.boards.txt 3 \
    "J10 (decide-placement): joint loop bump_mm 0.25/0, replace_margin 0.3/0 on the 71 boards baseline-2611b's joint loop left open (where windows run), at $S7, k=3" \
    "kae joint decide control $S7 (restarts)" "kae joint decide bump0 $S7 (restarts)" "kae joint decide rmargin0 $S7 (restarts)"
}

exps() {
  case $1 in
    1) echo legality-ab-place-down legality-ab-place-relax legality-ab-place-ctrl legality-ab-fixed-down legality-ab-fixed-relax copper-ab edge-ab2 aa-joint ;;
    1b) echo legality-ab2-place-down legality-ab2-fixed-down ;;
    2) echo eff-tiebreak-ab keepupright-ab area-cost-ab2 ;;
    3) echo placement-decide-staged placement-decide-joint ;;
  esac
}

case ${1:-} in
  register) "tier$2" ;;
  exps) exps "$2" ;;
  *) echo "usage: $0 register|exps TIER" >&2; exit 2 ;;
esac
