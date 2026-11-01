#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# A/B of the routing closeout as merged (main e9889fd: rules-merge3 + physics-functional-eval) against
# the merit kae methods (kae-complete 78d3de7 "lm-base" in merit-500r3k, kae-route-fixes 9a21bbf on the 9
# boards where that differs), on the same 213 merit boards, budget and restart portfolio.
#
#   kae bridge main            same wrapper flags as the merit bridge: the code alone
#   kae bridge main final      + --resume 0.5 --final (the last pass on the kept board), as the near-miss study ran it
#   kae staged main screen final  the merit staged wrapper (--resume 0.5 --check-placement) + --screen + --final
#
# Control: the merit methods as they stand (kae-route-fixes 9a21bbf, restart.py a046c92): kae bridge (restarts)
# a6b0f7df78ae and kae staged (restarts) 24868880ef30, re-run on all 213 boards in the same experiment, so
# both arms share the host's load and the same prepare harness. kaeres runs every method in a bwrap sandbox
# with a private /tmp, so Freerouting's slot pool (/tmp/kae-fr-slots) is per job, not host-wide.
#
# Numba cache: numba-kaemain-e9889fd, warmed for this code (tools/kaeres/experiments/warm-numba.sh).
set -euo pipefail
cd "$(dirname "$0")/../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=e9889fdf9e6c4397eca474a655c6eb31d65f527a
KAE=(--code kae=.@$SHA)
H=(--harness $SHA)
KH='$HOME/.cache/kaebench'
FORK="$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
rs() { local f=$1 sl=$2; shift 2
  echo "{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s $f --scale-first --slack $sl $* --"; }
add() {  # NAME KIND BASE_S WRAPPER DESCRIPTION INNER
  local name=$1 kind=$2 base=$3 wrap=$4 desc=$5 inner=$6; shift 6
  [ "$kind" = route ] || wrap="${wrap% --} --check-placement --"
  $K method add "$name" --kind "$kind" --description "$desc; restart portfolio (tools/kaeres/restart.py)" \
    --command "$wrap '$inner'" --param timeout_s="$base" --param timeout_scale=sqrt-fp40 --param parallel=4 \
    "${KAE[@]}" "${H[@]}"
}
CP="cp -r $KH/numba-kaemain-e9889fd numba 2>/dev/null;"
E="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
FIN="$CP $E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"

add "kae bridge main (restarts)" route 900 "$(rs 60 1.15)" "kae.route.cli at main e9889fd (routing closeout merged)" \
  "$CP $E -m kae.route.cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@"
add "kae bridge main final (restarts)" route 900 "$(rs 60 1.15 --resume 0.5 --final "'$FIN'")" \
  "kae.route.cli at main e9889fd; restart --resume 0.5 (resumed attempts route from the best board) and --final (kae.route.cli lastmile on the kept board)" \
  "$CP if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else $E -m kae.route.cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@; fi"
add "kae staged main screen final (restarts)" joint-fixed 900 "$(rs 300 1.15 --resume 0.5 --screen --final "'$FIN'")" \
  "kae.joint.cli --max-iters 0 --no-modules at main e9889fd; restart --resume 0.5 --screen (successive halving over placements) and --final (kae.route.cli lastmile on the kept board)" \
  "$CP if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else $E -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ --max-iters 0 --no-modules; fi"
