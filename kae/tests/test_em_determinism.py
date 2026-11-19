# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The physics evaluator gives the same numbers for the same copper: the order a file lists its tracks and vias
in never changes the mesh (kae.em.kicad.canonical_order), and the thread count never changes a solve (kae.em.blas)."""
import os
import random
import subprocess
import sys
from types import SimpleNamespace

import numpy as np

from kae.board.model import Stackup, Track, Via
from kae.em.kicad import BoardMesh, canonical_order


def _board(seed):
    """Copper where painting order mattered: thin tracks of two nets sharing raster cells, two overlapping thin
    tracks of one net, wide tracks of two nets whose edge cells touch, a via."""
    tr = [Track(uuid=f"t{k}", net=n, layer="F.Cu", width=w, start=s, end=e) for k, (n, w, s, e) in enumerate([
        ("A", 0.15, (0.2, 0.05), (5.8, 0.05)),
        ("B", 0.15, (0.3, 0.2), (5.6, 0.2)),
        ("A", 0.15, (1.0, 0.05), (1.0, 1.5)),
        ("A", 0.15, (1.0, 0.07), (1.0, 1.5)),
        ("C", 1.0, (0.5, 2.0), (5.0, 2.0)),
        ("D", 1.0, (0.5, 2.8), (5.0, 2.8)),
        ("C", 0.2, (2.0, 2.0), (2.0, 3.6)),
        ("C", 0.2, (2.0, 3.6), (4.0, 3.6), ),
    ])]
    vias = [Via(uuid=f"v{k}", net=n, x=x, y=y, size=0.6, drill=0.3, layers=["F.Cu", "B.Cu"])
            for k, (n, x, y) in enumerate([("C", 4.0, 3.6), ("A", 5.8, 0.05)])]
    rng = random.Random(seed)
    rng.shuffle(tr), rng.shuffle(vias)
    su = Stackup(copper=["F.Cu", "B.Cu"], cu_thickness=[0.035, 0.035], gaps=[1.5], er=[4.5], thickness=1.6,
                 source="assumed")
    return SimpleNamespace(tracks=tr, vias=vias, footprints=[], stackup=su, zones=[])


def _mesh(seed):
    m = BoardMesh(None, (0, -1, 6, 4), 0.25, b=_board(seed), fills={}).m
    names = np.vectorize(lambda k: m.nets[k] if k >= 0 else "")(m.lab)
    return names, m.cov.copy(), sorted(m.thin.items()), [b[1:] for b in m.bridges], \
        sorted((v.x, v.y, tuple(v.layers), m.nets[v.net]) for v in m.vias)


def test_the_file_order_of_tracks_and_vias_never_changes_the_mesh():
    """A router that writes the same copper in another order (two harness commits did) got another raster:
    the later of two claims on a cell won, and loss and drop moved by about 1 %. Every order now meshes alike."""
    ref = _mesh(0)
    for seed in range(1, 8):
        got = _mesh(seed)
        assert (got[0] == ref[0]).all()
        assert np.array_equal(got[1], ref[1])
        assert got[2:] == ref[2:]


def test_canonical_order_sorts_in_place_by_content():
    a, b = _board(1), _board(2)
    assert [t.uuid for t in a.tracks] != [t.uuid for t in b.tracks]
    canonical_order(a), canonical_order(b)
    assert [t.uuid for t in a.tracks] == [t.uuid for t in b.tracks]
    assert [v.uuid for v in a.vias] == [v.uuid for v in b.vias]


_PROBE = r"""
import numpy as np
from kae.em import solve as ES
from kae.em.mesh import Layer, Mesh
m = Mesh.over(0, 0, 24, 18, 0.25, [Layer("T", 1.6, 0.035, 2), Layer("B", 0.0, 0.035, 2)])
m.rect(0, "A", 1, 1, 23, 4); m.rect(0, "A", 1, 1, 4, 17); m.rect(0, "A", 20, 1, 23, 17)
m.rect(1, "G", 0.5, 0.5, 23.5, 17.5)
m.paint_line(0, "S", [(6, 8), (18, 9), (18, 15)], 0.2)
for name, l, x, y, net in [("a", 0, 21.5, 15, "A"), ("g", 1, 21.5, 15, "G"), ("s0", 0, 6, 8, "S"), ("s1", 0, 18, 15, "S"),
                           ("g0", 1, 6, 8, "G"), ("g1", 1, 18, 15, "G"), ("a2", 0, 2.5, 2.5, "A"), ("g2", 1, 2.5, 2.5, "G")]:
    m.terminal(name, l, xy=(x, y), net=net)
m.part("a2", "g2", R=0.5, L=1e-9)
m.part("s1", "g1", R=50.0)
net = ES.Network(m); op = ES.Operator(net)
out = []
for f in (0.0, 5e7):
    res = ES.potentials_many(m, [{"a": 1.0, "g": -1.0}, {"s0": 1.0, "g0": -1.0}, {"s0": 1.0, "a": -1.0}], f, net=net,
                             op=op, tol=1e-4)
    for V, info in res:
        out += [complex(V[t]) for t in sorted(V) if V[t] is not None and np.isfinite(V[t])]
print(" ".join(f"{z.real.hex()},{z.imag.hex()}" for z in out))
"""


def _probe(threads):
    env = dict(os.environ, KAE_EM_THREADS=str(threads), OMP_NUM_THREADS=str(threads),
               OPENBLAS_NUM_THREADS=str(threads), MKL_NUM_THREADS=str(threads), PYTHONHASHSEED=str(threads))
    env.pop("KAE_EM_BLAS_THREADS", None)
    src = os.path.join(os.path.dirname(__file__), "..", "src")
    env["PYTHONPATH"] = os.pathsep.join([os.path.abspath(src)] + [p for p in [env.get("PYTHONPATH")] if p])
    r = subprocess.run([sys.executable, "-W", "ignore", "-c", _PROBE], env=env, capture_output=True, text=True,
                       timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    return r.stdout.split()


def test_a_field_solve_is_bit_identical_at_any_thread_count():
    """A DC and a 50 MHz COCG solve of a plane, a pour and a thin track, in fresh processes at 1 and 4 threads (and
    two hash seeds). A threaded OpenBLAS (SuperLU's solves) had moved the 50 MHz potentials by up to 5e-9."""
    one, four = _probe(1), _probe(4)
    assert len(one) == 48 and one == four
