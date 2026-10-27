#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# usage: rundev6.sh SUITE TAG-SUFFIX BUDGET JOBS fn[:opts] ...   (run sequentially)
REPO="${KAE_REPO:-$(cd "$(dirname "$0")" && git rev-parse --show-toplevel)}"
cd $REPO
suite=$1; sfx=$2; b=$3; j=$4; shift 4
for spec in "$@"; do
  fn=${spec%%:*}; opts=""
  [ "$fn" != "$spec" ] && for o in $(echo "${spec#*:}" | tr ',' ' '); do opts="$opts --opt $o"; done
  name="mcts-$fn-$sfx"
  kae-work/runext.sh $REPO/tools/research/pnr_mcts/mcts.py:$fn $name $b $suite $j $opts
done
