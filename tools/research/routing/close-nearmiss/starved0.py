# SPDX-License-Identifier: GPL-3.0-or-later
# Does KiCad's DRC flag starved_thermal for a pad with 0 spokes? A GND SMD pad in a GND zone, foreign-net
# tracks across k of its 4 spoke directions; the pad also joined to a second GND pad by a track (or not).
# usage: starved0.py OUT.kicad_pcb K TRACK(0|1)
import pcbnew, sys
out, K, tr = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
mm = pcbnew.FromMM
b = pcbnew.BOARD()
gnd = pcbnew.NETINFO_ITEM(b, "GND"); b.Add(gnd)
sig = pcbnew.NETINFO_ITEM(b, "SIG"); b.Add(sig)
for x0, y0, x1, y1 in ((30, 30, 70, 30), (70, 30, 70, 70), (70, 70, 30, 70), (30, 70, 30, 30)):
    s = pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetLayer(pcbnew.Edge_Cuts)
    s.SetStart(pcbnew.VECTOR2I(mm(x0), mm(y0))); s.SetEnd(pcbnew.VECTOR2I(mm(x1), mm(y1))); b.Add(s)
def pad(x, y, num):
    fp = pcbnew.FOOTPRINT(b); b.Add(fp)
    p = pcbnew.PAD(fp); p.SetShape(pcbnew.PAD_SHAPE_RECT); p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetSize(pcbnew.VECTOR2I(mm(1.0), mm(1.0)))
    ls = pcbnew.LSET(); ls.AddLayer(pcbnew.F_Cu); p.SetLayerSet(ls); p.SetNumber("1"); p.SetNet(gnd)
    fp.Add(p); fp.SetReference(num); fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    return p
p1 = pad(50, 50, "U1"); pad(40, 40, "U2")
# foreign tracks crossing the spoke directions, 0.9 mm from the pad centre (inside the 1 mm thermal gap ring)
segs = [((50.9, 48), (50.9, 52)), ((49.1, 48), (49.1, 52)), ((48, 50.9), (52, 50.9)), ((48, 49.1), (52, 49.1))]
for (a, c) in segs[:K]:
    t = pcbnew.PCB_TRACK(b); t.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1]))); t.SetEnd(pcbnew.VECTOR2I(mm(c[0]), mm(c[1])))
    t.SetWidth(mm(0.2)); t.SetLayer(pcbnew.F_Cu); t.SetNet(sig); b.Add(t)
if tr:   # the pad's own connection to the other GND pad, leaving diagonally between the foreign tracks
    for (a, c) in (((50, 50), (52.5, 52.5)), ((52.5, 52.5), (40, 40))):
        t = pcbnew.PCB_TRACK(b); t.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1]))); t.SetEnd(pcbnew.VECTOR2I(mm(c[0]), mm(c[1])))
        t.SetWidth(mm(0.2)); t.SetLayer(pcbnew.F_Cu); t.SetNet(gnd); b.Add(t)
z = pcbnew.ZONE(b); z.SetLayer(pcbnew.F_Cu); z.SetNet(gnd)
o = z.Outline(); o.NewOutline()
for x, y in ((31, 31), (69, 31), (69, 69), (31, 69)): o.Append(mm(x), mm(y))
z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL); z.SetThermalReliefGap(mm(0.5)); z.SetThermalReliefSpokeWidth(mm(0.3))
z.SetMinThickness(mm(0.2)); z.SetLocalClearance(mm(0.3))
b.Add(z)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.Save(out)
