# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Place-term estimators vs exact kernels (docs/topics/physics/place-terms.md, Validation).

Each section builds the same geometry for an exact (or finer) solver and for the fast
estimator in kae.physics, and reports the error distribution. Sections:

  loop_peec     (a) commutation cells, routed around their pads (grid A*), PEEC
                (pw_peec, filament partial inductances with a PEC plane) vs the closed
                forms of kae.physics.kernels.loop_L on the same routed segments, and vs the
                placement estimator (jit loop_core on straight pad-to-pad hops);
  decap_peec    (b) decoupling loops (0402 cap at a QFN pin pair), same three ways;
  oblique       loop_core vs loop_L on random oblique straight-hop loops: what the fast
                path's pair pruning and projected-parallel approximation cost;
  spread        plane-pair spreading between two vias, (mu0 d / pi) ln(D / r), vs the
                finite-plane sheet solve of pw_sheet;
  esd           surge path (strip + via) L' l + L_via vs PEEC;
  coupling_l    (c) aggressor loop -> victim loop mutual inductance: loop_mutual_core vs
                the EMF PEEC induces in a probe path (pw_peec Net.induced);
  coupling_c    (c) patch mutual capacitance: patches_cm_core (first order in potential
                coefficients, air-side strengths) vs a method-of-moments solve with the
                plane image (air);
  cprime        (d) per-length trace capacitance (Hammerstad-Jensen) vs fe_field2d;
  thermal       (e) fin kernel with edge images (rings 0, 1, 2) vs tm_board_thermal_fv;
  rb_hf         (a) on human boards: estimator vs rb_board_passports' HF loop L of the
                same cell (kae-work/physics/human-k10-mmd; rb is uncalibrated: ranks).

Usage:
  python tools/research/physics/pt_validate_kernels.py [--only loop_peec,thermal] [--out DIR] [--quick]
Needs kae/.venv (numpy, scipy, shapely). Deterministic. About 5 minutes on one core.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'kae' / 'src'))
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

import pw_peec as pw  # noqa: E402
from kae.physics import kernels as K  # noqa: E402
from kae.physics.jit import GAUSS, PY  # noqa: E402

MM = 1e-3


def stats(est, ref):
    est = np.asarray(est, float)
    ref = np.asarray(ref, float)
    if len(est) == 0:
        return dict(n=0, median_abs=float('nan'), p90_abs=float('nan'), max_abs=float('nan'), bias=float('nan'))
    e = est / ref - 1.0
    a = np.abs(e)
    out = dict(n=int(len(e)), median_abs=float(np.median(a)), p90_abs=float(np.percentile(a, 90)),
               max_abs=float(a.max()), bias=float(np.median(e)))
    if len(e) > 3:
        out['spearman'] = float(spearmanr(est, ref).statistic)
    return out


def fmt(s):
    t = f"n {s['n']}: median |err| {100 * s['median_abs']:.1f}%, p90 {100 * s['p90_abs']:.1f}%, max {100 * s['max_abs']:.1f}%, " \
        f"median bias {100 * s['bias']:+.1f}%"
    if 'spearman' in s:
        t += f", Spearman {s['spearman']:.3f}"
    return t


# ============================================================================ geometry (loops)
def _rot(a):
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return lambda u, v: (u * c + v * s, -u * s + v * c)


def route(start, goal, blocked, x0, y0, res):
    """Manhattan grid A* with a turn penalty; returns corner points or None."""
    import heapq
    ny, nx = blocked.shape

    def cell(p):
        return (int(round((p[0] - x0) / res)), int(round((p[1] - y0) / res)))
    s, g = cell(start), cell(goal)
    blk = blocked.copy()
    for (i, j) in (s, g):
        if 0 <= i < nx and 0 <= j < ny:
            blk[j, i] = False
    dirs = ((1, 0), (-1, 0), (0, 1), (0, -1))
    best = {(s, -1): 0.0}
    prev = {}
    pq = [(abs(s[0] - g[0]) + abs(s[1] - g[1]), 0.0, s, -1)]
    while pq:
        _, cost, c, d = heapq.heappop(pq)
        if c == g:
            path = [c]
            key = (c, d)
            while key in prev:
                key = prev[key]
                path.append(key[0])
            pts = [(x0 + i * res, y0 + j * res) for i, j in path[::-1]]
            pts[0], pts[-1] = tuple(start), tuple(goal)
            return _simplify(pts)
        if best.get((c, d), 1e18) < cost - 1e-12:
            continue
        for k, (di, dj) in enumerate(dirs):
            n = (c[0] + di, c[1] + dj)
            if not (0 <= n[0] < nx and 0 <= n[1] < ny) or blk[n[1], n[0]]:
                continue
            nc = cost + 1.0 + (2.0 if (d != -1 and d != k) else 0.0)
            if nc < best.get((n, k), 1e18) - 1e-12:
                best[(n, k)] = nc
                prev[(n, k)] = (c, d)
                heapq.heappush(pq, (nc + abs(n[0] - g[0]) + abs(n[1] - g[1]), nc, n, k))
    return None


def _simplify(pts):
    out = [pts[0]]
    for p in pts[1:]:
        out.append(p)
        while len(out) >= 3:
            a, b, c = out[-3], out[-2], out[-1]
            if (abs(a[0] - b[0]) < 1e-9 and abs(b[0] - c[0]) < 1e-9) or (abs(a[1] - b[1]) < 1e-9 and abs(b[1] - c[1]) < 1e-9):
                out.pop(-2)
            else:
                break
    res = [out[0]]
    for p in out[1:]:
        q = res[-1]
        if abs(p[0] - q[0]) > 1e-9 and abs(p[1] - q[1]) > 1e-9:
            res.append((p[0], q[1]))
        res.append(p)
    return res


def _blocked(rects, x0, y0, res, nx, ny):
    xs = x0 + np.arange(nx) * res
    ys = y0 + np.arange(ny) * res
    X, Y = np.meshgrid(xs, ys)
    b = np.zeros((ny, nx), bool)
    for (a0, b0, a1, b1) in rects:
        b |= (X >= a0) & (X <= a1) & (Y >= b0) & (Y <= b1)
    return b


def cell_geometry(cfg):
    """Terminals of a loop: cap + pad Cp and - pad Cm (cap centred at cfg['cap_center'],
    rotated cfg['cap_rot']), IC supply pin VIN at (0, +p/2) and return pin GND at (0, -p/2)."""
    pc = cfg['cap'][0]
    pi_ = cfg['ic'][0]
    R = _rot(cfg['cap_rot'])
    cx, cy = cfg['cap_center']
    dp, dm = R(0, pc / 2), R(0, -pc / 2)
    return (cx + dp[0], cy + dp[1]), (cx + dm[0], cy + dm[1]), (0.0, pi_ / 2), (0.0, -pi_ / 2)


def cell_segments(cfg):
    """Routed 3-D segments (mm) of the loop Cm -> Cp (cap body) -> VIN (trace) -> GND (IC
    internal path) -> Cm (trace, or vias through the plane), over a plane at z = 0."""
    h, w = cfg['h'], cfg['w']
    pc, bw, bz = cfg['cap']
    pi_, iw, iz = cfg['ic']
    Cp, Cm, VIN, GND = cell_geometry(cfg)
    segs = []

    def strip(path, z):
        for a, b in zip(path[:-1], path[1:]):
            segs.append(dict(p0=(a[0], a[1], z), p1=(b[0], b[1], z), w=w))

    def body(a, b, z0, z1, bwid):
        g = K.gmd_rect(bwid)
        segs.append(dict(p0=(a[0], a[1], z0), p1=(a[0], a[1], z1), r=g, plate=True, b=bwid))
        for p, q in zip(_manhattan(a, b)[:-1], _manhattan(a, b)[1:]):
            segs.append(dict(p0=(p[0], p[1], z1), p1=(q[0], q[1], z1), w=bwid, t=0.1))
        segs.append(dict(p0=(b[0], b[1], z1), p1=(b[0], b[1], z0), r=g, plate=True, b=bwid))
    rv = cfg.get('via_r', 0.15)
    if cfg['ret'] == 'via':
        segs.append(dict(p0=(Cm[0], Cm[1], 0.0), p1=(Cm[0], Cm[1], h), r=rv))
    body(Cm, Cp, h, h + bz, bw)
    clr, res = cfg.get('clr', 0.2), cfg.get('res', 0.05)
    xs = [Cp[0], Cm[0], VIN[0], GND[0]]
    ys = [Cp[1], Cm[1], VIN[1], GND[1]]
    m = 4.0 + w
    x0, y0 = min(xs) - m, min(ys) - m
    nx, ny = int((max(xs) + m - x0) / res) + 1, int((max(ys) + m - y0) / res) + 1
    half = w / 2 + clr

    def padrect(p, s=0.45):
        return (p[0] - s - half, p[1] - s - half, p[0] + s + half, p[1] + s + half)
    sp = cfg.get('pad', 0.45)
    ip = cfg.get('icpad', 0.25)
    vin = route(Cp, VIN, _blocked([padrect(Cm, sp), padrect(GND, ip)], x0, y0, res, nx, ny), x0, y0, res)
    if vin is None:
        return None
    strip(vin, h)
    body(VIN, GND, h, h + iz, iw)
    if cfg['ret'] == 'lateral':
        obst = [padrect(Cp, sp), padrect(VIN, ip)] + [(min(p[0], q[0]) - w - clr, min(p[1], q[1]) - w - clr,
                                                         max(p[0], q[0]) + w + clr, max(p[1], q[1]) + w + clr)
                                                        for p, q in zip(vin[:-1], vin[1:])]
        gnd = route(GND, Cm, _blocked(obst, x0, y0, res, nx, ny), x0, y0, res)
        if gnd is None:
            return None
        strip(gnd, h)
    else:
        segs.append(dict(p0=(GND[0], GND[1], h), p1=(GND[0], GND[1], 0.0), r=rv))
    return segs


def _manhattan(p, q):
    (x0, y0), (x1, y1) = p, q
    if abs(x0 - x1) < 1e-9 or abs(y0 - y1) < 1e-9:
        return [p, q]
    return [p, (x1, y0), q]


def peec_L(segs, t=0.035):
    """PEEC loop inductance (nH) of a closed chain of axis-aligned segments; a chain that
    starts and ends on the plane (z = 0) is closed through the plane."""
    net = pw.Net(plane_z=0.0)
    n = len(segs)
    plane_end = abs(segs[0]['p0'][2]) < 1e-9 and abs(segs[-1]['p1'][2]) < 1e-9
    for k, s in enumerate(segs):
        a = 'P' if k == 0 else f'N{k}'
        b = f'N{k + 1}' if k < n - 1 else ('PLANE' if plane_end else 'N0')
        p0 = np.array(s['p0'], float)
        p1 = np.array(s['p1'], float)
        d = p1 - p0
        ax = int(np.argmax(np.abs(d)))
        L = float(abs(d[ax]))
        if L < 1e-9:
            net.tie(a, b)
            continue
        if ax == 2:
            if 'r' in s and not s.get('plate'):
                ztop, zbot = max(p0[2], p1[2]), min(p0[2], p1[2])
                if p0[2] > p1[2]:
                    net.via(a, b, p0[0] * MM, p0[1] * MM, ztop * MM, zbot * MM, r=s['r'] * MM, n=6)
                else:
                    net.via(b, a, p0[0] * MM, p0[1] * MM, ztop * MM, zbot * MM, r=s['r'] * MM, n=6)
            else:
                bw = s.get('b', 0.5)
                lo = min(p0[2], p1[2])
                ids = net.bar(a, b, ((p0[0] - 0.015) * MM, (p0[1] - bw / 2) * MM, lo * MM), 2, L * MM, 0.03 * MM,
                              bw * MM, nw=1, nt=8)
                if p1[2] < p0[2]:
                    net.bars[-1] = (b, a, ids)
            continue
        w = s['w']
        z = p0[2]
        th = s.get('t', t)
        nw = max(1, min(pw._nw(w * MM, z * MM), 60, int(w / (1.2 * th))))
        lo = min(p0[ax], p1[ax])
        corner = (lo * MM, (p0[1] - w / 2) * MM, z * MM) if ax == 0 else ((p0[0] - w / 2) * MM, lo * MM, z * MM)
        ids = net.bar(a, b, corner, ax, L * MM, w * MM, th * MM, nw=nw, nt=1)
        if p1[ax] < p0[ax]:
            net.bars[-1] = (b, a, ids)
    return net.L_port('P', 'PLANE' if plane_end else 'N0') * 1e9


def estimator_L(cfg, clr=0.15):
    """The placement estimator (jit loop_core, as LoopComp calls it) on straight pad-to-pad
    hops: terminals [Cp, VIN, GND, Cm]; hops Cp->VIN (trace), VIN->GND (IC body), GND->Cm
    (ground hop: via return through the plane when cfg['ret'] == 'via'), Cm->Cp (cap body)."""
    h, w = cfg['h'], cfg['w']
    pc, bw, bz = cfg['cap']
    pi_, iw, iz = cfg['ic']
    cx, cy = cfg['cap_center']
    a = math.radians(cfg['cap_rot'])
    X = np.array([cx, 0.0])
    Y = np.array([cy, 0.0])
    C = np.array([math.cos(a), 1.0])
    S = np.array([math.sin(a), 0.0])
    G = np.ones(2)
    ti = np.array([0, 1, 1, 0], np.int64)
    tlx = np.zeros(4)
    tly = np.array([pc / 2, pi_ / 2, -pi_ / 2, -pc / 2])
    isbody = np.array([False, True, False, True])
    widths = np.array([w, iw, w, bw])
    zb = np.array([0.0, iz, 0.0, bz])
    bodyd = np.array([0.0, pi_, 0.0, pc])
    H = np.full((81, 81), float(h))
    N = np.zeros((81, 81), np.int32)
    gmask = np.array([cfg['ret'] == 'via'])
    scr = (np.zeros(4), np.zeros(4), np.zeros(4))
    return PY.loop_core(X, Y, C, S, G, ti, tlx, tly, isbody, widths, zb, bodyd, 4, 2, 0.3, clr, 1.0, 1.6, 0.15,
                        H, H, N, N, gmask, -20.0, -20.0, 0.5, *scr)


def loop_section(name, cap, ic, hs, ws, ds, rets, yc=0.3, quick=False, extra=None):
    rows = []
    t0 = time.time()
    for h in hs:
        for w in ws:
            for d in ds:
                for rot in (0, 90, 180, 270):
                    for ret in rets:
                        cfg = dict(h=h, w=w, cap=cap, ic=ic, cap_center=(-d, yc), cap_rot=rot, ret=ret, **(extra or {}))
                        segs = cell_segments(cfg)
                        if segs is None:
                            continue
                        try:
                            Lp = peec_L(segs)
                        except ValueError:
                            continue
                        rows.append(dict(h=h, w=w, d=d, rot=rot, ret=ret, peec=Lp, closed=K.loop_L(segs),
                                         est=estimator_L(cfg)))
    out = dict(cases=len(rows), seconds=round(time.time() - t0, 1),
               closed_vs_peec=stats([r['closed'] for r in rows], [r['peec'] for r in rows]),
               estimator_vs_peec=stats([r['est'] for r in rows], [r['peec'] for r in rows]))
    for ret in rets:
        rr = [r for r in rows if r['ret'] == ret]
        if rr:
            out[f'estimator_vs_peec_{ret}'] = stats([r['est'] for r in rr], [r['peec'] for r in rr])
    # monotonicity: does the estimator order the cap positions of one geometry as PEEC does?
    agree = tot = 0
    keys = {(r['h'], r['w'], r['ret']) for r in rows}
    for k in keys:
        rr = [r for r in rows if (r['h'], r['w'], r['ret']) == k]
        for i in range(len(rr)):
            for j in range(i + 1, len(rr)):
                dp = rr[i]['peec'] - rr[j]['peec']
                if abs(dp) < 0.02 * max(rr[i]['peec'], rr[j]['peec']):
                    continue
                tot += 1
                agree += (dp > 0) == (rr[i]['est'] - rr[j]['est'] > 0)
    out['pairwise_order_agreement'] = agree / tot if tot else float('nan')
    out['pairs'] = tot
    print(f"[{name}] {len(rows)} routed loops ({out['seconds']} s)")
    print(f"  closed forms (loop_L on the routed segments) vs PEEC: {fmt(out['closed_vs_peec'])}")
    print(f"  estimator (straight hops) vs PEEC on the routed loop:  {fmt(out['estimator_vs_peec'])}")
    for ret in rets:
        if f'estimator_vs_peec_{ret}' in out:
            print(f"    return {ret:8s}: {fmt(out[f'estimator_vs_peec_{ret}'])}")
    print(f"  pairwise order (cap positions of one h, w, return; PEEC differs > 2%): estimator agrees "
          f"{100 * out['pairwise_order_agreement']:.1f}% of {tot}")
    return out


def sec_loop_peec(quick):
    hs = (0.1, 0.4, 1.5) if quick else (0.1, 0.2, 0.4, 0.8, 1.5)
    return loop_section('loop_peec', cap=(1.9, 1.25, 0.4), ic=(0.95, 0.3, 0.25), hs=hs, ws=(0.4, 1.0, 2.0),
                        ds=(2.5, 4.0, 7.0), rets=('lateral', 'via'))


def sec_decap_peec(quick):
    hs = (0.1, 0.4) if quick else (0.1, 0.2, 0.4, 1.0)
    return loop_section('decap_peec', cap=(1.0, 0.5, 0.25), ic=(0.5, 0.25, 0.2), hs=hs, ws=(0.25, 0.5),
                        ds=(1.5, 3.0, 5.0), rets=('lateral', 'via'), yc=0.0,
                        extra=dict(pad=0.25, icpad=0.1, clr=0.1, res=0.025, via_r=0.1))


# ============================================================================ oblique pruning
def sec_oblique(quick):
    """Random oblique 4-terminal loops (two parts, straight hops): loop_core (pairs with
    |cos| < 0.3 dropped; oblique pairs as parallel filaments at their mean distance) vs
    loop_L on identical segments (every pair, oblique ones by quadrature)."""
    rng = np.random.default_rng(7)
    est, ref = [], []
    n = 150 if quick else 400
    t0 = time.time()
    while len(est) < n:
        h = float(np.exp(rng.uniform(math.log(0.1), math.log(1.5))))
        w = float(rng.uniform(0.25, 1.0))
        pc, pi_ = float(rng.uniform(w + 0.7, 4.0)), float(rng.uniform(w + 0.7, 4.0))
        cx, cy = float(rng.uniform(-10, 10)), float(rng.uniform(-10, 10))
        if math.hypot(cx, cy) < 3.0 + 0.5 * (pc + pi_):
            continue
        rc = float(rng.uniform(0, 360))
        ri = float(rng.uniform(0, 360))
        a, b = math.radians(rc), math.radians(ri)
        X = np.array([cx, 0.0])
        Y = np.array([cy, 0.0])
        C = np.array([math.cos(a), math.cos(b)])
        S = np.array([math.sin(a), math.sin(b)])
        G = np.ones(2)
        ti = np.array([0, 1, 1, 0], np.int64)
        tlx = np.zeros(4)
        tly = np.array([pc / 2, pi_ / 2, -pi_ / 2, -pc / 2])
        P = [(X[i] + tlx[k] * C[i] + tly[k] * S[i], Y[i] - tlx[k] * S[i] + tly[k] * C[i]) for k, i in enumerate(ti)]
        # skip self-crossing quadrilaterals (the straight model of a loop that must be routed)
        # and near-coincident sides, where the estimator's guards (separation floor, under-part
        # hops) deliberately depart from the filament sum: this section measures the pruning
        # and the projected-parallel approximation alone
        if _segs_cross(P[0], P[1], P[2], P[3]):
            continue
        if min(_seg_dist2(P[0], P[1], P[2], P[3]), _seg_dist2(P[1], P[2], P[3], P[0])) < 1.5 + w:
            continue
        widths = np.array([w, 0.3, w, 1.0])
        zb = np.array([0.0, 0.25, 0.0, 0.4])
        bodyd = np.array([0.0, pi_, 0.0, pc])
        H = np.full((81, 81), h)
        N = np.zeros((81, 81), np.int32)
        scr = (np.zeros(4), np.zeros(4), np.zeros(4))
        L = PY.loop_core(X, Y, C, S, G, ti, tlx, tly, np.array([False, True, False, True]), widths, zb, bodyd, 4, -1,
                         0.3, 0.15, 1.0, 1.6, 0.15, H, H, N, N, np.array([False]), -20.0, -20.0, 0.5, *scr)
        segs = []
        for k in range(4):
            p, q = P[k], P[(k + 1) % 4]
            if k in (1, 3):
                z = zb[k]
                r = K.gmd_rect(widths[k])
                segs.append(dict(p0=(p[0], p[1], h), p1=(p[0], p[1], h + z), r=r))
                segs.append(dict(p0=(p[0], p[1], h + z), p1=(q[0], q[1], h + z), w=widths[k]))
                segs.append(dict(p0=(q[0], q[1], h + z), p1=(q[0], q[1], h), r=r))
            else:
                segs.append(dict(p0=(p[0], p[1], h), p1=(q[0], q[1], h), w=widths[k]))
        est.append(L)
        ref.append(K.loop_L(segs))
    s = stats(est, ref)
    print(f"[oblique] loop_core vs loop_L (all pairs, quadrature) on {n} random oblique loops, opposite sides >= w + 0.5 mm "
          f"apart ({time.time() - t0:.1f} s): {fmt(s)}")
    return s


def _seg_dist2(a, b, c, d, n=24):
    """Minimum distance between 2-D segments a-b and c-d (sampled)."""
    t = np.linspace(0.0, 1.0, n)
    P = np.array(a)[None, :] + t[:, None] * (np.array(b) - np.array(a))[None, :]
    Q = np.array(c)[None, :] + t[:, None] * (np.array(d) - np.array(c))[None, :]
    return float(np.sqrt(((P[:, None, :] - Q[None, :, :]) ** 2).sum(-1)).min())


def _segs_cross(p0, p1, p2, p3):
    """True when the quadrilateral p0 p1 p2 p3 has crossing opposite sides."""
    def ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])

    def inter(a, b, c, d):
        return ccw(a, c, d) != ccw(b, c, d) and ccw(a, b, c) != ccw(a, b, d)
    return inter(p0, p1, p2, p3) or inter(p1, p2, p3, p0)


# ============================================================================ spreading
def sec_spread(quick):
    """Plane-pair spreading between two vias: PlanePairLoop's (mu0 d / pi) ln(D / r) vs the
    sheet solve (pw_sheet, Peaceman well correction) on a finite square plane."""
    import pw_sheet as sh
    rv = 0.15
    rows = []
    for size, dx in ((60.0, 0.25),) if quick else ((60.0, 0.25), (30.0, 0.125)):
        n = int(size / dx)
        m = np.ones((n, n), bool)
        c = n // 2
        for D in (1.0, 2.0, 5.0, 10.0, 20.0):
            k = int(round(D / dx))
            if k >= n // 2:
                continue
            ea = np.zeros_like(m)
            eb = np.zeros_like(m)
            ea[c, c - k // 2] = True
            eb[c, c - k // 2 + k] = True
            nsq = sh.squares(m, ea, eb) + 2 * sh.peaceman_sq(dx * MM, rv * MM)
            rows.append(dict(plane=size, D=D, sheet=nsq, formula=math.log(D / rv) / math.pi))
    s = stats([r['formula'] for r in rows], [r['sheet'] for r in rows])
    print(f"[spread] (1/pi) ln(D/r) vs the finite-plane sheet solve: {fmt(s)}")
    for r in rows:
        print(f"    plane {r['plane']:.0f} mm, D {r['D']:5.1f} mm: N_sq sheet {r['sheet']:.3f}, formula {r['formula']:.3f}")
    return dict(stats=s, rows=rows)


# ============================================================================ ESD surge path
def sec_esd(quick):
    """Surge path connector pin -> strip of length l at height h -> protector -> via into
    the plane (connector side closed through its own pin/via): EsdComp's L'(w,h) l + vias
    vs PEEC."""
    from kae.physics import fastloop as FL
    rows = []
    for h in (0.1, 0.2, 0.4, 0.8):
        for ln in (2.0, 5.0, 10.0, 20.0):
            w = 0.25
            segs = [dict(p0=(0.0, 0.0, 0.0), p1=(0.0, 0.0, h), r=0.15),
                    dict(p0=(0.0, 0.0, h), p1=(ln, 0.0, h), w=w),
                    dict(p0=(ln, 0.0, h), p1=(ln, 0.0, 0.0), r=0.15)]
            Lp = peec_L(segs)
            lv = FL.m_self(h, 0.15) + FL._collinear(h, h, 0.0)
            one = K.lprime_hj(w, h) * ln + lv
            rows.append(dict(h=h, l=ln, peec=Lp, est_one_via=one, est_two_vias=one + lv))
    s1 = stats([r['est_one_via'] for r in rows], [r['peec'] for r in rows])
    s2 = stats([r['est_two_vias'] for r in rows], [r['peec'] for r in rows])
    print(f"[esd] surge path L' l + L_via vs PEEC: {fmt(s1)}")
    print(f"      with the connector-side via as well:   {fmt(s2)}")
    return dict(one_via=s1, two_vias=s2, rows=rows)


# ============================================================================ inductive coupling
def _rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def sec_coupling_l(quick):
    """Aggressor: closed strip loop (go and return strips joined at both ends) at height h over
    the plane, solved by PEEC (current spread over the strip width, plane images). Victim:
    a probe path, closed (rectangle at height hv) or closed through the plane (open path with
    vertical legs to the plane). M from the PEEC currents (Net.induced) vs loop_mutual_core."""
    rows = []
    t0 = time.time()
    for h in (0.1, 0.4):
        l, w, s = 6.0, 0.6, 1.0
        net, port = pw.lateral_loop(l * MM, w * MM, s * MM, h * MM, nw=pw._nw(w * MM, h * MM))
        # lateral_loop places the strips on z0 = 0 with the plane at -h: shift our frame by h
        _, I = net.solve(port[0], port[1])
        I = I.real
        # aggressor polygon (centre lines) at height h above the plane
        y_go, y_ret = w / 2, w + s + w / 2
        PA = np.array([(-w / 2, y_go), (l + w / 2, y_go), (l + w / 2, y_ret), (-w / 2, y_ret)])
        for closed in (True, False):
            for dx_, dy_ in ((0.0, 4.0), (0.0, 8.0), (3.0, 6.0), (8.0, 0.0), (12.0, 3.0), (0.0, 20.0)):
                a, b = 3.0, 2.0
                x0, y0 = l / 2 + dx_ - a / 2, y_ret + dy_
                if dy_ == 0.0:
                    x0, y0 = l + dx_, -b / 2
                hv = h
                corners = _rect(x0, y0, x0 + a, y0 + b)
                if closed:
                    pts = corners + [corners[0]]
                    path = []
                    for p, q in zip(pts[:-1], pts[1:]):
                        ax = 0 if abs(q[0] - p[0]) > 1e-9 else 1
                        ln = (q[ax] - p[ax])
                        path.append(((p[0] * MM, p[1] * MM, 0.0), ax, ln * MM))
                    PV = np.array(corners)
                else:
                    pts = corners[:3]
                    path = [((pts[0][0] * MM, pts[0][1] * MM, -hv * MM), 2, hv * MM)]
                    for p, q in zip(pts[:-1], pts[1:]):
                        ax = 0 if abs(q[0] - p[0]) > 1e-9 else 1
                        path.append(((p[0] * MM, p[1] * MM, 0.0), ax, (q[ax] - p[ax]) * MM))
                    path.append(((pts[-1][0] * MM, pts[-1][1] * MM, 0.0), 2, -hv * MM))
                    PV = np.array(pts)
                Mp = abs(net.induced(path, I)) * 1e9
                sc = tuple(np.zeros((512, 3)) for _ in range(4))
                Me = PY.loop_mutual_core(PA, True, h, PV, closed, hv, h, *GAUSS, *sc)
                rows.append(dict(h=h, closed=closed, dx=dx_, dy=dy_, peec=Mp, est=Me))
    ok = [r for r in rows if r['peec'] > 1e-6]
    s = stats([r['est'] for r in ok], [r['peec'] for r in ok])
    print(f"[coupling_l] loop-loop mutual, loop_mutual_core vs PEEC-induced EMF ({time.time() - t0:.1f} s): {fmt(s)}")
    for r in rows:
        print(f"    h {r['h']:.1f} {'closed ' if r['closed'] else 'via-leg'} offset ({r['dx']:4.1f},{r['dy']:4.1f}) mm: "
              f"PEEC {1e3 * r['peec']:8.3f} pH, estimator {1e3 * r['est']:8.3f} pH")
    return dict(stats=s, rows=rows)


# ============================================================================ capacitive coupling
def mom_caps(patches, h, n=8):
    """Capacitance matrix (pF) of square patches (x, y, side mm) at height h over a ground
    plane, in air: point-matched method of moments with pulse charges and the plane image."""
    eps0 = K.EPS0       # pF/mm
    cells = []
    owner = []
    for pi_, (x, y, s) in enumerate(patches):
        a = s / n
        for i in range(n):
            for j in range(n):
                cells.append((x - s / 2 + (i + 0.5) * a, y - s / 2 + (j + 0.5) * a, a))
                owner.append(pi_)
    c = np.array(cells)
    X, Y, A = c[:, 0], c[:, 1], c[:, 2]
    R = np.hypot(X[:, None] - X[None, :], Y[:, None] - Y[None, :])
    Ri = np.sqrt(R * R + (2 * h) ** 2)
    k = 1.0 / (4 * math.pi * eps0)
    with np.errstate(divide='ignore'):
        P = k * (1.0 / R - 1.0 / Ri)
    # self term: potential at the centre of a uniformly charged square of side a, per unit charge
    np.fill_diagonal(P, k * (4.0 * math.log(1 + math.sqrt(2)) / A - 1.0 / (2 * h)))
    Cc = np.linalg.inv(P)
    owner = np.array(owner)
    m = len(patches)
    Cm = np.zeros((m, m))
    for a_ in range(m):
        for b_ in range(m):
            Cm[a_, b_] = Cc[np.ix_(owner == a_, owner == b_)].sum()
    return Cm


def sec_coupling_c(quick):
    rows = []
    t0 = time.time()
    for h in (0.1, 0.2, 0.5):
        for side in (0.5, 1.0):
            for r_over in (2.0, 3.0, 5.0, 10.0, 20.0):
                r = r_over * side
                Cm = mom_caps([(0.0, 0.0, side), (r, 0.0, side)], h, n=8 if not quick else 6)
                ref = -Cm[0, 1]
                A = side * side
                est = PY.patches_cm_core(np.array([0.0]), np.array([0.0]), np.array([A]), np.array([r]),
                                         np.array([0.0]), np.array([A]), h, 1.0, K.EPS0)
                rows.append(dict(h=h, side=side, r=r, ref=ref, est=est))
    s = stats([r['est'] for r in rows], [r['ref'] for r in rows])
    far = [r for r in rows if r['r'] / r['side'] >= 5]
    sf = stats([r['est'] for r in far], [r['ref'] for r in far])
    print(f"[coupling_c] patch mutual C, first-order kernel vs MoM (air) ({time.time() - t0:.1f} s): {fmt(s)}")
    print(f"             centre distance >= 5 sides: {fmt(sf)}")
    return dict(stats=s, far=sf, rows=rows)


# ============================================================================ C' (crystal)
def sec_cprime(quick):
    import fe_field2d as fe
    rows = []
    t0 = time.time()
    cases = ((0.2, 0.1), (0.2, 0.2), (0.4, 0.2)) if quick else ((0.15, 0.1), (0.2, 0.1), (0.5, 0.1), (0.2, 0.2),
                                                                (0.4, 0.2), (0.25, 0.5), (0.2, 1.5))
    for w, h in cases:
        er = 4.3
        t = 0.035
        dx = min(w, h) / 10.0
        X, Y = max(2.0, 6 * h + 3 * w) * MM, max(2.0, 8 * h) * MM
        C = fe.solve_caps(X, Y, dx * MM, [(0, h * MM, er)], [(-w / 2 * MM, w / 2 * MM, h * MM, (h + t) * MM)])
        ref = C[0, 0] * 1e12 / 1e3         # pF/mm
        est = K.cprime_hj(w, h, er)
        rows.append(dict(w=w, h=h, ref=ref, est=est))
    s = stats([r['est'] for r in rows], [r['ref'] for r in rows])
    print(f"[cprime] microstrip C' Hammerstad-Jensen vs fe_field2d ({time.time() - t0:.1f} s): {fmt(s)}")
    for r in rows:
        print(f"    w {r['w']:.2f} h {r['h']:.2f}: field {r['ref']:.4f} pF/mm, closed form {r['est']:.4f}")
    return dict(stats=s, rows=rows)


# ============================================================================ thermal
def sec_thermal(quick):
    """2-layer 1 oz board with full planes, 60 x 40 mm, h = 10 W/m^2K per side; sources as
    3 x 3 mm pads. FV temperature at each source centre and at probe points vs the fin kernel
    with 0, 1, 2 rings of adiabatic-edge images (ThermalField)."""
    import tm_board_thermal_fv as tm
    from kae.physics.kernels import fin_params
    from kae.physics.structures import State, ThermalField
    lx, ly = 60.0, 40.0
    srcs = [(10.0, 10.0, 1.0), (30.0, 20.0, 0.5), (52.0, 32.0, 0.8), (45.0, 8.0, 0.3), (3.0, 37.0, 0.4)]
    probes = [(20.0, 20.0), (40.0, 30.0), (57.0, 5.0), (5.0, 25.0)]
    b = tm.two_layer(lx=lx * MM, ly=ly * MM, dx=0.5 * MM)
    b.cov[:] = True
    for (x, y, wt) in srcs:
        b.add_power(b.rect((x - 1.5) * MM, (y - 1.5) * MM, (x + 1.5) * MM, (y + 1.5) * MM), wt)
    t0 = time.time()
    T = b.solve()[0]
    fv = [T[int(x / 0.5), int(y / 0.5)] for (x, y, _) in srcs] + [T[int(x / 0.5), int(y / 0.5)] for (x, y) in probes]
    gs, lam = fin_params([tm.OZ * 1e3, tm.OZ * 1e3], [1.0, 1.0], 1.53, tm.K_CU, tm.K_XY, 10.0, 10.0)
    bv = type('BV', (), {})()
    bv.bbox = (0.0, 0.0, lx, ly)
    pts = [(x, y) for (x, y, _) in srcs] + probes
    st = State(len(pts))
    for i, (x, y) in enumerate(pts):
        st.set(i, x, y, 0.0, 1)
    out = {}
    a_eq = math.sqrt(9.0 / math.pi)
    for rings in (0, 1, 2):
        th = ThermalField(bv, [(i, wt, a_eq) for i, (_, _, wt) in enumerate(srcs)],
                          list(range(len(srcs), len(pts))), gs, lam, rings=rings)
        est = th.full(st)
        out[f'rings{rings}'] = stats(est, fv)
        out[f'rings{rings}_values'] = [float(v) for v in est]
    out['fv'] = [float(v) for v in fv]
    print(f"[thermal] fin kernel vs FV (lambda {lam:.1f} mm, G_s {gs:.4f} W/K) ({time.time() - t0:.1f} s)")
    for rings in (0, 1, 2):
        print(f"    {rings} ring(s) of edge images: {fmt(out[f'rings{rings}'])}")
    print("    FV / rings=1 at sources and probes: " + ', '.join(f'{a:.1f}/{e:.1f}' for a, e in zip(fv, out['rings1_values'])))
    return out


# ============================================================================ rb passports
def sec_rb_hf(quick):
    """Commutation-cell estimate at the human placement vs rb_board_passports' HF loop L of
    the same cell (switching part + its decoupling cap), from kae-work/physics/human-k10-mmd."""
    from kae.board.kicad_file import load
    from kae.circuit.brief import build
    from kae.physics.place_terms import Terms
    rows = []
    for f in sorted(glob.glob(str(ROOT / 'kae-work' / 'physics' / 'human-k10-mmd' / '*' / 'passports.json'))):
        d = json.load(open(f))
        # rb's own failures (a non-finite or absurd L, e.g. 1.9e11 nH on one cell) are dropped
        cells = [c for c in (d.get('hf') or {}).get('cells', [])
                 if c.get('status') == 'ok' and 0.0 < float(c.get('L_board_nH') or 0.0) < 1000.0]
        if not cells:
            continue
        bid = Path(f).parent.name
        pcb = ROOT / 'kae-work' / 'tasks' / bid / 'reference' / 'board.kicad_pcb'
        if not pcb.exists():
            continue
        b = load(str(pcb))
        T = Terms(b, build(b))
        poses = T.bv.pose0()
        T.total(poses)
        bd = {r['id']: r for r in T.breakdown(poses)}
        for c in cells:
            refs = set(c['ref'].split('+'))
            caps = set(c.get('decaps_in_loop') or c.get('cap_split', {}).keys())
            best = None
            for s in T.structs:
                if s.kind != 'commutation':
                    continue
                members = {T.bv.parts[i].ref for i in s.members}
                if refs & members and (not caps or caps & set(s.labels)):
                    best = s
                    break
            if best is None:
                continue
            rows.append(dict(board=bid, ref=c['ref'], caps=sorted(caps), rb=c['L_board_nH'],
                             rb_esl=c.get('L_esl_nH'), est=bd[best.id]['value'], struct=best.id))
    if len(rows) < 3:
        print(f"[rb_hf] {len(rows)} matched cells: too few")
        return dict(rows=rows)
    est = np.array([r['est'] for r in rows])
    rb = np.array([r['rb'] for r in rows])
    ratio = est / rb
    out = dict(n=len(rows), spearman=float(spearmanr(est, rb).statistic), ratio_median=float(np.median(ratio)),
               ratio_p10=float(np.percentile(ratio, 10)), ratio_p90=float(np.percentile(ratio, 90)), rows=rows)
    print(f"[rb_hf] {len(rows)} human-board cells: estimator / rb HF loop median {out['ratio_median']:.2f} "
          f"(p10 {out['ratio_p10']:.2f}, p90 {out['ratio_p90']:.2f}), Spearman {out['spearman']:.3f}")
    for r in rows:
        print(f"    {r['board'][:40]:40s} {r['ref']:10s} rb {r['rb']:6.2f} nH  estimator {r['est']:6.2f} nH")
    return out


SECTIONS = dict(loop_peec=sec_loop_peec, decap_peec=sec_decap_peec, oblique=sec_oblique, spread=sec_spread,
                esd=sec_esd, coupling_l=sec_coupling_l, coupling_c=sec_coupling_c, cprime=sec_cprime,
                thermal=sec_thermal, rb_hf=sec_rb_hf)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    ap.add_argument('--out', default=str(ROOT / 'kae-work' / 'physics' / 'place-terms' / 'validate'))
    ap.add_argument('--quick', action='store_true')
    a = ap.parse_args(argv)
    names = [n for n in a.only.split(',') if n] or list(SECTIONS)
    os.makedirs(a.out, exist_ok=True)
    res = {}
    for n in names:
        t0 = time.time()
        res[n] = SECTIONS[n](a.quick)
        res[n + '_seconds'] = round(time.time() - t0, 1)
    path = os.path.join(a.out, 'summary.json' if not a.only else f"summary-{'-'.join(names)}.json")
    json.dump(res, open(path, 'w'), indent=1, default=float)
    print('wrote', path)


if __name__ == '__main__':
    main()
