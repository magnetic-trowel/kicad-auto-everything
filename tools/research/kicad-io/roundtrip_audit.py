# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Does a load/save through KiCad's own reader and writer lose or change anything?

    python roundtrip_audit.py pick CORPUS N_PER_STAMP > ids.txt
    python roundtrip_audit.py run CORPUS WORK ids.txt > rows.jsonl     # needs KAE_KICAD_WRAP
    python roundtrip_audit.py summary rows.jsonl

For each board (copied out of the read-only corpus with its .kicad_pro/.kicad_dru),
pcbnew_inventory.py writes four variants: PCB_IO_MGR load+save ("plain", kae's writer),
plain re-saved ("plain2"), LoadBoard + PCB_IO_MGR.Save ("lb_plain", import_ses before
the fix) and LoadBoard + SaveBoard ("lb_save"). Compared here:
  - the format stamp before and after;
  - raw token counts (segments, vias, pads, zones, graphics, models, ...) of the
    original file and of "plain" (what KiCad's loader dropped is visible only here);
  - pcbnew's inventory of each variant against the original's (footprints, pads with
    nets, tracks with nets, drawings, zones, nets, embedded files, groups);
  - kae's own reader (kae.board.kicad_file.load) on the original and on "plain";
  - kae.board.sdiff between the original and "plain" (same-stamp boards only) and
    between "plain" and "plain2".
"""
import collections
import json
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

TOKENS = {
    "footprint": r"\((?:footprint|module)\s",
    "pad": r"\(pad\s",
    "segment": r"\(segment\s",
    "via": r"\(via\s",
    "arc": r"\(arc\s",
    "zone": r"\(zone\s",
    "gr": r"\(gr_(?:line|arc|circle|rect|poly|curve|text|text_box|bbox)\s",
    "fp_shape": r"\(fp_(?:line|arc|circle|rect|poly|curve)\s",
    "fp_text": r"\(fp_text\s",
    "property": r"\(property\s",
    "model": r"\(model\s",
    "group": r"\(group\s",
    "dimension": r"\(dimension\s",
    "image": r"\(image\s",
    "embedded_file": r"\(file\s*\(name",
    "target": r"\(target\s",
    "hide_yes_or_bare": r"\(hide(?:\s+yes)?\)|\shide[\s)]",
}


def stamp(path):
    with open(path, errors="replace") as f:
        m = re.search(r"\(version\s+(\d+)\)", f.read(400))
    return int(m.group(1)) if m else None


def tokens(path):
    t = Path(path).read_text(errors="replace")
    return {k: len(re.findall(v, t)) for k, v in TOKENS.items()}


def pick(corpus, n):
    rows = [json.loads(ln) for ln in open(Path(corpus) / "manifest.jsonl")]
    rng = random.Random(7)
    by = collections.defaultdict(list)
    for r in rows:
        if r.get("routed") and 100 <= (r.get("tracks") or 0) <= 4000 and (r.get("zones") or 0) >= 1:
            by[stamp(Path(corpus) / r["path"] / "board.kicad_pcb")].append(r["id"])
    out = []
    for s in (20171130, 20211014, 20221018, 20240108, 20241229, 20260206):
        out += rng.sample(sorted(by[s]), min(n, len(by[s])))
    # boards with embedded files or images, any stamp
    emb = [r["id"] for r in rows if "embedded" in " ".join(r.get("tags") or [])]
    return out + rng.sample(emb, min(2, len(emb)))


def msdiff(a, b):
    ca = collections.Counter(json.dumps(x) for x in a)
    cb = collections.Counter(json.dumps(x) for x in b)
    lost, new = ca - cb, cb - ca
    return dict(lost=sum(lost.values()), new=sum(new.values()),
                ex_lost=list(lost)[:3], ex_new=list(new)[:3])


def renets(a, b, geom):
    """Items whose geometry matches but whose net differs (geom: index of the net)."""
    def key(x):
        return json.dumps([v for i, v in enumerate(x) if i != geom])
    na = collections.defaultdict(list)
    for x in a:
        na[key(x)].append(x[geom])
    n, ex = 0, []
    for x in b:
        k = key(x)
        if na.get(k) and x[geom] not in na[k]:
            n += 1
            if len(ex) < 3:
                ex.append([na[k][0], x[geom]])
    return n, ex


def compare_inv(o, v):
    out = {}
    for k in ("footprints", "pads", "fpitems", "tracks", "drawings", "zones", "nets"):
        d = msdiff(o[k], v[k])
        if d["lost"] or d["new"]:
            out[k] = d
    for k in ("embedded", "groups"):
        if o[k] != v[k]:
            out[k] = [o[k], v[k]]
    # tracks: net is index -2 for segments/arcs, 3 for vias (separate them)
    segs_o = [t for t in o["tracks"] if t[0] != "PCB_VIA"]
    segs_v = [t for t in v["tracks"] if t[0] != "PCB_VIA"]
    vias_o = [t for t in o["tracks"] if t[0] == "PCB_VIA"]
    vias_v = [t for t in v["tracks"] if t[0] == "PCB_VIA"]
    n1, e1 = renets(segs_o, segs_v, 5)
    n2, e2 = renets(vias_o, vias_v, 3)
    n3, e3 = renets(o["pads"], v["pads"], 3)
    n4, e4 = renets(o["zones"], v["zones"], 0)
    rn = dict(tracks=n1, vias=n2, pads=n3, zones=n4)
    if any(rn.values()):
        out["renet"] = dict(rn, ex=e1 + e2 + e3 + e4)
    return out


def kae_view(path):
    from kae.board import kicad_file
    b = kicad_file.load(str(path))
    pads = sorted(json.dumps([f.ref, p.number, round(p.x, 4), round(p.y, 4), p.net]) for f in b.footprints
                  for p in f.pads)
    fps = sorted(json.dumps([f.ref, round(f.x, 4), round(f.y, 4), round(f.rot % 360, 3), f.side, f.locked])
                 for f in b.footprints)
    zones = sorted(json.dumps([z.net, sorted(z.layers)]) for z in b.zones)
    tracks = sorted(json.dumps([t.net, t.layer, round(t.width, 4), [round(v, 4) for v in t.start],
                                [round(v, 4) for v in t.end]]) for t in b.tracks)
    vias = sorted(json.dumps([v.net, round(v.x, 4), round(v.y, 4), round(v.size, 4), v.layers]) for v in b.vias)
    return dict(pads=pads, fps=fps, zones=zones, nets=sorted(b.nets), tracks=tracks, vias=vias)


def compare_kae(a, b):
    out = {}
    for k in a:
        ca, cb = collections.Counter(a[k]), collections.Counter(b[k])
        lost, new = ca - cb, cb - ca
        if lost or new:
            out[k] = dict(lost=sum(lost.values()), new=sum(new.values()), ex_lost=list(lost)[:2],
                          ex_new=list(new)[:2])
    return out


def run_one(corpus, work, bid):
    from kae.board import sdiff
    src = Path(corpus) / "boards" / bid
    d = Path(work) / bid
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    for f in src.iterdir():
        if f.name.startswith("board.") and f.suffix in (".kicad_pcb", ".kicad_pro", ".kicad_dru"):
            shutil.copy(f, d / f.name)
    board = d / "board.kicad_pcb"
    row = dict(id=bid, stamp=stamp(board), bytes=board.stat().st_size)
    inv = d / "inv.json"
    wrap = os.environ.get("KAE_KICAD_WRAP", "").split()
    cmd = ["bash", "-c", 'ulimit -v 40000000; exec "$@"', "x", *wrap, "python3",
           str(HERE / "pcbnew_inventory.py"), str(board), str(d / "out"), str(inv)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    if r.returncode or not inv.exists():
        row["error"] = (r.stderr or "")[-600:]
        return row
    res = json.loads(inv.read_text())
    plain = d / "out" / "plain.kicad_pcb"
    row["stamp_after"] = stamp(plain)
    to, tp = tokens(board), tokens(plain)
    row["tokens_changed"] = {k: [to[k], tp[k]] for k in to if to[k] != tp[k]}
    row["tokens"] = to
    o = res["orig"]
    row["n"] = dict(footprints=len(o["footprints"]), pads=len(o["pads"]), tracks=len(o["tracks"]),
                    zones=len(o["zones"]), drawings=len(o["drawings"]), nets=len(o["nets"]),
                    embedded=o["embedded"])
    for v in ("plain", "plain2", "lb_live", "lb_plain", "lb_save"):
        row["inv_" + v] = compare_inv(o, res[v])
    row["lb_save_ok"] = res["lb_save_ok"]
    try:
        row["kae_plain"] = compare_kae(kae_view(board), kae_view(plain))
    except Exception as e:  # noqa: BLE001
        row["kae_plain"] = dict(error=f"{type(e).__name__}: {e}")
    if row["stamp"] == row["stamp_after"]:
        ch = sdiff.diff(board, plain)
        row["sdiff_orig_plain"] = dict(n=len(ch), kinds=dict(collections.Counter(c["kind"] for c in ch)))
    ch = sdiff.diff(plain, d / "out" / "plain2.kicad_pcb")
    row["sdiff_plain_plain2"] = len(ch)
    return row


def summary(path):
    rows = [json.loads(ln) for ln in open(path)]
    for r in rows:
        if "error" in r:
            print(r["id"], r.get("stamp"), "ERROR", r["error"][-200:].replace("\n", " "))
            continue
        bad = {k: v for k, v in r.items() if k.startswith(("inv_", "kae_")) and v}
        print(f"{r['stamp']}->{r['stamp_after']} {r['id'][:55]:55s} n={r['n']}")
        print("   tokens changed:", r["tokens_changed"])
        for k, v in bad.items():
            print("  ", k, json.dumps(v)[:600])
        print("   sdiff:", r.get("sdiff_orig_plain"), "idempotent-diff:", r["sdiff_plain_plain2"])


def main(argv):
    if argv[0] == "pick":
        print("\n".join(pick(argv[1], int(argv[2]))))
    elif argv[0] == "run":
        corpus, work, ids = argv[1], argv[2], [x.strip() for x in open(argv[3]) if x.strip()]
        for bid in ids:
            try:
                row = run_one(corpus, work, bid)
            except Exception as e:  # noqa: BLE001
                row = dict(id=bid, error=f"{type(e).__name__}: {e}")
            print(json.dumps(row), flush=True)
    elif argv[0] == "summary":
        summary(argv[1])


if __name__ == "__main__":
    main(sys.argv[1:])
