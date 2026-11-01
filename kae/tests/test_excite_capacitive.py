# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.excite.capacitive: the stackup's sheets, and couplings as skippable circuit parts."""
from types import SimpleNamespace

import pytest

from kae.excite import capacitive as CP
from kae.excite.circuit import Circuit


def test_sheets_sit_on_the_dielectric_interfaces_with_the_gaps_permittivities():
    stackup = SimpleNamespace(copper=["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"], gaps=[0.2, 1.0, 0.2], er=[4.2, 4.5, 4.3])
    bm = SimpleNamespace(m=SimpleNamespace(layers=[SimpleNamespace(name=n) for n in stackup.copper]))
    st, zs = CP.stack_of(bm, stackup)
    assert zs == pytest.approx([1.4e-3, 1.2e-3, 0.2e-3, 0.0])
    assert list(st.z) == pytest.approx([0.0, 0.2e-3, 1.2e-3, 1.4e-3])
    assert list(st.eps) == [4.3, 4.5, 4.2]                 # bottom gap first
    assert st.eps_at(1.4e-3) == pytest.approx((4.2 + 1.0) / 2)   # the top sheet: half air


def test_an_ideal_copper_solve_leaves_the_layouts_couplings_out():
    def build(with_cm):
        c = Circuit("GND")
        c.z("R1", "A", "GND", lambda w: 50.0, "R1.1", "R1.2", "R")
        c.z("R2", "B", "GND", lambda w: 1e4, "R2.1", "R2.2", "R")
        if with_cm:
            c.z("cm:A~B", "A", "B", lambda w: 1 / (1j * w * 1e-12), "R1.1", "R2.1", CP.KIND)
        c.src("s", "GND", "A")
        return c
    f = 50e6
    a, b = build(True), build(False)
    Vs = a.solve(f, a.sources, skip=(CP.KIND,))["s"]["V"]
    Vref = b.solve(f, b.sources)["s"]["V"]
    assert Vs["B"] == pytest.approx(Vref["B"]) and abs(Vs["B"]) < 1e-6
    assert abs(a.solve(f, a.sources)["s"]["V"]["B"]) > 1.0          # with the coupling, B moves
