# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Figure: one net's harmonic field on a human-placed board (potential, expected wire
occupancy |J|/I, streamline tree vs the engine's A* route).

    python fig_field.py BOARD_ID OUT.png
"""
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pnr"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import methods as M  # noqa: E402
from common import load_world  # noqa: E402
from field import Field  # noqa: E402
from stream import tree_to_fine  # noqa: E402


def main(board, out):
    w = load_world(board)
    for pi in range(len(w.parts)):
        w.place_original(pi)
    r = M._router(w, {})
    nets = sorted(w.net_pins, key=lambda n: -len(w.net_pins[n]))
    F = Field(w, 0.4)
    # route every other net first (committed copper = walls), then the target net
    tgt = nets[min(1, len(nets) - 1)]
    for n in nets:
        if n != tgt:
            r.route_net(n, hard=True)
    sig = F.sigma(tgt)
    phi, pins, src = F.solve(tgt, sig)
    tree = F.streamlines(phi, sig, pins, src)
    fine = tree_to_fine(w, F, tgt, tree, pins, src)
    dens = F.density(phi, sig).reshape(F.L, F.Hc, F.Wc)
    r.route_net(tgt, hard=True)
    s = F.s
    ext = (w.x0, w.x0 + F.Wc * s * w.g, w.y0 + F.Hc * s * w.g, w.y0)
    fig, ax = plt.subplots(1, 3, figsize=(15, 5))
    ax[0].imshow(np.nanmax(phi.reshape(F.L, F.Hc, F.Wc), 0), extent=ext, cmap="viridis")
    ax[0].set_title(f"potential (net {w.net_names[tgt]}, max over layers)")
    ax[1].imshow(np.log10(dens.sum(0) + 1e-4), extent=ext, cmap="magma")
    ax[1].set_title("expected occupancy |J|/I (log10)")
    walls = (sig.min(0) < 0.02).astype(float)
    ax[2].imshow(walls, extent=ext, cmap="Greys", alpha=0.5)
    for p in fine:
        if p is not None:
            ax[2].plot(w.x0 + p[:, 2] * w.g, w.y0 + p[:, 1] * w.g, "C3-", lw=1.4)
    for p in r.routes.get(tgt, []):
        ax[2].plot(w.x0 + p[:, 2] * w.g, w.y0 + p[:, 1] * w.g, "C0--", lw=1.0)
    ax[2].set_title("streamline tree (red) vs A* (blue dashed); walls grey")
    for a in ax:
        for o in w.outline:
            a.plot(np.r_[o[:, 0], o[0, 0]], np.r_[o[:, 1], o[0, 1]], "c-", lw=0.8)
        a.set_aspect("equal")
    fig.suptitle(board)
    fig.tight_layout()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=100)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
