#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# fork.sh ARM BOARD: one board of an arm made from a stored run, without re-routing; scored by kaebench's
# scorer at SHA in a kaebench run of its own (sandboxed --command, the stored board read-only):
#   B    kae.route.cli finish on arm A's kept board (A_ID: A's kaeres method id), the task input's rules
#        and the board's operating facts; --time as restart.py's finish reserve (finish_estimate)
#   A0   merge3-ab's kae bridge main final board (286c2335844d, e9889fd), copied: its re-score at SHA
# Writes OUT/<ARM>/<BOARD>/: attempt.json (kaebench score, errors_by_type, clean_strict), output.kicad_pcb.gz,
# drc.json, adapter.log (finish's report is its last JSON line).
#   SHA=... A_ID=... OUT=/var/tmp/$USER/rf-ab fork.sh B BOARD        (run it through kaeq: submit.py fork)
set -euo pipefail
arm=$1 b=$2
. "$(dirname "$0")/common.sh"
case "$arm" in
  B) src=$(rf_run_dir "$b" "${A_ID:?A_ID: arm A method id}") || { echo "$b: no run of A (${A_ID:0:8})" >&2; exit 3; } ;;
  A0) src=$(rf_run_dir "$b" A0) || { echo "$b: no A0 run" >&2; exit 3; } ;;
  *) echo "ARM: B or A0" >&2; exit 2 ;;
esac
dest=$OUT/$arm/$b
[ -f "$dest/attempt.json" ] && { echo "$b: $arm done"; exit 0; }
ws=${KAEQ_SCRATCH:-$(mktemp -d "/var/tmp/$USER/rfab-fork-XXXXXX")}
mkdir -p "$ws/in" "$dest"
rf_env "$ws" "$b"
ulimit -v 40000000
rf_prepare "$ws" "$b"
zcat "$src/output.kicad_pcb.gz" > "$ws/in/stored.kicad_pcb"
op=$HOME/.cache/kaebench/rf-ab-operating-$(cat "$OPSRC"/*.operating.json | sha256sum | cut -c1-12)/$b.operating.json
[ -f "$op" ] || op=$OPSRC/$b.operating.json
cp "$op" "$ws/in/operating.json" 2>/dev/null || echo '{}' > "$ws/in/operating.json"
if [ "$arm" = B ]; then
  # restart.py finish_estimate with A's slowest judgement (its mean, as recorded) as the DRC time
  read -r T DS < <(python3 - "$src/run.json" "$ws/w/tasks/$b/route/input/board.kicad_pcb" <<'EOF'
import json, sys
w = json.load(open(sys.argv[1])).get("work") or {}
j = (w.get("judge_wall_s") or 0.0) / max(1, w.get("attempts") or 1)
pads = open(sys.argv[2], errors="replace").read().count("(pad ")
print(round(max(30.0, 15.0 + 0.17 * pads + 2 * j + 5.0)), round(j, 1))
EOF
)
  cp -r "$NUMBA" "$ws/in/numba" 2>/dev/null || true
  tpl="cp -r $ws/in/numba numba 2>/dev/null; env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 $KPY -m kae.route.cli finish {input} $ws/in/stored.kicad_pcb {output} --time $T --drc-s $DS --set operating=$ws/in/operating.json"
  tmo=$(( T * 3 + 600 ))
else
  tpl="cp $ws/in/stored.kicad_pcb {output}"
  tmo=600
fi
# the sandbox hides the corpus and the store: Apptainer gets only what the method can see (as kaeres does)
APPTAINER_BIND="$ws,$CODE,$CODE.venv-kae" "$KB" --workdir "$ws/w" run --adapter "rfab-$arm" --command "$tpl" --sandbox-ro "$ws/in" --sandbox-ro "$CODE" \
  --sandbox-ro "$CODE.venv-kae" --kinds route -k 1 --timeout "$tmo" --all --only "$b" --name "$arm" -j 1 > "$ws/run.log" 2>&1 || true
ad=$ws/w/results/$arm/rfab-$arm/route/$b/attempt-0
[ -f "$ad/attempt.json" ] || { tail -40 "$ws/run.log" >&2; exit 1; }
if ! grep -q '"status": "ok"' "$ad/attempt.json"; then   # not kept: a retry runs it again
  tail -c 3000 "$ad/adapter.log" >&2; rm -rf "$dest"; exit 1
fi
cp "$ad/attempt.json" "$dest/"
[ -f "$ad/adapter.log" ] && cp "$ad/adapter.log" "$dest/"
[ -f "$ad/score/drc.json" ] && cp "$ad/score/drc.json" "$dest/"
[ -f "$ad/output/board.kicad_pcb" ] && gzip -c "$ad/output/board.kicad_pcb" > "$dest/output.kicad_pcb.gz"
echo "{\"src\": \"$src\", \"sha\": \"$SHA\", \"time_s\": \"${T:-}\"}" > "$dest/source.json"
python3 -c "import json,sys; a=json.load(open(sys.argv[1])); s=a.get('score') or {}; print(sys.argv[2], a.get('status'), 'clean', s.get('clean'), 'strict', s.get('clean_strict'), 'unconn', s.get('unconnected'), 'errors', s.get('errors'))" "$dest/attempt.json" "$b"
[ -n "${KAEQ_SCRATCH:-}" ] || rm -rf "$ws"
