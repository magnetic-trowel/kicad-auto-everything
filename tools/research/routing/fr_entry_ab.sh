#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# fr_entry_ab.sh BOARDDIR ARM[-fr] SEED BUDGET_S FORK
# One arm of the native rule D entry A/B (kae.route.fr_entry + the fork's router.kae_pin_entries):
# `kae.route.cli route` of BOARDDIR/input.kicad_pcb (with its project files) with the Freerouting
# build FORK, KAE_FR_PIN_ENTRIES=on|off (ARM; "rails" also writes rail classes), then
# kae.route.pad_reroute on the result. ARM-fr: Freerouting's import alone (no repair rounds, no last
# mile, no diagnosis), to see the router's own ends. Writes BOARDDIR/ARM/{routed,rr}.kicad_pcb, route.json,
# rr.json, and score.json: per stage, KiCad DRC of the re-opened board (errors by type,
# unconnected) and pad-entry counts (pad_trim.stats: oblique, acute, on the centre line,
# overhanging, track length), plus run times and the fork's tail counts.
set -eo pipefail
dir=$(cd "$1" && pwd) arm=$2 seed=${3:-0} budget=${4:-300} fork=$5
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
PY=${AB_PY:?python with the kae dependencies}
source ~/.cache/kaebench/env.sh; export APPTAINER_BIND=${KAE_WORK:-/var/tmp/$USER}
out=$dir/$arm; rm -rf "$out"; mkdir -p "$out"
export PYTHONPATH=$REPO/kae/src:$REPO/bench/src KAE_BRIDGE_FREEROUTING=$fork OMP_NUM_THREADS=1 KAE_WORKERS=1
extra=()
case $arm in *-fr) extra=(--no-repair --no-last-mile --no-blocked);; esac
case ${arm%-fr} in
  on) export KAE_FR_PIN_ENTRIES=on KAE_FR_RAILS=off;;
  rails) export KAE_FR_PIN_ENTRIES=on KAE_FR_RAILS=on;;
  off) export KAE_FR_PIN_ENTRIES=off KAE_FR_RAILS=off;;
  *) echo "unknown arm $arm" >&2; exit 2;;
esac
ulimit -v 40000000
for t in routed rr; do for e in kicad_pro kicad_dru; do
  [ -f "$dir/input.$e" ] && cp "$dir/input.$e" "$out/$t.$e"; done; done
t0=$(date +%s.%N)
$PY -m kae.route.cli route "$dir/input.kicad_pcb" "$out/routed.kicad_pcb" --seed "$seed" --time "$budget" \
  --workdir "$out/work" --report "$out/route.json" "${extra[@]}" > "$out/route.log" 2>&1
t1=$(date +%s.%N)
$PY -m kae.route.pad_reroute "$out/routed.kicad_pcb" "$out/rr.kicad_pcb" --workdir "$out/rr-work" \
  --report "$out/rr.json" > "$out/rr.log" 2>&1 || cp "$out/routed.kicad_pcb" "$out/rr.kicad_pcb"
t2=$(date +%s.%N)
$PY - "$dir" "$out" "$t0" "$t1" "$t2" <<'PYEOF'
import json, sys
from pathlib import Path
from kae.route import drc, pad_trim as T
d, out, t0, t1, t2 = Path(sys.argv[1]), Path(sys.argv[2]), *map(float, sys.argv[3:6])
info = T._info(d / "input.kicad_pcb")
res = dict(route_s=round(t1 - t0, 1), reroute_s=round(t2 - t1, 1))
rep = json.loads((out / "route.json").read_text())
res["fork"] = ((rep.get("router") or {}).get("report") or {}).get("pin_entries")
res["fr_entry"] = (rep.get("translate") or {}).get("fr_entry")
for t in ("routed", "rr"):
    b = out / f"{t}.kicad_pcb"
    s = drc.summary(drc.run(b, out / f"{t}.drc.json", timeout=3600))
    res[t] = dict(drc=s, entries=T.stats(b.read_text(encoding="utf-8"), info))
(out / "score.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res))
PYEOF
find "$out/work" "$out/rr-work" -name "*.kicad_pcb" -delete 2>/dev/null || true
