# SPDX-License-Identifier: GPL-3.0-or-later
# synthetic: one rect SMD pad in a zone of its net, footprint rotated by ROT; where do KiCad's spokes go?
import pcbnew, sys, math
rot = float(sys.argv[1]); sa = float(sys.argv[2]) if len(sys.argv) > 2 else None
b = pcbnew.BOARD()
net = pcbnew.NETINFO_ITEM(b, "GND"); b.Add(net)
fp = pcbnew.FOOTPRINT(b); b.Add(fp)
p = pcbnew.PAD(fp); p.SetShape(pcbnew.PAD_SHAPE_RECT); p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
p.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(1.0), pcbnew.FromMM(0.3)))
ls = pcbnew.LSET(); ls.AddLayer(pcbnew.F_Cu); p.SetLayerSet(ls); p.SetNumber("1"); p.SetNet(net)
fp.Add(p); fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(50), pcbnew.FromMM(50)))
if sa is not None: p.SetThermalSpokeAngleDegrees(sa)
fp.SetOrientationDegrees(rot)
z = pcbnew.ZONE(b); z.SetLayer(pcbnew.F_Cu); z.SetNet(net)
o = z.Outline(); o.NewOutline()
for x, y in ((40, 40), (60, 40), (60, 60), (40, 60)): o.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL); z.SetThermalReliefGap(pcbnew.FromMM(0.5)); z.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.3)); z.SetMinThickness(pcbnew.FromMM(0.1))
b.Add(z)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
fill = z.GetFilledPolysList(pcbnew.F_Cu)
c = p.GetPosition()
print('rot', rot, 'pad orient', p.GetOrientationDegrees(), 'spoke angle', p.GetThermalSpokeAngleDegrees())
hits = []
for ang in range(0, 360, 5):
    f = ''.join('#' if fill.Contains(pcbnew.VECTOR2I(c.x + int(r_*1e6*math.cos(math.radians(ang))), c.y - int(r_*1e6*math.sin(math.radians(ang))))) else '.' for r_ in [0.05*k for k in range(3, 26)])
    print('  ', ang, f)
