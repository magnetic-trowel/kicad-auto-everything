# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Crystal load capacitance: the board's C_L in the pulling sensitivity (docs/research/physics/component-priors.md)."""
import math

import pytest

from kae.physics import priors as PR


# ----------------------------------------------------------------------------- crystals
def test_crystal_sensitivity_uses_the_boards_c_l(monkeypatch):
    _, s_legacy = PR.crystal_budget(32768)
    _, s7 = PR.crystal_budget(32768, c_load_pf=7.0)
    assert s_legacy == pytest.approx(8.0, abs=0.1) and s7 == pytest.approx(22.3, abs=0.2)
    monkeypatch.delenv("KAE_CRYSTAL_CL", raising=False)
    assert PR.crystal_cl({"C_L_pF": 7.0, "f_Hz": 32768}) is None
    monkeypatch.setenv("KAE_CRYSTAL_CL", "board")
    assert PR.crystal_cl({"C_L_pF": 7.0, "f_Hz": 32768}) == 7.0
    assert PR.crystal_cl({"f_Hz": 16e6}) == PR.CRYSTAL_CL_PRIOR["MHz"]


def test_crystal_load_from_text_or_caps():
    from kae.circuit.structures import crystal_load

    class P:
        def __init__(self, value, fields=None):
            self.value, self.fields = value, fields or {}
    assert crystal_load(P("16MHz 18pF"), [], [])[0] == 18.0
    assert crystal_load(P("32.768kHz", {"Load": "CL=6pF"}), [], [])[0] == 6.0
    cl, why = crystal_load(P("16MHz"), [22e-12], [22e-12])
    assert cl == pytest.approx(11 + PR.CRYSTAL_C_STRAY_PF) and "stray" in why
    assert crystal_load(P("Crystal"), [22e-12], [])[0] is None
    assert math.isfinite(PR.crystal_budget(16e6, c_load_pf=cl)[1])
