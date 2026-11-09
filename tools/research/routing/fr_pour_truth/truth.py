# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pour truth of a routed board: per zone net, pad groups by KiCad's connectivity after refill.
Usage (KiCad python): truth.py BOARD.kicad_pcb OUT.json"""
import json, sys, os
os.environ.setdefault("WX_ASSERT_LEVEL", "0")
_O = os.fdopen(os.dup(1), "w"); os.dup2(2, 1)
import pcbnew
path, out = sys.argv[1:3]
b = pcbnew.LoadBoard(path)
zs = pcbnew.ZONES()
for i in range(b.GetAreaCount()):
    zs.append(pcbnew.Cast_to_ZONE(b.GetArea(i)))
if len(zs):
    pcbnew.ZONE_FILLER(b).Fill(zs)
b.BuildConnectivity()
conn = b.GetConnectivity()
znets = {}
for z in zs:
    if z.GetIsRuleArea(): continue
    n = z.GetNetname()
    if n:
        znets.setdefault(n, []).append(z)
res = {}
pads = {}
for fp in b.GetFootprints():
    for p in fp.Pads():
        n = p.GetNetname()
        if n in znets and p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
            pads.setdefault(n, []).append(p)
for n, ps in pads.items():
    idx = {p.m_Uuid.AsString(): i for i, p in enumerate(ps)}
    par = list(range(len(ps)))
    def f(x):
        while par[x] != x: par[x] = par[par[x]]; x = par[x]
        return x
    onfill = [False] * len(ps)
    for i, p in enumerate(ps):
        its = [q for q in conn.GetConnectedItems(p) if type(q).__name__ == 'PAD']
        for q in its:
            j = idx.get(q.m_Uuid.AsString())
            if j is not None:
                a, c = f(i), f(j)
                if a != c: par[a] = c
    groups = {}
    for i, p in enumerate(ps):
        groups.setdefault(f(i), []).append(dict(ref=p.GetParentFootprint().GetReference(), pad=p.GetNumber(),
                                                uuid=p.m_Uuid.AsString(), x=p.GetPosition().x/1e6, y=p.GetPosition().y/1e6))
    res[n] = sorted(groups.values(), key=lambda g: -len(g))
tracks = sum(1 for t in b.GetTracks())
json.dump(dict(nets=res, tracks=tracks, zones=len(zs), layers={z.GetNetname(): z.GetLayerName() for z in zs}), open(out, "w"))
print("ok", file=_O)
