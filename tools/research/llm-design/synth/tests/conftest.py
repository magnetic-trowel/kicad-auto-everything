# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import shutil

import pytest

from kaesynth.kicadlib import footprint_dir, symbol_dir

HAVE_LIBS = symbol_dir() is not None and footprint_dir() is not None
HAVE_KICAD = HAVE_LIBS and shutil.which("kicad-cli") is not None


def pytest_collection_modifyitems(config, items):
    for it in items:
        if "kicad" in it.keywords and not HAVE_KICAD:
            it.add_marker(pytest.mark.skip(reason="needs kicad-cli and KiCad libraries"))
