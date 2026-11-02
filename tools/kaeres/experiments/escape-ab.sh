#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# A/B of escape bands in placement (kae.place.escape_band, branch place-escape-keepouts) on the merit
# boards with a ball grid or a pad ring at <= 0.5 mm pitch (escape-ab.boards.txt: the 67 of the 213
# merge3-ab boards where escape_band.bands finds one). Every arm is the merge3-ab staged arm (kae staged
# main screen final: merit staged wrapper + --screen + --final, budget 900 s x sqrt(footprints/40)) at the
# same commit; only the placer's escape_band switch differs:
#
#   kae staged escape off    --set escape_band=0
#   kae staged escape soft   escape_band=1 (default): parts unrelated to a package pay for overlapping its band
#   kae staged escape hard   --set escape_band=2: the band is occupancy against every part
#
# Three attempts (seeds 0-2) per board and arm; routing from the bare placement (joint-fixed task).
# Harness e87baed and in-job physics kae f769333 as merge3-ab. Experiments: escape-ab (off, soft) on all 67
# boards; escape-ab-hard (hard) on the 9 with a ball grid (escape-ab-grid.boards.txt): on a 300 s placement
# smoke (gecko5education, nekoink, sdi-mipi; 2 seeds) the hard band emptied the bands of the packages' own
# series parts and decaps too (own-part area 9-21 mm2 against 46-191 soft and 57-170 off).
set -euo pipefail
cd "$(dirname "$0")/../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=${SHA:?commit of place-escape-keepouts}
KAE=(--code kae=.@$SHA)
H=(--harness $SHA)   # the wrapper (restart.py --resume --screen --final) runs from the method's harness
KH='$HOME/.cache/kaebench'
FORK="$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
NUMBA=numba-kae-escape-${SHA:0:7}
rs() { local f=$1 sl=$2; shift 2
  echo "{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s $f --scale-first --slack $sl $* --"; }
add() {  # NAME BASE_S WRAPPER DESCRIPTION INNER
  local name=$1 base=$2 wrap=$3 desc=$4 inner=$5
  wrap="${wrap% --} --check-placement --"
  $K method add "$name" --kind joint-fixed --description "$desc; restart portfolio (tools/kaeres/restart.py)" \
    --command "$wrap '$inner'" --param timeout_s="$base" --param timeout_scale=sqrt-fp40 --param parallel=4 \
    "${KAE[@]}" "${H[@]}"
}
CP="cp -r $KH/$NUMBA numba 2>/dev/null;"
E="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
FIN="$CP $E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
arm() {  # NAME MODE
  add "$1" 900 "$(rs 300 1.15 --resume 0.5 --screen --final "'$FIN'")" \
    "kae.joint.cli --max-iters 0 --no-modules --set escape_band=$2 at ${SHA:0:7} (place-escape-keepouts); restart --resume 0.5 --screen --final, as merge3-ab's staged arm" \
    "$CP if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else $E -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ --max-iters 0 --no-modules --set escape_band=$2; fi"
}
arm "kae staged escape off (restarts)" 0
arm "kae staged escape soft (restarts)" 1
arm "kae staged escape hard (restarts)" 2
