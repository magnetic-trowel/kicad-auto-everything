#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Registers the fr-settings-ab arms (see PLAN.md) and the experiment. Run from the repo root.
set -euo pipefail
K="python3 tools/kaeres/kaeres.py"
SHA=7f17a5d35b7fb02f10ee06d6672c7c00cb7eaad9
KAE=(--code kae=.@$SHA)
KH='$HOME/.cache/kaebench'
FORK="$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
CP="cp -r $KH/numba-kaefr-7f17a5d numba 2>/dev/null;"
E_="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
FIN="$CP $E_ -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
W="{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s 60 --scale-first --slack 1.15 --resume 0.5 --final '$FIN' --"
add() {  # NAME EXTRA_OPTS [--param ...]
  local name=$1 x=$2; shift 2
  local inner="$CP if [ \"\$KAE_RESUME\" = 1 ]; then $E_ -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@ $x; else $E_ -m kae.route.cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@ $x; fi"
  $K method add "$name" --kind route --description "kae bridge final at 7f17a5d; fr-settings-ab arm: ${x:-none}" \
    --command "$W '$inner'" --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=4 "$@" "${KAE[@]}" --harness $SHA
}
add "fr-sab control" ""
add "fr-sab twin" "" --param replicate=twin
add "fr-sab fanout" "--fanout"
add "fr-sab ladder" "--set fr.autorouter.fallback_strategies=no-neck,continue-fine-neck"
add "fr-sab outside" "--pad-shapes outside"
add "fr-sab neck" "--neckdown"
add "fr-sab outside neck" "--pad-shapes outside --neckdown"
add "fr-sab start_necked off" "--set fr.autorouter.start_necked=false"
add "fr-sab cost cycle" "--set fr_cycle=scoring.via_costs=25,scoring.start_ripup_costs=200\;scoring.via_costs=100\;scoring.start_ripup_costs=50\;scoring.default_undesired_direction_trace_cost=2.0"
add "fr-sab repair pass cap 3" "--set repair_passes=3"
add "fr-sab repair pass cap 1" "--set repair_passes=1"
$K exp create fr-settings-ab --boards @tools/kaeres/experiments/fr-settings-ab/boards.txt --harness $SHA --kae $SHA \
  --description "Bridge settings on a congested suite; PLAN.md in tools/kaeres/experiments/fr-settings-ab" \
  --method "fr-sab control" --method "fr-sab twin" --method "fr-sab fanout" --method "fr-sab ladder" \
  --method "fr-sab outside" --method "fr-sab neck" --method "fr-sab outside neck" \
  --method "fr-sab start_necked off" --method "fr-sab cost cycle" --method "fr-sab repair pass cap 3" --method "fr-sab repair pass cap 1"
