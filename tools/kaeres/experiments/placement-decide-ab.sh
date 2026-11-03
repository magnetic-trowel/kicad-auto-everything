#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# A/Bs for the placement divergences the 2026-11 audit left open (branch decide-placement). Every switch
# is a kae.route.constraints / joint stage option that defaults to the current behaviour, so one commit
# serves all arms; only the --set differs.
#
# Placement arms: the merge3-ab staged arm (kae.joint.cli --max-iters 0 --no-modules, restart --resume 0.5
# --screen --final, 900 s x sqrt(fp/40)) on the 213 merit boards, 3 attempts (seeds 0-2), joint-fixed task:
#
#   kae staged decide control        defaults (place_w_cong=30, place_margin=-1 = auto)
#   kae staged decide cong0          --set place_w_cong=0     audit P5: RUDY term off
#   kae staged decide cong10         --set place_w_cong=10    audit P5: a third of today's weight
#   kae staged decide margin0        --set place_margin=0     audit P10: no a-priori routing margin
#
# Joint-loop arms: kae joint loop final (restart --resume 0.5 --final), same boards and attempts:
#
#   kae joint decide control         defaults (bump_mm=0.25, replace_margin=0.3)
#   kae joint decide bump0           --set bump_mm=0          audit J10: no bloat-style bump in windows
#   kae joint decide rmargin0        --set replace_margin=0   audit J10: no window routing margin
#
# Decide on paired per-board differences against the control of the same family: cp1, cpk (k=3),
# completion, unconnected items, DRC errors by type, physics sum u (rephysics evaluator), placer move
# rate (P5: the RUDY term's cost). P5 and P10 split out the dense boards (split C, or the place report's
# seed RUDY overflow > 0): elsewhere RUDY's overflow is ~0 and the margin is ~1 mm. Expected effects are small (|delta cp1| <= 0.02); a treatment that
# is not worse beyond the seed noise of the control (its spread over seeds 0-2) wins when it is the
# simpler arm (P5 cong0, J10 bump0 / rmargin0); margin0 must be at least as good to replace auto.
set -euo pipefail
cd "$(dirname "$0")/../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=${SHA:?commit of decide-placement}
KAE=(--code kae=.@$SHA)
H=(--harness $SHA)
KH='$HOME/.cache/kaebench'
FORK="$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
NUMBA=numba-kae-decide-${SHA:0:7}
rs() { local f=$1 sl=$2; shift 2
  echo "{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s $f --scale-first --slack $sl $* --"; }
add() {  # NAME WRAPPER DESCRIPTION INNER
  local name=$1 wrap=$2 desc=$3 inner=$4
  wrap="${wrap% --} --check-placement --"
  $K method add "$name" --kind joint-fixed --description "$desc; restart portfolio (tools/kaeres/restart.py)" \
    --command "$wrap '$inner'" --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=4 \
    "${KAE[@]}" "${H[@]}"
}
CP="cp -r $KH/$NUMBA numba 2>/dev/null;"
E="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
FIN="$CP $E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
RES="if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else"
staged() {  # NAME SET
  add "$1" "$(rs 300 1.15 --resume 0.5 --screen --final "'$FIN'")" \
    "kae.joint.cli --max-iters 0 --no-modules $2 at ${SHA:0:7} (decide-placement); restart --resume 0.5 --screen --final, as merge3-ab's staged arm" \
    "$CP $RES $E -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ --max-iters 0 --no-modules $2; fi"
}
joint() {  # NAME SET
  add "$1" "$(rs 300 1.15 --resume 0.5 --final "'$FIN'")" \
    "kae.joint.cli (joint loop) $2 at ${SHA:0:7} (decide-placement); restart --resume 0.5 --final" \
    "$CP $RES $E -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ $2; fi"
}
staged "kae staged decide control (restarts)" ""
staged "kae staged decide cong0 (restarts)" "--set place_w_cong=0"
staged "kae staged decide cong10 (restarts)" "--set place_w_cong=10"
staged "kae staged decide margin0 (restarts)" "--set place_margin=0"
joint "kae joint decide control (restarts)" ""
joint "kae joint decide bump0 (restarts)" "--set bump_mm=0"
joint "kae joint decide rmargin0 (restarts)" "--set replace_margin=0"
# Experiments (boards: experiments/merge3-ab/boards.txt; numba cache warmed with warm-numba.sh at $SHA):
#   placement-decide-place: the four staged arms, --attempts 3
#   placement-decide-joint: the three joint arms, --attempts 3
