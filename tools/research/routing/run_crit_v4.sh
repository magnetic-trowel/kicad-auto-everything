#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Critical-net routing A/B, fourth round, k=3 on splits A+B and on six split-C boards with
# switching cells, at one commit and one Freerouting build:
#   kae-fr       the bridge alone, inner plane layers open to traces (--planes allow, as KiCad
#                exports its layer types)
#   kae-frp      the bridge alone, inner planes priced at 4x a routing layer (--planes cost: a
#                board.rules file beside the DSN gives Freerouting per-layer trace costs)
#   kae-critc    critical copper + bridge with the pad and island joins (the defaults since
#                crit-v3's c arm), --planes allow
#   kae-critcp   the same with --planes cost (the default)
# then kaebench reports against kae-fr, per-module physics (crit_compare) and DC/HF passports
# and critics (RET-COV, PLANE-PERF) against the human boards (suite_physics).
#
# Run from the repository root at the commit to test:
#   W=<workdir with tasks/> J=16 KAE_SANDBOX_RO="<extra read-only paths>" \
#     tmux new -d -s crit 'bash tools/research/routing/run_crit_v4.sh > <log> 2>&1'
# W defaults to kae-work-v2; K (default 3) sets the attempts. Arms run one after another so they
# see the same host load. Freerouting peaks near 3.6 GB per attempt, so J=16 needs about 60 GB.
set -u
W=${W:-kae-work-v2}
case $W in /*) ;; *) W=$PWD/$W ;; esac
J=${J:-16}
K=${K:-3}
V=${V:-v4}
# per-attempt budgets (s): T_AB for splits A+B, T_C for the split-C boards (default 4x the v3 budgets
# of 600 and 900 s; the 10x sweep sets T_AB=6000 T_C=9000); change V with them
T_AB=${T_AB:-2400}
T_C=${T_C:-3600}
PY=$PWD/kae/.venv/bin/python
C=$W/code/kae-crit-$(git rev-parse --short HEAD)
RO=(--sandbox-ro "$C")
for p in ${KAE_SANDBOX_RO:-}; do RO+=(--sandbox-ro "$p"); done
NOISECARD=$(ls "$W"/tasks/pcbcorpus-tcsullivan-noisecard-noisecard/route/input/*.kicad_pcb | head -1)
if [ ! -d "$C/kae" ]; then
  mkdir -p "$C/.numba_cache" && cp -r kae/src/kae "$C/kae"
  mkdir -p "$W/tmp/kae-crit-warm"
  env PYTHONPATH="$C" NUMBA_CACHE_DIR="$C/.numba_cache" OMP_NUM_THREADS=1 "$PY" -m kae.route.critical_cli route \
    "$NOISECARD" "$W/tmp/kae-crit-warm/board.kicad_pcb" --no-bridge > "$W/tmp/kae-crit-warm/log" 2>&1 \
    || { echo "pre-warm failed"; tail -20 "$W/tmp/kae-crit-warm/log"; exit 1; }
fi
printf '%s\n' pcbcorpus-brenocq-bldc-motor-bldcm-power \
  pcbcorpus-caffeinated-labs-caffeinated-aftonsparv-caffeinated-aftonsparv libresolar-bms-c1-bms-c1 \
  pcbcorpus-azoninc-doorman-doorman pcbcorpus-waterloo-rocketry-canhw-processor pcbcorpus-justbuchanan-oasis-pcb \
  > "$W/suite-c6.txt"
for t in "$W"/tasks/*/; do
  t=$(basename "$t")
  "$PY" -c "import json,sys; sys.exit(0 if json.load(open('$W/tasks/$t/task.json')).get('split') in ('A','B') else 1)" \
    && echo "$t"
done > "$W/suite-ab.txt"
source bench/.venv/bin/activate
ENVP="env PYTHONPATH=$C NUMBA_CACHE_DIR=$C/.numba_cache OMP_NUM_THREADS=1 $PY -m"
run() {
  local name=$1 adapter=$2 mod=$3 t=$4 k=$5 extra=$6
  shift 6
  echo "$(date +%T) start $name"
  kaebench --workdir "$W" run --adapter "$adapter" --kinds route -k "$k" --timeout "$t" -j "$J" "$@" --name "$name" \
    "${RO[@]}" --command "$ENVP $mod route {input} {output} --seed {attempt} --time {timeout} $extra" \
    > "$W/$name.log" 2>&1
  echo "$(date +%T) done $name"
}
FR=kae-fr-$V; FRP=kae-frp-$V; CC=kae-critc-$V; CCP=kae-critcp-$V
for s in ab c6; do
  t=$T_AB; [ $s = c6 ] && t=$T_C
  run $FR-$s  kae-fr   kae.route.cli          $t "$K" "--planes allow" --only @"$W/suite-$s.txt"
  run $FRP-$s kae-fr   kae.route.cli          $t "$K" "--planes cost"  --only @"$W/suite-$s.txt"
  run $CC-$s  kae-crit kae.route.critical_cli $t "$K" "--planes allow" --only @"$W/suite-$s.txt"
  run $CCP-$s kae-crit kae.route.critical_cli $t "$K" "--planes cost"  --only @"$W/suite-$s.txt"
done
for s in ab c6; do
  for n in $FRP $CC $CCP; do
    kaebench report "$W/results/$n-$s" "$W/results/$FR-$s" > "$W/report-$n-$s.md"
  done
  "$PY" tools/research/physics/crit_compare.py --tasks "$W/tasks" --out "$W/physics/crit-$V-$s" -j "$J" \
    --arm bridge="$W/results/$FR-$s/kae-fr" --arm bridge_planes="$W/results/$FRP-$s/kae-fr" \
    --arm critc="$W/results/$CC-$s/kae-crit" --arm critc_planes="$W/results/$CCP-$s/kae-crit" \
    > "$W/physics-crit-$V-$s.log" 2>&1
  [ -d "$W/physics/human-$s" ] || "$PY" tools/research/physics/suite_physics.py --tasks "$W/tasks" \
    --suite "$W/suite-$s.txt" --out "$W/physics/human-$s" -j "$J" --timeout 600 > "$W/physics-human-$s.log" 2>&1
  for r in $FR-$s:kae-fr $FRP-$s:kae-fr $CC-$s:kae-crit $CCP-$s:kae-crit; do
    n=${r%%:*}; a=${r##*:}
    "$PY" tools/research/physics/suite_physics.py --tasks "$W/tasks" --out "$W/physics/$n" --label "$n" -j "$J" \
      --timeout 600 --boards-glob "$W/results/$n/$a/route/*/attempt-0/score/board.kicad_pcb" \
      --compare-to "$W/physics/human-$s" > "$W/physics-$n.log" 2>&1
  done
done
echo "$(date +%T) all done"
