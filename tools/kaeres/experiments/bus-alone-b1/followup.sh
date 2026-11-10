#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Hourly follow-up for bus-alone-b1: once the bus-alone runs are in, queue their views; once every view is made, write
# the analysis (WORK/out/SUMMARY.md, buses.csv). Idempotent. Usage: followup.sh WORK_DIR
set -u
export PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=$1
exp_left=$(kaeq status --owner exp-${EXP:-bus-alone-b1} | grep "^exp-${EXP:-bus-alone-b1}:" | grep -oE '(queued|running)=[0-9]+' | cut -d= -f2 | paste -sd+ | bc)
view_left=$(kaeq status --owner busview-${EXP:-bus-alone-b1} | grep '^busview' | grep -oE '(queued|running)=[0-9]+' | cut -d= -f2 | paste -sd+ | bc)
echo "$(date -Is) experiment jobs left: ${exp_left:-0}, view jobs left: ${view_left:-0}"
if [ "${exp_left:-0}" = 0 ] && [ ! -e "$WORK/.views-submitted" ]; then
  python3 "$HERE/submit_views.py" "${EXP:-bus-alone-b1}" "$WORK" --alone-method "${ALONE:-d0dd04f102a8}" && kaeq prio 7 --owner "busview-${EXP:-bus-alone-b1}" >/dev/null && touch "$WORK/.views-submitted"
  exit 0
fi
if [ -e "$WORK/.views-submitted" ] && [ "${view_left:-0}" = 0 ]; then
  python3 "$HERE/submit_views.py" "${EXP:-bus-alone-b1}" "$WORK" --alone-method "${ALONE:-d0dd04f102a8}" --dry-run | grep -q ', 0 views to make' || { python3 "$HERE/submit_views.py" "${EXP:-bus-alone-b1}" "$WORK" --alone-method "${ALONE:-d0dd04f102a8}"; kaeq prio 7 --owner "busview-${EXP:-bus-alone-b1}" >/dev/null; exit 0; }
  cat "$WORK"/runs-*.csv > "$WORK/runs.csv"
  python3 "$HERE/analyze.py" "$WORK/busnets" "$WORK/views" "$WORK/runs.csv" /var/tmp/eriks/board-tags/suites "$WORK/out" > "$WORK/analyze.log" 2>&1 && touch "$WORK/.done"
fi
