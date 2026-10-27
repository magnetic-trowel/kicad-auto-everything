#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""sig.py FOUND_GLOB WORKDIR EXISTING_MANIFEST [-j N] [--threshold 0.75]

Phase 1 of the pipeline: fetch every candidate board (and the existing manifest's
boards), fingerprint it by content, cluster near-duplicates with MinHash/LSH and pick
one representative per cluster. Writes WORKDIR/keep.txt (ids to enrich) and
WORKDIR/dups.jsonl (dropped id -> representative id, Jaccard).

Fingerprint: multiset of footprint library ids and values, plus the set of net names.
Exact sha256 matches are always duplicates. Imported (non-KiCad) boards are compared
by sha256 only, because importing every one just to fingerprint it is too slow.
"""
import concurrent.futures as cf
import json
import random
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import enrich  # noqa: E402
from kaebench import fetch as kfetch  # noqa: E402
from kaebench.manifest import import_format  # noqa: E402

NPERM, BANDS = 96, 24
ROWS = NPERM // BANDS
random.seed(1)
SEEDS = [random.getrandbits(61) for _ in range(NPERM)]
RANK = {"existing": 0, "pcb-corpus": 2, "discovery": 3, "hosts-misc": 3, "kicad-happy": 4}


def features(text):
    fps = Counter(re.findall(r'\((?:footprint|module) "?([^"\s)]+)', text))
    vals = Counter(a or b for a, b in re.findall(r'\(property "Value" "([^"]*)"|\(fp_text value "?([^"\s)]*)', text))
    nets = set(re.findall(r'\(net \d+ "((?:[^"\\]|\\.)+)"\)', text)) | set(re.findall(r'\(net \d+ ([^\s")]+)\)', text))
    nets |= set(re.findall(r'\(net "((?:[^"\\]|\\.)+)"\)', text))
    f = {f"fp:{k}#{i}" for k, n in fps.items() for i in range(n)}
    f |= {f"v:{k}#{i}" for k, n in vals.items() for i in range(n)}
    f |= {f"n:{k}" for k in nets if k}
    ver = re.search(r"\(version (\d+)\)", text[:2000])
    return f, int(ver.group(1)) if ver else 0, text.count("(segment") + text.count("(arc ")


def minhash(fs):
    hs = [hash(x) for x in fs]
    return tuple(min(((h ^ s) * 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF for h in hs) for s in SEEDS)


def fetch_one(row, workdir):
    cache = Path(workdir) / "cache" / row["id"]
    meta = cache / "fetch.json"
    if meta.exists():
        m = json.loads(meta.read_text())
        if m.get("repo") != row["repo"] or m.get("commit") != row.get("commit") or \
                Path(m.get("source_pcb") or m["kicad_pcb"]).name != Path(row["pcb_path"]).name:
            shutil.rmtree(cache)
    try:
        if import_format(row["pcb_path"]):
            # fetch the source only; import happens in enrich for representatives
            d = Path(workdir) / "srccache" / row["id"]
            m = d / "src.json"
            if m.exists():
                return row["id"], json.loads(m.read_text())
            d.mkdir(parents=True, exist_ok=True)
            paths = {"kicad_pcb": row["pcb_path"]}
            if row.get("archive_sha256"):
                got = kfetch._zip_fetch(row, paths, d)
            else:
                raw = kfetch._raw_url(row["repo"], row["commit"], row["pcb_path"])
                if raw:
                    out = d / Path(row["pcb_path"]).name
                    got = {"kicad_pcb": out} if kfetch._download(raw, out) else {}
                else:
                    got = kfetch._git_fetch(row["repo"], row["commit"], paths, d)
            if "kicad_pcb" not in got:
                return row["id"], {"error": "not found"}
            res = {"sha": kfetch.sha256(got["kicad_pcb"]), "imported": True}
            m.write_text(json.dumps(res))
            return row["id"], res
        got = kfetch.fetch(row, Path(workdir) / "cache")
        text = Path(got["kicad_pcb"]).read_text(errors="replace")
        if text.startswith("version https://git-lfs"):
            return row["id"], {"error": "git-lfs pointer"}
        f, ver, segs = features(text)
        return row["id"], {"sha": got["pcb_sha256"], "mh": minhash(f) if f else None, "nfeat": len(f),
                           "feats": sorted(f), "ver": ver, "segs": segs}
    except Exception as e:  # noqa: BLE001
        return row["id"], {"error": f"{type(e).__name__}: {e}"[:300]}


def main():
    found_glob, workdir, existing = sys.argv[1:4]
    workdir = str(Path(workdir).resolve())
    jobs = int(sys.argv[sys.argv.index("-j") + 1]) if "-j" in sys.argv else 16
    thr = float(sys.argv[sys.argv.index("--threshold") + 1]) if "--threshold" in sys.argv else 0.75
    rows, _ = enrich.build_rows(found_glob, [existing])
    old = [json.loads(l) for l in open(existing)]
    for e in old:
        e["dataset"] = "existing"
    allrows = old + rows
    sigs = {}
    sig_cache = Path(workdir) / "sigs.jsonl"
    if sig_cache.exists():
        for l in open(sig_cache):
            k, v = json.loads(l)
            sigs[k] = v
    todo = [r for r in allrows if r["id"] not in sigs or ("error" in sigs[r["id"]] and "nfeat" not in sigs[r["id"]])]
    print(f"{len(allrows)} boards ({len(old)} existing), {len(todo)} to fetch", file=sys.stderr)
    with cf.ThreadPoolExecutor(jobs) as ex, open(sig_cache, "a") as sc:
        for i, (rid, s) in enumerate(ex.map(lambda r: fetch_one(r, workdir), todo), 1):
            sigs[rid] = s
            sc.write(json.dumps([rid, s]) + "\n")
            if i % 100 == 0:
                print(f"  fetched {i}/{len(todo)}", file=sys.stderr, flush=True)
    byid = {r["id"]: r for r in allrows}
    for r in allrows:  # blank templates, plates and covers: nothing to place or route
        s = sigs.get(r["id"], {})
        if "error" not in s and not s.get("imported") and s.get("nfeat", 0) < 10 and r.get("dataset") != "existing":
            sigs[r["id"]] = dict(s, error=f"near-empty board ({s.get('nfeat', 0)} footprint/value/net features)")
    ok = [r["id"] for r in allrows if "error" not in sigs.get(r["id"], {"error": 1})]
    errs = [(r["id"], sigs.get(r["id"], {}).get("error")) for r in allrows if r["id"] not in set(ok)]

    parent = {i: i for i in ok}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    by_sha = defaultdict(list)
    for i in ok:
        by_sha[sigs[i]["sha"]].append(i)
    for ids in by_sha.values():
        for x in ids[1:]:
            union(ids[0], x)
    buckets = defaultdict(list)
    for i in ok:
        mh = sigs[i].get("mh")
        if mh:
            for b in range(BANDS):
                buckets[(b, tuple(mh[b * ROWS:(b + 1) * ROWS]))].append(i)
    fsets = {i: set(sigs[i]["feats"]) for i in ok if sigs[i].get("feats")}
    jac = {}
    seen = set()
    for ids in buckets.values():
        if len(ids) < 2 or len(ids) > 400:
            continue
        for a_i in range(len(ids)):
            for b_i in range(a_i + 1, len(ids)):
                a, b = ids[a_i], ids[b_i]
                if (a, b) in seen:
                    continue
                seen.add((a, b))
                A, B = fsets[a], fsets[b]
                j = len(A & B) / len(A | B)
                if j >= thr:
                    union(a, b)
                    jac[(a, b)] = jac[(b, a)] = j
    clusters = defaultdict(list)
    for i in ok:
        clusters[find(i)].append(i)

    def pref(i):
        r, s = byid[i], sigs[i]
        rank = RANK.get(r.get("dataset"), 1)
        return (rank, -s.get("ver", 0), -s.get("segs", 0), -s.get("nfeat", 0), r["pcb_path"])

    keep, dups = [], []
    for ids in clusters.values():
        rep = min(ids, key=pref)
        if byid[rep].get("dataset") != "existing":
            keep.append(rep)
        for i in ids:
            if i != rep and byid[i].get("dataset") != "existing":
                dups.append({"id": i, "repo": byid[i]["repo"], "pcb_path": byid[i]["pcb_path"], "rep": rep,
                             "rep_repo": byid[rep]["repo"], "rep_path": byid[rep]["pcb_path"],
                             "jaccard": round(jac.get((i, rep), 1.0 if sigs[i]["sha"] == sigs[rep]["sha"] else -1), 3)})
    Path(workdir, "keep.txt").write_text("\n".join(sorted(keep)) + "\n")
    with open(Path(workdir, "dups.jsonl"), "w") as f:
        for d in dups:
            f.write(json.dumps(d) + "\n")
    with open(Path(workdir, "fetch_errors.jsonl"), "w") as f:
        for i, e in errs:
            f.write(json.dumps({"id": i, "error": e}) + "\n")
    print(f"{len(ok)} fetched, {len(errs)} errors, {len(clusters)} clusters, keep {len(keep)} new, "
          f"{len(dups)} near-duplicates dropped", file=sys.stderr)


if __name__ == "__main__":
    main()
