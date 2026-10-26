#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Registers every placement and routing method that had merit (or partial merit) in the
# earlier experiments, as tested there, for one run each on a shared board sample.
# Sources: docs/ideas/original/scorecard.md (xf-experiments, keen-wright), bench/results/
# (vigilant-mayer), docs/topics/placement/autoplace-experiments-2026-10.md (autoplace-experiments).
set -euo pipefail
cd "$(dirname "$0")/../../.."
K="python3 tools/kaeres/kaeres.py"
KAE=(--code kae=.@origin/claude/vigilant-mayer-i91rrr)
XF=(--code pnr=.@origin/xf-experiments)
KW=(--code pnr=.@origin/claude/keen-wright-mlkjv6)
T=(--param timeout_s=900)
add() { $K method add "$@" "${T[@]}"; }

# kae (physics-first branch): routers on the human placement, and its place-and-route loops
add "kae bridge" --description "kae.route.cli: Freerouting fork bridge + last mile (bench/results/2026-10-24-last-mile-ab)" \
  --command "{py:kae} -m kae.route.cli route {input} {output} --seed {attempt} --time {timeout}" "${KAE[@]}"
add "kae portfolio" --description "kae.route.portfolio: waves of 4 seeded bridge attempts (bench/results/2026-10-24-portfolio-ab)" \
  --command "{py:kae} -m kae.route.portfolio route {input} {output} --seed {attempt} --time {timeout} --parallel 4" "${KAE[@]}"
add "kae critical+bridge" --description "kae.route.critical_cli: critical copper first, then the bridge (physics edge; 2026-10-24-last-mile-ab)" \
  --command "{py:kae} -m kae.route.critical_cli route {input} {output} --seed {attempt} --time {timeout}" "${KAE[@]}"
add "kae staged" --kind joint --description "kae.joint.cli --no-modules: kae place, then the bridge (2026-10-24-joint-ab)" \
  --command "{py:kae} -m kae.joint.cli run {input} {output} --seed {attempt} --time {timeout} --no-modules" "${KAE[@]}"
add "kae joint loop" --kind joint --description "kae.joint.cli: module stage, windows with last mile, finishing bridge (2026-10-24-joint-ab)" \
  --command "{py:kae} -m kae.joint.cli run {input} {output} --seed {attempt} --time {timeout}" "${KAE[@]}"

# pnr engine (joint place-and-route research), 120 CPU-s per attempt as in the scorecard.
# xf_run.sh copies a warm numba cache, when there is one, into the attempt's work dir.
pnr() {  # NAME KIND CODE-ARRAY-NAME SPEC [run.py options...]
  local name=$1 kind=$2 code=$3 spec=$4; shift 4
  local -n c=$code
  add "$name" --kind "$kind" --description "pnr engine $spec, 120 CPU-s (docs/ideas/original/scorecard.md)" \
    --command "env VIRTUAL_ENV={venv:kae} PYTHONPATH={code:pnr}/tools/research/collapse_joint:{code:pnr}/tools/research/xf_minplus KAE_KICAD_PYTHON={code:pnr}/tools/research/xf_common/kicad-python NUMBA_CACHE_DIR=\$HOME/.cache/kaebench/numba-$code NUMBA_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 sh {code:pnr}/tools/research/xf_common/xf_run.sh {code:pnr}/tools/research/$spec {input} {output} 120 {attempt} $*" \
    "${KAE[@]}" "${c[@]}"
}
R=tools/research
pnr "pnr route_only" route XF pnr/methods.py:route_only
pnr "pnr seq" joint XF pnr/methods.py:seq                      # control: HPWL place, then route
pnr "pnr seq_phys" joint XF pnr/methods_phys.py:seq_phys
pnr "pnr anneal_phys" joint XF pnr/methods_phys.py:anneal_phys
pnr "pnr repair" joint XF pnr/methods.py:repair
pnr "pnr negotiate" joint XF pnr/methods.py:negotiate
pnr "pnr beam" joint XF pnr_mcts/mcts.py:beam
pnr "pnr combo" joint XF pnr/methods_combo.py:combo
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

# autoplace: router-in-the-loop repair placer, scored with the Freerouting probe
add "autoplace sa-loop" --kind place --param probe=freerouting \
  --description "methods/autoplace place.py --algo sa-loop (docs/topics/placement/autoplace-experiments-2026-10.md)" \
  --command "env PYTHONPATH={code:ap}/bench/src {py:kae} {code:ap}/methods/autoplace/place.py --algo sa-loop --input {input} --output {output} --workdir {workdir} --attempt {attempt} --timeout {timeout}" \
  "${KAE[@]}" --code ap=.@origin/autoplace-experiments
