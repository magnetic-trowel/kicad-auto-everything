# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""FastHenry reference solver wrapper: neutral PCB copper geometry -> port Z(f).

Independent reference for validating the in-house quasi-static PEEC solver.
FastHenry (MIT, Kamon/Silveira/White; Whiteley Research "3.0wr" branch) solves
the magneto-quasi-static mesh equations with filament discretization.  This
module translates a small neutral geometry spec into a FastHenry input deck,
runs the binary and parses ``Zc.mat``.

Binary lookup: ``$KAE_FASTHENRY``, else ``fasthenry`` on ``$PATH``.

Spec (all lengths in ``units``, default mm)::

    spec = dict(
      units="mm", sigma=5.8e7,                    # S/m
      rects=[dict(x0, y0, x1, y1, z, t, name)],   # z = bottom of copper
      planes=[dict(x0, y0, x1, y1, z, t, holes=[(x0, y0, x1, y1)], name)],
      vias=[dict(x, y, z0, z1, d)],
      ports=[dict(p=(x, y, z), n=(x, y, z), name)],
      shorts=[dict(a=(x, y, z), b=(x, y, z))],
      freqs=[1e6, 1e8],
      # optional knobs (global; most can be overridden per rect/plane):
      nwinc=None, nhinc=None,      # filaments per segment (None = auto from skin depth)
      seg_aspect=4.0,              # rect is a 1-D segment if long/short >= this
      plane_pitch=0.5,             # target G-plane cell size (scalar or (px, py))
      plane_nhinc=None,            # filaments through plane thickness (None = auto)
      via_ninc=None,               # filaments per side of a via bar (None = auto)
      solver="auto",               # auto | lu | dense | multi
      tol=1e-4, timeout=1800, mem_gb=16, workdir=None, keep=True)

Per-rect keys: ``kind`` ("seg" | "plane") forces the representation;
``nwinc``/``nhinc``.  Per-plane (and plane-kind rect) keys: ``cells=(nx, ny)``
or ``pitch=(px, py)``, ``nhinc``.

Translation rules (see ``build_deck``):

* A rect with long/short >= ``seg_aspect`` (and no ``kind="plane"``) becomes a
  chain of FastHenry segments along its long axis, width = short side, height =
  t, on the centreline at z + t/2.  The chain is split at every attachment
  (junction, port, short, via); stubs beyond the outermost attachments carry no
  current and are dropped.
* Every other rect and every ``plane`` becomes a uniform reference plane
  ``G`` with nx x ny cells.  Nodes sit at cell centres (the G corners are inset
  by half a pitch), so the copper extent equals the rectangle exactly (no
  FastHenry edge overhang).  A hole removes every node whose cell centre lies
  inside it (``hole rect`` with exact node corners), so hole edges are
  quantized to the pitch.  Terminals snap to the nearest live node; the snap
  distance is reported in ``result["snaps"]``.
* Same-z rects/planes whose closed rectangles intersect (overlap or abut) are
  joined with ``.equiv``: seg-seg at the projection of the intersection centre;
  seg-plane by equiv'ing the segment node to the line of plane nodes across the
  trace width (a contact line); plane-plane at sample points along the
  intersection.  Overlapping copper is counted twice (warning) - split pours
  into abutting rectangles instead.
* A via is one vertical segment between the centre planes of the copper found at
  (x, y, z0) and (x, y, z1), square cross-section of equal area (side
  d*sqrt(pi)/2); on a plane it contacts every node in its d x d footprint
  (at least the nearest one).
* Ports become ``.external``; shorts become ``.equiv`` (current through them
  is not modelled electromagnetically).
* Units: the deck is written in mm; sigma is converted to S/mm.

Limitations: axis-aligned rectangles only (no polygons, arcs, diagonal
traces); a seg carries current only along its long axis, and two side-by-side
abutting segs are joined at one point only (use one rect or kind="plane");
one uniform pitch per plane and direction, holes and terminals quantized to
it (a feed "at the edge" of a plane sits half a pitch inside); terminals are
points, except seg-plane contact lines and via footprints; ports and shorts
are not modelled electromagnetically; vias are solid square bars; FastHenry is
magneto-quasi-static: Z = R + jwL, no capacitance or displacement current.

Solver: "lu" (-s ludecomp) up to 3000 filaments, "dense" (GMRES, -m direct)
up to 5000, else "multi" (GMRES + multipole, -t tol).  Build FastHenry with
KLU: the Sparse package's preconditioner factorization is 10-20x slower above
~10k filaments.

``solve(spec)`` returns dict(freqs, Z[nf, np, np], R, L, ports, log, deck,
seconds, nfil, warnings, snaps).  ``python ref_fasthenry.py selftest`` checks
the wrapper against independent analytic values.
"""
from __future__ import annotations

import cmath
import json
import math
import os
import re
import resource
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np

MU0 = 4e-7 * math.pi
C0 = 299792458.0
ETA0 = MU0 * C0
TOL = 1e-6  # mm, geometric coincidence tolerance

_UNIT_MM = {"mm": 1.0, "m": 1e3, "cm": 10.0, "um": 1e-3, "mil": 0.0254,
            "mils": 0.0254, "in": 25.4}


# --------------------------------------------------------------------------
# discretization helpers
# --------------------------------------------------------------------------

def skin_depth_mm(f, sigma):
    if f <= 0:
        return math.inf
    return 1e3 / math.sqrt(math.pi * f * MU0 * sigma)


def auto_ninc(size, target, nmax):
    """Smallest odd n whose outermost FastHenry filament (ratio 2) is <= target.

    With ratio 2 and n = 2k+1 the filament sizes are 1,2,..,2^k,..,2,1 units,
    total 3*2^k - 2 units.
    """
    if not math.isfinite(target) or size <= target:
        return 1
    k = 0
    while size / (3 * 2 ** k - 2) > target and 2 * k + 1 < nmax:
        k += 1
    return 2 * k + 1


def _f(x):
    return "%.10g" % x


# --------------------------------------------------------------------------
# conductor objects
# --------------------------------------------------------------------------

class SegCond:
    """Rect modelled as a 1-D chain of segments along its long axis."""

    def __init__(self, idx, r, nw, nh):
        self.idx, self.r = idx, r
        self.name = r.get("name", "rect%d" % idx)
        self.x0, self.y0, self.x1, self.y1 = r["x0"], r["y0"], r["x1"], r["y1"]
        self.z, self.t = r["z"], r["t"]
        self.zc = self.z + self.t / 2
        if self.x1 - self.x0 >= self.y1 - self.y0:
            self.axis, self.a0, self.a1 = 0, self.x0, self.x1
            self.c, self.w = (self.y0 + self.y1) / 2, self.y1 - self.y0
        else:
            self.axis, self.a0, self.a1 = 1, self.y0, self.y1
            self.c, self.w = (self.x0 + self.x1) / 2, self.x1 - self.x0
        self.nw, self.nh = nw, nh
        self.att = []        # (s, label)
        self.label2node = {}

    def contains(self, x, y):
        return (self.x0 - TOL <= x <= self.x1 + TOL
                and self.y0 - TOL <= y <= self.y1 + TOL)

    def attach(self, x, y):
        s = x if self.axis == 0 else y
        s = min(max(s, self.a0), self.a1)
        lab = "L%d_%d" % (self.idx, len(self.att))
        self.att.append((s, lab))
        snap = abs((y if self.axis == 0 else x) - self.c)
        return ("seg", self, lab), snap

    def build(self, lines):
        if not self.att:
            return 0
        ss = sorted(set(round(s / TOL) * TOL for s, _ in self.att))
        uniq = []
        for s in ss:
            if not uniq or s - uniq[-1] > 10 * TOL:
                uniq.append(s)
        names = []
        for k, s in enumerate(uniq):
            nm = "n%ds%d" % (self.idx, k)
            x, y = (s, self.c) if self.axis == 0 else (self.c, s)
            lines.append("%s x=%s y=%s z=%s" % (nm, _f(x), _f(y), _f(self.zc)))
            names.append(nm)
        for s, lab in self.att:
            k = min(range(len(uniq)), key=lambda i: abs(uniq[i] - s))
            self.label2node[lab] = names[k]
        nfil = 0
        for k in range(len(uniq) - 1):
            lines.append("e%ds%d %s %s w=%s h=%s nwinc=%d nhinc=%d" % (
                self.idx, k, names[k], names[k + 1], _f(self.w), _f(self.t),
                self.nw, self.nh))
            nfil += self.nw * self.nh
        return nfil


class PlaneCond:
    """Uniform FastHenry reference plane with cell-centred nodes."""

    def __init__(self, idx, r, nx, ny, nh, holes):
        self.idx, self.r = idx, r
        self.name = r.get("name", "plane%d" % idx)
        self.x0, self.y0, self.x1, self.y1 = r["x0"], r["y0"], r["x1"], r["y1"]
        self.z, self.t = r["z"], r["t"]
        self.zc = self.z + self.t / 2
        self.nx, self.ny, self.nh = max(2, nx), max(2, ny), nh
        self.px = (self.x1 - self.x0) / self.nx
        self.py = (self.y1 - self.y0) / self.ny
        self.X = self.x0 + self.px * (np.arange(self.nx) + 0.5)
        self.Y = self.y0 + self.py * (np.arange(self.ny) + 0.5)
        self.alive = np.ones((self.nx, self.ny), bool)
        self.holes = []
        self.warnings = []
        for (hx0, hy0, hx1, hy1) in holes:
            ii = np.nonzero((self.X > hx0 + TOL) & (self.X < hx1 - TOL))[0]
            jj = np.nonzero((self.Y > hy0 + TOL) & (self.Y < hy1 - TOL))[0]
            if len(ii) == 0 or len(jj) == 0:
                self.warnings.append("%s: hole (%g,%g,%g,%g) smaller than a cell,"
                                     " ignored" % (self.name, hx0, hy0, hx1, hy1))
                continue
            self.alive[ii[0]:ii[-1] + 1, jj[0]:jj[-1] + 1] = False
            self.holes.append((ii[0], jj[0], ii[-1], jj[-1]))
        self.used = set()

    def contains(self, x, y):
        return (self.x0 - TOL <= x <= self.x1 + TOL
                and self.y0 - TOL <= y <= self.y1 + TOL)

    def nearest(self, x, y):
        d2 = (self.X[:, None] - x) ** 2 + (self.Y[None, :] - y) ** 2
        d2 = np.where(self.alive, d2, np.inf)
        i, j = np.unravel_index(np.argmin(d2), d2.shape)
        if not np.isfinite(d2[i, j]):
            raise ValueError("%s: no live node" % self.name)
        return int(i), int(j), math.sqrt(d2[i, j])

    def node(self, i, j):
        self.used.add((i, j))
        return "n%dp%d_%d" % (self.idx, i, j)

    def attach(self, x, y):
        i, j, d = self.nearest(x, y)
        return self.node(i, j), d

    def nodes_in_box(self, bx0, by0, bx1, by1):
        ii = np.nonzero((self.X >= bx0 - TOL) & (self.X <= bx1 + TOL))[0]
        jj = np.nonzero((self.Y >= by0 - TOL) & (self.Y <= by1 + TOL))[0]
        out = [self.node(int(i), int(j)) for i in ii for j in jj if self.alive[i, j]]
        if not out:
            i, j, _ = self.nearest((bx0 + bx1) / 2, (by0 + by1) / 2)
            out = [self.node(i, j)]
        return out

    def nseg(self):
        a = self.alive
        return int((a[1:, :] & a[:-1, :]).sum() + (a[:, 1:] & a[:, :-1]).sum())

    def build(self, lines):
        X, Y, zc = self.X, self.Y, self.zc
        g = ["g%d x1=%s y1=%s z1=%s x2=%s y2=%s z2=%s x3=%s y3=%s z3=%s" % (
            self.idx, _f(X[0]), _f(Y[0]), _f(zc), _f(X[-1]), _f(Y[0]), _f(zc),
            _f(X[-1]), _f(Y[-1]), _f(zc)),
            "+ thick=%s seg1=%d seg2=%d nhinc=%d" % (
                _f(self.t), self.nx - 1, self.ny - 1, self.nh)]
        for (i, j) in sorted(self.used):
            g.append("+ n%dp%d_%d (%s,%s,%s)" % (self.idx, i, j, _f(X[i]), _f(Y[j]),
                                                 _f(zc)))
        for (i0, j0, i1, j1) in self.holes:
            g.append("+ hole rect (%s,%s,%s,%s,%s,%s)" % (
                _f(X[i0]), _f(Y[j0]), _f(zc), _f(X[i1]), _f(Y[j1]), _f(zc)))
        lines.extend(g)
        return self.nseg() * self.nh


class _UF:
    def __init__(self):
        self.p = {}

    def find(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


# --------------------------------------------------------------------------
# deck builder
# --------------------------------------------------------------------------

def _scaled(spec):
    """Copy of the geometry in mm."""
    k = _UNIT_MM[spec.get("units", "mm").lower()]
    sc = lambda v: v * k  # noqa: E731
    pt = lambda p: tuple(sc(v) for v in p)  # noqa: E731
    out = dict(spec)
    out["rects"] = [dict(r, **{q: sc(r[q]) for q in ("x0", "y0", "x1", "y1", "z", "t")})
                    for r in spec.get("rects", [])]
    out["planes"] = [dict(r, **{q: sc(r[q]) for q in ("x0", "y0", "x1", "y1", "z", "t")},
                          holes=[pt(h) for h in r.get("holes", [])])
                     for r in spec.get("planes", [])]
    out["vias"] = [dict(v, **{q: sc(v[q]) for q in ("x", "y", "z0", "z1", "d")})
                   for v in spec.get("vias", [])]
    out["ports"] = [dict(p, p=pt(p["p"]), n=pt(p["n"])) for p in spec.get("ports", [])]
    out["shorts"] = [dict(s, a=pt(s["a"]), b=pt(s["b"])) for s in spec.get("shorts", [])]
    pp = spec.get("plane_pitch", 0.5)
    out["plane_pitch"] = tuple(sc(v) for v in pp) if isinstance(pp, (tuple, list)) else sc(pp)
    for r in out["rects"] + out["planes"]:
        if "pitch" in r:
            r["pitch"] = tuple(sc(v) for v in r["pitch"])
    return out


def build_deck(spec):
    """Return (deck_text, info) for a spec (see module docstring)."""
    s = _scaled(spec)
    sigma = float(s.get("sigma", 5.8e7))
    freqs = [float(f) for f in s.get("freqs", [1e6])]
    fmax = max(freqs) if freqs else 0.0
    delta = skin_depth_mm(fmax, sigma)
    nmax = int(s.get("nmax_inc", 15))
    seg_aspect = float(s.get("seg_aspect", 4.0))
    warnings = []

    conds = []
    for r in s["rects"]:
        lx, ly = r["x1"] - r["x0"], r["y1"] - r["y0"]
        if lx <= 0 or ly <= 0 or r["t"] <= 0:
            raise ValueError("degenerate rect %r" % r)
        kind = r.get("kind")
        if kind is None:
            kind = "seg" if max(lx, ly) / min(lx, ly) >= seg_aspect else "plane"
        if kind == "seg":
            w = min(lx, ly)
            nw = r.get("nwinc", s.get("nwinc")) or auto_ninc(w, max(delta, r["t"]) / 2, nmax)
            nh = r.get("nhinc", s.get("nhinc")) or auto_ninc(r["t"], delta / 2, nmax)
            conds.append(SegCond(len(conds), r, int(nw), int(nh)))
        else:
            conds.append(_mk_plane(len(conds), r, s, delta, nmax, []))
    for r in s["planes"]:
        conds.append(_mk_plane(len(conds), r, s, delta, nmax, r.get("holes", [])))
    for c in conds:
        if isinstance(c, PlaneCond):
            warnings += c.warnings

    uf = _UF()
    pending = []   # (handleA, handleB) to union after build
    snaps = []

    def find_copper(x, y, z):
        best = None
        for c in conds:
            if c.contains(x, y) and c.z - TOL <= z <= c.z + c.t + TOL:
                dz = abs(z - c.zc)
                if best is None or dz < best[0]:
                    best = (dz, c)
        return best[1] if best else None

    # same-z junctions
    for a in range(len(conds)):
        for b in range(a + 1, len(conds)):
            A, B = conds[a], conds[b]
            if abs(A.z - B.z) > TOL:
                continue
            ix0, ix1 = max(A.x0, B.x0), min(A.x1, B.x1)
            iy0, iy1 = max(A.y0, B.y0), min(A.y1, B.y1)
            if ix0 > ix1 + TOL or iy0 > iy1 + TOL:
                continue
            ovl = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
            cx, cy = (ix0 + ix1) / 2, (iy0 + iy1) / 2
            if isinstance(A, SegCond) and isinstance(B, SegCond):
                ha, _ = A.attach(cx, cy)
                hb, _ = B.attach(cx, cy)
                pending.append((ha, hb))
            elif isinstance(A, PlaneCond) and isinstance(B, PlaneCond):
                if ovl > TOL:
                    warnings.append("planes %s/%s overlap (%.3g mm^2): copper counted"
                                    " twice" % (A.name, B.name, ovl))
                pmin = min(A.px, A.py, B.px, B.py)
                nxs = max(1, int(math.ceil((ix1 - ix0) / pmin)))
                nys = max(1, int(math.ceil((iy1 - iy0) / pmin)))
                seen = set()
                for i in range(nxs):
                    for j in range(nys):
                        x = ix0 + (i + 0.5) * (ix1 - ix0) / nxs
                        y = iy0 + (j + 0.5) * (iy1 - iy0) / nys
                        na, _ = A.attach(x, y)
                        nb, _ = B.attach(x, y)
                        if (na, nb) not in seen:
                            seen.add((na, nb))
                            pending.append((na, nb))
            else:
                S, P = (A, B) if isinstance(A, SegCond) else (B, A)
                if ovl > 2 * S.w * S.w + TOL:
                    warnings.append("seg %s overlaps plane %s by %.3g mm^2: copper "
                                    "counted twice" % (S.name, P.name, ovl))
                hs, _ = S.attach(cx, cy)
                if S.axis == 0:   # x-directed, width along y
                    box = (cx, max(S.y0, iy0), cx, min(S.y1, iy1))
                else:
                    box = (max(S.x0, ix0), cy, min(S.x1, ix1), cy)
                # widen along the axis by half a plane pitch so a column is hit
                hp = 0.5 * (P.px if S.axis == 0 else P.py)
                if S.axis == 0:
                    box = (box[0] - hp, box[1], box[2] + hp, box[3])
                else:
                    box = (box[0], box[1] - hp, box[2], box[3] + hp)
                pn = P.nodes_in_box(*box)
                # keep only the column/row nearest to the junction centre
                if S.axis == 0:
                    i0, _, _ = P.nearest(cx, cy)
                    pn = [n for n in pn if n.split("p")[1].split("_")[0] == str(i0)] or pn
                else:
                    _, j0, _ = P.nearest(cx, cy)
                    pn = [n for n in pn if n.split("_")[-1] == str(j0)] or pn
                for n in pn:
                    pending.append((hs, n))

    def attach_point(p, what):
        x, y, z = p
        c = find_copper(x, y, z)
        if c is None:
            raise ValueError("%s at %r: no copper there" % (what, p))
        h, d = c.attach(x, y)
        snaps.append(dict(what=what, at=p, cond=c.name, snap_mm=d))
        return h

    lines_extra = []
    nfil_via = 0
    for k, v in enumerate(s["vias"]):
        x, y, d = v["x"], v["y"], v["d"]
        ends = []
        for zz, tag in ((v["z0"], "b"), (v["z1"], "t")):
            c = find_copper(x, y, zz)
            nm = "nv%d%s" % (k, tag)
            zc = c.zc if c else zz
            ends.append((nm, zc))
            if c is None:
                warnings.append("via %d end z=%g: no copper, dangling" % (k, zz))
            elif isinstance(c, SegCond):
                h, dd = c.attach(x, y)
                pending.append((h, nm))
                snaps.append(dict(what="via%d%s" % (k, tag), at=(x, y, zz), cond=c.name,
                                  snap_mm=dd))
            else:
                hw = max(d / 2, 0.0)
                for n in c.nodes_in_box(x - hw, y - hw, x + hw, y + hw):
                    pending.append((n, nm))
        a = d * math.sqrt(math.pi) / 2
        ni = v.get("ninc", s.get("via_ninc")) or auto_ninc(a, max(delta, a / 10) / 2, 7)
        (nb, zb), (nt, zt) = ends
        lines_extra.append("%s x=%s y=%s z=%s" % (nb, _f(x), _f(y), _f(zb)))
        lines_extra.append("%s x=%s y=%s z=%s" % (nt, _f(x), _f(y), _f(zt)))
        lines_extra.append("ev%d %s %s w=%s h=%s nwinc=%d nhinc=%d" % (
            k, nb, nt, _f(a), _f(a), ni, ni))
        nfil_via += ni * ni

    for k, sh in enumerate(s["shorts"]):
        pending.append((attach_point(sh["a"], "short%d.a" % k),
                        attach_point(sh["b"], "short%d.b" % k)))
    port_h = []
    for k, p in enumerate(s["ports"]):
        port_h.append((attach_point(p["p"], "port%d.p" % k),
                       attach_point(p["n"], "port%d.n" % k)))

    # build
    body = []
    nfil = 0
    for c in conds:
        nfil += c.build(body)
    body += lines_extra
    nfil += nfil_via

    def res(h):
        if isinstance(h, tuple):
            return h[1].label2node[h[2]]
        return h

    for a, b in pending:
        uf.union(res(a), res(b))
    ports = [(res(a), res(b)) for a, b in port_h]
    for k, (a, b) in enumerate(ports):
        if uf.find(a) == uf.find(b):
            raise ValueError("port %d is shorted by equivalences" % k)
    groups = {}
    for n in list(uf.p):
        groups.setdefault(uf.find(n), []).append(n)

    out = ["* kae ref_fasthenry deck", ".units mm",
           ".default sigma=%s" % _f(sigma * 1e-3)]
    for c in conds:
        out.append("* cond %s = %s (%s)" % (c.idx, c.name, type(c).__name__))
    out += body
    for g in groups.values():
        if len(g) > 1:
            g = sorted(g)
            for i in range(0, len(g) - 1, 30):
                out.append(".equiv " + " ".join(g[i:i + 31]))
    for k, (a, b) in enumerate(ports):
        out.append(".external %s %s p%d" % (a, b, k))
    info = dict(nfil=nfil, warnings=warnings, snaps=snaps, delta_mm=delta,
                conds=[(c.name, type(c).__name__,
                        dict(nw=c.nw, nh=c.nh) if isinstance(c, SegCond) else
                        dict(nx=c.nx, ny=c.ny, px=c.px, py=c.py, nh=c.nh))
                       for c in conds])
    return "\n".join(out) + "\n", info


def _mk_plane(idx, r, s, delta, nmax, holes):
    lx, ly = r["x1"] - r["x0"], r["y1"] - r["y0"]
    if "cells" in r:
        nx, ny = r["cells"]
    else:
        pitch = r.get("pitch", s.get("plane_pitch", 0.5))
        px, py = pitch if isinstance(pitch, (tuple, list)) else (pitch, pitch)
        nx = max(2, int(math.ceil(lx / px - 1e-9)))
        ny = max(2, int(math.ceil(ly / py - 1e-9)))
    nh = r.get("nhinc", s.get("plane_nhinc")) or auto_ninc(r["t"], delta / 2, nmax)
    return PlaneCond(idx, r, int(nx), int(ny), int(nh), holes)


# --------------------------------------------------------------------------
# running and parsing
# --------------------------------------------------------------------------

def fasthenry_bin():
    b = os.environ.get("KAE_FASTHENRY") or shutil.which("fasthenry")
    if not b:
        raise FileNotFoundError("FastHenry binary not found: set KAE_FASTHENRY")
    return b


_CPX = re.compile(r"([-+]?(?:\d+\.?\d*(?:[eE][-+]?\d+)?|nan|inf))\s*([-+])\s*"
                  r"(\d+\.?\d*(?:[eE][-+]?\d+)?|nan|inf)j", re.I)


def parse_zc(path):
    """Parse Zc.mat -> (port_row_names, [(f, Z ndarray)])."""
    rows, mats = {}, []
    with open(path) as fh:
        txt = fh.read().splitlines()
    i = 0
    while i < len(txt):
        ln = txt[i]
        m = re.match(r"Row (\d+):.*port name: (\S+)", ln)
        if m:
            rows[int(m.group(1)) - 1] = m.group(2)
        m = re.match(r"\s*Impedance matrix for frequency = (\S+) (\d+) x (\d+)", ln)
        if m:
            f, n, k = float(m.group(1)), int(m.group(2)), int(m.group(3))
            Z = np.zeros((n, k), complex)
            for r in range(n):
                i += 1
                vals = _CPX.findall(txt[i])
                if len(vals) != k:
                    raise ValueError("bad Zc row: %r" % txt[i])
                Z[r] = [float(a) + (1 if sg == "+" else -1) * 1j * float(b)
                        for a, sg, b in vals]
            mats.append((f, Z))
        i += 1
    names = [rows[k] for k in sorted(rows)]
    return names, mats


def _freq_runs(freqs):
    """Group requested frequencies into FastHenry .freq runs."""
    pos = sorted(set(f for f in freqs if f > 0))
    runs = []
    if any(f == 0 for f in freqs):
        runs.append((0.0, 0.0, 1.0))
    if len(pos) == 1:
        runs.append((pos[0], pos[0], 1.0))
    elif pos:
        lg = np.log10(pos)
        step = np.min(np.diff(lg))
        q = (lg - lg[0]) / step
        if np.all(np.abs(q - np.round(q)) < 1e-6) and q[-1] <= 200:
            runs.append((pos[0], pos[-1], 1.0 / step))
        else:
            runs += [(f, f, 1.0) for f in pos]
    return runs


def solve(spec, verbose=False):
    deck, info = build_deck(spec)
    nport = len(spec.get("ports", []))
    if nport == 0:
        raise ValueError("no ports")
    freqs = [float(f) for f in spec.get("freqs", [1e6])]
    wd_root = spec.get("workdir")
    if wd_root:
        os.makedirs(wd_root, exist_ok=True)
    wd = tempfile.mkdtemp(prefix="fh_", dir=wd_root)
    solver = spec.get("solver", "auto")
    nfil = info["nfil"]
    if solver == "auto":
        solver = "lu" if nfil <= 3000 else ("dense" if nfil <= 5000 else "multi")
    tol = str(spec.get("tol", 1e-4))
    opts = {"lu": ["-s", "ludecomp"],
            "dense": ["-s", "iterative", "-m", "direct", "-t", tol, "-b", "1e-3"],
            "multi": ["-s", "iterative", "-m", "multi", "-t", tol, "-b", "1e-3"]}[solver]
    mem = int(float(spec.get("mem_gb", 16)) * 2 ** 30)

    def lim():
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))

    got = {}
    names = None
    t0 = time.time()
    log = os.path.join(wd, "fasthenry.log")
    with open(log, "w") as lf:
        for k, (fmin, fmax, ndec) in enumerate(_freq_runs(freqs)):
            inp = os.path.join(wd, "run%d.inp" % k)
            with open(inp, "w") as fh:
                fh.write(deck)
                fh.write(".freq fmin=%s fmax=%s ndec=%s\n.end\n" % (
                    _f(fmin), _f(fmax), _f(ndec)))
            o = opts
            if fmin == 0 and solver == "lu":
                # the KLU build segfaults in fill_diagR() for DC with -s ludecomp
                o = ["-s", "iterative", "-m", "direct", "-t", tol, "-b", "1e-3"]
            cmd = [fasthenry_bin()] + o + ["-S", "_%d" % k, inp]
            lf.write("$ %s\n" % " ".join(cmd))
            lf.flush()
            p = subprocess.run(cmd, cwd=wd, stdout=lf, stderr=subprocess.STDOUT,
                               timeout=float(spec.get("timeout", 1800)), preexec_fn=lim)
            if p.returncode != 0:
                raise RuntimeError("fasthenry failed (rc=%d), see %s" % (p.returncode, log))
            names, mats = parse_zc(os.path.join(wd, "Zc_%d.mat" % k))
            for f, Z in mats:
                got[f] = Z
    secs = time.time() - t0
    order = [names.index("p%d" % k) for k in range(nport)]
    Zs = []
    fl = sorted(got)
    for f in freqs:
        fk = min(fl, key=lambda g: abs(g - f) / max(f, 1e-30) if f > 0 else abs(g))
        if (f > 0 and abs(fk - f) > 1e-5 * f) or (f == 0 and fk != 0):
            raise RuntimeError("frequency %g not in FastHenry output" % f)
        Z = got[fk][np.ix_(order, order)]
        Zs.append(Z)
    Z = np.array(Zs)
    w = 2 * np.pi * np.array(freqs)[:, None, None]
    with np.errstate(divide="ignore", invalid="ignore"):
        L = np.where(w > 0, Z.imag / np.where(w > 0, w, 1), np.nan)
    with open(os.path.join(wd, "deck.inp"), "w") as fh:
        fh.write(deck)
    stats = {}
    with open(log) as fh:
        for ln in fh:
            m = re.match(r"\s*(Number of filaments|Number of segments|Number of nodes)"
                         r"\s*:\s*(\d+)", ln)
            if m:
                stats[m.group(1)] = int(m.group(2))
    if verbose:
        print(deck)
    return dict(freqs=freqs, Z=Z, R=Z.real, L=L, seconds=secs, log=log, workdir=wd,
                ports=[p.get("name", "p%d" % k) for k, p in enumerate(spec["ports"])],
                nfil=nfil, solver=solver, warnings=info["warnings"],
                snaps=info["snaps"], conds=info["conds"], stats=stats,
                delta_mm=info["delta_mm"])


# --------------------------------------------------------------------------
# independent analytic references
# --------------------------------------------------------------------------

def _hl_f(x, y, z):
    """Hoer & Love (1965) eq. (14) kernel; long double for the cancellation."""
    x, y, z = (np.longdouble(abs(v)) for v in (x, y, z))
    x2, y2, z2 = x * x, y * y, z * z
    r = np.sqrt(x2 + y2 + z2)
    out = np.longdouble(0)
    if x > 0 and (y2 + z2) > 0:
        out += (y2 * z2 / 4 - y2 * y2 / 24 - z2 * z2 / 24) * x * np.arcsinh(x / np.sqrt(y2 + z2))
    if y > 0 and (x2 + z2) > 0:
        out += (x2 * z2 / 4 - x2 * x2 / 24 - z2 * z2 / 24) * y * np.arcsinh(y / np.sqrt(x2 + z2))
    if z > 0 and (x2 + y2) > 0:
        out += (x2 * y2 / 4 - x2 * x2 / 24 - y2 * y2 / 24) * z * np.arcsinh(z / np.sqrt(x2 + y2))
    out += (x2 * x2 + y2 * y2 + z2 * z2 - 3 * x2 * y2 - 3 * y2 * z2 - 3 * z2 * x2) * r / 60
    if x > 0 and y > 0 and z > 0:
        out -= x * y * z * z2 / 6 * np.arctan(x * y / (z * r))
        out -= x * y * y2 * z / 6 * np.arctan(x * z / (y * r))
        out -= x * x2 * y * z / 6 * np.arctan(y * z / (x * r))
    return out


def hoer_love_mutual(a, b, l1, c, d, l3, E, P, l2):
    """Mutual inductance [H, lengths in m] of two parallel rectangular bars.

    Bar 1: a (x) by b (y), length l1 along z from 0.  Bar 2: c by d, length l3,
    corner offset (E, P, l2).  Hoer & Love, J. Res. NBS 69C (1965) 127-137.
    """
    q = (E - a, E + c - a, E + c, E)
    r = (P - b, P + d - b, P + d, P)
    s = (l2 - l1, l2 + l3 - l1, l2 + l3, l2)
    tot = np.longdouble(0)
    for i in range(4):
        for j in range(4):
            for k in range(4):
                sg = (-1) ** (i + j + k + 3 + 1)
                tot += sg * _hl_f(q[i], r[j], s[k])
    return float(MU0 / (4 * math.pi) * tot / (a * b * c * d))


def bar_self_L(w, t, l):
    return hoer_love_mutual(w, t, l, w, t, l, 0.0, 0.0, 0.0)


def bar_self_L_numeric(w, t, l):
    """Cross-check: uniform-current bar, filament mutual integrated over the
    cross-section (4-D integral reduced to 2-D by the autocorrelation)."""
    from scipy.integrate import dblquad

    def g(v, u):
        dd = math.hypot(u, v)
        return 2 * (l * math.asinh(l / dd) - math.hypot(l, dd) + dd) * (w - u) * (t - v)

    val, _ = dblquad(g, 0, w, 0, t, epsabs=0, epsrel=1e-10)
    return MU0 / (4 * math.pi) * 4 * val / (w * t) ** 2


def wheeler77_L(w, h, t):
    """Air microstrip L' [H/m] from Wheeler (1977) with strip thickness, er=1."""
    er = 1.0
    dw = t / math.pi * math.log(4 * math.e / math.sqrt(
        (t / h) ** 2 + (1 / math.pi / (w / t + 1.1)) ** 2)) * (1 + 1 / er) / 2
    wp = w + dw
    k = (14 + 8 / er) / 11 * 4 * h / wp
    z0 = ETA0 / (2 * math.pi * math.sqrt(2 * (1 + er))) * math.log(
        1 + 4 * h / wp * (k + math.sqrt(k * k + math.pi ** 2 * (1 + 1 / er) / 2)))
    return z0 / C0


def hammerstad_L(w, h, t):
    """Air microstrip L' [H/m], Hammerstad & Jensen (1980) with thickness."""
    u = w / h
    if t > 0:
        u += t / (math.pi * h) * math.log(1 + 4 * math.e / (
            t / h / math.tanh(math.sqrt(6.517 * u)) ** 2))
    fu = 6 + (2 * math.pi - 6) * math.exp(-(30.666 / u) ** 0.7528)
    z0 = ETA0 / (2 * math.pi) * math.log(fu / u + math.sqrt(1 + 4 / u ** 2))
    return z0 / C0


def surface_Lint(f, sigma, t):
    """Internal inductance per square [H] of one sheet of thickness t carrying
    surface current on one face: Im(Zs)/omega, Zs = k/sigma coth(k t)."""
    w = 2 * math.pi * f
    k = cmath.sqrt(1j * w * MU0 * sigma)
    zs = k / sigma / np.tanh(k * t)
    return float(np.imag(zs) / w)


def strip_pair_L_uniform(w, t, D):
    """2-D L' [H/m] of two w x t rectangles, centre distance D, uniform opposite
    currents: (mu0/pi) ln(GMD12 / GMD11), integrals done numerically."""
    from scipy.integrate import dblquad

    def g(v, u):
        wt = (w - u) * (t - abs(v))
        return 0.5 * math.log((u * u + (v + D) ** 2) / (u * u + v * v)) * wt

    val, _ = dblquad(g, 0, w, -t, t, epsabs=0, epsrel=1e-9)
    return MU0 / math.pi * 2 * val / (w * t) ** 2


def grover_rect_L(l1, l2, R):
    """Grover rectangle formula (GMD form) [H], sides l1, l2, GMD R [m]."""
    d = math.hypot(l1, l2)
    return MU0 / math.pi * (l1 * math.log(2 * l1 / R) + l2 * math.log(2 * l2 / R)
                            + 2 * d - l1 * math.asinh(l1 / l2) - l2 * math.asinh(l2 / l1)
                            - 2 * (l1 + l2))


# --------------------------------------------------------------------------
# self-tests
# --------------------------------------------------------------------------

def _row(rows, test, qty, val, ref, sec, disc, unit=""):
    err = (val - ref) / ref * 100
    rows.append((test, qty, val, ref, err, sec, disc, unit))
    return err


def test_strip(rows, workdir):
    sig = 5.8e7
    w, t, l = 1.0, 0.035, 10.0
    base = dict(sigma=sig, rects=[dict(x0=0, y0=0, x1=l, y1=w, z=0, t=t, name="strip")],
                ports=[dict(p=(0, w / 2, t / 2), n=(l, w / 2, t / 2), name="P")],
                workdir=workdir)
    r = solve(dict(base, freqs=[0.0], nwinc=1, nhinc=1))
    Rdc = l * 1e-3 / (sig * w * 1e-3 * t * 1e-3)
    _row(rows, "a strip", "R_DC [mOhm]", r["R"][0, 0, 0] * 1e3, Rdc * 1e3, r["seconds"],
         "1x1 fil")
    Lhl = bar_self_L(w * 1e-3, t * 1e-3, l * 1e-3)
    Lnum = bar_self_L_numeric(w * 1e-3, t * 1e-3, l * 1e-3)
    print("  Hoer-Love %.6g nH, numeric cross-check %.6g nH (%.2e rel)"
          % (Lhl * 1e9, Lnum * 1e9, Lhl / Lnum - 1))
    r = solve(dict(base, freqs=[1e3], nwinc=7, nhinc=3))
    _row(rows, "a strip", "Lp 1 kHz [nH]", r["L"][0, 0, 0] * 1e9, Lhl * 1e9, r["seconds"],
         "7x3 fil")
    # HF estimate: thin strip with the edge-singular (arcsine) current density;
    # <ln d> = ln(w/4) instead of ln(w) - 3/2 and <d> = 4w/pi^2 instead of w/3
    # in Lp = mu0/2pi [l (ln 2l - <ln d> - 1) + <d>]; internal L neglected.
    dL = MU0 / (2 * math.pi) * (-l * (1.5 - math.log(4)) + (4 / math.pi ** 2 - 1 / 3) * w) * 1e-3
    for nw, nh in ((9, 5), (15, 7)):
        r = solve(dict(base, freqs=[1e8], nwinc=nw, nhinc=nh))
        _row(rows, "a strip", "Lp 100 MHz vs HL [nH]", r["L"][0, 0, 0] * 1e9, Lhl * 1e9,
             r["seconds"], "%dx%d fil (ref: uniform-I HL)" % (nw, nh))
    _row(rows, "a strip", "Lp 100 MHz vs HF est [nH]", r["L"][0, 0, 0] * 1e9,
         (Lhl + dL) * 1e9, r["seconds"], "%dx%d fil (ref: HL + edge-crowding est.)" % (nw, nh))


def microstrip_spec(L, workdir, ny_mid=41, nhs=5, nws=9, f=1e8):
    w, h, t = 0.5, 0.2, 0.035
    zs = t + h
    yc = 5.0
    x0 = 5.5
    # plane 40 x 10 mm: fine band under the strip abutting two coarse bands
    planes = [dict(x0=0, y0=0, x1=40, y1=4, z=0, t=t, cells=(40, 8), name="gnd_lo"),
              dict(x0=0, y0=4, x1=40, y1=6, z=0, t=t, cells=(40, ny_mid), name="gnd_mid"),
              dict(x0=0, y0=6, x1=40, y1=10, z=0, t=t, cells=(40, 8), name="gnd_hi")]
    return dict(sigma=5.8e7, freqs=[f], nwinc=nws, nhinc=nhs, plane_nhinc=nhs,
                rects=[dict(x0=x0, y0=yc - w / 2, x1=x0 + L, y1=yc + w / 2, z=zs, t=t,
                            name="strip")],
                planes=planes,
                ports=[dict(p=(x0, yc, zs + t / 2), n=(x0, yc, t / 2), name="P")],
                shorts=[dict(a=(x0 + L, yc, zs + t / 2), b=(x0 + L, yc, t / 2))],
                workdir=workdir)


def test_microstrip(rows, workdir, ny_mid=41, nhs=5, nws=9):
    w, h, t = 0.5, 0.2, 0.035
    f = 1e8
    r20 = solve(microstrip_spec(20.0, workdir, ny_mid, nhs, nws, f))
    r30 = solve(microstrip_spec(30.0, workdir, ny_mid, nhs, nws, f))
    Lp = (r30["L"][0, 0, 0] - r20["L"][0, 0, 0]) / 10e-3   # H/m
    d = skin_depth_mm(f, 5.8e7)
    Lw = wheeler77_L(w, h, t)
    Lh = hammerstad_L(w, h, t)
    # Wheeler incremental-inductance rule: all walls recede by delta/2
    Lw_int = wheeler77_L(w - d, h + d, t - d)
    Lh_int = hammerstad_L(w - d, h + d, t - d)
    print("  microstrip: Wheeler77 %.4g nH/m, Hammerstad %.4g nH/m, Wheeler77 + "
          "internal (delta=%.2f um) %.4g nH/m" % (Lw * 1e9, Lh * 1e9, d * 1e3,
                                                  Lw_int * 1e9))
    disc = "strip %dx%d, gnd mid py=%.3g mm nh=%d" % (nws, nhs, 2.0 / ny_mid, nhs)
    sec = r20["seconds"] + r30["seconds"]
    _row(rows, "b microstrip", "L' (L30-L20) vs W77 [nH/m]", Lp * 1e9, Lw * 1e9, sec, disc)
    _row(rows, "b microstrip", "L' vs W77+internal [nH/m]", Lp * 1e9, Lw_int * 1e9, sec, disc)
    _row(rows, "b microstrip", "L' vs HJ80+internal [nH/m]", Lp * 1e9, Lh_int * 1e9, sec, disc)


def test_loop(rows, workdir, s=0.5, nf=1):
    l1, l2 = 20.0, 10.0
    g = 0.02  # port gap in the bottom bar
    hs = s / 2
    rects = [dict(x0=-hs, y0=-hs, x1=l1 / 2 - g / 2, y1=hs, z=0, t=s, name="bot_l"),
             dict(x0=l1 / 2 + g / 2, y0=-hs, x1=l1 + hs, y1=hs, z=0, t=s, name="bot_r"),
             dict(x0=l1 - hs, y0=-hs, x1=l1 + hs, y1=l2 + hs, z=0, t=s, name="right"),
             dict(x0=-hs, y0=l2 - hs, x1=l1 + hs, y1=l2 + hs, z=0, t=s, name="top"),
             dict(x0=-hs, y0=-hs, x1=hs, y1=l2 + hs, z=0, t=s, name="left")]
    spec = dict(sigma=5.8e7, freqs=[1e3], nwinc=nf, nhinc=nf, rects=rects,
                ports=[dict(p=(l1 / 2 + g / 2, 0, s / 2), n=(l1 / 2 - g / 2, 0, s / 2),
                            name="P")], workdir=workdir)
    r = solve(spec)
    R = 0.44705 * s * 1e-3        # GMD of a square section
    Lg = grover_rect_L(l1 * 1e-3, l2 * 1e-3, R)
    disc = "%dx%d fil, 1 kHz" % (nf, nf)
    _row(rows, "c loop", "L vs Grover, s=%.2g mm [nH]" % s, r["L"][0, 0, 0] * 1e9,
         Lg * 1e9, r["seconds"], disc + " (round wire a=%.3g mm)" % (R * 1e3 / math.exp(-0.25)))
    # exact uniform-current partial-inductance sum of the 5 centreline bars
    # (Hoer-Love self and mutual terms, includes the port gap)
    m = 1e-3
    xb = [(0.0, l1 / 2 - g / 2, 0.0, +1), (l1 / 2 + g / 2, l1, 0.0, +1), (0.0, l1, l2, -1)]
    yb = [(0.0, l2, l1, +1), (0.0, l2, 0.0, -1)]

    def psum(bars):
        tot = 0.0
        for (a0, a1, c, sa) in bars:
            for (b0, b1, d, sb) in bars:
                tot += sa * sb * hoer_love_mutual(s * m, s * m, (a1 - a0) * m, s * m, s * m,
                                                  (b1 - b0) * m, (d - c) * m, 0.0,
                                                  (b0 - a0) * m)
        return tot
    Lx = psum(xb) + psum(yb)
    _row(rows, "c loop", "L vs exact partial sum [nH]", r["L"][0, 0, 0] * 1e9, Lx * 1e9,
         r["seconds"], disc)


def plane_pair_spec(n, workdir, f, nh, sigma=5.8e7, h=0.1, t=0.035, a=20.0, lx=None):
    """Two a x a (or lx x a) plates, gap h; fed along x=0, shorted along x=lx."""
    lx = a if lx is None else lx
    zb, zt = 0.0, t + h
    py = a / n[1]
    ys = [py * (j + 0.5) for j in range(n[1])]
    shorts = []
    for j in range(n[1] - 1):   # equipotential feed edges on both plates
        shorts.append(dict(a=(0, ys[j], zt + t / 2), b=(0, ys[j + 1], zt + t / 2)))
        shorts.append(dict(a=(0, ys[j], t / 2), b=(0, ys[j + 1], t / 2)))
    for y in ys:                 # far edge: top shorted to bottom
        shorts.append(dict(a=(lx, y, zt + t / 2), b=(lx, y, t / 2)))
    return dict(sigma=sigma, freqs=[f], plane_nhinc=nh,
                planes=[dict(x0=0, y0=0, x1=lx, y1=a, z=zb, t=t, cells=n, name="bot"),
                        dict(x0=0, y0=0, x1=lx, y1=a, z=zt, t=t, cells=n, name="top")],
                ports=[dict(p=(0, a / 2, zt + t / 2), n=(0, a / 2, t / 2), name="P")],
                shorts=shorts, workdir=workdir)


def plane_pair_hf_ref(f, sig, W, H, t):
    """2-D L' [H/m] of a wide plate pair at HF: perfect-conductor TEM value with
    Kirchhoff's fringing, C'/eps0 = W/H + (1 + ln(2 pi W/H))/pi, plus the
    internal inductance Im(Zs)/omega of each plate (Zs of a slab of thickness t
    with field on one face only)."""
    Cp = W / H + (1 + math.log(2 * math.pi * W / H)) / math.pi
    return MU0 / Cp + 2 * surface_Lint(f, sig, t) / W


def test_plane_pair(rows, workdir, n=(20, 40), nh_hf=5):
    sig, h, t, a = 5.8e7, 0.1, 0.035, 20.0
    m = 1e-3
    px = a / n[0]
    leff = (a - px) * m        # feed and short node rows are px/2 inside the edges
    disc = "cells %dx%d, l_eff=%.3g mm" % (n[0], n[1], leff / m)
    # (1) 1 kHz, uniform current: exact 3-D partial inductance of two w x t x l_eff
    #     sheets (Hoer-Love), 2*(Lself - M)
    r = solve(plane_pair_spec(n, workdir, 1e3, 1))
    L3 = 2 * (bar_self_L(a * m, t * m, leff)
              - hoer_love_mutual(a * m, t * m, leff, a * m, t * m, leff, 0.0, (h + t) * m, 0.0))
    _row(rows, "d plane pair", "L 1 kHz vs 3-D HL sheets [pH]", r["L"][0, 0, 0] * 1e12,
         L3 * 1e12, r["seconds"], disc + " nh=1")
    L2 = strip_pair_L_uniform(a * m, t * m, (h + t) * m) * leff
    _row(rows, "d plane pair", "L 1 kHz vs mu0(h+2t/3)l/w [pH]", r["L"][0, 0, 0] * 1e12,
         MU0 * (h + 2 * t / 3) * m * leff / (a * m) * 1e12, r["seconds"],
         "2-D, no fringe/ends; 2-D GMD w/ fringe %.5g pH" % (L2 * 1e12))
    # (2) 100 MHz: 2-D TEM + Kirchhoff + internal, raw and length-differenced
    f = 1e8
    Lp_ref = plane_pair_hf_ref(f, sig, a * m, h * m, t * m)
    r20 = solve(plane_pair_spec(n, workdir, f, nh_hf))
    _row(rows, "d plane pair", "L 100 MHz vs 2-D ref*l_eff [pH]", r20["L"][0, 0, 0] * 1e12,
         Lp_ref * leff * 1e12, r20["seconds"], disc + " nh=%d (open ends incl.)" % nh_hf)
    n10 = (n[0] // 2, n[1])
    r10 = solve(plane_pair_spec(n10, workdir, f, nh_hf, lx=a / 2))
    Lp = (r20["L"][0, 0, 0] - r10["L"][0, 0, 0]) / (a / 2 * m)
    _row(rows, "d plane pair", "L' 100 MHz (L20-L10) [nH/m]", Lp * 1e9, Lp_ref * 1e9,
         r20["seconds"] + r10["seconds"], "py=%.3g mm nh=%d" % (a / n[1], nh_hf))
    print("  plane pair 100 MHz: mu0 h/w = %.5g nH/m, ref L' = %.5g nH/m (internal %.4g)"
          % (MU0 * h / a * 1e9, Lp_ref * 1e9,
             2 * surface_Lint(f, sig, t * m) / (a * m) * 1e9))


def smoke_spec(workdir, hole=True):
    """2-port: two traces over a holed plane; trace 1 ends on a pad with a via
    to the plane, trace 2 is shorted to the plane at its far end."""
    t, zt = 0.035, 0.235
    rects = [dict(x0=2, y0=4.75, x1=18, y1=5.25, z=zt, t=t, name="tr1"),
             dict(x0=17.5, y0=4.25, x1=19, y1=5.75, z=zt, t=t, name="pad"),
             dict(x0=2, y0=8.25, x1=18, y1=8.75, z=zt, t=t, name="tr2")]
    plane = dict(x0=0, y0=0, x1=20, y1=10, z=0, t=t, cells=(40, 20), name="gnd",
                 holes=[(8, 3, 12, 7)] if hole else [])
    top, bot = zt + t / 2, t / 2
    return dict(sigma=5.8e7, freqs=[1e7], rects=rects, planes=[plane],
                vias=[dict(x=18.5, y=5.0, z0=top, z1=bot, d=0.3)],
                ports=[dict(p=(2, 5, top), n=(2.25, 5, bot), name="P1"),
                       dict(p=(2, 8.5, top), n=(2.25, 8.75, bot), name="P2")],
                shorts=[dict(a=(18, 8.5, top), b=(18.25, 8.75, bot))],
                workdir=workdir)


def test_smoke(rows, workdir):
    r = solve(smoke_spec(workdir, hole=True))
    r0 = solve(smoke_spec(workdir, hole=False))
    Z, L = r["Z"][0], r["L"][0]
    asym = abs(Z[0, 1] - Z[1, 0]) / abs(Z[0, 1])
    print("  smoke: Z12 vs Z21 rel. diff %.2e, eig(R) %s, L11 hole/no hole %.4g/%.4g nH,"
          " warnings %s" % (asym, np.linalg.eigvalsh((Z.real + Z.real.T) / 2),
                            L[0, 0] * 1e9, r0["L"][0][0, 0] * 1e9, r["warnings"]))
    rows.append(("e smoke", "|Z12-Z21|/|Z12|", asym, 0.0, float("nan"), r["seconds"],
                 "via+hole+pad, solver %s, %d fil" % (r["solver"], r["nfil"]), ""))
    _row(rows, "e smoke", "L11 with hole / without", L[0, 0] / r0["L"][0][0, 0], 1.0,
         r["seconds"] + r0["seconds"], "expect > 1 (return path detours)")


def selftest(quick=False):
    workdir = os.environ.get("KAE_REF_WORKDIR") or tempfile.mkdtemp(prefix="fhself_")
    rows = []
    print("FastHenry:", fasthenry_bin(), " workdir:", workdir)
    test_strip(rows, workdir)
    test_loop(rows, workdir)
    test_loop(rows, workdir, s=0.2)
    if quick:   # coarse, ~1 min: the HF rows then carry a few % discretization error
        test_microstrip(rows, workdir, ny_mid=21, nhs=3, nws=7)
        test_plane_pair(rows, workdir, n=(10, 20), nh_hf=3)
    else:
        test_microstrip(rows, workdir)
        test_plane_pair(rows, workdir)
        test_smoke(rows, workdir)
    print()
    print("%-13s %-30s %12s %12s %8s %8s  %s" % ("test", "quantity", "FastHenry",
                                                 "analytic", "err %", "sec", "discretization"))
    for t, q, v, ref, e, s, d, _ in rows:
        print("%-13s %-30s %12.6g %12.6g %8.3f %8.1f  %s" % (t, q, v, ref, e, s, d))
    return rows


def main(argv):
    if len(argv) >= 1 and argv[0] == "selftest":
        selftest(quick="--quick" in argv)
        return 0
    if len(argv) == 2 and argv[0] == "solve":
        with open(argv[1]) as fh:
            spec = json.load(fh)
        r = solve(spec)
        out = dict(freqs=r["freqs"], ports=r["ports"],
                   Z_re=r["Z"].real.tolist(), Z_im=r["Z"].imag.tolist(),
                   seconds=r["seconds"], log=r["log"], warnings=r["warnings"],
                   snaps=r["snaps"])
        json.dump(out, sys.stdout, indent=1)
        print()
        return 0
    if len(argv) == 2 and argv[0] == "deck":
        with open(argv[1]) as fh:
            print(build_deck(json.load(fh))[0])
        return 0
    print("usage: ref_fasthenry.py selftest [--quick] | solve spec.json | deck spec.json")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
