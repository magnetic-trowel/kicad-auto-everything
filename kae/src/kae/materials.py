# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Board material constants that more than one model uses, with where each comes from.

One value per physical quantity, so the router, the DC and thermal evaluators and the place
terms agree (docs/topics/rules/thermal.md, docs/topics/rules/power/high-current.md).

    VIA_PLATING_MM   0.020 mm   via hole-wall copper: the IPC-6012 class 2 average (class 3 is
                                25 um). A board that orders class 3, or a fab that states its
                                plating, overrides it (opts via_plating_mm); 25 um is the
                                optimistic side for every check that uses it (less resistance,
                                more current per via, more heat through a via).
    barrel_area_mm2  pi (d + t) t, with d the finished hole (the hole a KiCad via names) and t
                     the plating: KiCad's own via calculator (pcb_calculator panel_via_size)
                     and IPC's annulus. A fab that drills d and plates inward leaves
                     pi (d - t) t, 12 % less at 0.3 mm: within the class 2 vs 3 spread.
    K_CU             390 W/(m K)  copper (annealed: 385-401).
    RHO_CU_OHM_MM    1.72e-5      copper resistivity at 20 C.
    SIGMA_CU         5.8e7 S/m    annealed copper's conductivity at T_REF_C (IEC 60028: 1/58 ohm mm^2/m),
                                  the field solver's value.
    ALPHA_CU         3.93e-3 1/K  copper resistance's temperature coefficient at T_REF_C (IEC 60028 via
                                  IS 8130); kae.excite.heat's TCR fixed point.
    T_REF_C          20 C         the temperature RHO_CU_OHM_MM and SIGMA_CU hold at.
    K_FR4_THROUGH    0.3  W/(m K) FR-4 through the laminate: measured 0.29 (Azar and Graebner,
                                  SEMI-THERM 1996), datasheets 0.3 (Shengyi S1141) to 0.4 (Isola
                                  370HR); TI SNVA419 lists 0.23 without a source.
    K_FR4_IN         0.8  W/(m K) FR-4 along the laminate: the glass weave conducts along it,
                                  measured 0.81 (Azar and Graebner) to 1.06; Graebner 1997: about 3x
                                  through-plane. The research FV solver (tm_board_thermal_fv) and the
                                  place terms' ThermalFV already use 0.8. Isotropic 0.3 overstated a
                                  copper-sparse part's rise by ~60 % (decide note, RC6).
    H_AIR            10   W/(m^2 K) still-air natural convection plus radiation from each face:
                                  TI SNVA419 Table 1 (0.001 W/cm^2 C). Correlations give
                                  ~3-6 (convection; a downward face the least) + ~6 (radiation,
                                  emissivity 0.9 near 300-330 K) per face; 10 is their average,
                                  and an enclosure only lowers it.
"""
from __future__ import annotations

import math

VIA_PLATING_MM = 0.020
K_CU = 390.0
RHO_CU_OHM_MM = 1.72e-5
SIGMA_CU = 5.8e7
ALPHA_CU = 3.93e-3
T_REF_C = 20.0
K_FR4_THROUGH = 0.3
K_FR4_IN = 0.8
H_AIR = 10.0


def barrel_area_mm2(drill_mm, plating_mm=VIA_PLATING_MM):
    """Copper cross-section (mm^2) of a via barrel of finished hole `drill_mm`: pi (d + t) t."""
    return math.pi * (drill_mm + plating_mm) * plating_mm
