# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic but PCB-like placement instances for solver micro-benchmarks.

Footprint courtyards (mm) and pin offsets (mm, relative to footprint centre, rotation 0)
are rough IPC-7351-nominal approximations; they are only meant to give a realistic size
mix (many tiny passives, some ICs, a few big connectors).
"""
import math
import random
from dataclasses import dataclass, field


@dataclass
class Fp:
    name: str
    w: float
    h: float
    pins: list  # list of (dx, dy)
    tht: bool = False


def _qfn(n, body, pitch):
    per = n // 4
    pins = []
    span = (per - 1) * pitch / 2
    e = body / 2
    for i in range(per):
        t = -span + i * pitch
        pins += [(-e, t), (t, -e), (e, -t), (-t, e)]
    return pins


FPS = {
    "R0402": Fp("R0402", 1.8, 1.0, [(-0.5, 0), (0.5, 0)]),
    "C0402": Fp("C0402", 1.8, 1.0, [(-0.5, 0), (0.5, 0)]),
    "C0603": Fp("C0603", 2.6, 1.4, [(-0.8, 0), (0.8, 0)]),
    "SOT23": Fp("SOT23", 3.4, 3.0, [(-0.95, -1.1), (0.95, -1.1), (0, 1.1)]),
    "SOIC8": Fp("SOIC8", 7.4, 5.4, [(-2.7, y) for y in (-1.905, -0.635, 0.635, 1.905)]
                + [(2.7, y) for y in (-1.905, -0.635, 0.635, 1.905)]),
    "QFN32": Fp("QFN32", 6.0, 6.0, _qfn(32, 5.0, 0.5)),
    "TQFP64": Fp("TQFP64", 13.0, 13.0, _qfn(64, 11.0, 0.5)),
    "HDR2x5": Fp("HDR2x5", 13.5, 6.0, [(-5.08 + 2.54 * i, s * 1.27) for i in range(5) for s in (-1, 1)], tht=True),
}


@dataclass
class Comp:
    id: int
    fp: Fp
    cluster: int


@dataclass
class Instance:
    comps: list
    nets: list            # list of list of (comp_id, pin_idx)
    decaps: list          # list of (cap_comp, cap_pin, ic_comp, ic_pin, dmax_mm)
    board_w: float
    board_h: float
    keepouts: list        # list of (x, y, w, h) mm, fixed
    meta: dict = field(default_factory=dict)


def make_instance(n, seed=0, util=0.45, aspect=1.5, decaps_per_ic=(2, 4), dmax=3.0):
    rnd = random.Random(seed)
    comps = []

    def add(fpname, cl):
        comps.append(Comp(len(comps), FPS[fpname], cl))
        return comps[-1]

    n_ic = max(1, round(n / 15))
    n_conn = max(1, round(n / 50))
    ics = []
    for i in range(n_ic):
        ics.append(add(rnd.choice(["QFN32", "TQFP64", "SOIC8", "QFN32"]), i))
    decaps = []
    for ic in ics:
        k = rnd.randint(*decaps_per_ic)
        # pick VDD pins spread around the IC
        vdd_pins = rnd.sample(range(len(ic.fp.pins)), k)
        for p in vdd_pins:
            c = add("C0402", ic.cluster)
            decaps.append((c.id, 0, ic.id, p, dmax))
    for i in range(n_conn):
        add("HDR2x5", rnd.randrange(n_ic))
    n_sot = max(0, round(n / 12))
    for i in range(n_sot):
        add("SOT23", rnd.randrange(n_ic))
    while len(comps) < n:
        add(rnd.choice(["R0402", "R0402", "C0402", "C0603"]), rnd.randrange(n_ic))
    comps = comps[:n]
    decaps = [d for d in decaps if d[0] < n and d[2] < n]

    by_cluster = {}
    for c in comps:
        by_cluster.setdefault(c.cluster, []).append(c)

    nets = []
    used = set()
    # power nets: IC VDD pin + its decap pin 1 (pin 0 of decap goes to VDD, pin 1 -> GND plane, ignored)
    for (cc, cp, ic, ip, _) in decaps:
        nets.append([(ic, ip), (cc, cp)])
        used.add((ic, ip)); used.add((cc, cp)); used.add((cc, 1))
    # signal nets: every free pin of non-IC parts connects to an IC pin (mostly own cluster) and
    # sometimes to another passive pin -> 2..4 pin nets with locality
    ic_ids = [c.id for c in comps if c.fp.name in ("QFN32", "TQFP64", "SOIC8")]
    for c in comps:
        if c.fp.name in ("QFN32", "TQFP64", "SOIC8"):
            continue
        for pi in range(len(c.fp.pins)):
            if (c.id, pi) in used:
                continue
            if rnd.random() < 0.25:     # left for GND / unconnected
                continue
            cl_ics = [i for i in ic_ids if comps[i].cluster == c.cluster] or ic_ids
            if rnd.random() < 0.15:
                cl_ics = ic_ids        # some inter-cluster nets
            ic = rnd.choice(cl_ics)
            free = [p for p in range(len(comps[ic].fp.pins)) if (ic, p) not in used]
            if not free:
                continue
            ip = rnd.choice(free)
            net = [(c.id, pi), (ic, ip)]
            used.add((c.id, pi)); used.add((ic, ip))
            if rnd.random() < 0.3:
                others = [o for o in by_cluster[c.cluster] if o.id != c.id and o.fp.name in ("R0402", "C0603", "C0402")]
                if others:
                    o = rnd.choice(others)
                    op = rnd.randrange(len(o.fp.pins))
                    if (o.id, op) not in used:
                        net.append((o.id, op)); used.add((o.id, op))
            nets.append(net)
    # a few IC-to-IC buses
    for _ in range(max(1, n // 20)):
        if len(ic_ids) < 2:
            break
        a, b = rnd.sample(ic_ids, 2)
        fa = [p for p in range(len(comps[a].fp.pins)) if (a, p) not in used]
        fb = [p for p in range(len(comps[b].fp.pins)) if (b, p) not in used]
        if fa and fb:
            pa, pb = rnd.choice(fa), rnd.choice(fb)
            nets.append([(a, pa), (b, pb)]); used.add((a, pa)); used.add((b, pb))

    area = sum(c.fp.w * c.fp.h for c in comps)
    hole = 6.0
    ko_area = 4 * hole * hole
    tot = area / util + ko_area
    bh = math.sqrt(tot / aspect)
    bw = aspect * bh
    # make room for the antenna-style edge keep-out too
    bw *= 1.05
    keepouts = [(0, 0, hole, hole), (bw - hole, 0, hole, hole), (0, bh - hole, hole, hole),
                (bw - hole, bh - hole, hole, hole),
                (bw * 0.4, bh - 0.12 * bh, 0.2 * bw, 0.12 * bh)]  # edge keep-out (e.g. antenna)
    return Instance(comps, nets, decaps, bw, bh, keepouts,
                    meta=dict(n=n, seed=seed, util=util, n_nets=len(nets), n_decaps=len(decaps),
                              board_mm=(round(bw, 1), round(bh, 1))))


if __name__ == "__main__":
    for n in (30, 100, 300, 1000):
        inst = make_instance(n)
        print(inst.meta, sum(len(x) for x in inst.nets), "pins in nets")
