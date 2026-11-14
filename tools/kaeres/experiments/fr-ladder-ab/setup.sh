#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Registers the fr-ladder-ab arms (see PLAN.md) and the experiment. Run from the repo root.
# The arms differ only in the Freerouting build: the production pin (d137fd1) and the fork
# branch kae-ladder-no-neck (40c89c3, d137fd1 plus the no-fanout fallback ladder).
set -euo pipefail
K="python3 tools/kaeres/kaeres.py"
SHA=6fdfc89c159cbd50a1686c3b0f8a5238021f25f1
FRREPO=https://github.com/magnetic-trowel/freerouting
KH='$HOME/.cache/kaebench'
CP="cp -r $KH/numba-kaeladder-6fdfc89 numba 2>/dev/null;"
add() {  # NAME BUILD FORK_COMMIT [--param ...]
  local name=$1 build=$2 frc=$3; shift 3
  local fr="$HOME/.cache/kaebench/$build/bin/freerouting"
  local e="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$fr {py:kae}"
  local fin="$CP $e -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
  local w="{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s 60 --scale-first --slack 1.15 --resume 0.5 --final '$fin' --"
  local inner="$CP if [ \"\$KAE_RESUME\" = 1 ]; then $e -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@ ; else $e -m kae.route.cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@ ; fi"
  $K method add "$name" --kind route --description "kae bridge final at 6fdfc89; Freerouting $build" \
    --command "$w '$inner'" --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=4 "$@" \
    --code kae=.@$SHA --code fr=$FRREPO@$frc --harness $SHA
}
add "frl control" kae-freerouting-fork-d137fd1 d137fd1bb934a5136ad0ac2c165cbe0324ed05fa
add "frl ladder" kae-fr-ladder-40c89c3 40c89c338be60aa36628ef08859d01519e8217c0
$K exp create fr-ladder-ab --boards @tools/kaeres/experiments/fr-ladder-ab/boards.txt --harness $SHA --kae $SHA \
  --description "Freerouting fallback ladder without fanout or neck width; PLAN.md in tools/kaeres/experiments/fr-ladder-ab" \
  --method "frl control" --method "frl ladder"
