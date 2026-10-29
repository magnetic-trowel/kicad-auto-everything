# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A neutral geometry spec (the one tools/research/physics/ref_fasthenry.py takes) as a Mesh, so the
raster solver and FastHenry solve the same problem.

spec: units mm; rects [x0, y0, x1, y1, z (bottom), t]; planes (same, plus holes [(x0, y0, x1, y1)]);
vias [x, y, z0, z1, d]; ports [p=(x, y, z), n=(x, y, z)]; shorts [a, b]; freqs. All copper is one
conductor where it touches (as in the FastHenry translation); terminals are the cell under the
point on the layer whose copper contains z.
"""
from __future__ import annotations

import numpy as np

from .mesh import Layer, Mesh


def mesh_of(spec, pitch, nsub=2, margin=0.0):
    shapes = list(spec.get("rects") or []) + list(spec.get("planes") or [])
    zs = sorted({(round(s["z"], 9), round(s["t"], 9)) for s in shapes}, reverse=True)
    layers = [Layer(f"L{k}", z, t, nsub) for k, (z, t) in enumerate(zs)]
    li = {(round(l.z, 9), round(l.t, 9)): k for k, l in enumerate(layers)}
    x0 = min(s["x0"] for s in shapes) - margin
    y0 = min(s["y0"] for s in shapes) - margin
    x1 = max(s["x1"] for s in shapes) + margin
    y1 = max(s["y1"] for s in shapes) + margin
    m = Mesh.over(x0, y0, x1, y1, pitch, layers, sigma=spec.get("sigma", 5.8e7))
    X, Y = m.centres()
    for s in shapes:
        k = li[(round(s["z"], 9), round(s["t"], 9))]
        m.rect(k, "C", s["x0"], s["y0"], s["x1"], s["y1"])
    for s in spec.get("planes") or []:
        k = li[(round(s["z"], 9), round(s["t"], 9))]
        for hx0, hy0, hx1, hy1 in s.get("holes") or []:
            hole = (X > hx0) & (X < hx1) & (Y > hy0) & (Y < hy1)
            m.lab[k][hole] = -1
            m.cov[k][hole] = 0.0

    def layer_at(z):
        for k, l in enumerate(layers):
            if l.z - 1e-9 <= z <= l.z + l.t + 1e-9:
                return k
        raise ValueError(f"no copper layer at z = {z}")
    for v in spec.get("vias") or []:
        a, b = layer_at(v["z0"]), layer_at(v["z1"])
        m.via(v["x"], v["y"], list(range(min(a, b), max(a, b) + 1)), "C", drill=v["d"])
    n_t = [0]

    def term(pt):
        n_t[0] += 1
        name = f"t{n_t[0]}"
        k = layer_at(pt[2])
        occ = m.lab[k] >= 0
        d = np.where(occ, (X - pt[0]) ** 2 + (Y - pt[1]) ** 2, np.inf)
        j, i = np.unravel_index(np.argmin(d), d.shape)          # the nearest copper cell (a snap)
        mask = np.zeros_like(occ)
        mask[j, i] = True
        return m.terminal(name, k, mask=mask)
    for sh in spec.get("shorts") or []:
        m.part(term(sh["a"]), term(sh["b"]))
    for p in spec.get("ports") or []:
        m.port(p.get("name", f"P{len(m.ports)}"), term(p["p"]), term(p["n"]))
    return m
