# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kaesynth: from an LLM-authored circuit description to checked KiCad schematics and
placement intent. See synth/README.md."""
from .ir import (Barrier, Block, Design, DesignError, Domain, Isolation, Net, Part, PartDef, PinDef,
                 Ratings, VLimit)
from .placement import BoardSpec, Hole

__all__ = ["Barrier", "Block", "BoardSpec", "Design", "DesignError", "Domain", "Hole", "Isolation", "Net",
           "Part", "PartDef", "PinDef", "Ratings", "VLimit"]
__version__ = "0.1.0"
