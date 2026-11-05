# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Shared settings of the route-finish-ab job scripts (sourced). SHA must be set: the route-finish commit
# whose frozen checkout and venvs kaeres made at `exp create` (~/kae-baselines/code/...@SHA12).
: "${SHA:?commit of the experiment harness and kae}"
STORE=${KAE_RESULTS:-$HOME/kae-baselines}
CORPUS=${KAE_CORPUS:-$HOME/kae-boards}
CODE=$STORE/code/kicad-auto-everything@${SHA:0:12}
KB=$CODE.venv/bin/kaebench
KPY=$CODE.venv-kae/bin/python
OUT=${OUT:-/var/tmp/$USER/rf-ab}
OPSRC=${OPSRC:-/var/tmp/$USER/intent-213/compiled-6329e71}
NUMBA=$HOME/.cache/kaebench/numba-rf-${SHA:0:7}
FORK=$HOME/.cache/kaebench/kae-freerouting-fork-2e1125a/bin/freerouting
A0_RUN=kae-bridge-main-final-restarts.286c2335.a0      # merge3-ab's arm, e9889fd
[ -x "$KB" ] && [ -x "$KPY" ] || { echo "no frozen code for ${SHA:0:12}: run route-finish-ab.sh (kaeres exp create) first" >&2; exit 2; }
. "$HOME/.cache/kaebench/env.sh"

# rf_run_dir BOARD ID8|A0: the stored kaeres run folder of a method on a board (attempt 0)
rf_run_dir() {
  local b=$1 m=$2 d
  if [ "$m" = A0 ]; then d=$STORE/boards/$b/runs/$A0_RUN
  else d=$(ls -d "$STORE"/boards/"$b"/runs/*."${m:0:8}".a0 2>/dev/null | head -1); fi
  [ -n "$d" ] && [ -f "$d/output.kicad_pcb.gz" ] && echo "$d"
}

# rf_env WS BOARD: the job environment kaeres gives its jobs (KiCad at 2 threads, DRC timeout by size)
rf_env() {
  local ws=$1 b=$2 mb
  mb=$(( $(stat -c %s "$CORPUS/boards/$b/board.kicad_pcb") / 1048576 ))
  export APPTAINER_BIND="$ws,$(readlink -f "$CORPUS"),$STORE,/var/tmp/$USER"
  export KICAD_CONFIG_HOME=$STORE/kicad-config/threads-2
  export KAE_DRC_TIMEOUT=$([ "$mb" -lt 20 ] && echo 900 || echo 3600)
  unset VIRTUAL_ENV
}

# rf_prepare WS BOARD: the route task in WS/w/tasks/BOARD (kaebench prepare-dir, as a kaeres job)
rf_prepare() {
  local ws=$1 b=$2 p
  mkdir -p "$ws/src/$b"
  for p in "$CORPUS/boards/$b"/board.* "$CORPUS/boards/$b"/row.json; do
    [ -e "$p" ] && ln -sf "$p" "$ws/src/$b/$(basename "$p")"
  done
  [ -f "$ws/w/tasks/$b/task.json" ] || "$KB" --workdir "$ws/w" prepare-dir --dir "$ws/src" --board-glob board.kicad_pcb \
    --only "$b" --kinds route -j 1 > "$ws/prepare.log" 2>&1
  [ -f "$ws/w/tasks/$b/task.json" ] || { tail -30 "$ws/prepare.log" >&2; return 1; }
}
