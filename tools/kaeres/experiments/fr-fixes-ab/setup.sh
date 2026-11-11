#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Registers the fr-fixes-ab arms and experiments (see PLAN.md). Run from the repo root.
set -euo pipefail
K="python3 tools/kaeres/kaeres.py"
SHA=7f17a5d35b7fb02f10ee06d6672c7c00cb7eaad9
FR_SRC=${FR_SRC:?set FR_SRC to a clone of magnetic-trowel/freerouting}
FIX_NOMP=${FIX_NOMP:?set FIX_NOMP to bin/freerouting of the c2192531f install with the R11 no-cap wrapper}
KC=${KAE_HOME:-$HOME/.cache/kaebench}
if [ "${BRIDGE2:-0}" != 1 ]; then
# adapter arms: the R11 no-cap wrapper around each build
$K method add "fr-fork 2e1125a nomp fx" --binary $KC/kae-fr-2e1125a-nomp-r11/bin/freerouting --code router=$FR_SRC@2e1125a \
  --harness $SHA --param passes=none-stock-default --param wrapper=freerouting-nomp-v1 --param replicate=fx \
  --description "fr-fixes-ab control: production fork 2e1125a, no -mp cap" --build "install_freerouting_fork.sh 2e1125a; nomp wrapper (R11)"
$K method add "fr-fork c219253 nomp fx" --binary $FIX_NOMP --code router=$FR_SRC@c2192531f \
  --harness $SHA --param passes=none-stock-default --param wrapper=freerouting-nomp-v1 --param replicate=fx \
  --description "fr-fixes-ab: fork 2e1125a + #8 + #9 + #10 (branch kae-fixes-2611), no -mp cap" \
  --build "KAE_HOME=<private> install_freerouting_fork.sh c2192531f; nomp wrapper (R11)"
$K exp create fr-fixes-ab --boards @$(dirname "$0")/boards.txt --harness $SHA --kae $SHA \
  --method "fr-fork 2e1125a nomp fx" --method "fr-fork c219253 nomp fx" \
  --description "Fork fixes #8-#10 vs 2e1125a; PLAN.md in tools/kaeres/experiments/fr-fixes-ab"
# bridge arms: merge3-ab's "kae bridge main final" recipe, differing only in the Freerouting build
KAE=(--code kae=.@$SHA)
br() {  # NAME FORK_BINARY
  local name=$1 fork=$2
  local CP="cp -r \$HOME/.cache/kaebench/numba-kaefr-7f17a5d numba 2>/dev/null;"
  local E_="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$fork {py:kae}"
  local FIN="$CP $E_ -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
  local W="{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s 60 --scale-first --slack 1.15 --resume 0.5 --final '$FIN' --"
  local inner="$CP if [ \"\$KAE_RESUME\" = 1 ]; then $E_ -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else $E_ -m kae.route.cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@; fi"
  $K method add "$name" --kind route --description "kae bridge final at 7f17a5d, Freerouting $fork; fr-fixes-bridge" \
    --command "$W '$inner'" --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=4 "${KAE[@]}" --harness $SHA
}
br "fr-fx bridge 2e1125a" "$KC/kae-freerouting-fork-2e1125a/bin/freerouting"
br "fr-fx bridge c219253" "$KC/kae-fr-c219253/bin/freerouting"
$K exp create fr-fixes-bridge --boards @$(dirname "$0")/bridge.txt --harness $SHA --kae $SHA \
  --method "fr-fx bridge 2e1125a" --method "fr-fx bridge c219253" \
  --description "Fork fixes #8-#10 through the bridge, 40 selected boards; PLAN.md in tools/kaeres/experiments/fr-fixes-ab"
fi
KAE=(--code kae=.@$SHA)

# fr-fixes-bridge2: the same bridge arms with harness 0cd03a7 (restart.py keeps why an attempt failed, PR #55);
# kae stays at 7f17a5d, so its numba cache and code are unchanged
SHA2=0cd03a7ceead32db9c2b36e10719e40860ecd97f
br2() {  # NAME FORK_BINARY
  local name=$1 fork=$2
  local CP="cp -r \$HOME/.cache/kaebench/numba-kaefr-7f17a5d numba 2>/dev/null;"
  local E_="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$fork {py:kae}"
  local FIN="$CP $E_ -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
  local W="{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s 60 --scale-first --slack 1.15 --resume 0.5 --final '$FIN' --"
  local inner="$CP if [ \"\$KAE_RESUME\" = 1 ]; then $E_ -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else $E_ -m kae.route.cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@; fi"
  $K method add "$name" --kind route --description "kae bridge final (kae 7f17a5d, harness 0cd03a7), Freerouting $fork; fr-fixes-bridge2" \
    --command "$W '$inner'" --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=4 "${KAE[@]}" --harness $SHA2
}
if [ "${BRIDGE2:-0}" = 1 ]; then
  br2 "fr-fx2 bridge 2e1125a" "$KC/kae-freerouting-fork-2e1125a/bin/freerouting"
  br2 "fr-fx2 bridge c219253" "$KC/kae-fr-c219253/bin/freerouting"
  $K exp create fr-fixes-bridge2 --boards @$(dirname "$0")/bridge.txt --harness $SHA2 --kae $SHA \
    --method "fr-fx2 bridge 2e1125a" --method "fr-fx2 bridge c219253" \
    --description "Fork fixes #8-#10 through the bridge, 40 selected boards, failed attempts keep their cause; PLAN.md in tools/kaeres/experiments/fr-fixes-ab"
fi
