# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Which KiCad fill rule separates pads the fork's fill model calls connected? For one routed board:
pad groups per zone net under varied zone settings. Usage: variants.py BOARD OUT.json"""
import json, sys, os
_O = os.fdopen(os.dup(1), "w"); os.dup2(2, 1)
import pcbnew
path, out = sys.argv[1:3]
def groups(b, zones):
    filler = pcbnew.ZONE_FILLER(b)
    zs = pcbnew.ZONES()
    for z in zones: zs.append(z)
    filler.Fill(zs)
    b.BuildConnectivity()
    conn = b.GetConnectivity()
    nets = {}
    for fp in b.GetFootprints():
        for p in fp.Pads():
            n = p.GetNetname()
            if n in znets and p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
                nets.setdefault(n, []).append(p)
    tot = 0
    for n, ps in nets.items():
        idx = {p.m_Uuid.AsString(): i for i, p in enumerate(ps)}
        par = list(range(len(ps)))
        def f(x):
            while par[x] != x: par[x] = par[par[x]]; x = par[x]
            return x
        for i, p in enumerate(ps):
            for q in conn.GetConnectedItems(p):
                if type(q).__name__ == "PAD":
                    j = idx.get(q.m_Uuid.AsString())
                    if j is not None:
                        a, c = f(i), f(j)
                        if a != c: par[a] = c
        tot += len({f(i) for i in range(len(ps))}) - 1
    return tot
b = pcbnew.LoadBoard(path)
zones = [pcbnew.Cast_to_ZONE(b.GetArea(i)) for i in range(b.GetAreaCount())]
zones = [z for z in zones if not z.GetIsRuleArea()]
znets = {z.GetNetname() for z in zones if z.GetNetname()}
orig = [(z.GetMinThickness(), z.GetPadConnection(), z.GetLocalClearance()) for z in zones]
res = dict(minw=[o[0]/1e6 for o in orig], clear=[(o[2] if isinstance(o[2], int) else 0)/1e6 for o in orig][:4])
res["base"] = groups(b, zones)
for z in zones: z.SetMinThickness(pcbnew.FromMM(0.02))
res["minw0"] = groups(b, zones)
for z in zones: z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
res["minw0_full"] = groups(b, zones)
for z, o in zip(zones, orig): z.SetMinThickness(o[0])
res["full"] = groups(b, zones)
json.dump(res, open(out, "w"))
print("ok", file=_O)
