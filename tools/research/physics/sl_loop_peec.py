# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hot-loop inductance: cheap proxies vs a quasi-static PEEC reference (workstream 3, solver ladder).

What it computes
----------------
Manhattan current loops made of copper traces (width w, thickness t) at height h
above an ideal ground plane (PEC image, valid above ~1 MHz for 35 um copper) or
in free space (no plane). For each loop it evaluates:

  AREA   plan-view loop area (shoelace on the centreline), the rule of thumb;
  PP     sum(l * mu0 * h / w), the parallel-plate "trace over plane" estimate;
  MS     sum(l * L'(w, h)), L' from the Hammerstad-Jensen air microstrip Z0 / c0
         (fringing included, mutual coupling between loop sides ignored);
  PEEC1  partial-inductance sum, one filament per segment (+ images);
  PEECN  reference: N filaments across each trace width, high-frequency current
         split solved exactly (Z = jwL, filaments of a segment in parallel),
         images for the plane. Partial inductances use Grover's closed form for
         parallel filaments; self terms use the rectangle GMD 0.2235 (w + t).

It prints (1) Spearman rank correlation and error spread of each proxy against
PEECN over random loop families, split by regime, i.e. the "trust radius" of each
proxy; (2) wall-clock time per evaluation, single and batched; (3) optionally a
FastHenry input deck for cross-checking PEECN with a meshed finite plane
(--fasthenry DIR writes decks; FastHenry itself is not bundled, see open-solvers.md
for its licence problem).

Run:  python tools/research/physics/sl_loop_peec.py          # ~20 s, deterministic
      python tools/research/physics/sl_loop_peec.py --fasthenry /tmp/fh
Needs numpy and scipy.
"""

import argparse
import math
import os
import time

import numpy as np
from scipy.stats import spearmanr

MU0 = 4e-7 * math.pi
C0 = 299792458.0
ETA0 = MU0 * C0


def _G(u, d):
    return u * np.arcsinh(u / d) - np.sqrt(u * u + d * d)


def m_parallel(l1, l2, s, d):
    """Mutual partial inductance of two parallel co-directed filaments (Grover).

    Filament 1 spans [0, l1], filament 2 spans [s, s + l2] along the same axis,
    perpendicular distance d. Vectorized over numpy arrays.
    """
    return MU0 / (4 * math.pi) * (_G(s + l2, d) - _G(s + l2 - l1, d) - _G(s, d) + _G(s - l1, d))


def filaments_from_loop(pts, widths, z, t, nf):
    """Split each Manhattan segment of a closed polyline into nf filaments across its width.

    Returns arrays (axis, lo, hi, sign, cx, cz, seg_id, gmd) per filament; axis 0 = x, 1 = y.
    """
    out = []
    n = len(pts)
    for k in range(n):
        (x0, y0), (x1, y1) = pts[k], pts[(k + 1) % n]
        w = widths[k]
        if abs(y1 - y0) < 1e-15:
            axis, a0, a1, c = 0, x0, x1, y0
        else:
            axis, a0, a1, c = 1, y0, y1, x0
        sign = 1.0 if a1 > a0 else -1.0
        lo, hi = min(a0, a1), max(a0, a1)
        offs = (np.arange(nf) + 0.5) / nf * w - w / 2
        for o in offs:
            out.append((axis, lo, hi, sign, c + o, z, k, 0.2235 * (w / nf + t)))
    return np.array(out, dtype=float)


def l_matrix(F, plane_z=None):
    """Partial inductance matrix of filaments F (with PEC image plane at plane_z if given)."""
    ax, lo, hi, sg, cx, cz, gmd = F[:, 0], F[:, 1], F[:, 2], F[:, 3], F[:, 4], F[:, 5], F[:, 7]
    same = ax[:, None] == ax[None, :]
    l1 = (hi - lo)[:, None]
    l2 = (hi - lo)[None, :]
    s = lo[None, :] - lo[:, None]
    dxy = cx[:, None] - cx[None, :]
    d = np.sqrt(dxy ** 2 + (cz[:, None] - cz[None, :]) ** 2)
    np.fill_diagonal(d, gmd)
    d = np.maximum(d, 1e-9)
    sgn = sg[:, None] * sg[None, :]
    L = np.where(same, sgn * m_parallel(l1, l2, s, d), 0.0)
    if plane_z is not None:
        zi = 2 * plane_z - cz  # image heights; horizontal image current reversed
        di = np.sqrt(dxy ** 2 + (cz[:, None] - zi[None, :]) ** 2)
        L = L - np.where(same, sgn * m_parallel(l1, l2, s, di), 0.0)
    return L


def loop_l_peec(pts, widths, h, t=35e-6, nf=1, plane=True):
    """Loop inductance (H) of a closed Manhattan loop, high-frequency current split."""
    F = filaments_from_loop(pts, widths, h, t, nf)
    L = l_matrix(F, 0.0 if plane else None)
    nseg = len(pts)
    if nf == 1:
        return float(L.sum())
    B = np.zeros((len(F), nseg))
    B[np.arange(len(F)), F[:, 6].astype(int)] = 1.0
    Y = np.linalg.solve(L, B)  # L^-1 B
    K = B.T @ Y  # B^T L^-1 B
    V = np.linalg.solve(K, np.ones(nseg))
    return float(V.sum())


def shoelace(pts):
    x, y = np.array(pts).T
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def seg_lengths(pts):
    p = np.array(pts)
    return np.abs(np.roll(p, -1, axis=0) - p).sum(axis=1)


def lprime_ms(w, h):
    """Per-unit-length inductance of a trace over a plane: Hammerstad-Jensen air Z0 / c0."""
    u = w / h
    f = 6 + (2 * math.pi - 6) * np.exp(-((30.666 / u) ** 0.7528))
    z0 = ETA0 / (2 * math.pi) * np.log(f / u + np.sqrt(1 + (2 / u) ** 2))
    return z0 / C0


def ms2_mutual(pts, h):
    """Coupled-microstrip correction: -2 * sum over antiparallel overlapping sides of
    overlap * (mu0 / 4 pi) * ln(1 + (2h / s)^2) (s = centre-line separation)."""
    F = filaments_from_loop(pts, [0.0] * len(pts), h, 0.0, 1)
    tot = 0.0
    for i in range(len(F)):
        for j in range(i + 1, len(F)):
            if F[i, 0] != F[j, 0]:
                continue
            ov = min(F[i, 2], F[j, 2]) - max(F[i, 1], F[j, 1])
            sep = abs(F[i, 4] - F[j, 4])
            if ov <= 0 or sep <= 0:
                continue
            tot += 2 * F[i, 3] * F[j, 3] * ov * MU0 / (4 * math.pi) * math.log(1 + (2 * h / sep) ** 2)
    return tot


def proxies(pts, widths, h):
    L = seg_lengths(pts)
    w = np.array(widths)
    ms = float(np.sum(L * lprime_ms(w, h)))
    return {
        "AREA": shoelace(pts),
        "PP": float(np.sum(L * MU0 * h / w)),
        "MS": ms,
        "MS2": ms + ms2_mutual(pts, h),
    }


# ---------------------------------------------------------------- loop families
def rect(a, b):
    return [(0, 0), (a, 0), (a, b), (0, b)]


def hairpin(length, gap):
    """U-shaped loop: out and back along x with centre-line separation `gap`."""
    return [(0, 0), (length, 0), (length, gap), (0, gap)]


def ell(a, b, ca, cb):
    """L-shaped loop: a x b rectangle with a ca x cb corner removed."""
    return [(0, 0), (a, 0), (a, b - cb), (a - ca, b - cb), (a - ca, b), (0, b)]


def sample_family(rng, n, plane=True, fixed=None):
    """Random rect / hairpin / L loops; fixed=(w, h) pins the stackup and width."""
    rows = []
    for i in range(n):
        kind = ("rect", "hairpin", "ell")[i % 3]
        h = float(np.exp(rng.uniform(np.log(0.08e-3), np.log(1.6e-3))))
        w = float(np.exp(rng.uniform(np.log(0.15e-3), np.log(4e-3))))
        if fixed:
            w, h = fixed
        if kind == "rect":
            a, b = rng.uniform(1.5e-3, 20e-3, 2)
            a, b = max(a, 1.5 * w), max(b, 1.5 * w)
            pts = rect(a, b)
        elif kind == "hairpin":
            ln = rng.uniform(3e-3, 25e-3)
            gap = max(rng.uniform(0.2e-3, 4e-3), 1.3 * w)
            pts = hairpin(ln, gap)
        else:
            a, b = rng.uniform(3e-3, 20e-3, 2)
            a, b = max(a, 4 * w), max(b, 4 * w)
            ca, cb = rng.uniform(0.25, 0.6) * a, rng.uniform(0.25, 0.6) * b
            pts = ell(a, b, ca, cb)
        widths = [w] * len(pts)
        rows.append((kind, pts, widths, h))
    return rows


def evaluate(rows, plane, nf_ref=7):
    res = []
    for kind, pts, widths, h in rows:
        p = proxies(pts, widths, h)
        p["PEEC1"] = loop_l_peec(pts, widths, h, nf=1, plane=plane)
        p["PEECN"] = loop_l_peec(pts, widths, h, nf=nf_ref, plane=plane)
        w = widths[0]
        sep = min(np.ptp(np.array(pts)[:, 0]), np.ptp(np.array(pts)[:, 1]))
        p.update(kind=kind, w_over_h=w / h, sep_over_h=sep / h)
        res.append(p)
    return res


def report(res, plane, label=""):
    ref = np.array([r["PEECN"] for r in res])
    print(f"\n== {'over ideal plane' if plane else 'free space (no plane)'}{label}: {len(res)} loops,"
          f" PEECN median {np.median(ref)*1e9:.2f} nH (range {ref.min()*1e9:.2f}-{ref.max()*1e9:.1f} nH)")
    masks = {
        "all": np.ones(len(res), bool),
        "w/h<1": np.array([r["w_over_h"] < 1 for r in res]),
        "w/h>=3": np.array([r["w_over_h"] >= 3 for r in res]),
        "hairpin": np.array([r["kind"] == "hairpin" for r in res]),
        "hairpin sep/h<4": np.array([r["kind"] == "hairpin" and r["sep_over_h"] < 4 for r in res]),
        "sep/h>=10": np.array([r["sep_over_h"] >= 10 for r in res]),
    }
    print(f"{'proxy':6s} {'subset':16s} {'n':>4s} {'spearman':>8s} {'med err':>8s} {'p10..p90 err':>16s}")
    for name in ("AREA", "PP", "MS", "MS2", "PEEC1"):
        v = np.array([r[name] for r in res])
        for mname, m in masks.items():
            if m.sum() < 8:
                continue
            rho = spearmanr(v[m], ref[m]).statistic
            if name == "AREA":
                print(f"{name:6s} {mname:16s} {m.sum():4d} {rho:8.3f} {'(mm^2, rank only)':>25s}")
                continue
            err = v[m] / ref[m] - 1
            print(f"{name:6s} {mname:16s} {m.sum():4d} {rho:8.3f} {np.median(err)*100:7.1f}% "
                  f"{np.percentile(err,10)*100:7.1f}..{np.percentile(err,90)*100:6.1f}%")


def timing(rng):
    rows = sample_family(rng, 60, True)
    out = {}
    for label, fn in (
        ("MS proxy", lambda r: proxies(r[1], r[2], r[3])["MS"]),
        ("PEEC1 (1 filament/segment, images)", lambda r: loop_l_peec(r[1], r[2], r[3], nf=1)),
        ("PEECN (7 filaments, solved split)", lambda r: loop_l_peec(r[1], r[2], r[3], nf=7)),
        ("PEECN (15 filaments)", lambda r: loop_l_peec(r[1], r[2], r[3], nf=15)),
    ):
        t0 = time.perf_counter()
        for _ in range(3):
            for r in rows:
                fn(r)
        out[label] = (time.perf_counter() - t0) / (3 * len(rows))
    # batched PEEC1 for many rectangles at once: one vectorized pass
    nb = 20000
    a = rng.uniform(2e-3, 20e-3, nb)
    b = rng.uniform(2e-3, 20e-3, nb)
    w = rng.uniform(0.2e-3, 3e-3, nb)
    h = rng.uniform(0.1e-3, 1.6e-3, nb)
    t0 = time.perf_counter()
    Lb = rect_loop_batch(a, b, w, h)
    out[f"PEEC1 batched rectangles ({nb} at once), per loop"] = (time.perf_counter() - t0) / nb
    chk = loop_l_peec(rect(a[0], b[0]), [w[0]] * 4, h[0], nf=1)
    assert abs(Lb[0] / chk - 1) < 1e-9, (Lb[0], chk)
    print("\n== timing (this machine, 1 CPU thread, numpy)")
    for k, v in out.items():
        print(f"  {k:52s} {v*1e6:10.1f} us")


def rect_loop_batch(a, b, w, h, t=35e-6):
    """Vectorized PEEC1 for rectangles over a plane: 4 self + 2 opposite-side pairs + images."""
    gmd = 0.2235 * (w + t)
    tot = 0.0
    for l, sep in ((a, b), (b, a)):
        self_ = m_parallel(l, l, 0.0, gmd) - m_parallel(l, l, 0.0, 2 * h)
        opp = m_parallel(l, l, 0.0, sep) - m_parallel(l, l, 0.0, np.sqrt(sep ** 2 + 4 * h ** 2))
        tot = tot + 2 * self_ - 2 * opp  # opposite sides carry opposite currents
    return tot


def write_fasthenry(outdir):
    """FastHenry decks: rectangle loops over a finite meshed plane, for cross-checking PEECN."""
    os.makedirs(outdir, exist_ok=True)
    cases = [(10, 10, 1.0, 0.5), (10, 10, 1.0, 0.2), (20, 2, 0.5, 0.2), (10, 10, 0.3, 1.0)]
    for i, (a, b, w, h) in enumerate(cases):
        pl = 30.0
        nseg = int(round(pl / min(0.25, h / 2)))
        x0, y0 = -a / 2, -b / 2
        deck = [
            f"* rect loop a={a} b={b} w={w} h={h} mm over {pl} mm plane",
            ".units mm",
            ".default sigma=5.8e4 nwinc=5 nhinc=1",
            f"gp x1={-pl/2} y1={-pl/2} z1=0 x2={pl/2} y2={-pl/2} z2=0 x3={pl/2} y3={pl/2} z3=0"
            f" thick=0.035 seg1={nseg} seg2={nseg}",
            f"N1 x={x0+0.05} y={y0} z={h}",
            f"N2 x={x0+a} y={y0} z={h}",
            f"N3 x={x0+a} y={y0+b} z={h}",
            f"N4 x={x0} y={y0+b} z={h}",
            f"N5 x={x0} y={y0} z={h}",
            f"E1 N1 N2 w={w} h=0.035",
            f"E2 N2 N3 w={w} h=0.035",
            f"E3 N3 N4 w={w} h=0.035",
            f"E4 N4 N5 w={w} h=0.035",
            ".external N1 N5",
            ".freq fmin=1e8 fmax=1e8 ndec=1",
            ".end",
        ]
        path = os.path.join(outdir, f"rect{i}.inp")
        with open(path, "w") as fh:
            fh.write("\n".join(deck) + "\n")
        Lref = loop_l_peec(rect(a * 1e-3, b * 1e-3), [w * 1e-3] * 4, h * 1e-3, nf=7)
        Lfree = loop_l_peec(rect(a * 1e-3, b * 1e-3), [w * 1e-3] * 4, h * 1e-3, nf=7, plane=False)
        print(f"{path}: PEECN image-plane {Lref*1e9:.3f} nH, free space {Lfree*1e9:.3f} nH")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--fasthenry", metavar="DIR")
    args = ap.parse_args()
    if args.fasthenry:
        write_fasthenry(args.fasthenry)
        return
    rng = np.random.default_rng(7)
    rows = sample_family(rng, args.n, True)
    report(evaluate(rows, True), True)
    report(evaluate(rows, False), False)
    for wh in ((0.5e-3, 0.1e-3), (0.5e-3, 0.2e-3), (1.0e-3, 1.5e-3)):
        rows_f = sample_family(np.random.default_rng(11), 300, True, fixed=wh)
        report(evaluate(rows_f, True), True, f", fixed w={wh[0]*1e3:.1f} mm h={wh[1]*1e3:.1f} mm")
    timing(np.random.default_rng(3))


if __name__ == "__main__":
    main()
