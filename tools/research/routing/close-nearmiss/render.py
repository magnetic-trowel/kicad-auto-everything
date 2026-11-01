# SPDX-License-Identifier: GPL-3.0-or-later
"""Render a window of several routed boards side by side: pads (outline, label = net when
highlighted), tracks (F red, B blue, inner green), vias; highlight nets; mark opens.
usage: render.py out.png x0,y0,x1,y1 net1,net2 drc.json[.gz]|- board1[:title] board2[:title] ...
"""
import sys, json, gzip, re, math
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
from matplotlib.transforms import Affine2D
from kae.board.kicad_file import load

out, win, hl, drcp = sys.argv[1], [float(v) for v in sys.argv[2].split(",")], set(sys.argv[3].split(",")), sys.argv[4]
boards = sys.argv[5:]
opens = []
if drcp != "-":
    d = json.load(gzip.open(drcp) if drcp.endswith(".gz") else open(drcp))
    for u in d["unconnected_items"]:
        it = u["items"]
        if len(it) == 2:
            opens.append(((it[0]["pos"]["x"], it[0]["pos"]["y"]), (it[1]["pos"]["x"], it[1]["pos"]["y"])))
COL = {"F.Cu": "tab:red", "B.Cu": "tab:blue"}
fig, axs = plt.subplots(1, len(boards), figsize=(10 * len(boards), 10))
axs = [axs] if len(boards) == 1 else axs
x0, y0, x1, y1 = win


def inwin(x, y, m=2):
    return x0 - m <= x <= x1 + m and y0 - m <= y <= y1 + m


for ax, spec in zip(axs, boards):
    path, _, title = spec.partition(":")
    if path.endswith(".gz"):
        import tempfile, shutil
        tf = tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False)
        with gzip.open(path, "rb") as f:
            shutil.copyfileobj(f, tf)
        tf.close()
        path = tf.name
    b = load(path, rules=False)
    for fp in b.footprints:
        for p in fp.pads:
            if not inwin(p.x, p.y):
                continue
            cu = [l for l in p.layers if l.endswith(".Cu") or l == "*.Cu"]
            c = "k" if p.drill or "*.Cu" in cu else COL.get(cu[0] if cu else "", "gray")
            w, h = p.size
            rot = (fp.rot or 0) + (p.lrot or 0)
            on = p.net in hl
            if p.shape == "circle":
                patch = Circle((p.x, p.y), w / 2, fill=on, alpha=0.5 if on else 1, ec=c, fc=c, lw=0.8)
            else:
                patch = Rectangle((p.x - w / 2, p.y - h / 2), w, h, fill=on, alpha=0.5 if on else 1, ec=c, fc=c, lw=0.8,
                                  transform=Affine2D().rotate_deg_around(p.x, p.y, -rot) + ax.transData)
            ax.add_patch(patch)
            if on:
                ax.text(p.x, p.y, p.net[:10], fontsize=6, ha="center")
    for t in b.tracks:
        if not (inwin(*t.start, 10) or inwin(*t.end, 10)):
            continue
        on = t.net in hl
        ax.plot([t.start[0], t.end[0]], [t.start[1], t.end[1]], color=COL.get(t.layer, "tab:green"),
                lw=max(0.6, t.width * 25 / max(1, (x1 - x0) / 5)) * (1.6 if on else 1), alpha=1.0 if on else 0.45,
                solid_capstyle="round")
    for v in b.vias:
        if inwin(v.x, v.y):
            ax.add_patch(Circle((v.x, v.y), v.size / 2, fc="k" if v.net in hl else "0.5", ec="k", lw=0.3))
    for a, c in opens:
        ax.plot([a[0], c[0]], [a[1], c[1]], "g--", lw=1.2)
        ax.plot([a[0], c[0]], [a[1], c[1]], "gx", ms=7)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y1, y0)
    ax.set_aspect("equal")
    ax.set_title(title or path, fontsize=10)
fig.tight_layout()
fig.savefig(out, dpi=90)
