#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pin names and electrical types for corpus boards that were never updated from their schematic.

About 57% of the corpus (KiCad 5 boards, imports) has pads without pin function or type, so
pin-level analysis (routed physics: which IC pins a capacitor decouples) sees nothing. The
schematic, at the board's pinned commit, still has them. This tool:

  pintypes.py fetch   [--only ids|@FILE] [-j 8]   download each unannotated board's schematic (root sheet,
                                                   sub-sheets, and for KiCad 5 the symbol cache library)
  pintypes.py extract [--only ids|@FILE] [-j 8]   per board: {reference: {pad number: {type, name}}}
                                                   -> ~/kae-baselines/boards/<id>/pintypes.json

Fetching honours the corpus rules: only boards from github.com, gitlab.com and codeberg.org, at the
pinned commit, never a board tagged host-robots-restricted, and only where the host's robots.txt
allows the raw URL. Files land in ~/kae-baselines/schematics/<id>/ (third-party; never committed).
Supported: KiCad 6+ .kicad_sch (lib_symbols, instances, symbol_instances, hierarchical sheets),
KiCad 4/5 .sch with its -cache.lib, and Eagle XML .sch (pin directions, and each device's own pin to
pad map). A board without a recorded schematic path tries the board's own path with .kicad_sch, .sch.
Altium schematics are recorded as unsupported.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

STORE = Path(os.path.expanduser(os.environ.get("KAE_RESULTS", "~/kae-baselines")))
CORPUS = Path(os.path.expanduser(os.environ.get("KAE_CORPUS", "~/kae-boards")))
SCH = STORE / "schematics"
UA = "kicad-auto-everything-research/1 (pin types for open-hardware boards; github.com/magnetic-trowel/kicad-auto-everything)"
HOSTS = ("github.com", "gitlab.com", "codeberg.org")
NEVER = ("gitlab.fabcloud.org",)
MAX_FILES = 60          # sheets per design
MAX_BYTES = 40 << 20    # per file
EAGLE_TYPES = {"in": "input", "out": "output", "io": "bidirectional", "oc": "open_collector", "hiz": "tri_state",
               "pas": "passive", "pwr": "power_in", "sup": "power_out", "nc": "no_connect"}
LEGACY_TYPES = {"I": "input", "O": "output", "B": "bidirectional", "T": "tri_state", "P": "passive",
                "U": "unspecified", "W": "power_in", "w": "power_out", "C": "open_collector",
                "E": "open_emitter", "N": "no_connect"}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rows():
    with open(CORPUS / "manifest.jsonl") as f:
        return {r["id"]: r for r in (json.loads(l) for l in f if l.strip())}


def select(only):
    rs = rows()
    if only:
        ids = Path(only[1:]).read_text().split() if only.startswith("@") else only.split(",")
        return [rs[i] for i in ids if i in rs]
    return list(rs.values())


def annotated(row):
    """True if the corpus board already carries pin types (then nothing is needed)."""
    p = CORPUS / row["path"] / "board.kicad_pcb"
    try:
        with open(p, "rb") as f:
            while True:
                chunk = f.read(1 << 22)
                if not chunk:
                    return False
                if b"(pintype " in chunk:
                    return True
    except OSError:
        return False


# ------------------------------------------------------------------ fetching
def raw_url(repo, commit, path):
    u = urllib.parse.urlparse(repo)
    slug = u.path.strip("/").removesuffix(".git")
    q = urllib.parse.quote(path)
    if u.netloc == "github.com":
        return f"https://raw.githubusercontent.com/{slug}/{commit}/{q}"
    if u.netloc == "gitlab.com":
        return f"https://gitlab.com/{slug}/-/raw/{commit}/{q}"
    if u.netloc == "codeberg.org":
        return f"https://codeberg.org/{slug}/raw/commit/{commit}/{q}"
    return None


_robots, _rlock = {}, threading.Lock()


def allowed(url):
    host = urllib.parse.urlparse(url).netloc
    with _rlock:
        rp = _robots.get(host)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            try:
                req = urllib.request.Request(f"https://{host}/robots.txt", headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=30) as r:
                    rp.parse(r.read().decode("utf-8", "replace").splitlines())
            except urllib.error.HTTPError as e:
                rp.parse([] if e.code in (404, 410) else ["User-agent: *", "Disallow: /"])
            except (urllib.error.URLError, OSError):
                rp.parse(["User-agent: *", "Disallow: /"])
            _robots[host] = rp
    return rp.can_fetch(UA, url)


def get(url, tries=5):
    """Bytes of url, None if it does not exist; backs off on rate limits."""
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read(MAX_BYTES + 1)
                return data if len(data) <= MAX_BYTES else None
        except urllib.error.HTTPError as e:
            if e.code in (404, 410, 400):
                return None
            if e.code in (429, 403, 500, 502, 503, 504):
                time.sleep(min(300, 15 * 2 ** i))
                continue
            return None
        except (urllib.error.URLError, OSError, TimeoutError):
            time.sleep(5 * 2 ** i)
    return None


def sub_sheets(path, text):
    """Sheet file names referenced by a schematic, relative to the repo root."""
    base = PurePosixPath(path).parent
    if path.endswith(".kicad_sch"):
        names = re.findall(r'\(property\s+"Sheet ?[Ff]ile"\s+"([^"]+)"', text)
    else:
        names = re.findall(r'^F1\s+"([^"]+)"', text, re.M)
    out = []
    for n in names:
        n = n.replace("\\", "/")
        p = os.path.normpath(str(base / n)).replace("\\", "/")
        if not p.startswith(".."):
            out.append(p)
    return out


def fetch_one(row):
    d = SCH / row["id"]
    meta_p = d / "fetch.json"
    if meta_p.exists():
        return json.loads(meta_p.read_text())["status"]
    host = urllib.parse.urlparse(row.get("repo") or "").netloc
    meta = dict(board=row["id"], repo=row.get("repo"), commit=row.get("commit"), root=row.get("sch_path"), at=now(), files=[])

    def done(status, **kw):
        meta.update(status=status, **kw)
        d.mkdir(parents=True, exist_ok=True)
        meta_p.write_text(json.dumps(meta, indent=1))
        return status

    if host in NEVER or host not in HOSTS or "host-robots-restricted" in (row.get("tags") or []) or not row.get("commit"):
        return done("host_not_fetched", host=host)
    # the recorded path first; manifests sometimes record the KiCad 6+ name of a KiCad 5 project's
    # schematic (or none), so the other extension and the board's own name are tried too
    roots = []
    for base in ([os.path.splitext(row["sch_path"])[0]] if row.get("sch_path") else []) + [os.path.splitext(row["pcb_path"])[0]]:
        for ext in (".kicad_sch", ".sch") if not row.get("sch_path") or base != os.path.splitext(row["sch_path"])[0] \
                else (os.path.splitext(row["sch_path"])[1], ".sch" if row["sch_path"].endswith(".kicad_sch") else ".kicad_sch"):
            if base + ext not in roots:
                roots.append(base + ext)
    if row.get("sch_path") and not row["sch_path"].endswith((".kicad_sch", ".sch")):
        return done("unsupported_format")
    root = None
    for cand in roots:
        url = raw_url(row["repo"], row["commit"], cand)
        if url and allowed(url):
            data = get(url)
            if data is not None:
                root = cand
                break
    if root is None:
        return done("no_schematic_path" if not row.get("sch_path") else "root_missing", tried=roots)
    meta["root"] = root
    queue, seen = [root], set()
    if root.endswith(".sch"):  # KiCad 5 keeps pin types in the project's symbol cache
        queue += [root[:-4] + "-cache.lib", root[:-4] + "-rescue.lib"]
    while queue and len(seen) < MAX_FILES:
        p = queue.pop(0)
        if p in seen:
            continue
        seen.add(p)
        url = raw_url(row["repo"], row["commit"], p)
        if not url or not allowed(url):
            meta["files"].append(dict(path=p, status="robots"))
            continue
        data = get(url)
        if data is None:
            meta["files"].append(dict(path=p, status="missing"))
            continue
        out = d / "files" / p
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        meta["files"].append(dict(path=p, status="ok", url=url, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)))
        if p.endswith((".sch", ".kicad_sch")):
            text = data.decode("utf-8", "replace")
            if text.lstrip().startswith("<?xml") or "<eagle" in text[:2000]:
                meta["files"][-1]["format"] = "eagle"
                continue
            queue += sub_sheets(p, text)
    rf = next((f for f in meta["files"] if f["path"] == root), {})
    if rf.get("status") != "ok":
        return done("root_" + (rf.get("status") or "missing"))
    return done("ok", format=rf.get("format", "kicad"))


# ------------------------------------------------------------------ parsing
_TOK = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


def sexpr(text):
    """Nested lists of a KiCad s-expression file; strings unquoted."""
    stack, cur = [], []
    for m in _TOK.finditer(text):
        t = m.group(0)
        if t == "(":
            stack.append(cur)
            cur = []
        elif t == ")":
            done_, cur = cur, stack.pop()
            cur.append(done_)
        else:
            cur.append(t[1:-1].replace('\\"', '"') if t.startswith('"') else t)
    return cur


def kids(node, name):
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


def kid(node, name):
    k = kids(node, name)
    return k[0] if k else None


def _sym_pins(sym, lib):
    """{number: (type, name)} of a lib_symbols entry, units and inheritance included."""
    pins = {}
    stack = [sym]
    while stack:
        s = stack.pop()
        for p in kids(s, "pin"):
            typ = p[1] if len(p) > 1 and isinstance(p[1], str) else "unspecified"
            nm = kid(p, "name")
            num = kid(p, "number")
            if num and len(num) > 1:
                pins[str(num[1])] = (typ, str(nm[1]) if nm and len(nm) > 1 else "")
        stack += kids(s, "symbol")
    ext = kid(sym, "extends")
    if not pins and ext and len(ext) > 1:
        base = lib.get(ext[1]) or next((v for k, v in lib.items() if k.split(":")[-1] == ext[1]), None)
        if base is not None and base is not sym:
            return _sym_pins(base, lib)
    return pins


def parse_kicad_sch(files):
    """{ref: {pad: (type, name)}} from KiCad 6+ sheets."""
    out = {}
    uuid_lib, extra = {}, []
    for path, text in files:
        tree = sexpr(text)
        root = next((n for n in tree if isinstance(n, list) and n and n[0] == "kicad_sch"), None)
        if root is None:
            continue
        lib = {}
        ls = kid(root, "lib_symbols")
        for s in kids(ls or [], "symbol"):
            if len(s) > 1:
                lib[s[1]] = s
        for s in kids(root, "symbol"):
            lid = kid(s, "lib_id")
            if not lid or len(lid) < 2:
                continue
            pins = _sym_pins(lib[lid[1]], lib) if lid[1] in lib else {}
            refs = set()
            for prop in kids(s, "property"):
                if len(prop) > 2 and prop[1] == "Reference":
                    refs.add(prop[2])
            for inst in kids(s, "instances"):
                for proj in kids(inst, "project"):
                    for pth in kids(proj, "path"):
                        r = kid(pth, "reference")
                        if r and len(r) > 1:
                            refs.add(r[1])
            u = kid(s, "uuid")
            if u and len(u) > 1:
                uuid_lib[u[1]] = pins
            for r in refs:
                if r and not r.startswith("#") and "?" not in r:
                    out.setdefault(r, {}).update(pins)
        for si in kids(root, "symbol_instances"):  # KiCad 6.0: references per sheet instance, at the root
            for pth in kids(si, "path"):
                r = kid(pth, "reference")
                if len(pth) > 1 and r and len(r) > 1:
                    extra.append((pth[1].rsplit("/", 1)[-1], r[1]))
    for u, r in extra:
        if u in uuid_lib and not r.startswith("#") and "?" not in r:
            out.setdefault(r, {}).update(uuid_lib[u])
    return out


def parse_legacy(files, libs):
    """{ref: {pad: (type, name)}} from KiCad 4/5 sheets and their cache/rescue libraries."""
    defs = {}
    for _, text in libs:
        cur = None
        for line in text.splitlines():
            if line.startswith("DEF "):
                cur = {}
                defs[line.split()[1].lstrip("~")] = cur
            elif line.startswith("ALIAS ") and cur is not None:
                for a in line.split()[1:]:
                    defs[a] = cur
            elif line.startswith("X ") and cur is not None:
                f = line.split()
                if len(f) >= 12:
                    cur[f[2]] = (LEGACY_TYPES.get(f[11], "unspecified"), "" if f[1] == "~" else f[1])
            elif line.startswith("ENDDEF"):
                cur = None
    out = {}
    for _, text in files:
        for comp in re.findall(r"\$Comp\n(.*?)\$EndComp", text, re.S):
            m = re.search(r"^L\s+(\S+)\s+(\S+)", comp, re.M)
            if not m:
                continue
            name, ref = m.groups()
            cands = (name.replace(":", "_"), name.split(":")[-1], name)
            pins = next((defs[c] for c in cands if c in defs), None)
            if pins is None:
                continue
            refs = {ref} | set(re.findall(r'AR Path="[^"]*" Ref="([^"]+)"', comp))
            for r in refs:
                if r and not r.startswith("#") and "?" not in r:
                    out.setdefault(r, {}).update(pins)
    return out


def parse_eagle(text):
    """{ref: {pad: (type, name)}} from an Eagle XML schematic: each part's device maps its gates' pins to
    package pads (one pin may land on several pads)."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(text.encode("utf-8", "replace"))
    sch = root.find("./drawing/schematic")
    if sch is None:
        return {}
    devices = {}
    for lib in sch.findall("./libraries/library"):
        ln = lib.get("name")
        syms = {sy.get("name"): {pn.get("name"): EAGLE_TYPES.get(pn.get("direction", "io"), "unspecified")
                                 for pn in sy.findall("./pin")} for sy in lib.findall("./symbols/symbol")}
        for ds in lib.findall("./devicesets/deviceset"):
            gates = {g.get("name"): syms.get(g.get("symbol"), {}) for g in ds.findall("./gates/gate")}
            for dv in ds.findall("./devices/device"):
                pads = {}
                for c in dv.findall("./connects/connect"):
                    pin = c.get("pin") or ""
                    typ = gates.get(c.get("gate"), {}).get(pin, "unspecified")
                    for pad in (c.get("pad") or "").split():
                        pads[pad] = (typ, re.sub(r"@\d+$", "", pin))
                devices[(ln, ds.get("name"), dv.get("name") or "")] = pads
    out = {}
    for part in sch.findall("./parts/part"):
        pads = devices.get((part.get("library"), part.get("deviceset"), part.get("device") or ""))
        if pads:
            out[part.get("name")] = dict(pads)
    return out


def board_refs(row):
    txt = (CORPUS / row["path"] / "board.kicad_pcb").read_text(errors="replace")
    refs = set(re.findall(r'\(property\s+"Reference"\s+"([^"]+)"', txt)) | set(re.findall(r'\(fp_text\s+reference\s+"?([^\s")]+)', txt))
    return refs


def extract_one(row):
    d = SCH / row["id"]
    meta = json.loads((d / "fetch.json").read_text()) if (d / "fetch.json").exists() else None
    out_p = STORE / "boards" / row["id"] / "pintypes.json"
    if not meta or meta["status"] != "ok":
        return "not_fetched"
    ok = [f for f in meta["files"] if f["status"] == "ok"]
    texts = [(f["path"], (d / "files" / f["path"]).read_text(errors="replace")) for f in ok]
    root = meta.get("root") or row.get("sch_path")
    sch = [(p, t) for p, t in texts if p.endswith((".sch", ".kicad_sch")) and not t.lstrip().startswith("<?xml")]
    try:
        if meta.get("format") == "eagle":
            refs = parse_eagle(next(t for p, t in texts if p == root))
        elif root.endswith(".kicad_sch"):
            refs = parse_kicad_sch(sch)
        else:
            refs = parse_legacy(sch, [(p, t) for p, t in texts if p.endswith(".lib")])
    except Exception as e:  # noqa: BLE001
        refs, err = {}, f"{type(e).__name__}: {e}"
    else:
        err = None
    on_board = board_refs(row)
    matched = sorted(set(refs) & on_board)
    rec = dict(schema="kaeres.pintypes/1", board=row["id"], at=now(), repo=meta["repo"], commit=meta["commit"],
               root=root, format=meta.get("format", "kicad"),
               files=[{k: f[k] for k in ("path", "url", "sha256")} for f in ok],
               error=err, refs={r: {n: dict(type=t, name=nm) for n, (t, nm) in sorted(refs[r].items())} for r in matched},
               stats=dict(schematic_refs=len(refs), board_refs=len(on_board), matched_refs=len(matched),
                          pins=sum(len(refs[r]) for r in matched),
                          power_pins=sum(1 for r in matched for t, _ in refs[r].values() if t in ("power_in", "power_out"))))
    if not matched:
        rec["note"] = "no schematic reference matches the board"
    out_p.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_p.with_name(out_p.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(rec, indent=1))
    os.replace(tmp, out_p)
    return "ok" if matched else "no_match"


def run_all(fn, items, jobs, label):
    from collections import Counter
    c = Counter()
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        for i, st in enumerate(ex.map(fn, items), 1):
            c[st] += 1
            if i % 200 == 0 or i == len(items):
                print(f"[{label} {i}/{len(items)} {time.time() - t0:.0f}s] {dict(c)}", flush=True)
    return c


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("fetch", "extract"))
    ap.add_argument("--only")
    ap.add_argument("-j", "--jobs", type=int, default=8)
    a = ap.parse_args()
    items = select(a.only)
    print(f"{len(items)} boards; checking which lack pin types", flush=True)
    with ThreadPoolExecutor(max_workers=16) as ex:
        items = [r for r, ann in zip(items, ex.map(annotated, items)) if not ann]
    print(f"{len(items)} boards without pin types", flush=True)
    if a.cmd == "fetch":
        run_all(fetch_one, items, a.jobs, "fetch")
    else:
        run_all(extract_one, items, a.jobs, "extract")


if __name__ == "__main__":
    main()
