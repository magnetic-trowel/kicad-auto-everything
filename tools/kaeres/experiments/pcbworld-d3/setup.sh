#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# PCBWorld D3-A/B location experiment (PLAN.md in this folder): registers the methods and creates the
# experiments. Submits nothing. Needs the PCBWorld corpus built by tools/research/pcbworld/d3_corpus.py
# (KAE_CORPUS) and a checkout of kicad-auto-everything at SHA (the pushed main commit the methods run).
#
#   KAE_CORPUS=<corpus> DRY=1 SHA=<sha> bash setup.sh   # print every method add / exp create
#   KAE_CORPUS=<corpus> SHA=<sha> bash setup.sh         # register (store writes only; no kaeq job)
#
# Arms (route task, PCBWorld's boards and rules, KiCad 10.0.7 scoring):
#   bridge: kae.route.cli under restart.py at its defaults, the Stage 2 bridge recipe without operating
#           facts (none exist for these boards), counted-work budgets, Freerouting fork d137fd1 named
#           explicitly (KAE_BRIDGE_FREEROUTING and KAE_FREEROUTING) in the wrapper and every inner command.
#   pnr:    tools/research/pnr methods.py:route_only at SHA, one attempt per seed, wall-clock budget.
#   fork:   the registered "s2 fr-fork d137fd1 mp10" (kaebench adapter, -mp 10 = PCBWorld's control setting),
#           one run per board (deterministic), in its own experiment with k = 1.
# Stock Freerouting 2.5.0 is not run (user, 2026-11-11).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
SHA=${SHA:?pushed main commit}
SHA=$(git rev-parse "$SHA")
S7=${SHA:0:7}
: "${KAE_CORPUS:?the PCBWorld corpus (d3_corpus.py --out)}"
K=${K:-python3 tools/kaeres/kaeres.py}
run() { if [ -n "${DRY:-}" ]; then printf '%q ' "$@"; echo; echo; else "$@"; fi; }
madd() { run $K method add "$@"; }

KH='$HOME/.cache/kaebench'                     # expanded at run time, in the sandbox
FORK="$KH/kae-freerouting-fork-d137fd1/bin/freerouting"
FRENV="KAE_BRIDGE_FREEROUTING=$FORK KAE_FREEROUTING=$FORK"
WENV="env KAE_BUDGET=work PYTHONHASHSEED=0 KAE_WORKERS=1"
NUMBA=numba-s2-$S7                              # the Stage 2 warm cache when present; cold compile otherwise
CP="cp -r $KH/$NUMBA numba 2>/dev/null;"
E="$WENV NUMBA_CACHE_DIR=\$PWD/numba OMP_NUM_THREADS=1 $FRENV {py:kae}"
CODE=(--code "kae=.@$SHA" --harness "$SHA")

# ---------------------------------------------------------------- kae bridge (Stage 2's BR minus operating facts)
LM="$CP $E -m kae.route.cli lastmile @IN@ @BEST@ @OUT@ --seed @SEED@ --time @TIME@"
RINNER="$CP if [ \"\$KAE_RESUME\" = 1 ]; then $E -m kae.route.cli route @BEST@ @OUT@ --seed @SEED@ --time @TIME@; else $E -m kae.route.cli route @IN@ @OUT@ --seed @SEED@ --time @TIME@; fi"
WRAP="$WENV $FRENV {py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time \$(( {timeout} / 4 )) --seed {attempt} --parallel 4 --first-s 60 --scale-first --slack 1.15 --resume 0.5 --final '$LM' --"
BR="d3 bridge $S7 (restarts)"
madd "$BR" --kind route --description "kae bridge at its defaults: kae.route.cli at $S7 under restart.py (parallel 4, first-s 60, scale-first, slack 1.15, resume 0.5, --final last mile), no operating facts, counted-work budgets (nominal 900 s x sqrt(fp/40), ceiling 4x), Freerouting fork d137fd1" \
  --command "$WRAP '$RINNER'" --param timeout_s=3600 --param timeout_scale=sqrt-fp40 --param timeout_cap_s=57600 --param parallel=4 "${CODE[@]}"

# ---------------------------------------------------------------- pnr route_only (one attempt per seed)
PNRENV="env VIRTUAL_ENV={venv:kae} PYTHONPATH={code:pnr}/tools/research/collapse_joint:{code:pnr}/tools/research/xf_minplus KAE_KICAD_PYTHON={code:pnr}/tools/research/xf_common/kicad-python NUMBA_CACHE_DIR=$KH/numba-anytfast NUMBA_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 $FRENV"
PN="d3 pnr route_only $S7 (restarts)"
madd "$PN" --kind route --description "pnr route_only (tools/research/pnr at $S7) under restart.py, one attempt (max-attempts 1), wall-clock budget 900 s x sqrt(fp/40); pnr calls no Freerouting (the fork is named anyway)" \
  --command "$WENV $FRENV {py:kae} {code:harness}/tools/kaeres/restart.py --input {input} --output {output} --time {timeout} --seed {attempt} --parallel 1 --first-s 100000 --scale-first --slack 100 --max-attempts 1 -- '$PNRENV sh {code:pnr}/tools/research/xf_common/xf_run.sh {code:pnr}/tools/research/pnr/methods.py:route_only @IN@ @OUT@ @TIME@ @SEED@'" \
  --param timeout_s=900 --param timeout_scale=sqrt-fp40 --param parallel=1 --code "pnr=.@$SHA" "${CODE[@]}"

FC=${FC:-b07f426d7c2f}                          # "s2 fr-fork d137fd1 mp10", registered by Stage 2 at harness 3a482ed

# ---------------------------------------------------------------- experiments (all created before any run)
X=(--harness "$SHA" --kae "$SHA")
D="PCBWorld D3 location at $S7 (KiCad 10.0.7, PCBWorld's boards and rules); plan tools/kaeres/experiments/pcbworld-d3/PLAN.md"
run $K exp create pcbworld-d3-smoke --boards "@$here/boards-smoke.txt" --method "$BR" --method "$PN" --method "$FC" "${X[@]}" \
  --description "smoke of the $D: 2 D3-C boards (outside the measured splits), k=1"
run $K exp create pcbworld-d3 --boards "@$here/boards.txt" --attempts 5 --method "$BR" --method "$PN" "${X[@]}" \
  --description "$D: D3-A (99) + D3-B (10), kae bridge and pnr, k=5 (PCBWorld's @5)"
run $K exp create pcbworld-d3-fr --boards "@$here/boards.txt" --method "$FC" "${X[@]}" \
  --description "$D: D3-A (99) + D3-B (10), Freerouting fork d137fd1 -mp 10, one run per board (deterministic)"
echo "registered; nothing submitted"
