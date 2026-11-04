#!/bin/bash
# critical stage only (--no-bridge) per copper-ab arm on one board's stripped human layout: hazards and caps
set -u
id=$1; W=$KAE_AB_WORK/cdry/$id; rm -rf $W; mkdir -p $W/src $W/in
for e in kicad_pcb kicad_pro kicad_dru; do [ -f ~/kae-boards/boards/$id/board.$e ] && cp ~/kae-boards/boards/$id/board.$e $W/src/; done
. ~/.cache/kaebench/env.sh
export APPTAINER_BIND=$KAE_LOCAL,$HOME/kae-baselines/code,$HOME/kae-boards OMP_NUM_THREADS=1 KAE_WORKERS=1
export NUMBA_CACHE_DIR=$W/numba; cp -r ~/.cache/kaebench/numba-kae-decide-680c30e $NUMBA_CACHE_DIR
ulimit -v 40000000
H=$HOME/kae-baselines/code/kicad-auto-everything@680c30ebb0c9
$KAE_KICAD_WRAP python3 $H/bench/src/kaebench/kicad_scripts/pcbnew_ops.py strip-routing $W/src/board.kicad_pcb $W/in/board.kicad_pcb > $W/strip.log 2>&1
for e in kicad_pro kicad_dru; do [ -f $W/src/board.$e ] && cp $W/src/board.$e $W/in/; done
PY=$H.venv-kae/bin/python
for arm in default rail_over_cap=1 via_A=1.0; do
  o=(); [ $arm != default ] && o=(--opt $arm)
  timeout 1200 $PY -m kae.route.critical_cli route $W/in/board.kicad_pcb $W/out-$arm.kicad_pcb --no-bridge --seed 0 --time 600 "${o[@]}" --report $W/rep-$arm.json > $W/log-$arm 2>&1
  echo "$id $arm rc=$?"
done
rm -rf $NUMBA_CACHE_DIR
