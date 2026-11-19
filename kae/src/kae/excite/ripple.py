# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The board-level AC copper loss of each switching cell's inductor ripple: loss.copper_ac.

A cell is excited (kae.excite.sources) by its commutated current: the pulsed current the switch hands between the
input capacitors and the switches, whose copper loss over the whole board loss.loop_ac prices (its R_loop is
Re J^T Z J at the switch port: by reciprocity the dissipation of that current pattern in all the copper it reaches,
bulk caps, input traces and planes included). What that excitation leaves out is the inductor's triangular ripple
current, the other AC current of a converter: through the switch node, the inductor, the output capacitors and the
ground copper back to the switches. Its copper loss is not in loss.copper (the DC band) nor in loss.loop_ac.

Model. A Norton current source across the inductor's pads (the switching sets the inductor current; the inductor's
own impedance, tens of ohms at f_sw, carries next to none of it), solved on the board's copper at f_sw, 3 f_sw and
5 f_sw with the board solve's network. Per unit amplitude its copper dissipation P_1(f) = 1/2 sum_b R_b(f) |I_b|^2
over the copper's branches (filaments and via barrels, not the parts), each layer's R times kae.em.skin.correction(f)
(crowding through the thickness beyond nsub filaments; the lateral crowding toward the return is in the solve).
The ripple's spectrum, a triangle of peak-to-peak dI rising for D T and falling for (1 - D) T:
    c_n = dI |sin(n pi D)| / (pi^2 n^2 D (1 - D)),   sum_n c_n^2 / 2 = dI^2 / 12,
    dI = V D (1 - D) / (L f_sw)   (V the switch's bus: buck V_in, boost V_out; CCM; capped at 2 I, the DCM boundary;
                                  kae.physics.converter.ripple_pp),
    loss.copper_ac = sum_n c_n^2 P_1(n f_sw),
P_1 interpolated log-log between the three solves and as sqrt(f) above 5 f_sw (the c_n fall as 1/n^2, so the first
three odd harmonics carry > 99 % of it at D = 0.5).

Left out: the cross term between the commutated and the ripple current where both flow (the switch's ground
pins), and the ripple of cells without an inductor in their structure (charge pumps, class-D without a filter
inductor on the board).
"""
from __future__ import annotations

import math

import numpy as np

HARMONICS = (1, 3, 5)
LEAK = 0.01                  # share of the ripple an island may hold unbalanced before the path counts as open
N_HARM = 99


def inductor_elem(bd, brief, s):
    """(the inductor's circuit element, its ref) for cell source s, or (None, None)."""
    st = next((x for x in brief.get("structures") or [] if x.get("id") == s.meta.get("cell")), {})
    ref = (brief["parts"].get(st.get("inductor")) or {}).get("ref")
    if not ref:
        return None, None
    for e in bd.circuit.elems:
        if e.pa and e.pb and e.pa.rsplit(".", 1)[0] == ref and e.pb.rsplit(".", 1)[0] == ref:
            return e, ref
    return None, ref


def p1(net, sol_I, f, nsub):
    """1/2 sum R_b(f) |I_b|^2 over the copper branches (W per A^2 of the source's amplitude)."""
    from .hotloop import _skin_R
    R = _skin_R(net, f, nsub)
    n = net.off["l"]
    return 0.5 * float(np.sum(R[:n] * np.abs(sol_I[:n]) ** 2))


def ripple_amplitude(val, L):
    """dI (A peak to peak) at one corner's values."""
    from kae.physics.converter import ripple_pp
    dI = ripple_pp(val.get("V_V", 0.0), val.get("D", 0.5), L, val.get("f_sw_Hz", 0.0))
    if dI is None:
        return 0.0
    I = val.get("I_A")
    return min(dI, 2 * I) if I is not None else dI         # a static leg (I = 0) carries no ripple of its own


def p1_of_f(fs, ps):
    fs, ps = np.asarray(fs, float), np.maximum(np.asarray(ps, float), 1e-30)

    def P(f):
        f = np.asarray(f, float)
        out = np.exp(np.interp(np.log(np.clip(f, fs[0], fs[-1])), np.log(fs), np.log(ps)))
        hi = f > fs[-1]
        out[hi] = ps[-1] * np.sqrt(f[hi] / fs[-1])
        return out
    return P


def loss(dI, D, f_sw, P):
    """sum_n c_n^2 P_1(n f_sw) for the triangle of dI peak to peak and duty D."""
    D = min(max(D, 1e-3), 1 - 1e-3)
    n = np.arange(1, N_HARM + 1)
    c = dI * np.abs(np.sin(n * math.pi * D)) / (math.pi ** 2 * n ** 2 * D * (1 - D))
    return float(np.sum(c ** 2 * P(n * f_sw)))
