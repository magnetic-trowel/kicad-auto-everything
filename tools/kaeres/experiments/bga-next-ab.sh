#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# A/B of three router changes for ball grids (branch route-bga-next) on the ball-grid boards:
#   1. close-bga-region merged: the monotone BGA window repair before the last mile (bridge opts region,
#      repair_window; not region_mode=full), measured once: 916 -> 729 open on 6 boards x 3 seeds;
#   2. one ball-grid test for router and placer (kae.route.escape.ball_grid): small wafer-level grids
#      (circuitmonkey chips-0123's 12-ball MAX98365) get escape plans and dog-bones;
#   3. rings from open voids: balls beside a depopulated channel (nekoink U202, sdi-mipi U12, gecko5 U9)
#      escape on the surface into it; dog-bones and the placer's bands follow (the nekoink prototype was
#      within seed noise, hence this A/B).
#
#   A  kae staged base (restarts)      kae at 7221e4a (place-escape-keepouts head before the changes)
#   B  kae staged bga-next (restarts)  kae at $SHA_B (route-bga-next)
#
# Both arms: merge3-ab's staged wrapper (restart.py --resume 0.5 --screen --final, --check-placement,
# 900 s x sqrt(footprints/40)), escape_band at its default; 10 ball-grid boards (escape-ab-grid.boards.txt,
# which already holds chips-0123, the only merit board whose package part 2 newly makes a grid), 3 seeds.
#
# Harness. A method's --harness is where its restart wrapper runs from AND which harness prepares its
# boards; kaeres discards runs on another task spec (and exp create refuses such methods). So both
# methods and the experiment use --harness $SHA_B: the same prepare and scorer for both arms. A's kae code
# stays A's (--code kae=.@7221e4a, its {py:kae} venv); only its wrapper (tools/kaeres/restart.py) comes
# from B, which does not change restart.py relative to A (git diff 7221e4a $SHA_B -- tools/kaeres/restart.py
# is empty), so A runs exactly A's code.
#
# Numba caches per commit (tools/kaeres/experiments/warm-numba.sh), so no arm compiles inside its budget:
#   numba-kae-bga-base-7221e4a and numba-kae-bga-next-${SHA_B:0:7}.
#
# Usage: SHA_B=<route-bga-next commit, pushed> tools/kaeres/experiments/bga-next-ab.sh
# then (ids from `kaeres method list`):
#   kaeres exp create bga-next-smoke --method A --method B --boards circuitmonkey-chips-0123-class-d-amp-max98365,zephray-nekoink-pcb-2 \
#       --attempts 1 --harness $SHA_B --kae $SHA_B
#   warm-numba.sh 7221e4a... numba-kae-bga-base-7221e4a ... ; warm-numba.sh $SHA_B numba-kae-bga-next-... ...
#   kaeres exp submit bga-next-smoke; check it; then
#   kaeres exp create bga-next-ab --boards @tools/kaeres/experiments/escape-ab-grid.boards.txt --attempts 3 ... ; exp submit; exp install-timer
set -euo pipefail
cd "$(dirname "$0")/../../.."
K="python3 tools/kaeres/kaeres.py"
SHA_A=$(git rev-parse 7221e4a)
SHA_B=${SHA_B:?commit of route-bga-next (pushed)}
git diff --quiet "$SHA_A" "$SHA_B" -- tools/kaeres/restart.py || { echo "restart.py differs between A and B" >&2; exit 1; }
H=(--harness "$SHA_B")
KH='$HOME/.cache/kaebench'
FORK="$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
rs() { local f=$1 sl=$2; shift 2
  echo "{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s $f --scale-first --slack $sl $* --"; }
arm() {  # NAME SHA NUMBA DESCRIPTION
  local name=$1 sha=$2 numba=$3 desc=$4
  local CP="cp -r $KH/$numba numba 2>/dev/null;"
  local E="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
  local FIN="$CP $E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
  local wrap inner
  wrap="$(rs 300 1.15 --resume 0.5 --screen --final "'$FIN'")"
  wrap="${wrap% --} --check-placement --"
  inner="$CP if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else $E -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ --max-iters 0 --no-modules; fi"
  $K method add "$name" --kind joint-fixed --description "$desc; restart --resume 0.5 --screen --final, as merge3-ab's staged arm; restart portfolio (tools/kaeres/restart.py)" \
    --command "$wrap '$inner'" --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=4 \
    --code kae=.@"$sha" "${H[@]}"
}
arm "kae staged base (restarts)" "$SHA_A" numba-kae-bga-base-${SHA_A:0:7} \
  "kae.joint.cli --max-iters 0 --no-modules at ${SHA_A:0:7} (place-escape-keepouts, before route-bga-next); wrapper from harness ${SHA_B:0:7} (restart.py unchanged)"
arm "kae staged bga-next (restarts)" "$SHA_B" numba-kae-bga-next-${SHA_B:0:7} \
  "kae.joint.cli --max-iters 0 --no-modules at ${SHA_B:0:7} (route-bga-next: BGA window repair merged, small ball grids, rings from open voids)"
