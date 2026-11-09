#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# A/B of the routing-pipeline redesign (docs/topics/routing/routing-stages.md section 6) on the physics set:
# the 213 merge3-ab boards with compiled intents. Plan, criteria and noise handling:
# tools/kaeres/experiments/route-finish-ab/PLAN.md.
#
# Every arm is merge3-ab's "kae bridge main final" wrapper (restart portfolio, --resume 0.5, --final last
# mile, 900 s x sqrt(footprints/40), parallel 4, Freerouting fork 2e1125a) at commit SHA of route-finish:
#
#   A   rf legacy (restarts)           pad_entry=centre, no finish, fork pin entries off (KAE_FR_PIN_ENTRIES=off);
#                                      tighten is a kae.route.critical option, which the bridge never runs
#   C   rf finish (restarts)           defaults (rule D born-right grid copper) + --finish on the kept board
#   D   rf finish import-tails (restarts)   C + --set import_tails=true (rule D tails on each repair-round import)
#   E   rf finish ground-vias (restarts)    C + KAE_ESCAPE_GROUND_VIAS=1 (decap ground vias before routing)
#   B   is not a kaeres method: kae.route.cli finish on each of A's kept boards (route-finish-ab/fork.sh B)
#   A0  is merge3-ab's stored "kae bridge main final (restarts)" 286c2335844d (e9889fd, task spec 8, score 7);
#       it is never put in these experiments (task spec 9 here would make kaeres re-run it); fork.sh A0
#       re-scores its stored boards with this harness instead
#
# Every arm gets the board's operating facts (OPSRC/<board>.operating.json) through --set operating=...:
# the sandbox hides /var/tmp, so they are copied under ~/.cache/kaebench (readable there) into a folder named
# by their content hash (a change of facts gives new method ids). The command finds its board's file from
# the kaebench attempt path of {input} (<id>/attempt-N/work/input/board.kicad_pcb).
#
# After restart.py, the command prints restarts/summary.json and restarts/report.json between RFAB_<name>
# and RFAB_end lines, so adapter.log.gz keeps the attempt log, the finish summary and the kept board's
# hazards (kaeres stores only output, adapter.log and router-report.json).
#
#   SHA=<pushed route-finish commit> STAGE=s1|full|smoke tools/kaeres/experiments/route-finish-ab.sh
#     s1    route-finish-ab-s1: 40 boards (route-finish-ab-s1.boards.txt), arms A and C (TWIN=1: and an A/A twin of A)
#     s1r   route-finish-ab-s1r: the same 40 boards, arms A and C, at the fixed code (PLAN.md section 9)
#     full  route-finish-ab: 213 boards, arms A, C, D, E (reuses the s1 runs)
#     smoke route-finish-ab-smoke: one board (BOARD, default freetronics-secsense-secsense), arms A, C, D, E
# Registers methods and the experiment only. Then (each needs the user's approval for its size):
#   1. warm the numba cache:   route-finish-ab/warm.sh SHA   (through kaeq, ~10 min)
#   2. route:                  python3 tools/kaeres/kaeres.py exp submit <experiment>
#   3. B and A0:               route-finish-ab/submit.py fork --arm B|A0 ...   (after A's runs exist)
#   4. measures and physics:   route-finish-ab/submit.py measure --arm ...     (after each arm's runs exist)
#   5. tables:                 route-finish-ab/analyze.py ...
set -euo pipefail
cd "$(dirname "$0")/../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=${SHA:?pushed commit of route-finish (full sha)}
SHA=$(git rev-parse "$SHA")
STAGE=${STAGE:-s1}
KAE=(--code kae=.@$SHA)
H=(--harness $SHA)
KH='$HOME/.cache/kaebench'
FORK="$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
NUMBA=numba-rf-${SHA:0:7}
OPSRC=${OPSRC:-/var/tmp/$USER/intent-213/compiled-9867d0b}
STEP_CACHE=${STEP_CACHE:-/var/tmp/$USER/step-cache-rf-ab}
D=tools/kaeres/experiments

# operating facts where the sandbox can read them, named by content
OPH=$(cat "$OPSRC"/*.operating.json | sha256sum | cut -c1-12)
OPD=$HOME/.cache/kaebench/rf-ab-operating-$OPH
if [ ! -d "$OPD" ]; then
  mkdir -p "$OPD.tmp$$" && cp "$OPSRC"/*.operating.json "$OPD.tmp$$"/ && mv "$OPD.tmp$$" "$OPD"
fi
echo "operating facts: $OPD ($(ls "$OPD" | wc -l) boards)"

rs() { local f=$1 sl=$2; shift 2
  echo "{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s $f --scale-first --slack $sl $* --"; }
PRE="export RFAB_OP=$KH/rf-ab-operating-$OPH/\$(basename \$(dirname \$(dirname \$(dirname \$(dirname {input}))))).operating.json; ls -l \$RFAB_OP;"
POST="; rc=\$?; for f in summary report; do test -f restarts/\$f.json && echo RFAB_\$f && cat restarts/\$f.json && echo && echo RFAB_end; done; exit \$rc"
CP="cp -r $KH/$NUMBA numba 2>/dev/null;"
OP="--set operating=\$RFAB_OP"

add() {  # NAME DESCRIPTION ENV ROUTE_SETS FINISH(0/1) [EXTRA --param K=V]
  local name=$1 desc=$2 env=$3 sets=$4 fin=$5 extra=(); [ -n "${6:-}" ] && extra=(--param "$6")
  local E="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 $env KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
  local LM="$CP $E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@ $OP"
  local FN="$CP $E -m kae.route.cli finish @IN@ @BEST@ @OUT@ --time @TIME@ --input-drc @DRC@ --drc-s @DRC_S@ $OP"
  local wrap
  if [ "$fin" = 1 ]; then wrap=$(rs 60 1.15 --resume 0.5 --final "'$LM'" --finish "'$FN'")
  else wrap=$(rs 60 1.15 --resume 0.5 --final "'$LM'"); fi
  local inner="$CP if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@ $OP $sets; else $E -m kae.route.cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@ $OP $sets; fi"
  $K method add "$name" --kind route --description "$desc; restart portfolio (tools/kaeres/restart.py) as merge3-ab's kae bridge main final; operating facts rf-ab-operating-$OPH" \
    --command "$PRE $wrap '$inner'$POST" \
    --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=4 "${extra[@]}" "${KAE[@]}" "${H[@]}" >/dev/null
  echo "method: $name"
}
S7=${SHA:0:7}
A="rf legacy $S7 (restarts)"
C="rf finish $S7 (restarts)"
DD="rf finish import-tails $S7 (restarts)"
EE="rf finish ground-vias $S7 (restarts)"
add "$A" "kae.route.cli at $S7 (route-finish) with the legacy options: KAE_PAD_ENTRY=centre, KAE_FR_PIN_ENTRIES=off, no finish" \
  "KAE_PAD_ENTRY=centre KAE_FR_PIN_ENTRIES=off" "" 0
add "$C" "kae.route.cli at $S7 (route-finish) defaults (rule D born-right grid copper); restart --finish (kae.route.cli finish on the kept board after --final)" \
  "" "" 1
# A/A twin of A (a second id for the same recipe: the run-to-run noise of the restart portfolio), stage 1 only
AT="rf legacy twin $S7 (restarts)"
[ "$STAGE" = s1 ] && [ -n "${TWIN:-}" ] && add "$AT" "A/A replicate of '$A' (identical recipe; param replicate=2 only separates the ids)" \
  "KAE_PAD_ENTRY=centre KAE_FR_PIN_ENTRIES=off" "" 0 replicate=2
add "$DD" "as '$C' plus --set import_tails=true (rule D tails on each repair-round import, repair.import_tails)" \
  "" "--set import_tails=true" 1
add "$EE" "as '$C' plus KAE_ESCAPE_GROUND_VIAS=1 (decap and IC ground vias laid in lastmile.plane_escapes before routing)" \
  "KAE_ESCAPE_GROUND_VIAS=1" "" 1

desc="routing-stages section 6 A/B at ${S7} (route-finish): arms A legacy, C finish, D import tails, E ground vias; B (finish on A's boards) and A0 (merge3-ab 286c2335844d re-scored) outside kaeres (route-finish-ab/fork.sh). Operating facts rf-ab-operating-$OPH. Recipe: tools/kaeres/experiments/route-finish-ab.sh; plan route-finish-ab/PLAN.md"
case "$STAGE" in
  s1) $K exp create route-finish-ab-s1 --method "$A" --method "$C" ${TWIN:+--method "$AT"} --boards @$D/route-finish-ab-s1.boards.txt \
        --harness $SHA --kae $SHA --env KAE_STEP_CACHE=$STEP_CACHE --description "stage 1 (40 boards, A and C) of the $desc" >/dev/null ;;
  full) $K exp create route-finish-ab --method "$A" --method "$C" --method "$DD" --method "$EE" \
        --boards @$D/route-finish-ab.boards.txt --harness $SHA --kae $SHA --env KAE_STEP_CACHE=$STEP_CACHE --description "$desc" >/dev/null ;;
  s1r) $K exp create route-finish-ab-s1r --method "$A" --method "$C" --boards @$D/route-finish-ab-s1.boards.txt \
        --harness $SHA --kae $SHA --env KAE_STEP_CACHE=$STEP_CACHE --description "stage 1 rerun (the same 40 boards, A and C) at $S7 with the corrected physics set, score v12, task spec 10; criteria in route-finish-ab/PLAN.md section 9. $desc" >/dev/null ;;
  smoke) B1=${BOARD:-freetronics-secsense-secsense}
        $K exp create route-finish-ab-smoke-$S7 --method "$A" --method "$C" --method "$DD" --method "$EE" --boards "$B1" \
        --harness $SHA --kae $SHA --env KAE_STEP_CACHE=$STEP_CACHE --description "smoke ($B1) of the $desc" >/dev/null ;;
  *) echo "STAGE: s1, s1r, full or smoke" >&2; exit 2 ;;
esac
echo "experiment created (STAGE=$STAGE); nothing submitted"
