# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# dump pads/tracks/vias of a (gz) kicad_pcb to json: dump.py IN.kicad_pcb[.gz] OUT.json
import pcbnew, sys, json, gzip, os, tempfile, shutil
src, out = sys.argv[1], sys.argv[2]
tmp = None
if src.endswith('.gz'):
    tmp = tempfile.mkdtemp(dir=os.environ.get('TMPDIR', os.path.join(os.environ.get('ESC_WORK', '.'), 'tmp')))
    p = os.path.join(tmp, 'b.kicad_pcb')
    with gzip.open(src) as f, open(p, 'wb') as g: shutil.copyfileobj(f, g)
    src = p
b = pcbnew.LoadBoard(src)
mm = pcbnew.ToMM
ds = b.GetDesignSettings()
L = lambda l: b.GetLayerName(l)
res = {'min_track': mm(ds.m_TrackMinWidth), 'min_clear': mm(ds.m_MinClearance),
       'min_via': mm(ds.m_ViasMinSize), 'min_drill': mm(ds.m_MinThroughDrill),
       'copper': b.GetCopperLayerCount(), 'netclasses': {}, 'fps': [], 'tracks': [], 'vias': [], 'zones': []}
try:
    ns = ds.m_NetSettings
    for name, nc in list(ns.GetNetclasses().items()) + [('Default', ns.GetDefaultNetclass())]:
        try:
            res['netclasses'][str(name)] = {'track': mm(nc.GetTrackWidth()), 'clear': mm(nc.GetClearance()),
                                            'via': mm(nc.GetViaDiameter()), 'drill': mm(nc.GetViaDrill())}
        except Exception as e: pass
except Exception as e:
    res['nc_err'] = str(e)
for fp in b.GetFootprints():
    f = {'ref': fp.GetReference(), 'fpid': fp.GetFPIDAsString(), 'x': mm(fp.GetPosition().x), 'y': mm(fp.GetPosition().y),
         'rot': fp.GetOrientationDegrees(), 'side': L(fp.GetLayer()), 'pads': []}
    for p in fp.Pads():
        ls = [L(l) for l in p.GetLayerSet().CuStack()]
        nc = ''
        try: nc = p.GetNetClassName()
        except Exception: pass
        f['pads'].append({'n': p.GetNumber(), 'x': mm(p.GetPosition().x), 'y': mm(p.GetPosition().y),
                          'sx': mm(p.GetSizeX()), 'sy': mm(p.GetSizeY()), 'rot': p.GetOrientationDegrees(),
                          'shape': int(p.GetShape()), 'attr': int(p.GetAttribute()), 'layers': ls,
                          'net': p.GetNetname(), 'nc': nc, 'drill': mm(p.GetDrillSizeX())})
    res['fps'].append(f)
for t in b.GetTracks():
    c = t.GetClass()
    if c == 'PCB_VIA':
        res['vias'].append({'x': mm(t.GetPosition().x), 'y': mm(t.GetPosition().y), 'd': mm(t.GetWidth(pcbnew.F_Cu)) if hasattr(t,'GetWidth') else 0,
                            'drill': mm(t.GetDrillValue()), 'net': t.GetNetname(), 'top': L(t.TopLayer()), 'bot': L(t.BottomLayer())})
    else:
        res['tracks'].append({'x1': mm(t.GetStart().x), 'y1': mm(t.GetStart().y), 'x2': mm(t.GetEnd().x), 'y2': mm(t.GetEnd().y),
                              'w': mm(t.GetWidth()), 'l': L(t.GetLayer()), 'net': t.GetNetname(), 'arc': c == 'PCB_ARC'})
for z in b.Zones():
    if z.GetIsRuleArea(): continue
    res['zones'].append({'net': z.GetNetname(), 'layers': [L(l) for l in z.GetLayerSet().CuStack()], 'filled': z.IsFilled()})
json.dump(res, open(out, 'w'))
if tmp: shutil.rmtree(tmp)
