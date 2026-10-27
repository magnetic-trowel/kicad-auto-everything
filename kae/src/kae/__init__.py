# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae: physics-first joint placement and routing for KiCad boards.

Subpackages: `kae.board` (board model, KiCad file reader, transforms, pcbnew bridge),
`kae.circuit`, `kae.physics`. `kae` never imports `kaebench`; methods plug into the
harness through `kaebench run --command`.
"""
__version__ = "0.1.0"
