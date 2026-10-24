#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Put `kaeq` on PATH (~/.local/bin) and report which isolation features work here.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p ~/.local/bin
chmod +x "$here/kaeq.py"
ln -sf "$here/kaeq.py" ~/.local/bin/kaeq
~/.local/bin/kaeq doctor
echo "Optional, survives reboots/logouts: kaeq install-service"
