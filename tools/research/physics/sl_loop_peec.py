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
  MS2    MS minus the coupled-line mutual of antiparallel overlapping sides,
         2 * overlap * (mu0 / 4 pi) * ln(1 + (2h / s)^2);
  PEEC1  partial-inductance sum, one filament per segment (+ images);
  PEECN  reference: N filaments across each trace width, high-frequency current
         split solved exactly (Z = jwL, filaments of a segment in parallel),
         images for the plane. Partial inductances use Grover's closed form for
         parallel filaments; self terms use the rectangle GMD 0.2235 (w + t).

It prints (1) Spearman rank correlation and error spread of each proxy against
PEECN over random loop families (mixed and fixed stackups), split by regime, i.e.
the "trust radius" of each proxy; (2) decision quality: how often each proxy picks
the PEECN-best of 10 candidates, and the regret; (3) wall-clock time per
evaluation, single and batched; (4) a residual surrogate (log-linear correction of
MS2) vs a black-box fit, trained on 300 PEECN labels. With --fasthenry DIR it
writes FastHenry decks for four rectangles over a finite meshed plane and prints
PEECN next to the FastHenry results measured for them (FH_MEASURED; PEECN within
1.3 %). FastHenry itself is not bundled: see docs/topics/physics/open-solvers.md
for its non-commercial licence header.

Run:  python tools/research/physics/sl_loop_peec.py          # ~10-30 s, deterministic
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


def decision(res, label, k=10, trials=2000, seed=1):
    """Pick-the-best test: how often does a proxy choose the PEECN-best of k candidates, and the regret."""
    rng = np.random.default_rng(seed)
    ref = np.array([r["PEECN"] for r in res])
    print(f"\n== decision quality, {label}: best of {k} random candidates, {trials} trials")
    for name in ("AREA", "MS", "MS2", "PEEC1"):
        v = np.array([r[name] for r in res])
        hit, reg = 0, []
        for _ in range(trials):
            idx = rng.choice(len(res), k, replace=False)
            pick, best = idx[np.argmin(v[idx])], idx[np.argmin(ref[idx])]
            hit += pick == best
            reg.append(ref[pick] / ref[best] - 1)
        reg = np.array(reg)
        miss = reg[reg > 0]
        mtxt = f"; misses: median {np.median(miss)*100:.1f}%, max {miss.max()*100:.1f}%" if miss.size else ""
        print(f"  {name:6s} picks the true best {hit/trials*100:5.1f}%; regret median {np.median(reg)*100:5.1f}%,"
              f" p95 {np.percentile(reg, 95)*100:6.1f}%{mtxt}")


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


def surrogate(rng):
    """Residual surrogate: learn log(PEECN / MS2) from 5 features vs a black-box fit of log(PEECN)."""
    rows = sample_family(rng, 1500, True)
    res = evaluate(rows, True)
    def feats(r, kind_pts):
        kind, pts, widths, h = kind_pts
        per = seg_lengths(pts).sum()
        return [1.0, math.log(r["w_over_h"]), math.log(r["sep_over_h"]), math.log(per / h),
                float(kind == "hairpin"), float(kind == "ell")]
    X = np.array([feats(r, kp) for r, kp in zip(res, rows)])
    y_ref = np.log([r["PEECN"] for r in res])
    y_ms2 = np.log([r["MS2"] for r in res])
    ntr = 300
    print(f"\n== surrogates trained on {ntr} PEECN labels, tested on {len(res)-ntr} held-out loops")
    for name, target, base in (("black-box log-linear", y_ref, 0.0), ("residual on MS2", y_ref - y_ms2, y_ms2)):
        coef, *_ = np.linalg.lstsq(X[:ntr], target[:ntr], rcond=None)
        pred = X[ntr:] @ coef + (base[ntr:] if np.ndim(base) else 0.0)
        err = np.exp(pred - y_ref[ntr:]) - 1
        print(f"  {name:22s} median |err| {np.median(np.abs(err))*100:5.1f}%  p95 |err| "
              f"{np.percentile(np.abs(err), 95)*100:5.1f}%  max {np.abs(err).max()*100:5.1f}%")
    raw = np.exp(y_ms2[ntr:] - y_ref[ntr:]) - 1
    print(f"  {'MS2 uncalibrated':22s} median |err| {np.median(np.abs(raw))*100:5.1f}%  p95 |err| "
          f"{np.percentile(np.abs(raw), 95)*100:5.1f}%")


# FastHenry 3.0 results measured for these decks (100 MHz, 1 core; see open-solvers.md):
# (a, b, w, h mm) -> FastHenry nH, filaments, wall s   |  PEECN (7 filaments, ideal image) nH
FH_MEASURED = {
    (10, 10, 1.0, 0.5): (11.012, 29520, 70),   # PEECN 10.99
    (10, 10, 1.0, 0.2): (6.067, 25060, 56),    # PEECN 6.02 (6.09 with 15 filaments)
    (20, 2, 0.5, 0.2): (10.348, 11210, 7),     # PEECN 10.48
    (10, 10, 0.3, 1.0): (23.791, 29520, 115),  # PEECN 23.96
}


def write_fasthenry(outdir):
    """FastHenry decks: rectangle loops over a finite meshed plane (floating, eddy currents only)."""
    os.makedirs(outdir, exist_ok=True)
    # (a, b, w, h) mm, plane half-sizes (px, py) mm, plane cell mm
    cases = [((10, 10, 1.0, 0.5), (15, 15), 0.25), ((10, 10, 1.0, 0.2), (11, 11), 0.2),
             ((20, 2, 0.5, 0.2), (13, 4), 0.2), ((10, 10, 0.3, 1.0), (15, 15), 0.25)]
    for i, ((a, b, w, h), (px, py), cell) in enumerate(cases):
        x0, y0 = -a / 2, -b / 2
        deck = [
            f"* rect loop a={a} b={b} w={w} h={h} mm over a {2*px}x{2*py} mm plane, {cell} mm cells",
            ".units mm",
            ".default sigma=5.8e4 nwinc=5 nhinc=1",
            f"gp x1={-px} y1={-py} z1=0 x2={px} y2={-py} z2=0 x3={px} y3={py} z3=0"
            f" thick=0.035 seg1={int(round(2*px/cell))} seg2={int(round(2*py/cell))}",
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
        fh_nh, nfil, secs = FH_MEASURED[(a, b, w, h)]
        print(f"{path}: PEECN {Lref*1e9:.3f} nH; FastHenry (measured) {fh_nh:.3f} nH,"
              f" {nfil} filaments, {secs} s -> PEECN/FH = {Lref*1e9/fh_nh:.3f}")


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
    res_mixed = evaluate(rows, True)
    report(res_mixed, True)
    report(evaluate(rows, False), False)
    for wh in ((0.5e-3, 0.1e-3), (0.5e-3, 0.2e-3), (1.0e-3, 1.5e-3)):
        rows_f = sample_family(np.random.default_rng(11), 300, True, fixed=wh)
        res_f = evaluate(rows_f, True)
        report(res_f, True, f", fixed w={wh[0]*1e3:.1f} mm h={wh[1]*1e3:.1f} mm")
        if wh[1] == 0.2e-3:
            decision(res_f, "fixed w=0.5 mm h=0.2 mm (shape-only choices)")
    decision(res_mixed, "mixed widths and stackups (shape + width + layer choices)")
    timing(np.random.default_rng(3))
    surrogate(np.random.default_rng(5))


if __name__ == "__main__":
    main()
