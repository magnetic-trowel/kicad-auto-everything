#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# finish_smoke.sh DIR [chain|finish|phys-TAG]
# DIR holds before.kicad_pcb (a routed board) with its .kicad_pro/.kicad_dru when it has them;
# INTENT_DIR (optional) holds <board>.operating.json (board = basename of DIR), the pads' and rails'
# currents for every pass in both arms.
#   chain:    today's three gated passes in a row: pad_reroute (rule D) -> chain_tails, taut ->
#             chain_taut, power_copper -> chain; reports chain_{tails,taut,pc}.json; seconds and
#             KiCad DRC runs per pass in chain.times.json; stats.chain*.json.
#   finish:   kae.route.finish (one journaled gate) -> finish.kicad_pcb, report finish.json;
#             stats.finish.json.
#   phys-TAG: physics of TAG.kicad_pcb (eval_intent.sh, the input's rules) -> DIR/phys/TAG.*
# Summary: tools/research/routing/finish_summary.py DIR...
set -eo pipefail
dir=$(cd "$1" && pwd) mode=${2:-finish} id=$(basename "$dir")
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
source ~/.cache/kaebench/env.sh; export APPTAINER_BIND=${KAE_WORK:-/var/tmp/$USER}
PY=${FINISH_PY:-python3}
op=(); [ -n "$INTENT_DIR" ] && [ -f "$INTENT_DIR/$id.operating.json" ] && op=(--operating "$INTENT_DIR/$id.operating.json")
proj() { for e in kicad_pro kicad_dru; do [ -f "$dir/before.$e" ] && cp "$dir/before.$e" "$dir/$1.$e"; done; true; }
drcs() { find "$1" -maxdepth 1 \( -name "in.drc.json" -o -name "out.*.json" \) 2>/dev/null | wc -l; }
now() { date +%s.%N; }
case "$mode" in
  chain)
    ( ulimit -v 40000000; export PYTHONPATH=$REPO/kae/src
      rm -rf "$dir"/chain-*-work
      proj chain_tails; proj chain_taut; proj chain
      t0=$(now)
      $PY -m kae.route.pad_reroute "$dir/before.kicad_pcb" "$dir/chain_tails.kicad_pcb" --workdir "$dir/chain-tails-work" \
        --report "$dir/chain_tails.json" "${op[@]}" > /dev/null
      t1=$(now)
      $PY -m kae.route.taut run "$dir/chain_tails.kicad_pcb" "$dir/chain_taut.kicad_pcb" --workdir "$dir/chain-taut-work" \
        --report "$dir/chain_taut.json" "${op[@]}" > /dev/null
      t2=$(now)
      $PY -m kae.route.power_copper "$dir/chain_taut.kicad_pcb" "$dir/chain.kicad_pcb" --workdir "$dir/chain-pc-work" \
        --report "$dir/chain_pc.json" "${op[@]}" > /dev/null
      t3=$(now)
      $PY -c "import json, sys; a = list(map(float, sys.argv[1:5])); d = list(map(int, sys.argv[5:8]))
print(json.dumps(dict(seconds=dict(tails=a[1]-a[0], taut=a[2]-a[1], power=a[3]-a[2], total=a[3]-a[0]),
                      drc_runs=dict(tails=d[0], taut=d[1], power=d[2], total=sum(d)))))" \
        "$t0" "$t1" "$t2" "$t3" "$(drcs "$dir/chain-tails-work")" "$(drcs "$dir/chain-taut-work")" \
        "$(drcs "$dir/chain-pc-work")" > "$dir/chain.times.json"
      for t in before chain_tails chain_taut chain; do
        [ -f "$dir/stats.$t.json" ] || $PY -m kae.route.taut stats "$dir/$t.kicad_pcb" > "$dir/stats.$t.json"; done
    ) > "$dir/chain.log" 2>&1
    find "$dir"/chain-*-work -name "*.kicad_pcb" -delete 2>/dev/null || true;;
  finish)
    ( ulimit -v 40000000; export PYTHONPATH=$REPO/kae/src
      rm -rf "$dir/finish-work"; proj finish
      $PY -m kae.route.finish "$dir/before.kicad_pcb" "$dir/finish.kicad_pcb" --workdir "$dir/finish-work" \
        --report "$dir/finish.json" "${op[@]}" > /dev/null
      [ -f "$dir/stats.before.json" ] || $PY -m kae.route.taut stats "$dir/before.kicad_pcb" > "$dir/stats.before.json"
      $PY -m kae.route.taut stats "$dir/finish.kicad_pcb" > "$dir/stats.finish.json"
    ) > "$dir/finish.log" 2>&1
    find "$dir/finish-work" -name "*.kicad_pcb" -delete 2>/dev/null || true;;
  phys-*)
    t=${mode#phys-}
    INTENT_DIR=${INTENT_DIR:?set INTENT_DIR}
    KAE_RULES_FROM=$dir/before.kicad_pcb bash "$REPO/tools/research/physics/eval_intent.sh" "$dir/$t.kicad_pcb" \
      "$INTENT_DIR/$id.operating.json" "$INTENT_DIR/$id.intent.json" "$dir/phys" "$t";;
  *) echo "unknown mode $mode" >&2; exit 2;;
esac
