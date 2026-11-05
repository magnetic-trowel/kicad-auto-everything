# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Runs under KiCad's Python. Writes the round-trip variants of one board and an
inventory of each, as pcbnew sees it, for roundtrip_audit.py.

    python pcbnew_inventory.py BOARD WORKDIR OUT_JSON

Variants (all in WORKDIR):
  plain.kicad_pcb    PCB_IO_MGR.Load + PCB_IO_MGR.Save (kae's writer)
  plain2.kicad_pcb   plain.kicad_pcb re-saved the same way (idempotence)
  lb_plain.kicad_pcb LoadBoard + PCB_IO_MGR.Save (what import_ses did)
  lb_save.kicad_pcb  LoadBoard + SaveBoard (the old fallback)
The inventory of each variant is taken from a plain re-load of that file.
"""
import json
import os
import shutil
import sys
import tempfile

_OUT = os.fdopen(os.dup(1), "w")
os.dup2(2, 1)
import pcbnew  # noqa: E402

SEXP = pcbnew.PCB_IO_MGR.KICAD_SEXP


def warm():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "w.kicad_pcb")
    with open(p, "w") as f:
        f.write('(kicad_pcb (version 20240108) (generator "pcbnew") (generator_version "8.0"))\n')
    pcbnew.LoadBoard(p)
    shutil.rmtree(d)


def plain_load(p):
    return pcbnew.PCB_IO_MGR.Load(SEXP, p)


def save_plain(board, dest):
    d = tempfile.mkdtemp()
    tmp = os.path.join(d, os.path.basename(dest))
    pcbnew.PCB_IO_MGR.Save(SEXP, tmp, board)
    shutil.move(tmp, dest)
    shutil.rmtree(d)


def save_board(board, dest):
    d = tempfile.mkdtemp()
    tmp = os.path.join(d, os.path.basename(dest))
    ok = pcbnew.SaveBoard(tmp, board, True)
    shutil.move(tmp, dest)
    shutil.rmtree(d)
    return ok


def pt(v):
    return [int(v.x), int(v.y)]


def inventory(board):
    """Multisets as sorted lists of keys, comparable across files (no uuids, which a
    pre-6 file does not carry and pcbnew invents)."""
    fps, pads, fpitems = [], [], []
    for fp in board.GetFootprints():
        fps.append([fp.GetReference(), pt(fp.GetPosition()), round(fp.GetOrientationDegrees(), 4),
                    int(fp.GetLayer()), bool(fp.IsLocked()), len(fp.Pads()), len(fp.GraphicalItems()),
                    len(fp.Zones()), len(fp.Models()), len(fp.GetFields())])
        for p in fp.Pads():
            pads.append([fp.GetReference(), p.GetNumber(), pt(p.GetPosition()), p.GetNetname(),
                         int(p.GetAttribute())])
        for g in fp.GraphicalItems():
            fpitems.append([fp.GetReference(), g.GetClass(), int(g.GetLayer())])
    tracks = []
    for t in board.GetTracks():
        c = t.GetClass()
        if c == "PCB_VIA":
            tracks.append([c, pt(t.GetPosition()), t.GetWidth(pcbnew.F_Cu), t.GetNetname(), bool(t.IsLocked())])
        else:
            tracks.append([c, pt(t.GetStart()), pt(t.GetEnd()), int(t.GetLayer()), t.GetWidth(),
                           t.GetNetname(), bool(t.IsLocked())])
    drawings = []
    for d in board.GetDrawings():
        rec = [d.GetClass(), int(d.GetLayer())]
        if d.GetClass() == "PCB_SHAPE":
            rec += [d.ShowShape(), pt(d.GetStart()), pt(d.GetEnd()), d.GetWidth()]
        elif hasattr(d, "GetText"):
            rec += [d.GetText(), pt(d.GetPosition())]
        drawings.append(rec)
    zones = []
    for z in board.Zones():
        zones.append([z.GetNetname(), bool(z.GetIsRuleArea()), sorted(int(x) for x in z.GetLayerSet().Seq()),
                      z.Outline().FullPointCount(), z.GetAssignedPriority(), bool(z.IsLocked())])
    nets = sorted(str(n) for n in board.GetNetsByName().keys() if str(n))
    emb = -1  # EMBEDDED_FILES is not wrapped by SWIG in 10.0.7; counted from the file text
    groups = len(board.Groups()) if hasattr(board, "Groups") else -1
    return dict(footprints=sorted(fps, key=json.dumps), pads=sorted(pads, key=json.dumps),
                fpitems=sorted(fpitems, key=json.dumps), tracks=sorted(tracks, key=json.dumps),
                drawings=sorted(drawings, key=json.dumps), zones=sorted(zones, key=json.dumps),
                nets=[str(n) for n in nets], embedded=emb, groups=groups)


def main(src, work, out):
    warm()
    os.makedirs(work, exist_ok=True)
    res = {}
    b = plain_load(src)
    res["orig"] = inventory(b)
    p1 = os.path.join(work, "plain.kicad_pcb")
    save_plain(b, p1)
    b1 = plain_load(p1)
    res["plain"] = inventory(b1)
    p2 = os.path.join(work, "plain2.kicad_pcb")
    save_plain(b1, p2)
    res["plain2"] = inventory(plain_load(p2))
    lb = pcbnew.LoadBoard(src)
    res["lb_live"] = inventory(lb)
    p3 = os.path.join(work, "lb_plain.kicad_pcb")
    save_plain(lb, p3)
    res["lb_plain"] = inventory(plain_load(p3))
    lb2 = pcbnew.LoadBoard(src)
    p4 = os.path.join(work, "lb_save.kicad_pcb")
    res["lb_save_ok"] = bool(save_board(lb2, p4))
    res["lb_save"] = inventory(plain_load(p4))
    with open(out, "w") as f:
        json.dump(res, f)
    _OUT.write('{"ok": true}\n')


if __name__ == "__main__":
    main(*sys.argv[1:4])
