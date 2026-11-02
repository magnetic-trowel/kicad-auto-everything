#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Baselines after the 2026-11 bug audit (place-escape-keepouts 21bc53d: router, placer, loader, physics,
# harness and scoring fixes; place-fixed classifier rules 5 = task spec 9; score v9). Every earlier
# place-fixed / joint-fixed result is on task spec 8 and every physics number on the old evaluator, so
# the reference methods run again on the 213 merit boards, 1 attempt each, budget 900 s x sqrt(fp/40):
#
#   kae bridge final (restarts)       route        kae.route.cli, restart --resume 0.5 --final
#   kae joint loop final (restarts)   joint-fixed  kae.joint.cli (the loop), restart --resume 0.5 --final
#   kae staged escape soft (restarts) joint-fixed  the escape-ab soft arm (= kae staged at this commit:
#                                                  escape_band=1 is the default), registered by escape-ab.sh
#   freerouting 2.5.0                 route        a2c19e50f2b6 (task ids change with the spec: re-run)
#
# Physics is evaluated in the jobs with kae at the same commit. Numba cache: numba-kae-escape-<sha7>.
set -euo pipefail
cd "$(dirname "$0")/../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=${SHA:?commit}
KAE=(--code kae=.@$SHA)
H=(--harness $SHA)
KH='$HOME/.cache/kaebench'
FORK="$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
CP="cp -r $KH/numba-kae-escape-${SHA:0:7} numba 2>/dev/null;"
E_="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
FIN="$CP $E_ -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
rs() { local f=$1 sl=$2; shift 2
  echo "{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s $f --scale-first --slack $sl $* --"; }
add() {  # NAME KIND WRAPPER DESCRIPTION INNER
  local name=$1 kind=$2 wrap=$3 desc=$4 inner=$5
  [ "$kind" = route ] || wrap="${wrap% --} --check-placement --"
  $K method add "$name" --kind "$kind" --description "$desc; restart portfolio (tools/kaeres/restart.py)" \
    --command "$wrap '$inner'" --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=4 "${KAE[@]}" "${H[@]}"
}
RES="if [ \"\$KAE_RESUME\" = 1 ]; then $E_ -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else"
add "kae bridge final (restarts)" route "$(rs 60 1.15 --resume 0.5 --final "'$FIN'")" \
  "kae.route.cli at ${SHA:0:7} (post-audit); restart --resume 0.5 --final" \
  "$CP $RES $E_ -m kae.route.cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@; fi"
add "kae joint loop final (restarts)" joint-fixed "$(rs 300 1.15 --resume 0.5 --final "'$FIN'")" \
  "kae.joint.cli (joint loop) at ${SHA:0:7} (post-audit); restart --resume 0.5 --final" \
  "$CP $RES $E_ -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@; fi"
