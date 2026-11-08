#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# A/B of zone-aware placement (kae.place.zones, branch place-zone-aware): in the place-fixed and
# joint-fixed tasks the human's copper zones stay where they were, and the placer now keeps parts over
# their own nets' fixed zones (zone_pull, seed anchors and pinned packages) and other nets' pads out of
# outer zones they would bridge (zone_keepout).
#
#   base  kae staged base (restarts)   kae at 7221e4a, the branch's base: method c797ddafd9f5, registered
#                                      by bga-next-ab.sh (route-bga-next) and reused here, so runs on the
#                                      boards both experiments hold are shared
#   zone  kae staged zone (restarts)   kae at $SHA (place-zone-aware), defaults zone_pull=3, zone_keepout=1
#
# Both arms: merge3-ab's staged wrapper (restart.py --resume 0.5 --screen --final, --check-placement,
# 900 s x sqrt(footprints/40)), 3 seeds. Boards (zone-ab.boards.txt): the merge3-ab merit boards whose
# human placement has at least 10 movable pads (place-fixed's fixed classes held) whose net owns a fixed
# copper zone on a layer the pad reaches, zones covering >= 90% of the board left out: the info
# "pull_pads" of kae.place.zones.build(Problem.build(board, held=kae.place.fixed.fixed_uuids(board,
# classes=("connectors", "mounting", "user")))) on ~/kae-boards/boards/<id>/board.kicad_pcb.
#
# Harness. The base method's harness is c5f328a (route-bga-next); the zone method and the experiment use
# $SHA. Neither commit changes bench/ (prepare, scorer) or tools/kaeres/{restart,kaeres}.py against
# 7221e4a (git diff below), so both arms see the same task spec, task ids and evaluator.
#
# Numba caches per commit (warm-numba.sh): numba-kae-bga-base-7221e4a (bga-next-ab) and
# numba-kae-zone-${SHA:0:7}.
#
# Usage: SHA=<place-zone-aware commit, pushed> tools/kaeres/experiments/zone-ab.sh   (registers the zone arm)
# then:
#   warm-numba.sh $SHA numba-kae-zone-${SHA:0:7} /var/tmp/eriks/prof/tasks/M/route.kicad_pcb ... (inputs S/M/L)
#   kaeres exp create zone-smoke --method c797ddafd9f5 --method <zone id> \
#       --boards logisim-evolution-gecko5education-gecko5education,zephray-nekoink-pcb-2 --attempts 1 --harness $SHA --kae $SHA
#   kaeres exp submit zone-smoke; check runs, bugs, scores; then
#   kaeres exp create zone-ab --method c797ddafd9f5 --method <zone id> --boards @tools/kaeres/experiments/zone-ab.boards.txt \
#       --attempts 3 --harness $SHA --kae $SHA; kaeres exp submit zone-ab; kaeres exp install-timer zone-ab
set -euo pipefail
cd "$(dirname "$0")/../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=$(git rev-parse "${SHA:?commit of place-zone-aware (pushed)}")
BASE=7221e4a
for h in c5f328a "$SHA"; do
  git diff --quiet "$BASE" "$h" -- bench tools/kaeres/restart.py tools/kaeres/kaeres.py \
    || { echo "$h changes the harness against $BASE" >&2; exit 1; }
done
KH='$HOME/.cache/kaebench'
FORK="$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
NUMBA=numba-kae-zone-${SHA:0:7}
CP="cp -r $KH/$NUMBA numba 2>/dev/null;"
E="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
FIN="$CP $E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
WRAP="{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s 300 --scale-first --slack 1.15 --resume 0.5 --screen --final '$FIN' --check-placement --"
INNER="$CP if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else $E -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ --max-iters 0 --no-modules; fi"
$K method add "kae staged zone (restarts)" --kind joint-fixed \
  --description "kae.joint.cli --max-iters 0 --no-modules at ${SHA:0:7} (place-zone-aware: fixed zones as placement facts, zone_pull=3, zone_keepout=1); restart --resume 0.5 --screen --final, as merge3-ab's staged arm; restart portfolio (tools/kaeres/restart.py)" \
  --command "$WRAP '$INNER'" --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=4 \
  --code kae=.@"$SHA" --harness "$SHA"
