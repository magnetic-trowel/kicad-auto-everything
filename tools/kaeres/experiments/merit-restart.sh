#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# The merit-500 methods (merit-500.sh) and both Freerouting baselines, each run the same fair
# way: tools/kaeres/restart.py wraps the method in a restart portfolio (4 differently seeded
# attempts at a time, 60 s first wave, doubling; KiCad DRC picks the best, the first clean one
# stops the run), with a budget that grows with the board: 900 s x sqrt(footprints / 40),
# at least 900 s, at most 4 h. restart.py also measures the work (CPU over all processes,
# restarts, peak memory). kae portfolio is left out: it is kae bridge in this same wrapper.
#   HARNESS=<commit> keeps an earlier harness (same method ids).
set -euo pipefail
cd "$(dirname "$0")/../../.."
K="python3 tools/kaeres/kaeres.py"
KAE=(--code kae=.@origin/claude/vigilant-mayer-i91rrr)
XF=(--code pnr=.@origin/xf-experiments)
KW=(--code pnr=.@origin/claude/keen-wright-mlkjv6)
P=(--param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=4)
rs() { echo "{py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 4 --first-s 60 --slack ${SLACK:-1} --"; }
add() {  # NAME KIND DESCRIPTION INNER-COMMAND CODE-ARGS...
  local name=$1 kind=$2 desc=$3 inner=$4; shift 4
  $K method add "$name" --kind "$kind" --description "$desc; restart portfolio (tools/kaeres/restart.py)" \
    --command "$(rs) $inner" "${P[@]}" "${KAE[@]}" "$@" ${HARNESS:+--harness $HARNESS}
}

add "freerouting 2.5.0 (restarts)" route "Freerouting v2.5.0 release through kaebench's adapter" \
  "env PYTHONPATH={code:harness}/bench/src {py:kae} {code:harness}/tools/kaeres/fr_attempt.py --binary $HOME/.cache/kaebench/freerouting-2.5.0-linux-x64/bin/freerouting --input @IN@ --output @OUT@ --seed @SEED@ --time @TIME@"
add "fr-fork master (restarts)" route "magnetic-trowel/freerouting master 06d2686 through kaebench's adapter" \
  "env PYTHONPATH={code:harness}/bench/src {py:kae} {code:harness}/tools/kaeres/fr_attempt.py --binary $HOME/.cache/kaebench/kae-freerouting-fork-06d2686/bin/freerouting --input @IN@ --output @OUT@ --seed @SEED@ --time @TIME@"

add "kae bridge (restarts)" route "kae.route.cli: bridge + last mile" \
  "{py:kae} -m kae.route.cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@"
add "kae critical+bridge (restarts)" route "kae.route.critical_cli: critical copper, then the bridge" \
  "{py:kae} -m kae.route.critical_cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@"
add "kae staged (restarts)" joint "kae.joint.cli --no-modules: kae place, then the bridge" \
  "{py:kae} -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@ --no-modules"
add "kae joint loop (restarts)" joint "kae.joint.cli: module stage, windows with last mile, finishing bridge" \
  "{py:kae} -m kae.joint.cli run @IN@ @OUT@ --seed @SEED@ --time @TIME@"

pnr() {  # NAME KIND CODE-ARRAY-NAME SPEC [run.py options...]; budget = the attempt's wave budget (CPU-s)
  local name=$1 kind=$2 code=$3 spec=$4; shift 4
  local -n c=$code
  SLACK=3 add "$name (restarts)" "$kind" "pnr engine $spec (docs/ideas/original/scorecard.md)" \
    "env VIRTUAL_ENV={venv:kae} PYTHONPATH={code:pnr}/tools/research/collapse_joint:{code:pnr}/tools/research/xf_minplus KAE_KICAD_PYTHON={code:pnr}/tools/research/xf_common/kicad-python NUMBA_CACHE_DIR=\$HOME/.cache/kaebench/numba-$code NUMBA_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 sh {code:pnr}/tools/research/xf_common/xf_run.sh {code:pnr}/tools/research/$spec @IN@ @OUT@ @TIME@ @SEED@ $*" \
    "${c[@]}"
}
pnr "pnr route_only" route XF pnr/methods.py:route_only
pnr "pnr seq" joint XF pnr/methods.py:seq                      # control: HPWL place, then route
pnr "pnr seq_phys" joint XF pnr/methods_phys.py:seq_phys
pnr "pnr anneal_phys" joint XF pnr/methods_phys.py:anneal_phys
pnr "pnr repair" joint XF pnr/methods.py:repair
pnr "pnr negotiate" joint XF pnr/methods.py:negotiate
pnr "pnr beam" joint XF pnr_mcts/mcts.py:beam
pnr "pnr combo" joint XF pnr/methods_combo.py:combo
pnr "pnr combo_full" joint XF pnr/methods_combo.py:combo_full
pnr "pnr seq_collapse" joint XF collapse_cplace/methods_cplace.py:seq_collapse
pnr "pnr grad_phys" joint XF pnr_grad/grad.py:grad_phys --opt post=phys
pnr "pnr jc" joint XF collapse_joint/jc.py:jc
pnr "pnr jc_lv" joint XF collapse_joint/jc.py:jc_lv
pnr "pnr jc_full" joint XF collapse_joint/jc.py:jc_full
pnr "pnr xf_h minplus" joint XF xf_minplus/minplus.py:xf_h
pnr "pnr pjc2 pour maps" joint XF xf_pour/pjc.py:pjc2
pnr "pnr hjc_press" joint XF harmonic/hjc.py:hjc_press
pnr "pnr qd" joint XF qd_archive/qd.py:qd
pnr "pnr jc2_fix" joint KW collapse_joint/jc2.py:jc2_fix
pnr "pnr jc2_fixmp_lv" joint KW collapse_joint/jc2.py:jc2_fixmp_lv

add "autoplace sa-loop (restarts)" place "methods/autoplace place.py --algo sa-loop" \
  "env PYTHONPATH={code:ap}/bench/src {py:kae} {code:ap}/methods/autoplace/place.py --algo sa-loop --input @IN@ --output @OUT@ --workdir \$PWD --attempt @SEED@ --seed @SEED@ --timeout @TIME@" \
  --code ap=.@origin/autoplace-experiments --param probe=freerouting
