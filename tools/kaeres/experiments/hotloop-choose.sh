#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Choose-better follow-up of the hot-loop A/B (hotloop-ab.sh on route-finish-ab; plan hotloop-choose/PLAN.md):
# kae's default router (N) and its hot-loop keep-out (K) run side by side in one restart portfolio and the better
# board is kept (tools/kaeres/restart.py --alt-env/--tiebreak), and the keep-out that leaves room for the loop's
# own vias (hotloop_keepout_loopvias).
#
#   C   choose N/K    restart.py --alt-env KAE_HOTLOOP_KEEPOUT=1 --tiebreak (kae.excite.cellquote score): odd
#                     attempts with K's keep-out; KiCad's rank first, the cells' quote between clean boards
#   KV  keepout vias  K + KAE_HOTLOOP_KEEPOUT_LOOPVIAS=1
#   CV  choose N/KV   as C with KV's setting as arm B
# N and K are hotloop-ab's runs (b8703501: the routing code here differs only by these options, off by default).
#
#   SHA=<pushed commit> [STAGE=full|smoke] [BOARD=...] tools/kaeres/experiments/hotloop-choose.sh
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

rs() { local cb=""; [ -n "${ALT:-}" ] && cb="--alt-env '$ALT' --tiebreak '$TB'"
  echo "{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s 60 --scale-first --slack 1.15 --resume 0.5 $cb $* --"; }
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
TB="env OMP_NUM_THREADS=2 KAE_EM_THREADS=2 OPENBLAS_NUM_THREADS=2 NUMBA_CACHE_DIR=\$PWD/numba {py:kae} -m kae.excite.cellquote @BOARD@ --intent \$RFAB_OP --score-out @OUT@"
C="hl choose N/K $S7 (restarts)"; KV="hl keepout vias $S7 (restarts)"; CV="hl choose N/KV $S7 (restarts)"
add "$KV" "as hotloop-ab's K plus KAE_HOTLOOP_KEEPOUT_LOOPVIAS=1 (room for the loop's own vias in the keep-outs)" \
  "KAE_HOTLOOP_KEEPOUT=1 KAE_HOTLOOP_KEEPOUT_LOOPVIAS=1" "" 1
ALT="KAE_HOTLOOP_KEEPOUT=1" add "$C" "choose-better: odd attempts with KAE_HOTLOOP_KEEPOUT=1 (K), KiCad's rank first, the cells' quote (kae.excite.cellquote) between clean boards" "" "" 1
ALT="KAE_HOTLOOP_KEEPOUT=1 KAE_HOTLOOP_KEEPOUT_LOOPVIAS=1" add "$CV" "choose-better: odd attempts with KAE_HOTLOOP_KEEPOUT=1 KAE_HOTLOOP_KEEPOUT_LOOPVIAS=1 (KV), KiCad's rank first, the cells' quote between clean boards" "" "" 1
desc="hot-loop choose-better at $S7: C (N/K side by side, the better board kept), KV (keep-out with room for the loop's vias), CV (N/KV). Recipe: tools/kaeres/experiments/hotloop-choose.sh; plan hotloop-choose/PLAN.md. Operating facts rf-ab-operating-$OPH"
M=(--method "$C" --method "$KV" --method "$CV")
case "$STAGE" in
  full) $K exp create hotloop-choose "${M[@]}" --boards @$D/hotloop-choose/boards.txt --harness $SHA --kae $SHA \
          --env KAE_STEP_CACHE=$STEP_CACHE --description "$desc" >/dev/null ;;
  smoke) $K exp create hotloop-choose-smoke-$S7 "${M[@]}" --boards "${BOARD:?BOARD}" --harness $SHA --kae $SHA \
          --env KAE_STEP_CACHE=$STEP_CACHE --description "smoke (${BOARD}) of the $desc" >/dev/null ;;
  rerun) $K exp create hotloop-choose-rerun-$S7 --method "$C" --method "$CV" --boards @$D/hotloop-choose/rerun-boards.txt \
          --harness $SHA --kae $SHA --env KAE_STEP_CACHE=$STEP_CACHE --description "rerun of C and CV (final tie-break) on the boards where both arms finished clean: $desc" >/dev/null ;;
  *) echo "STAGE: full, smoke or rerun" >&2; exit 2 ;;
esac
echo "experiment created (STAGE=$STAGE); nothing submitted"
