# SPDX-License-Identifier: GPL-3.0-or-later
# Is the human's copper of the given nets inside a box legal in our Space (bare input board)?
# usage: hcheck.py <input> <human .gz> x0,y0,x1,y1 net1,net2,...   (checks each item alone against pads/obstacles,
# then all the human's copper of those nets together)
import sys, gzip, shutil, collections
from pathlib import Path
from shapely.geometry import box, LineString, Point
from kae.board import pcbnew_io
from kae.board.kicad_file import load
from kae.route import constraints, bridge
from kae.route.critical_space import Space
inp, hum, bx, nets = sys.argv[1], sys.argv[2], [float(v) for v in sys.argv[3].split(',')], set(sys.argv[4].split(','))
import tempfile
od = Path(tempfile.mkdtemp(prefix='hcheck-'))
with gzip.open(hum, 'rb') as f, open(od / 'h.kicad_pcb', 'wb') as g: shutil.copyfileobj(f, g)
hb = load(od / 'h.kicad_pcb', rules=False)
opts = dict(bridge.DEFAULT_OPTS, seed=0)
info = pcbnew_io.export_dsn(inp, od / 'k.dsn')
opts['severities'] = bridge.severities(inp)
plan = constraints.plan(info, inp, opts)
sp = Space(load(inp), info, plan=plan, sev=opts['severities'])
win = box(*bx)
for n in sorted(nets):
    print(n, 'our via', sp.via_size(n), 'widths', sp.width_limits(n, sp.cu[0]))
items = []
for t in hb.tracks:
    if t.net in nets and LineString([t.start, t.end]).intersects(win):
        items.append(('t', t))
for v in hb.vias:
    if v.net in nets and Point(v.x, v.y).intersects(win):
        items.append(('v', v))
for k, x in items:
    if k == 't':
        vs = sp.track_violations(x.net, x.layer, x.width, x.start, x.end)
        print('track', x.net, x.layer, x.width, [round(c, 2) for c in x.start], [(getattr(v[0], 'kind', v[0]), getattr(v[0], 'net', ''), str(getattr(v[0], 'owner', ''))[:25], [round(a, 3) for a in v[1:3]]) for v in vs][:3])
    else:
        vs = sp.via_violations(x.net, x.x, x.y, size=x.size, drill=x.drill)
        print('via', x.net, x.size, x.drill, (round(x.x, 2), round(x.y, 2)), [(getattr(v[0], 'kind', v[0]), getattr(v[0], 'net', ''), str(getattr(v[0], 'owner', ''))[:25], [round(a, 3) for a in v[1:3]]) for v in vs][:3])
