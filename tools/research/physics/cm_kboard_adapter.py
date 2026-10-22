# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Temporary loader: a .kicad_pcb as Contract-1-shaped objects, for prototyping kae.circuit.

Until kae.board's loader lands, comprehension is exercised on the 112 reference boards
through rb_board_passports.KBoard (footprints, absolute pad positions, zones) plus one extra
pass over the footprint blocks for what KBoard drops (fields, attrs, rotation, side, uuid,
schematic sheet) and the sibling .kicad_pro for net classes. Field names follow Contract 1
(docs/topics/architecture/month-plan.md), so swapping in kae.board.kicad_file.load is a one-line
change in the callers. kae itself never imports this module.

Positions (Footprint.x/y, Pad.x/y) are filled for the evaluation script's weak labels only;
kae.circuit never reads them.

Usage (smoke test):  python -I cm_kboard_adapter.py BOARD.kicad_pcb
"""
import fnmatch
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rb_board_passports as rb  # noqa: E402
from pc_refplane import first, kids, parse  # noqa: E402


def _netclasses(pcb_path, net_names):
    """net -> class string from the .kicad_pro (cached assignments first, then wildcard patterns)."""
    pro = os.path.splitext(pcb_path)[0] + '.kicad_pro'
    try:
        ns = json.load(open(pro, encoding='utf-8')).get('net_settings', {})
    except (OSError, ValueError):
        return {}
    out = {}
    asg = ns.get('netclass_assignments') or {}
    for n, cl in asg.items():
        out[n] = ','.join(cl) if isinstance(cl, list) else str(cl)
    pats = [(p.get('pattern', ''), p.get('netclass', '')) for p in ns.get('netclass_patterns') or []]
    for n in net_names:
        if n in out:
            continue
        hit = []
        for pat, cl in pats:
            if not pat or cl in hit:
                continue
            if fnmatch.fnmatchcase(n.upper(), pat.upper()) or fnmatch.fnmatchcase(n.rsplit('/', 1)[-1].upper(), pat.upper()):
                hit.append(cl)
        if hit:
            out[n] = ','.join(hit)
    return out


def load(path):
    """Board-like namespace with Contract 1 field names (footprints, nets, zones, path, version)."""
    kb = rb.KBoard(path)
    tree = parse(open(path, encoding='utf-8', errors='replace').read())
    nodes = kids(tree, 'footprint') + kids(tree, 'module')
    assert len(nodes) == len(kb.fps), (len(nodes), len(kb.fps))
    fps = []
    for node, rec in zip(nodes, kb.fps):
        at = first(node, 'at')
        rot = float(at[3]) if at is not None and len(at) > 3 else 0.0
        props = {p[1]: p[2] for p in kids(node, 'property') if len(p) > 2}
        a = first(node, 'attr')
        attrs = set(a[1:]) if a else set()
        if first(node, 'locked') is not None or (len(node) > 2 and 'locked' in node[:4]):
            locked = True
        else:
            locked = False
        sheet = None
        sn = first(node, 'sheetname')
        sp = first(node, 'path')
        if sp is not None and len(sp) > 1 and '/' in str(sp[1]):
            sheet = str(sp[1]).rsplit('/', 1)[0] or '/'           # sheet instance path (UUIDs)
        elif sn is not None and len(sn) > 1:
            sheet = sn[1]
        uuid = (first(node, 'uuid') or [None, None])[1]
        fields = {k: v for k, v in props.items() if k not in ('Reference', 'Value')}
        pads = []
        pad_nodes = kids(node, 'pad')
        for pn, pd in zip(pad_nodes, rec['pads']):
            sz = first(pn, 'size')
            pads.append(SimpleNamespace(
                number=pd['num'], net=pd['net'], kind=pd['kind'], shape=pn[3] if len(pn) > 3 else '',
                size=(float(sz[1]), float(sz[2]) if len(sz) > 2 else float(sz[1])) if sz else None,
                x=pd['x'], y=pd['y'], layers=pd['layers'], drill=pd['drill'],
                pinfunction=pd.get('pinfunction') or '', pintype=pd.get('pintype') or ''))
        side = 'B' if str(rec['layer']).startswith('B.') else 'F'
        fps.append(SimpleNamespace(ref=rec['ref'], value=rec['value'], lib_id=rec['lib'], uuid=uuid, x=rec['x'], y=rec['y'],
                                   rot=rot, side=side, locked=locked, attrs=attrs, fields=fields, pads=pads, sheet=sheet,
                                   on_board=True))
    net_names = sorted({p.net for f in fps for p in f.pads if p.net})
    ncl = _netclasses(path, net_names)
    nets = {}
    for n in net_names:
        nets[n] = SimpleNamespace(name=n, netclass=ncl.get(n, ''), pads=[(f.ref, p.number) for f in fps for p in f.pads if p.net == n])
    zones = [SimpleNamespace(net=z['net'], layers=z['layers']) for z in kb.zones]
    return SimpleNamespace(path=path, version=kb.version, footprints=fps, nets=nets, zones=zones, outline=kb.outline,
                           stackup=SimpleNamespace(copper=kb.cu), _kb=kb)


if __name__ == '__main__':
    b = load(sys.argv[1])
    print(f"{len(b.footprints)} footprints, {len(b.nets)} nets, {len(b.zones)} zones, "
          f"{sum(1 for n in b.nets.values() if n.netclass)} nets with a net class")
    for f in b.footprints[:5]:
        print(f.ref, f.value, f.lib_id, sorted(f.attrs), f.sheet, [(p.number, p.net, p.pinfunction, p.pintype) for p in f.pads][:4])
