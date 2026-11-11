# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Copy a routed board's tracks, arcs and vias onto PCBWorld's KiCad 9 input board.

PCBWorld's scorer (KiCad 9.0.8 engine) cannot open KiCad 10 files, and kaebench writes KiCad 10.
This reads the copper of a routed board (any version from 9 on: segments, arcs and vias, nets by
name or number) as text, and adds it with KiCad 9's pcbnew to PCBWorld's own unrouted input
board (processed_v9_guide_v3_unrouted.kicad_pcb), which is what its rule-based routers start
from. Nothing else of the routed board is carried over, as in our own scorer (bench/README.md,
"Scoring"): footprints, zones, rules and outline stay PCBWorld's.

Run it with an interpreter that imports KiCad 9's pcbnew (PCBWorld-Engine's BUILD_PCBNEW=1 build):

    python -I transplant_v9.py JOBS.jsonl <build_rl>/pcbnew
    # each line: {"routed": ".../output.kicad_pcb[.gz]", "base": ".../..._unrouted.kicad_pcb", "out": ".../x.kicad_pcb"}

Prints one JSON line per job: counts copied, nets not found on the base board, and errors.
"""
import gzip
import json
import sys


def sexpr(text):
    """Parse an S-expression file into nested lists of str (atoms; quoted strings unquoted)."""
    out, stack, i, n = [], [], 0, len(text)
    cur = out
    while i < n:
        c = text[i]
        if c == "(":
            stack.append(cur)
            new = []
            cur.append(new)
            cur = new
            i += 1
        elif c == ")":
            cur = stack.pop()
            i += 1
        elif c.isspace():
            i += 1
        elif c == '"':
            j, buf = i + 1, []
            while text[j] != '"':
                if text[j] == "\\":
                    buf.append(text[j + 1])
                    j += 2
                else:
                    buf.append(text[j])
                    j += 1
            cur.append(("str", "".join(buf)))
            i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "()":
                j += 1
            cur.append(text[i:j])
            i = j
    return out[0]


def val(x):
    return x[1] if isinstance(x, tuple) else x


def field(node, key):
    for c in node[1:]:
        if isinstance(c, list) and c and c[0] == key:
            return c
    return None


def copper(path):
    op = gzip.open if str(path).endswith(".gz") else open
    with op(path, "rt", encoding="utf-8") as f:
        root = sexpr(f.read())
    nets = {}  # number -> name, for files that still store items' nets by number
    items = []
    for c in root[1:]:
        if not isinstance(c, list) or not c:
            continue
        if c[0] == "net" and len(c) >= 3:
            nets[val(c[1])] = val(c[2])
        elif c[0] in ("segment", "arc", "via"):
            items.append(c)
    return items, nets


def main():
    sys.path.insert(0, sys.argv[2])  # the directory of KiCad 9's pcbnew.py (run with -I: no PYTHONPATH)
    import pcbnew  # KiCad 9 (PCBWorld-Engine build)

    mm = pcbnew.FromMM
    for line in open(sys.argv[1]):
        if not line.strip():
            continue
        job = json.loads(line)
        rec = dict(out=job["out"], segments=0, arcs=0, vias=0, missing_nets=[], skipped=0)
        try:
            items, numbered = copper(job["routed"])
            board = pcbnew.LoadBoard(job["base"])
            if len(board.GetTracks()):
                raise ValueError(f"base board has {len(board.GetTracks())} tracks; expected none")
            byname = {str(k): v for k, v in board.GetNetsByName().items()}
            missing = set()

            def net_of(node):
                f = field(node, "net")
                if f is None or len(f) < 2:
                    return byname.get("")
                name = val(f[1]) if isinstance(f[1], tuple) else numbered.get(f[1], f[1] if not f[1].isdigit() else None)
                if name is None or name not in byname:
                    missing.add(str(name))
                    return None
                return byname[name]

            def xy(node, key):
                f = field(node, key)
                return pcbnew.VECTOR2I(mm(float(f[1])), mm(float(f[2])))

            for it in items:
                net = net_of(it)
                if net is None:
                    rec["skipped"] += 1
                    continue
                if it[0] in ("segment", "arc"):
                    t = pcbnew.PCB_ARC(board) if it[0] == "arc" else pcbnew.PCB_TRACK(board)
                    t.SetStart(xy(it, "start"))
                    if it[0] == "arc":
                        t.SetMid(xy(it, "mid"))
                    t.SetEnd(xy(it, "end"))
                    t.SetWidth(mm(float(field(it, "width")[1])))
                    t.SetLayer(board.GetLayerID(val(field(it, "layer")[1])))
                    t.SetNet(net)
                    board.Add(t)
                    rec["arcs" if it[0] == "arc" else "segments"] += 1
                else:
                    v = pcbnew.PCB_VIA(board)
                    v.SetPosition(xy(it, "at"))
                    v.SetWidth(mm(float(field(it, "size")[1])))
                    v.SetDrill(mm(float(field(it, "drill")[1])))
                    flags = {a for a in it[1:] if isinstance(a, str)}
                    if "micro" in flags:
                        v.SetViaType(pcbnew.VIATYPE_MICROVIA)
                    elif "blind" in flags or "buried" in flags:
                        v.SetViaType(pcbnew.VIATYPE_BLIND_BURIED)
                    else:
                        v.SetViaType(pcbnew.VIATYPE_THROUGH)
                    lay = [val(x) for x in field(it, "layers")[1:]]
                    v.SetLayerPair(board.GetLayerID(lay[0]), board.GetLayerID(lay[-1]))
                    v.SetNet(net)
                    board.Add(v)
                    rec["vias"] += 1
            rec["missing_nets"] = sorted(missing)
            pcbnew.SaveBoard(job["out"], board)
        except Exception as e:  # one bad board must not stop the batch
            rec["error"] = f"{type(e).__name__}: {e}"
        print(json.dumps(rec), flush=True)


if __name__ == "__main__":
    main()
