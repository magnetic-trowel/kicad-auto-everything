# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""scan_task_inputs.py KAE_SRC boards.txt OUT.json FIXED.json (from classify_fixed.py)
Array detector on each board's task input (corpus board with the task's fixed parts locked):
old = kae.place.arrays as at caeb1e06 (net pins from movable parts only); fixed = net pins from all parts, members movable."""
import sys, json, glob, os, types
sys.path.insert(0, sys.argv[1])
from collections import defaultdict
from kae.board.kicad_file import load
from kae.place import arrays as A
from kae.place.problem import net_class_guess
base = os.path.expanduser("~/kae-baselines")

def buses_fixed(fps, all_fps, kinds, exclude=()):
    pins = defaultdict(list)
    for f in all_fps:
        for p in f.pads:
            if p.net:
                pins[p.net].append((f, p))
    groups = defaultdict(list)
    for f in fps:
        if f.uuid in exclude or not A.PASSIVE_REF.match(f.ref) or len(f.pads) != 2 or any(p.drill for p in f.pads):
            continue
        n1, n2 = f.pads[0].net, f.pads[1].net
        if not n1 or not n2 or n1 == n2 or A._is_power(n1, kinds) or A._is_power(n2, kinds):
            continue
        o1 = [(g, p) for g, p in pins[n1] if g.uuid != f.uuid]
        o2 = [(g, p) for g, p in pins[n2] if g.uuid != f.uuid]
        if len(o1) != 1 or len(o2) != 1:
            continue
        (g1, p1), (g2, p2) = o1[0], o2[0]
        if g1.uuid == g2.uuid:
            continue
        a, b = (g1, p1), (g2, p2)
        if a[0].uuid > b[0].uuid:
            a, b = b, a
        groups[(f.lib_id, a[0].uuid, b[0].uuid)].append((f, a[1].number))
    return [len(m) for m in groups.values() if len(m) >= A.MIN_BUS]

FIX = json.load(open(sys.argv[4]))
out = {}
for b in [l.strip() for l in open(sys.argv[2]) if l.strip()]:
    fixed = None
    for t in glob.glob(f"{base}/boards/{b}/tasks/*/task.json"):
        j = json.load(open(t))
        if j["recipe"].get("kind") == "joint-fixed" and j["recipe"].get("task_spec") == 11:
            fixed = {r["ref"] for r in j["record"]["tasks"]["place-fixed"]["fixed_mech"]}
    src = "task"
    if fixed is None:
        fixed, src = set(FIX.get(b) or []), "classify-mech"
        if b not in FIX or isinstance(FIX[b], str):
            out[b] = dict(error="no fixed list"); print(b, out[b], flush=True); continue
    bd = load(os.path.expanduser(f"~/kae-boards/boards/{b}/board.kicad_pcb"))
    for f in bd.footprints:
        f.locked = f.ref in fixed
    allf = [f for f in bd.footprints if f.pads]
    mov = [f for f in allf if not f.locked]
    pins = defaultdict(int)
    for f in bd.footprints:
        for p in f.pads:
            if p.net:
                pins[p.net] += 1
    kinds = {k: net_class_guess(k, v, max(1, len(bd.footprints))) for k, v in pins.items()}
    mats = A.matrices(mov, kinds)
    taken = {u for g in mats for u in g.cells}
    old_b = [len(g.cells) for g in A.buses(mov, kinds, exclude=taken)]
    new_b = buses_fixed(mov, allf, kinds, exclude=taken)
    # unlocked (human-board) view, as at selection
    mats_h = A.matrices(allf, kinds)
    out[b] = dict(src=src, fixed=len(fixed), matrices=[len(g.cells) for g in mats], old_buses=old_b, fixed_buses=new_b,
                  human_matrices=[len(g.cells) for g in mats_h])
    print(b, out[b], flush=True)
json.dump(out, open(sys.argv[3], "w"), indent=0)
