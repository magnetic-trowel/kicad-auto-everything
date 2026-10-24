# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Joint collapse by continuation (docs/ideas/original/layer-collapse.md, "Joint collapse
by continuation"), on the pnr engine (tools/research/pnr).

    lift (beta = 0)   every part at its HPWL + physics optimum ignoring other parts
                      (overlaps allowed), every net routed alone (present cost 0)
    collapse          one coupling beta, raised geometrically (adaptive to the remaining
                      conflict, and fast enough to finish inside the budget). At each beta,
                      in the same iteration:
                        (a) nets: rip and re-route every net with PathFinder present cost
                            beta (foreign-halo count DT/DV, pads included) + history
                        (b) parts: each part jumps to its whole-board argmin over XY and
                            the 4 rotations of
                              (HPWL + routed pin tension)/g + phys_w * physics / g
                              + beta * (keep-out overlap cells on every plane
                                        + foreign route cells under its pad halos)
                              + part history
                            (FFT correlation maps; physics exact at the best candidates)
                      Units: one currency, grid cells of wire (g mm). A conflicting cell
                      costs beta for a wire and for a part alike.
    end               nearest legal pose for every part still overlapping (Kit.legal_map),
                      PathFinder from the collapsed routes + Router.legalize; optional short
                      anneal_phys polish.
    obstruction map   wire history (sum over layers) + part history: where prices climbed.

Plug-ins for run.py: jc (joint, polish 15 %), jc_nopol (no polish), jc_frozen (parts
legalized right after the lift and frozen: routing-only collapse), jc_fast / jc_slow
(beta schedule speed). Options via --opt key=value.
"""
import math
import os
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/user/kicad-auto-everything/tools/research/pnr")

import methods as M  # noqa: E402
import methods_phys as MP  # noqa: E402
from physics import Phys  # noqa: E402
from placekit import Clock, Kit, corr  # noqa: E402
from router import add_hist, vias_of  # noqa: E402

ROOT = Path("/home/user/kicad-auto-everything")


def _corr0(arr, offs):
    return corr(arr, offs, pad_value=0.0)


def _board_id(world):
    parts = Path(world.data.get("path", "board")).parts
    for s in reversed(parts):
        if (ROOT / "kae-work" / "tasks" / s).is_dir():
            return s
    return Path(world.data.get("path", "board")).parent.name


class FFTCorr:
    """Whole-board correlations sum_k M[y + dy_k, x + dx_k] by FFT, with kernel transforms
    cached by their cell set (identical footprints share them) and map transforms reused
    for every orientation: cost(ri) = irfft(sum_maps F(M) * conj F(K_ri,map))."""

    def __init__(self, H, W, R, cap_bytes=1.0e9):
        from scipy import fft as sfft
        self.fft = sfft
        self.H, self.W = H, W
        self.Hf = sfft.next_fast_len(H + R + 1, real=True)
        self.Wf = sfft.next_fast_len(W + R + 1, real=True)
        self.cache = {}
        self.order = []
        self.bytes = 0
        self.cap = cap_bytes
        self.hits = self.miss = 0

    def map(self, M):
        Mp = np.zeros((self.Hf, self.Wf), np.float32)
        Mp[:self.H, :self.W] = M
        return self.fft.rfft2(Mp, workers=1)

    def kernel(self, cells):
        key = cells.tobytes()
        F = self.cache.get(key)
        if F is not None:
            self.hits += 1
            return F
        self.miss += 1
        K = np.zeros((self.Hf, self.Wf), np.float32)
        np.add.at(K, (cells[:, 1] % self.Hf, cells[:, 0] % self.Wf), 1.0)
        F = np.conj(self.fft.rfft2(K, workers=1)).astype(np.complex64)
        self.cache[key] = F
        self.order.append(key)
        self.bytes += F.nbytes
        while self.bytes > self.cap and len(self.order) > 1:
            old = self.order.pop(0)
            self.bytes -= self.cache.pop(old).nbytes
        return F

    def corr(self, pairs):
        """pairs: [(F(map), cells)] -> sum of correlations (H, W)."""
        acc = None
        for FM, cells in pairs:
            if FM is None or len(cells) == 0:
                continue
            t = FM * self.kernel(cells)
            acc = t if acc is None else acc + t
        if acc is None:
            return np.zeros((self.H, self.W))
        return self.fft.irfft2(acc, s=(self.Hf, self.Wf), workers=1)[:self.H, :self.W]


class Collapse:
    def __init__(self, world, seed, budget, log, phys_w=2.0, tension_w=0.3, hist_inc=0.3,
                 hist_p=0.0, k_phys=24, trust_mm=0.0, pad_wire=1.0, tension_beta=1.0, max_stuck=8, **kw):
        self.w = world
        self.log = log
        self.rng = random.Random(seed)
        self.clock = Clock(budget)
        self.budget = budget
        M._place_fixed(world)
        self.r = M._router(world, kw)
        self.kit = Kit(world, self.r)
        M.place_mechanical(world, self.kit, log)
        self.ph = Phys(world, world.data["path"])
        world.phys = self.ph
        self.phys_w = phys_w
        self.tension_w = tension_w
        self.hist_inc = hist_inc
        self.hist_p = hist_p
        self.k_phys = k_phys
        self.g = world.g
        self.hist_c = np.zeros((world.P, world.H, world.W), np.float32)
        self.nets = list(world.net_pins)
        self.inside = {}
        self.bias = M.center_bias(self.kit, 0.05)
        self.kcache = {}
        self.trust = trust_mm
        self.pad_wire = pad_wire
        self.tension_beta = tension_beta
        self.max_stuck = max_stuck
        self.stuck = {}
        self.trace = []
        self.last_pose = {}
        mov = self.kit.movable()
        self.F = FFTCorr(world.H, world.W, self.max_radius(mov), cap_bytes=kw.get("fft_cap", 1.0e9))

    # ------------------------------------------------------------ helpers
    def inside_map(self, pi, ri):
        key = (pi, ri)
        if key not in self.inside:
            self.inside[key] = M._inside_map(self.w, self.kit, pi, ri)
        return self.inside[key]

    def overlap_cells(self):
        return int(np.maximum(self.w.court.astype(np.int32) - 1, 0).sum())

    def wire_conflicts(self):
        return sum(self.r.net_conflicts(n) for n in self.nets if self.r.routes.get(n))

    def route_all(self, beta):
        r, w = self.r, self.w
        r.pres = beta
        order = list(self.nets)
        self.rng.shuffle(order)
        for n in order:
            r.rip(n)
            r.route_net(n)
        bad = [n for n in self.nets if r.routes.get(n) and r.net_conflicts(n)]
        for n in bad:
            for p in r.routes[n]:
                add_hist(p, n, w.DT, w.occT, w.hist, self.hist_inc)
        return bad

    def route_maps(self):
        """Per-layer route centreline cell counts (one per net per cell) and via cells."""
        w = self.w
        CT = np.zeros((w.nl, w.H, w.W), np.float32)
        CV = np.zeros((w.H, w.W), np.float32)
        per = {}
        for n, ps in self.r.routes.items():
            if not ps:
                continue
            a = np.concatenate(ps)
            a = np.unique(a, axis=0)
            v = np.concatenate([vias_of(p) for p in ps])
            v = np.unique(v[:, 1:], axis=0) if len(v) else np.zeros((0, 2), np.int32)
            per[n] = (a, v)
            CT[a[:, 0], a[:, 1], a[:, 2]] += 1
            if len(v):
                CV[v[:, 0], v[:, 1]] += 1
        return CT, CV, per

    def anchors(self, pi):
        """Per pad of placed part pi with a routed net: the route cell ~2 mm out of the pad
        (where its wire would pull the pad: the envelope-theorem pin tension)."""
        w, r = self.w, self.r
        cx, cy, ri = w.pose[pi]
        rr = w.raster(pi)
        look = max(3, int(2.0 / w.g))
        out = []
        for k, ent in enumerate(rr["pads"]):
            n = ent["net"]
            if not r.routes.get(n):
                continue
            cells = {(int(x + cx), int(y + cy)) for x, y in ent["cu"]}
            for p in r.routes[n]:
                for end, step in ((0, 1), (len(p) - 1, -1)):
                    if (int(p[end, 2]), int(p[end, 1])) in cells:
                        j = end
                        while 0 <= j + step < len(p) and (int(p[j, 2]), int(p[j, 1])) in cells:
                            j += step
                        j = min(max(j + step * look, 0), len(p) - 1)
                        out.append((k, float(p[j, 2]), float(p[j, 1])))
        return out

    def tension_map(self, pi, ri, anchors):
        """Sum over anchored pads of the L1 distance (cells) pad -> anchor, per origin."""
        w = self.w
        if not anchors:
            return 0.0
        rr = w.part_raster(w.parts[pi], ri)
        X = np.arange(w.W, dtype=np.float64)
        Y = np.arange(w.H, dtype=np.float64)
        fx = np.zeros(w.W)
        fy = np.zeros(w.H)
        for k, ax, ay in anchors:
            c = rr["pads"][k]["center"] / w.g
            fx += np.abs(X + c[0] - ax)
            fy += np.abs(Y + c[1] - ay)
        return fy[:, None] + fx[None, :]

    def kernels(self, pi, ri):
        """Cell sets of part pi at orientation ri: keep-out per plane, union of pad track
        halos per copper layer, union of pad via halos."""
        key = (pi, ri)
        k = self.kcache.get(key)
        if k is None:
            w = self.w
            rr = w.part_raster(w.parts[pi], ri)
            byl, hv = {}, []
            for ent in rr["pads"]:
                for l in ent["layers_halo"]:
                    byl.setdefault(l, []).append(ent["hT"])
                hv.append(ent["hV"])
            ht = {l: np.ascontiguousarray(np.unique(np.concatenate(cs), axis=0), np.int32) for l, cs in byl.items()}
            hv = np.ascontiguousarray(np.unique(np.concatenate(hv), axis=0), np.int32) if hv else np.zeros((0, 2), np.int32)
            k = self.kcache[key] = (rr["keep"], ht, hv)
        return k

    def max_radius(self, parts):
        R = 1
        for pi in parts:
            for ri in range(4):
                keep, ht, hv = self.kernels(pi, ri)
                for c in [c for _, c in keep] + list(ht.values()) + [hv]:
                    if len(c):
                        R = max(R, int(np.abs(c).max()))
        return R

    def part_cost_maps(self, pi, beta, CT, CV, anchors):
        """Yields (ri, cost map in cells without physics, inside mask). The part must be
        unplaced and its own nets removed from CT/CV."""
        w = self.w
        g = self.g
        F = self.F
        FP = FT = FV = None
        if beta > 0:
            FP = [F.map(beta * (w.court[p] > 0) * (1.0 + self.hist_c[p]) + self.hist_p * self.hist_c[p])
                  for p in range(w.P)]
            bw = beta * self.pad_wire
            FT = [F.map(bw * CT[l]) if (bw and CT[l].any()) else None for l in range(w.nl)]
            FV = F.map(bw * CV) if (bw and CV.any()) else None
        for ri in range(4):
            inside = self.inside_map(pi, ri)
            if not inside.any():
                continue
            c = self.kit.hpwl_map(pi, ri) / g
            if self.tension_w and anchors and beta >= self.tension_beta:
                c = (1 - self.tension_w) * c + self.tension_w * self.tension_map(pi, ri, anchors)
            c = c + self.bias(pi, ri) * 0.1 / g
            if beta > 0:
                keep, ht, hv = self.kernels(pi, ri)
                pairs = [(FP[p], cells) for p, cells in keep]
                pairs += [(FT[l], cells) for l, cells in ht.items()]
                pairs.append((FV, hv))
                c = c + F.corr(pairs)
            yield ri, c, inside

    def best_response(self, pi, beta, CT, CV, per):
        w, ph = self.w, self.ph
        cur = w.pose[pi]
        anchors = self.anchors(pi) if (self.tension_w and beta >= self.tension_beta) else []
        nets = self.kit.part_nets([pi])
        # remove the part's own nets from the route maps
        for n in nets:
            if n in per:
                a, v = per[n]
                CT[a[:, 0], a[:, 1], a[:, 2]] -= 1
                if len(v):
                    CV[v[:, 0], v[:, 1]] -= 1
        w.unplace(pi)
        use_phys = pi in ph.active and self.phys_w > 0
        cands = []
        win = None
        if self.trust:
            rad = int(self.trust / w.g * 2 ** min(self.stuck.get(pi, 0), self.max_stuck))
            if rad < max(w.W, w.H):
                win = np.zeros((w.H, w.W), bool)
                win[max(0, cur[1] - rad):cur[1] + rad + 1, max(0, cur[0] - rad):cur[0] + rad + 1] = True
        for ri, c, inside in self.part_cost_maps(pi, beta, CT, CV, anchors):
            c = np.where(inside if win is None else inside & win, c, np.inf)
            if use_phys:
                flat = np.argpartition(c, min(self.k_phys * 20, c.size - 1), axis=None)[: self.k_phys * 20]
                flat = flat[np.argsort(c.flat[flat])]
                taken = []
                nms = max(3, int(0.6 / w.g))
                for f in flat:
                    v = c.flat[f]
                    if not np.isfinite(v):
                        break
                    y, x = divmod(int(f), w.W)
                    if any(abs(x - a) < nms and abs(y - b) < nms for a, b in taken):
                        continue
                    taken.append((x, y))
                    cands.append((float(v), x, y, ri))
                    if len(taken) >= self.k_phys // 4 + 2:
                        break
                if ri == cur[2] and inside[cur[1], cur[0]]:
                    cands.append((float(c[cur[1], cur[0]]), cur[0], cur[1], ri))
            else:
                j = int(np.argmin(c))
                if np.isfinite(c.flat[j]):
                    cands.append((float(c.flat[j]), j % w.W, j // w.W, ri))
        if use_phys and cands:
            cands = [(v + self.phys_w * ph.delta(pi, (x, y, ri)) / self.g, x, y, ri) for v, x, y, ri in cands]
        best = min(cands) if cands else (0.0,) + tuple(cur)
        w.place(pi, best[1], best[2], best[3])
        ph.commit(pi)
        if self.trust:
            # the trust radius doubles while the part stays in conflict (homotopy tracking:
            # parts move locally, so the lifted cluster expands keeping its topology)
            ov, _ = w.part_violation(pi)
            self.stuck[pi] = self.stuck.get(pi, 0) + 1 if ov > 0 else 0
        for n in nets:
            if n in per:
                a, v = per[n]
                CT[a[:, 0], a[:, 1], a[:, 2]] += 1
                if len(v):
                    CV[v[:, 0], v[:, 1]] += 1
        return tuple(best[1:]) != tuple(cur)

    # ------------------------------------------------------------ phases
    def lift(self, mov):
        """beta = 0: parts at their HPWL + physics optimum ignoring other parts (growth order,
        so the first parts see their placed neighbours), then each net alone."""
        w, kit, ph = self.w, self.kit, self.ph
        ph.sync()
        for pi in M.growth_order(w, kit, self.rng):
            best = None
            for ri in range(4):
                inside = self.inside_map(pi, ri)
                if not inside.any():
                    continue
                c = kit.hpwl_map(pi, ri) + self.bias(pi, ri)
                if self.phys_w > 0 and pi in ph.active and len(w.pose) > 1:
                    c = c + self.phys_w * ph.coarse_map(pi, ri, step_mm=1.2, legal=inside)
                c = np.where(inside, c, np.inf)
                j = int(np.argmin(c))
                if np.isfinite(c.flat[j]) and (best is None or c.flat[j] < best[0]):
                    best = (c.flat[j], j % w.W, j // w.W, ri)
            if best is None:
                best = (0, *self.kit.candidates(pi, k=1)[0][1:]) if self.kit.candidates(pi, k=1) else None
            if best is not None:
                w.place(pi, best[1], best[2], best[3])
                ph.commit(pi)
        self.route_all(0.0)

    def legalize_parts(self, max_evict=60):
        """Nearest legal pose (Kit.legal_map) for every part still overlapping, smallest
        violation first; a part with no legal spot anywhere evicts smaller parts
        (methods._evict_for) which are re-queued for their nearest legal pose."""
        w, kit = self.w, self.kit
        mov = [q for q in kit.movable() if q in w.pose]
        bad = [(w.part_violation(q), q) for q in mov]
        queue = [q for v, q in sorted((v[0] + 100 * v[1], q) for v, q in bad if v != (0, 0))]
        home = {q: w.pose[q] for q in queue}
        moved = evict = 0
        nbad = len(queue)
        while queue:
            q = queue.pop(0)
            if q in w.pose:
                if w.part_violation(q) == (0, 0):
                    continue
                cur = w.pose[q]
                w.unplace(q)
            else:
                cur = home.get(q) or self.last_pose.get(q)
            x, y = w.xy(cur[0], cur[1])
            D = kit.dist_map(x, y)
            best = None
            for ri in range(4):
                L = kit.legal_map(q, ri)
                if not L.any():
                    continue
                c = np.where(L, D + (0 if ri == cur[2] else 0.3) + 0.05 * kit.hpwl_map(q, ri), np.inf)
                j = int(np.argmin(c))
                if best is None or c.flat[j] < best[0]:
                    best = (c.flat[j], j % w.W, j // w.W, ri)
            if best is not None:
                w.place(q, best[1], best[2], best[3])
                moved += 1
            else:
                poses0 = dict(w.pose)
                victims = M._evict_for(w, kit, q) if evict < max_evict else None
                if victims is None:
                    w.place(q, *cur)
                    self.log(f"  no legal spot for {w.parts[q].ref}")
                    continue
                evict += len(victims)
                for v in victims:
                    self.last_pose[v] = poses0[v]
                queue.extend(victims)
                moved += 1
            self.ph.commit(q)
        return moved, nbad

    def obstruction_png(self, path, title):
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except Exception as e:  # pragma: no cover
            self.log(f"  no png: {e}")
            return
        w = self.w
        wire = w.hist.sum(0)
        part = self.hist_c.sum(0)
        fig, ax = plt.subplots(1, 3, figsize=(15, 5))
        ext = (w.x0, w.x0 + w.W * w.g, w.y0 + w.H * w.g, w.y0)
        for a, m, t in ((ax[0], wire, "wire history (sum of layers)"), (ax[1], part, "part history (keep-out planes)")):
            im = a.imshow(np.where(w.inside, m, np.nan), extent=ext, cmap="magma")
            a.set_title(t)
            fig.colorbar(im, ax=a, shrink=0.7)
        cour = (w.court[0] > 0).astype(float) + 2 * (w.court[1] > 0)
        ax[2].imshow(np.where(w.inside, cour, np.nan), extent=ext, cmap="Greys", alpha=0.6)
        for n, ps in self.r.routes.items():
            for p in ps:
                xs, ys = w.x0 + p[:, 2] * w.g, w.y0 + p[:, 1] * w.g
                ax[2].plot(xs, ys, lw=0.6, color=("C3" if p[0, 0] == 0 else "C0"))
        ax[2].set_title("final placement and copper")
        for a in ax:
            for o in w.outline:
                a.plot(np.r_[o[:, 0], o[0, 0]], np.r_[o[:, 1], o[0, 1]], "c-", lw=0.8)
            a.set_aspect("equal")
        fig.suptitle(title)
        fig.tight_layout()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=110)
        plt.close(fig)
        np.savez_compressed(str(path).replace(".png", ".npz"), wire=wire, part=part, inside=w.inside)


def collapse_once(C, run_budget, gamma, beta0, beta_end, beta_max, frozen, log):
    """One lift + continuation + legalization from scratch. Returns (iterations, beta)."""
    w, r, kit, ph = C.w, C.r, C.kit, C.ph
    clock = C.clock
    t_start = clock.budget - clock.left()
    end_t = t_start + run_budget
    mov = [q for q in kit.movable() if q not in w.pose]
    C.lift(mov)
    mov = [q for q in kit.movable() if q in w.pose]
    ph.sync()
    log(f"jc lift: overlap={C.overlap_cells()} cells wire_conflicts={C.wire_conflicts()} "
        f"{r.stats()} hpwl={w.hpwl():.1f} phys={ph.total():.2f} parts={len(mov)}")
    if frozen:
        m, nb = C.legalize_parts()
        ph.sync()
        log(f"jc frozen: legalized {m}/{nb} parts after the lift; hpwl={w.hpwl():.1f} phys={ph.total():.2f}")
    beta = beta0
    g_cur = gamma
    prev = None
    it = zero = 0
    t_it = []
    while True:
        it += 1
        t0 = clock.budget - clock.left()
        bad = C.route_all(beta)
        moved = 0
        if not frozen:
            CT, CV, per = C.route_maps()
            order = list(mov)
            C.rng.shuffle(order)
            for pi in order:
                moved += C.best_response(pi, beta, CT, CV, per)
        C.hist_c += C.hist_inc * (w.court > 1)
        ovc = C.overlap_cells()
        wc = C.wire_conflicts()
        conf = ovc + wc
        used = clock.budget - clock.left()
        t_it.append(used - t0)
        C.trace.append((beta, ovc, wc, w.hpwl()))
        log(f"  jc it={it} beta={beta:.3g} gamma={g_cur:.2f} moved={moved} overlap={ovc} "
            f"wire_conf={wc} nets_bad={len(bad)} {r.stats()} hpwl={w.hpwl():.1f} phys={ph.total():.2f} t={used:.1f}")
        zero = zero + 1 if conf == 0 else 0
        if conf == 0 and (moved == 0 or zero >= 2):
            break
        if used > end_t:
            break
        # adaptive geometric schedule: faster while the conflict stalls, back to gamma while
        # it falls quickly; never slower than needed to reach beta_end within the run budget
        if prev is not None and prev > 0:
            ratio = conf / prev
            if ratio > 0.85:
                g_cur = min(2.5, g_cur * 1.15)
            elif ratio < 0.5:
                g_cur = max(gamma, g_cur / 1.15)
        prev = conf
        per_it = float(np.mean(t_it[-3:]))
        left_its = max(1.0, (end_t - used) / max(per_it, 1e-3))
        need = (beta_end / beta) ** (1.0 / left_its) if beta < beta_end else 1.0
        beta = min(beta_max, beta * max(g_cur, need))
    m, nb = C.legalize_parts()
    ph.sync()
    log(f"jc end: beta={beta:.3g} its={it} legalized {m}/{nb} parts; overlap={C.overlap_cells()}")
    r.pathfinder(iters=20, pres0=max(0.5, min(beta, 4.0)), pres_mul=1.6)
    if any(r.unrouted.values()):
        r.pathfinder(iters=15, log=None)
    return it, beta


def _reset(C):
    w, r, kit = C.w, C.r, C.kit
    for q in [q for q in kit.movable() if q in w.pose]:
        w.unplace(q)
    r.rip_all()
    r.unrouted.clear()
    w.hist[:] = 0
    C.hist_c[:] = 0
    C.stuck.clear()


def jc(world, seed=0, budget=300, log=print, gamma=1.35, beta0=0.05, beta_end=60.0, beta_max=500.0,
       frozen=False, polish=0.15, restarts=True, first=0.35, png_dir=None, full_w=0.0, **kw):
    """Joint collapse; with `restarts`, the budget left after one continuation is spent on
    further continuations from the lift (new random orders, gamma varied), keeping the best
    legal end state by routed cost + phys_w * fast physics (+ full_w * full routed physics,
    physics.RoutedPhys, when full_w > 0); then an optional anneal_phys polish of
    `polish` x budget. phys_w = 0 is the length + vias objective."""
    C = Collapse(world, seed, budget, log, **kw)
    w, r, kit, ph = world, C.r, C.kit, C.ph
    clock = C.clock
    run_end = budget * (1 - polish)
    best = None
    k = 0
    gammas = [gamma, gamma * 0.9, gamma * 1.2, gamma * 0.8, gamma * 1.4]
    t_run = None
    rp = None
    runs = []
    while True:
        t0 = budget - clock.left()
        if k > 0:
            if not restarts or t_run is None or run_end - t0 < 1.1 * t_run:
                break
            _reset(C)
            C.rng = random.Random(seed * 1000 + k)
        C.trace = []
        g = gammas[k % len(gammas)] if not frozen else gamma
        it, beta = collapse_once(C, min(run_end - t0, budget * first) * 0.85, max(1.02, g), beta0,
                                 beta_end, beta_max, frozen, log)
        t_run = budget - clock.left() - t0
        st = r.stats()
        cost = kit.total_cost() + C.phys_w * ph.total()
        if full_w:
            if rp is None:
                import tempfile
                from physics import RoutedPhys
                rp = RoutedPhys(w, ph, tempfile.mkdtemp(prefix="jc-rp-"))
            v = rp(r)
            cost += full_w * (v if v is not None else 0.0)
            log(f"jc run {k}: routed physics {v}")
        log(f"jc run {k}: gamma={g:.2f} its={it} {st} hpwl={w.hpwl():.1f} phys={ph.total():.2f} "
            f"cost={cost:.1f} t_run={t_run:.1f}")
        runs.append(dict(k=k, gamma=round(g, 3), its=it, beta=round(beta, 3), cost=round(cost, 2),
                         t_run=round(t_run, 1), hpwl=round(w.hpwl(), 2), phys=round(ph.total(), 3), **st))
        if best is None or cost < best[0]:
            best = (cost, dict(w.pose), kit.snapshot(list(w.net_pins)), k, w.hist.copy(), C.hist_c.copy(),
                    list(C.trace))
        k += 1
    if best[3] != k - 1:  # restore the best run
        mov = kit.movable()
        for q in [q for q in mov if q in w.pose]:
            w.unplace(q)
        r.rip_all()
        r.unrouted.clear()
        for q, p in best[1].items():
            if q in mov:
                w.place(q, *p)
        kit.restore(best[2])
        ph.sync()
    w.hist[:] = best[4]
    C.hist_c[:] = best[5]
    r.legalize(list(w.net_pins))
    log(f"jc collapsed: best run {best[3]} of {k} {r.stats()} hpwl={w.hpwl():.1f} phys={ph.total():.2f} "
        f"t={budget - clock.left():.1f}")
    if png_dir is None:
        png_dir = os.environ.get("JC_PNG_DIR")
    if png_dir:
        C.obstruction_png(Path(png_dir) / f"{_board_id(w)}.png",
                          f"{_board_id(w)}: obstruction map (frozen={frozen})")
        np.save(str(Path(png_dir) / f"{_board_id(w)}.trace.npy"), np.array(best[6]))
        import json
        (Path(png_dir) / f"{_board_id(w)}.runs.json").write_text(json.dumps(dict(best=best[3], runs=runs)))
    if polish > 0 and clock.left() > 2:
        r = MP.anneal_phys(w, seed=seed, budget=max(1.0, clock.left()), log=log, phys_w=C.phys_w, router=r)
        log(f"jc polished: {r.stats()} hpwl={w.hpwl():.1f} phys={ph.total():.2f}")
    return r


def jc_nopol(world, **kw):
    """The continuation alone (restarts, no polish)."""
    kw.setdefault("polish", 0.0)
    return jc(world, **kw)


def jc_frozen(world, **kw):
    """Routing-only collapse: parts legalized right after the lift and frozen."""
    kw.setdefault("frozen", True)
    kw.setdefault("polish", 0.0)
    return jc(world, **kw)


def jc_fast(world, **kw):
    """Fast schedule (gamma 2, restarts, no polish)."""
    kw.setdefault("gamma", 2.0)
    kw.setdefault("polish", 0.0)
    return jc(world, **kw)


def jc_slow(world, **kw):
    """Slow schedule: one continuation paced to reach beta_end at the end of the budget."""
    kw.setdefault("gamma", 1.02)
    kw.setdefault("restarts", False)
    kw.setdefault("first", 1.0)
    kw.setdefault("polish", 0.0)
    return jc(world, **kw)


def jc_lv(world, **kw):
    """Length + vias objective (phys_w = 0), with the short polish."""
    kw["phys_w"] = 0.0
    return jc(world, **kw)


def jc_lv_nopol(world, **kw):
    """Length + vias objective (phys_w = 0), continuation alone."""
    kw["phys_w"] = 0.0
    kw.setdefault("polish", 0.0)
    return jc(world, **kw)


def jc_full(world, **kw):
    """Physics objective; restarts judged by routed cost + 2 fast physics + 5 full routed
    physics (RoutedPhys at the end of every continuation), no polish."""
    kw.setdefault("full_w", 5.0)
    kw.setdefault("polish", 0.0)
    return jc(world, **kw)
