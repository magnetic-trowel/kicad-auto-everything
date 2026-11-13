#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# smoke_prof.sh ARM BOARD: one profiled run of an arm of confirm-default-ab.sh outside the sandbox (seed 0, the
# arm's budget and wrapper flags), with py-spy over every Python process (--subprocesses --idle, raw) and Java
# Flight Recorder on Freerouting. Writes PROF/<BOARD>.<ARM>/: meta (wall, budget, peak RSS), log, summary.json,
# report.json, prof.txt (py-spy raw) and jfr/*.jfr. Time per stage: stage_prof.py prof.txt.
#   SHA=... ARM=A|N  (PROF default /var/tmp/$USER/cab-prof; PYSPY, JDK as below)
set -u
arm=$1 b=$2
. "$(dirname "$0")/../route-finish-ab/common.sh"
PROF=${PROF:-/var/tmp/$USER/cab-prof}
PYSPY=${PYSPY:-/var/tmp/$USER/prof/venv/bin/py-spy}
JDK=${JDK:-$HOME/.cache/kaebench/jdk-25}
ws=${KAEQ_SCRATCH:-$(mktemp -d "/var/tmp/$USER/cabp.XXXX")}
rf_env "$ws" "$b"; export APPTAINER_BIND="$APPTAINER_BIND,/var/tmp/$USER"
ulimit -v 40000000
rf_prepare "$ws" "$b" || exit 2
D=$PROF/$b.$arm; rm -rf "$D"; mkdir -p "$D/in" "$D/jfr" "$D/work"
in=$ws/w/tasks/$b/route/input
cp "$in"/board.kicad_pcb "$D/in/"; for e in kicad_pro kicad_dru; do [ -f "$in/board.$e" ] && cp "$in/board.$e" "$D/in/"; done
cat > "$D/fr" <<EOF
#!/bin/sh
exec $JDK/bin/java -XX:StartFlightRecording=filename=$D/jfr/fr-\$\$.jfr,settings=profile \$FREEROUTING_JAVA_OPTS -jar $(dirname "$(dirname "$FORK")")/lib/freerouting.jar "\$@"
EOF
chmod +x "$D/fr"
fp=$(python3 -c "import json;print(json.load(open('$CORPUS/boards/$b/row.json')).get('footprints') or 0)")
T=$(python3 -c "print(int(min(4*3600, 900*max(1.0, $fp/40)**0.5)))")
OP=$OPSRC/$b.operating.json
export NUMBA_CACHE_DIR=$ws/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$D/fr
cp -r "$NUMBA" "$ws/numba" 2>/dev/null
E=$KPY
LM="$E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@ --set operating=$OP"
FN="$E -m kae.route.cli finish @IN@ @BEST@ @OUT@ --time @TIME@ --input-drc @DRC@ --drc-s @DRC_S@ --set operating=$OP"
case "$arm" in
  A) export KAE_PAD_ENTRY=centre KAE_FR_PIN_ENTRIES=off; RF="--no-finish"; FIN=() ;;
  N) RF=""; FIN=(--finish "$FN") ;;
  *) echo "ARM: A or N" >&2; exit 2 ;;
esac
INNER="if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@ --set operating=$OP $RF; else $E -m kae.route.cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@ --set operating=$OP $RF; fi"
cd "$D/work"
t0=$(date +%s.%N)
"$PYSPY" record --subprocesses --nonblocking --idle -r 20 -f raw -o "$D/prof.txt" -- /usr/bin/time -v -o "$D/time.txt" \
  "$KPY" "$CODE/tools/kaeres/restart.py" --input "$D/in/board.kicad_pcb" --output "$D/out.kicad_pcb" --time "$T" --seed 0 \
  --parallel 4 --first-s 60 --scale-first --slack 1.15 --resume 0.5 --final "$LM" "${FIN[@]}" -- "$INNER" > "$D/log" 2>&1
rc=$?
t1=$(date +%s.%N)
echo "arm $arm board $b budget $T code ${SHA:0:12} rc $rc wall $(python3 -c "print(round($t1-$t0,1))") peak_kb $(grep -o 'Maximum resident set size (kbytes): [0-9]*' "$D/time.txt" | grep -o '[0-9]*$')" > "$D/meta"
for f in summary report; do cp "restarts/$f.json" "$D/" 2>/dev/null; done
exit $rc
