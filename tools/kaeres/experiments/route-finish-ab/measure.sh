#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# measure.sh BOARD ARM [DX DY]: one arm's kept board of one board, measured:
#   OUT/measure/BOARD/ARM.stats.json          kae.route.taut stats (pad entries perpendicular/oblique/acute,
#                                             overhanging, copper length by class, corners, arcs)
#   OUT/measure/BOARD/phys/ARM[@DX,DY].*      the fixed physics evaluator at SHA (tools/research/physics/
#                                             eval_intent.sh as ab4 ran it; KAE_EM_TOL=1e-4), and kae.intent
#                                             status under the board's intent. DX DY: the raster window shifted
#                                             (offset_eval.py), for the noise check in PLAN.md
# ARM: human (the corpus board), A0 (merge3-ab 286c2335844d), B (OUT/B/BOARD), or ARM=ID (a kaeres method id:
# its stored run). The board's rules come from the corpus board (KAE_RULES_FROM), as every rescore did.
#   SHA=... measure.sh BOARD 1a2b3c4d5e6f      (through kaeq with 16 cpus: submit.py measure)
set -euo pipefail
b=$1 arm=$2 dx=${3:-} dy=${4:-}
. "$(dirname "$0")/common.sh"
here=$(cd "$(dirname "$0")" && pwd)
M=$OUT/measure/$b
mkdir -p "$M/phys"
case "$arm" in
  human) src=$CORPUS/boards/$b/board.kicad_pcb ;;
  B) src=$OUT/B/$b/output.kicad_pcb.gz ;;
  A0) src=$(rf_run_dir "$b" A0)/output.kicad_pcb.gz ;;
  *) d=$(rf_run_dir "$b" "$arm") || { echo "$b: no run of $arm" >&2; exit 3; }; src=$d/output.kicad_pcb.gz ;;
esac
[ -f "$src" ] || { echo "$b: no board for $arm ($src)" >&2; exit 3; }
tag=${arm:0:12}; [ -n "$dx" ] && tag="$tag@$dx,$dy"
ws=${KAEQ_SCRATCH:-$(mktemp -d "/var/tmp/$USER/rfab-meas-XXXXXX")}
export APPTAINER_BIND="$ws,$(readlink -f "$CORPUS"),/var/tmp/$USER"
export KAE_EM_TOL=1e-4 KAE_EVAL_VMEM_KB=${KAE_EVAL_VMEM_KB:-250000000} KAE_PY=$KPY
case "$src" in *.gz) zcat "$src" > "$ws/board.kicad_pcb" ;; *) cp "$src" "$ws/board.kicad_pcb" ;; esac
for e in kicad_pro kicad_dru; do [ -f "$CORPUS/boards/$b/board.$e" ] && cp "$CORPUS/boards/$b/board.$e" "$ws/board.$e"; done
if [ -z "$dx" ] && [ ! -s "$M/${arm:0:12}.stats.json" ]; then
  ( ulimit -v 40000000; PYTHONPATH=$CODE/kae/src "$KPY" -m kae.route.taut stats "$ws/board.kicad_pcb" ) > "$M/${arm:0:12}.stats.json" \
    2> "$ws/stats.err" || { tail -5 "$ws/stats.err" >&2; rm -f "$M/${arm:0:12}.stats.json"; }
fi
if [ -z "$dx" ]; then      # overhang by land type and exposed acute notches (DFM criteria, PLAN.md section 9)
  for t in overhang_diag notch_stats; do
    j=$M/${arm:0:12}.$t.json
    [ -s "$j" ] || ( ulimit -v 40000000; PYTHONPATH=$CODE/kae/src "$KPY" "$CODE/tools/research/routing/$t.py" "$ws/board.kicad_pcb" --json "$j" ) \
      > /dev/null 2> "$ws/$t.err" || { tail -5 "$ws/$t.err" >&2; rm -f "$j"; }
  done
fi
[ -n "${NO_PHYSICS:-}" ] && exit 0
[ -s "$M/phys/$tag.status.json" ] && { echo "$b $tag: physics done"; exit 0; }
op=$OPSRC/$b.operating.json it=$OPSRC/$b.intent.json
t0=$(date +%s)
if [ -z "$dx" ]; then
  KAE_RULES_FROM=$ws/board.kicad_pcb bash "$CODE/tools/research/physics/eval_intent.sh" "$ws/board.kicad_pcb" "$op" "$it" \
    "$M/phys" "$tag" > /dev/null
else
  T=${KAEQ_CPUS:-4}
  ( export PYTHONPATH=$CODE/kae/src NUMBA_THREADING_LAYER=omp KAE_EM_THREADS=$T OMP_NUM_THREADS=$T OPENBLAS_NUM_THREADS=$T MKL_NUM_THREADS=$T
    ( ulimit -v 40000000; $KAE_KICAD_WRAP kicad-cli pcb upgrade --force "$ws/board.kicad_pcb" >/dev/null 2>&1 || true )
    ulimit -v "$KAE_EVAL_VMEM_KB"
    "$KPY" -u -W ignore "$here/offset_eval.py" "$ws/board.kicad_pcb" "$op" "$M/phys/$tag.ev.json" "$dx" "$dy" > "$M/phys/$tag.ev.txt" 2>&1
    "$KPY" -u -W ignore -m kae.intent status "$M/phys/$tag.ev.json" --intent "$it" -o "$M/phys/$tag.status.json" > "$M/phys/$tag.status.txt" 2>&1 )
  echo "eval_s $(( $(date +%s) - t0 ))" >> "$M/phys/$tag.status.txt"
fi
rm -rf "$M/phys/$tag.work"
[ -n "${KAEQ_SCRATCH:-}" ] || rm -rf "$ws"
echo "$b $tag: $(grep -m1 -i total "$M/phys/$tag.status.txt" || true)"
