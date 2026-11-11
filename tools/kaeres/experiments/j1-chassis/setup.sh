#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# J1: the chassis ablation ladder (see PLAN.md, written before any run). One commit for all arms; only the
# inner kae.joint.cli flags differ. Same restart wrapper for every arm (restart --resume 0.5 --final
# lastmile, no --screen). Budget 900 s x sqrt(fp/40), as every merit joint run.
#
#   SHA=<pushed commit with the loop reports> tools/kaeres/experiments/j1-chassis/setup.sh
set -euo pipefail
cd "$(dirname "$0")/../../../.."
K="python3 tools/kaeres/kaeres.py"
SHA=${SHA:?commit}
S7=${SHA:0:7}
KAE=(--code kae=.@$SHA)
H=(--harness $SHA)
KH='$HOME/.cache/kaebench'
FORK="\$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting"
NUMBA=numba-kae-j1-$S7
CP="cp -r $KH/$NUMBA numba 2>/dev/null;"
E="env NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 KAE_WORKERS=1 KAE_BRIDGE_FREEROUTING=$FORK {py:kae}"
FIN="$CP $E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
RES="if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else"
WRAP="{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s 300 --scale-first --slack 1.15 --resume 0.5 --final '$FIN' --check-placement --"
add() {  # NAME DESCRIPTION JOINT_FLAGS [METHOD ADD OPTIONS...]
  local name=$1 desc=$2 flags=$3; shift 3
  $K method add "$name" --kind joint-fixed --description "$desc; restart portfolio (tools/kaeres/restart.py) --resume 0.5 --final at $S7" \
    --command "$WRAP '$CP $RES $E -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ $flags; fi'" \
    --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=4 "${KAE[@]}" "${H[@]}" "$@"
}
if [ -n "${SCREEN:-}" ]; then   # J11 (PLAN.md Addendum 2): arm (d) replicated, against arm (d) with --screen
  add "kae j1 joint twin $S7 (restarts)" "J11 control: arm d's recipe, replicated so it runs side by side" "" --param replicate=j1-screen
  WRAP="${WRAP/--resume 0.5/--resume 0.5 --screen}"
  add "kae j1 joint screen $S7 (restarts)" "J11: arm d with restart --screen (successive halving replaces the --resume schedule)" ""
  exit 0
fi
add "kae j1 staged $S7 (restarts)"            "arm a: kae.joint.cli --max-iters 0 --no-modules (no module stage, no finish)" "--max-iters 0 --no-modules"
add "kae j1 modules $S7 (restarts)"           "arm b: kae.joint.cli --max-iters 0 (staged + module stage, no finish)"        "--max-iters 0"
add "kae j1 modules finish $S7 (restarts)"    "arm c: kae.joint.cli --max-iters 0 --set finish=1 (staged + modules + finish, no windows)" "--max-iters 0 --set finish=1"
add "kae j1 joint $S7 (restarts)"             "arm d: kae.joint.cli defaults (staged + modules + windows + finish)"          ""
# Experiments: see PLAN.md (j1-chassis-smoke, then j1-chassis; numba cache warmed with warm-numba.sh at $SHA).
