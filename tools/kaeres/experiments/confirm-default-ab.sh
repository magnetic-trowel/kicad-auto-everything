#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Confirmation A/B of the new routing default (finish in the time left, docs/topics/routing/routing-stages.md
# section 7.1) before it goes to main. Plan and pre-registered criteria: confirm-default-ab/PLAN.md.
#
#   A   cab legacy (restarts)        route-finish-ab's arm A at the new code: KAE_PAD_ENTRY=centre,
#                                    KAE_FR_PIN_ENTRIES=off, and --no-finish (finish is now on by default in
#                                    kae.route.cli route, so the legacy arm must turn it off)
#   N   cab default (restarts)       the default kae recipe for the restart portfolio: --final (last mile) and
#                                    --finish (kae.route.cli finish on the kept board in the time left; attempts
#                                    get KAE_FINISH_KEPT=1), nothing else set: rule D entries, no reserve
#   A2  cab legacy twin (restarts)   A again (param replicate=2 only separates the ids), on the large open boards
#
# Everything else as route-finish-ab: restart.py --parallel 4 --first-s 60 --scale-first --slack 1.15 --resume 0.5,
# 900 s x sqrt(footprints/40) (at most 4 h), Freerouting fork 2e1125a, operating facts by content hash, step cache.
#
#   SHA=<pushed commit> [STAGE=full|smoke] [BOARD=...] tools/kaeres/experiments/confirm-default-ab.sh
# Registers only; submission, physics and analysis: confirm-default-ab/PLAN.md section "Running order".
set -euo pipefail
cd "$(dirname "$0")/../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=$(git rev-parse "${SHA:?pushed commit (full sha)}")
STAGE=${STAGE:-full}
KH='$HOME/.cache/kaebench'
FORK="$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
NUMBA=numba-rf-${SHA:0:7}
OPSRC=${OPSRC:-/var/tmp/$USER/intent-213/compiled-9867d0b}
STEP_CACHE=${STEP_CACHE:-/var/tmp/$USER/step-cache-rf-ab}
D=tools/kaeres/experiments
OPH=$(cat "$OPSRC"/*.operating.json | sha256sum | cut -c1-12)
OPD=$HOME/.cache/kaebench/rf-ab-operating-$OPH
[ -d "$OPD" ] || { mkdir -p "$OPD.tmp$$" && cp "$OPSRC"/*.operating.json "$OPD.tmp$$"/ && mv "$OPD.tmp$$" "$OPD"; }

rs() { echo "{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s 60 --scale-first --slack 1.15 --resume 0.5 $* --"; }
PRE="export RFAB_OP=$KH/rf-ab-operating-$OPH/\$(basename \$(dirname \$(dirname \$(dirname \$(dirname {input}))))).operating.json; ls -l \$RFAB_OP;"
POST="; rc=\$?; for f in summary report; do test -f restarts/\$f.json && echo RFAB_\$f && cat restarts/\$f.json && echo && echo RFAB_end; done; exit \$rc"
CP="cp -r $KH/$NUMBA numba 2>/dev/null;"
OP="--set operating=\$RFAB_OP"

add() {  # NAME DESCRIPTION ENV ROUTE_FLAGS FINISH(0/1) [EXTRA --param K=V]
  local name=$1 desc=$2 env=$3 rflags=$4 fin=$5 extra=(); [ -n "${6:-}" ] && extra=(--param "$6")
  local E="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 $env KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
  local LM="$CP $E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@ $OP"
  local FN="$CP $E -m kae.route.cli finish @IN@ @BEST@ @OUT@ --time @TIME@ --input-drc @DRC@ --drc-s @DRC_S@ $OP"
  local wrap
  if [ "$fin" = 1 ]; then wrap=$(rs --final "'$LM'" --finish "'$FN'"); else wrap=$(rs --final "'$LM'"); fi
  local inner="$CP if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@ $OP $rflags; else $E -m kae.route.cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@ $OP $rflags; fi"
  $K method add "$name" --kind route --description "$desc; restart portfolio (tools/kaeres/restart.py) as route-finish-ab; operating facts rf-ab-operating-$OPH" \
    --command "$PRE $wrap '$inner'$POST" --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=4 \
    "${extra[@]}" --code kae=.@$SHA --harness $SHA >/dev/null
  echo "method: $name"
}
S7=${SHA:0:7}
A="cab legacy $S7 (restarts)"; N="cab default $S7 (restarts)"; A2="cab legacy twin $S7 (restarts)"
LEG="KAE_PAD_ENTRY=centre KAE_FR_PIN_ENTRIES=off"
add "$A" "kae.route.cli at $S7 with the legacy options: KAE_PAD_ENTRY=centre, KAE_FR_PIN_ENTRIES=off, route --no-finish, no finish pass" "$LEG" "--no-finish" 0
add "$N" "kae.route.cli at $S7 as kae ships it: defaults, --final last mile and --finish in the time left (no reserve)" "" "" 1
add "$A2" "A/A twin of '$A' (identical recipe; param replicate=2 only separates the ids)" "$LEG" "--no-finish" 0 replicate=2
desc="confirmation A/B of the routing default at $S7: A legacy, N the default (finish in the time left), A2 twin of A. Recipe: tools/kaeres/experiments/confirm-default-ab.sh; plan confirm-default-ab/PLAN.md. Operating facts rf-ab-operating-$OPH"
case "$STAGE" in
  full)
    $K exp create confirm-default-ab --method "$A" --method "$N" --boards @$D/confirm-default-ab/all.boards.txt \
      --harness $SHA --kae $SHA --env KAE_STEP_CACHE=$STEP_CACHE --description "$desc" >/dev/null
    $K exp create confirm-default-ab-twin --method "$A2" --boards @$D/confirm-default-ab/large-open.boards.txt \
      --harness $SHA --kae $SHA --env KAE_STEP_CACHE=$STEP_CACHE --description "A/A twin on the large open boards. $desc" >/dev/null ;;
  smoke)
    $K exp create confirm-default-ab-smoke-$S7 --method "$A" --method "$N" --method "$A2" --boards "${BOARD:?BOARD}" \
      --harness $SHA --kae $SHA --env KAE_STEP_CACHE=$STEP_CACHE --description "smoke (${BOARD}) of the $desc" >/dev/null ;;
  *) echo "STAGE: full or smoke" >&2; exit 2 ;;
esac
echo "experiment created (STAGE=$STAGE); nothing submitted"
