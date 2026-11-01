#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Put `kaeq` on PATH (~/.local/bin) and report which isolation features work here.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p ~/.local/bin
# a stable copy: the daemon must not change (or vanish) when this checkout switches branches
mkdir -p ~/.local/share/kaeq
install -m 755 "$here/kaeq.py" ~/.local/share/kaeq/kaeq.py
install -m 755 "$here/kaeqtop.py" ~/.local/share/kaeq/kaeqtop.py
ln -sf ~/.local/share/kaeq/kaeq.py ~/.local/bin/kaeq
ln -sf ~/.local/share/kaeq/kaeqtop.py ~/.local/bin/kaeqtop
# user-level skill: sessions in any repo/branch get the usage text
mkdir -p ~/.claude/skills/kaeq
cp "$here/../../.claude/skills/kaeq/SKILL.md" ~/.claude/skills/kaeq/SKILL.md
~/.local/bin/kaeq doctor
echo "Optional, survives reboots/logouts: kaeq install-service. After updating kaeq.py, re-run this and: systemctl --user restart kaeq"
