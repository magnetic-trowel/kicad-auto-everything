#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""enrich.py FOUND_GLOB OUT_JSONL WORKDIR [-j N] [--skip MANIFEST,...] [--only IDS_FILE] [--reverse]

Turn agent-found rows into kaebench manifest rows: fetch at pinned commit (sha256),
pcbnew stats, kicad-cli DRC under the board's own rules, heuristic tags.
Run with the kaebench venv python. Resumable: per-board results cached in WORKDIR/meta.
"""
import concurrent.futures as cf
import glob
import json
import re
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

from kaebench import fetch as kfetch, tools
from kaebench.manifest import import_format

TIER = {}
for k in ("MIT", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "ISC", "0BSD", "Unlicense", "CC0-1.0", "CC-BY-4.0",
          "CC-BY-3.0", "CERN-OHL-P-2.0", "Zlib", "BSL-1.0", "MIT-0", "Solderpad-0.51", "SHL-0.51", "SHL-2.0", "SHL-2.1",
          "WTFPL", "BSD-1-Clause", "CC-BY-2.0", "CC-BY-2.5", "PDDL-1.0", "Apache-1.1"):
    TIER[k] = "permissive"
for k in ("CERN-OHL-W-2.0", "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later", "MPL-2.0"):
    TIER[k] = "weak-copyleft"
for k in ("GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later", "AGPL-3.0-only",
          "AGPL-3.0-or-later", "EUPL-1.2"):
    TIER[k] = "copyleft"
for k in ("CERN-OHL-S-2.0", "CERN-OHL-1.1", "CERN-OHL-1.2", "TAPR-OHL-1.0", "CC-BY-SA-4.0", "CC-BY-SA-3.0",
          "CC-BY-SA-2.5", "CC-BY-SA-2.0", "OHL"):
    TIER[k] = "reciprocal-hardware"
ORDER = ["permissive", "weak-copyleft", "copyleft", "reciprocal-hardware", "noncommercial"]
BAD = re.compile(r"proprietary|all rights reserved|source-available|no-?licen[cs]e", re.I)
ND = re.compile(r"-ND\b|NoDeriv|no-derivatives", re.I)
NC = re.compile(r"-NC\b|-NC-|NonCommercial|Non-?Commercial|No-?Commercial|NC-AGPL", re.I)
LICREF = {"LicenseRef-Lone-Dynamics-Open-License": "permissive",
          "LicenseRef-ULX3S-modified-MIT": "permissive",
          "LicenseRef-CERN-OHL-unspecified-version": "reciprocal-hardware",  # OSHWA says only "CERN"
          "LicenseRef-Solderpad-unspecified-version": "permissive"}
ALIASES = {"GPL-3.0": "GPL-3.0-only", "GPL-2.0": "GPL-2.0-only", "GPLv3": "GPL-3.0-only", "LGPL-3.0": "LGPL-3.0-only",
           "LGPL-2.1": "LGPL-2.1-only", "AGPL-3.0": "AGPL-3.0-only", "CERN-OHL-S": "CERN-OHL-S-2.0",
           "CERN-OHL-W": "CERN-OHL-W-2.0", "CERN-OHL-P": "CERN-OHL-P-2.0", "CC-BY-SA": "CC-BY-SA-4.0",
           "CC-BY": "CC-BY-4.0", "CC0": "CC0-1.0", "Apache 2.0": "Apache-2.0", "TAPR-OHL": "TAPR-OHL-1.0",
           "CERN-OHL-v1.2": "CERN-OHL-1.2", "CERN-OHL-1.2-S": "CERN-OHL-1.2", "Solderpad-2.1": "SHL-2.1",
           "Solderpad": "LicenseRef-Solderpad-unspecified-version"}


def norm_license(expr):
    toks = re.split(r"(\s+(?:AND|OR|WITH)\s+|[()])", expr.strip())
    return "".join(ALIASES.get(t.strip(), t.strip()) if t.strip() and not re.fullmatch(r"\s*(AND|OR|WITH)\s*|[()]", t) else t
                   for t in toks)


def tier_of(expr):
    if BAD.search(expr) or ND.search(expr):
        return None
    if " OR " not in expr:
        if ND.search(expr):
            return None  # ND excluded: a modified output is too easy to publish by accident
        if NC.search(expr):
            return "noncommercial"
    if " OR " in expr:
        ts = [tier_of(p) for p in re.split(r"\s+OR\s+", expr.strip("() "))]
        ts = [t for t in ts if t]
        return min(ts, key=ORDER.index) if ts else None
    parts = [p.strip("() ") for p in re.split(r"\s+(?:AND|WITH)\s+", expr)]
    ts = [LICREF.get(p) if p.startswith("LicenseRef") else
          TIER.get(p) or TIER.get(re.sub(r"(-\d\.\d)-[A-Z]{2,3}$|(\+|-or-later)$", r"\1", p)) for p in parts
          if "exception" not in p.lower() and not re.search(r"Duet|attribution|logo", p, re.I)]
    if not ts or None in ts:
        return None
    return max(ts, key=ORDER.index)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def make_id(row):
    m = re.search(r"://([^/]+)/(.+?)(?:\.git)?/?$", row["repo"])
    rec = re.search(r"zenodo\.org/(?:api/)?records/(\d+)", row["repo"])
    if rec:
        owner_repo = f"zenodo-{rec.group(1)}"
    elif row["repo"].lower().endswith(".zip"):
        host = m.group(1).split(".")[-2]
        owner_repo = slug(f"{host}-{Path(m.group(2)).stem}")
    else:
        owner_repo = slug(m.group(2)) if m else slug(row["repo"])
    stem = slug(Path(row["pcb_path"]).stem)
    if stem in owner_repo.split("-", 1)[-1] or stem == owner_repo.split("-")[-1]:
        stem_part = stem
    else:
        stem_part = stem
    return f"{owner_repo}-{stem_part}"[:120].strip("-")


def source_of(repo):
    host = re.sub(r"^https?://", "", repo).split("/")[0]
    return {"github.com": "github", "gitlab.com": "gitlab"}.get(host, "other")


IFACE = [
    ("usb3", r"SSTX|SSRX|USB3|SS_?TX|SS_?RX"),
    ("usb2", r"USB.?D[PN+-]|\bD[+-]$|USB_?DP|USB_?DM|USB.*D_?[PN]\b"),
    ("ethernet", r"\bMDI|ETH|RJ45|PHY_|RGMII|RMII|SGMII|TRD\d"),
    ("hdmi", r"HDMI|TMDS"),
    ("pcie", r"PCIE|PERST|PE_?TX|PE_?RX|REFCLK"),
    ("ddr", r"DDR|DQS|\bDQ\d|DQ\d+\b|_DQ\d|MA\d+|BA\d"),
    ("mipi", r"MIPI|CSI|DSI"),
    ("can", r"CAN_?H|CAN_?L|CANH|CANL"),
    ("lvds", r"LVDS"),
]
FP_TAGS = [
    ("bga", r"BGA"),
    ("usb-c", r"USB_C|USB-C|TYPE-?C|USB_Type-C|UsbC"),
    ("rf", r"U\.?FL|SMA|IPEX|MHF|Antenna|ANT_|BNC|Coax|chip_antenna|LoRa|RFM9|SX12|nRF|ESP32|CC1101"),
    ("esp32", r"ESP32|ESP-WROOM|ESP32-S3|ESP32-C"),
    ("rp2040", r"RP2040"),
    ("rp2350", r"RP2350"),
    ("stm32", r"STM32"),
    ("fpga", r"ICE40|iCE40|ECP5|LFE5|XC7|XC[A-Z]U|Artix|Kintex|Cyclone|GW1N|GW2A|MachXO|LIFCL|CCGM|Spartan"),
]


def heur_tags(st, nets, fp_names):
    tags = set()
    nl = " ".join(nets)
    for t, rx in IFACE:
        if any(re.search(rx, n, re.I) for n in nets):
            tags.add(t)
    if sum(1 for n in nets if re.search(r"(_P|_N|\+|-|_DP|_DN)$", n)) >= 2:
        tags.add("diff-pairs")
    for t, rx in FP_TAGS:
        if any(re.search(rx, f, re.I) for f in fp_names):
            tags.add(t)
    if "usb2" in tags or "usb3" in tags or "ethernet" in tags:
        tags.add("diff-pairs") if re.search(r"D[+-]|_P\b|_N\b", nl) else None
    return tags


def sexpr_names(text):
    nets = set(re.findall(r'\(net (?:\d+ )?"((?:[^"\\]|\\.)*)"\)', text))
    nets |= set(re.findall(r"\(net \d+ ([^\s\")]+)\)", text))
    nets.discard("")
    fps = re.findall(r'\((?:footprint|module) "?([^"\s]+)', text)
    vals = re.findall(r'\(property "Value" "([^"]*)"|\(fp_text value "?([^"\s)]*)', text)
    fps += [a or b for a, b in vals]
    return sorted(nets), fps


def process(row, workdir, kicad_ver):
    meta_dir = Path(workdir) / "meta"
    out = meta_dir / f"{row['id']}.json"
    if out.exists():
        cached = json.loads(out.read_text())
        if all(cached.get(k) == row.get(k) for k in ("repo", "commit", "pcb_path", "archive_sha256")):
            cached.update({k: row[k] for k in ("license", "license_evidence", "license_tier", "dataset", "sch_path")})
            return cached
        shutil.rmtree(Path(workdir) / "cache" / row["id"], ignore_errors=True)
    res = dict(row)
    try:
        got = kfetch.fetch(row, Path(workdir) / "cache")
        pcb = Path(got["kicad_pcb"])
        res["pcb_sha256"] = got["pcb_sha256"]
        text = pcb.read_text(errors="replace")
        if text.startswith("version https://git-lfs"):
            raise ValueError("git-lfs pointer")
        m = re.search(r"\(version (\d+)\)", text[:2000])
        res["kicad_file_version"] = int(m.group(1)) if m else None
        st = tools.run_ops("stats", str(pcb), timeout=900)
        res.update(layers=st["copper_layers"], footprints=st["footprints"], nets=st["nets"],
                   tracks=st["tracks"] + st["arcs"], vias=st["vias"], zones=st["zones"],
                   board_mm=st["board_mm"] if st["board_mm"][0] > 0 else None)
        # DRC under own rules as saved; refill pass if unconnected and zones exist
        drc_dir = Path(workdir) / "drc" / row["id"]
        if drc_dir.exists():
            shutil.rmtree(drc_dir)
        drc_dir.mkdir(parents=True)
        shutil.copy2(pcb, drc_dir / "board.kicad_pcb")
        has_pro = False
        for k in ("kicad_pro", "kicad_dru"):
            if k in got:
                shutil.copy2(got[k], drc_dir / f"board.{k}")
                has_pro |= k == "kicad_pro"
        cmd = [*tools.kicad_cli(), "pcb", "drc", "--format", "json", "--severity-all", "--units", "mm",
               "-o", "saved.json", "board.kicad_pcb"]
        subprocess.run(cmd, cwd=drc_dir, capture_output=True, timeout=1800)
        rep = json.load(open(drc_dir / "saved.json"))
        s = tools.summarize_drc(rep)
        notes = [f"KiCad {kicad_ver} DRC as saved ({'own rules' if has_pro else 'default rules'}): "
                 f"unconnected={s['unconnected']} errors={s['errors']} warnings={s['warnings']}"
                 + (f" [{','.join(f'{k}:{v}' for k, v in sorted(s['errors_by_type'].items(), key=lambda x: -x[1])[:3])}]"
                    if s["errors_by_type"] else "")]
        unconn = s["unconnected"]
        if unconn and res["zones"]:
            try:
                rep2 = tools.run_drc(drc_dir / "board.kicad_pcb", drc_dir / "refill.json", timeout=900)
                s2 = tools.summarize_drc(rep2)
                notes.append(f"after --refill-zones: unconnected={s2['unconnected']} errors={s2['errors']}")
                if s2["unconnected"] < unconn:
                    unconn, s = s2["unconnected"], s2
            except Exception as e:  # noqa: BLE001
                notes.append(f"refill DRC failed: {str(e)[:80]}")
        copper = res["tracks"] + res["vias"]
        res["routed"] = bool(copper) and unconn == 0
        tags = set()
        L = res["layers"]
        tags.add("2layer" if L <= 2 else "4layer" if L <= 4 else "6plus")
        if res["routed"] and s["errors"] == 0:
            tags.add("drc-clean")
        if not copper:
            tags.add("unrouted")
        elif unconn:
            tags.add("partially-routed")
        if not has_pro and not import_format(row["pcb_path"]):
            tags.add("no-project-rules")
        if not row.get("sch_path"):
            tags.add("no-schematic")
        v = res["kicad_file_version"] or 0
        fmt = import_format(row["pcb_path"])
        if fmt:
            if fmt == "auto":
                head = Path(got["source_pcb"]).read_bytes()[:200]
                fmt = "eagle" if b"<?xml" in head or b"<eagle" in head else "allegro"
            tags.add(f"imported-{fmt}")
            has_pro = False
        elif v < 20171130:
            tags.add("legacy-format")
        elif v >= 20250000 and not fmt:
            tags.add("kicad10-format" if v >= 20250900 else "kicad9-format")
        nets, fps = sexpr_names(text)
        tags |= heur_tags(st, nets, fps)
        tags |= set(row.get("extra_tags") or [])
        res["tags"] = sorted(tags)
        res["notes"] = (row.get("notes") or "").rstrip(". ") + (". " if row.get("notes") else "") + "; ".join(notes) + "."
        res["_ok"] = True
    except Exception as e:  # noqa: BLE001
        res["_ok"] = False
        res["_error"] = f"{type(e).__name__}: {e}"[:400]
        if not isinstance(e, (FileNotFoundError, ValueError, tools.ToolError)):
            res["_trace"] = traceback.format_exc()[-800:]
    meta_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res))
    return res


KEYS = ("id", "source", "repo", "commit", "pcb_path", "sch_path", "pcb_sha256", "license", "license_evidence",
        "license_tier", "kicad_file_version", "layers", "footprints", "nets", "tracks", "vias", "zones",
        "board_mm", "routed", "tags", "dataset", "notes", "archive_sha256")


def build_rows(found_glob, skip_paths=()):
    """Normalise agent-found rows into manifest skeletons (licence-filtered, deduped by repo+path)."""
    existing = set()
    for p in skip_paths:
        for line in open(p):
            e = json.loads(line)
            existing.add((e["repo"].rstrip("/").lower(), e.get("pcb_path")))
    rows, ids, rejected = [], set(), []
    bulk = ("discovery", "kicad-happy", "kicad-happy-review", "hosts-misc")  # script-classified sources go last
    for f in sorted(glob.glob(found_glob), key=lambda f: (Path(f).stem in bulk, Path(f).stem)):
        if f.endswith(".rejected.jsonl"):
            continue
        sector = Path(f).stem
        for line in open(f):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            r["pcb_path"] = (r.get("pcb_path") or r.get("altium_pcbdoc") or r.get("eagle_brd") or r.get("allegro_brd")
                             or r.get("pads_asc"))
            archive = r.get("archive_sha256") or r.get("zip_sha256")
            if not archive and not r.get("commit") and r.get("download_url") and re.fullmatch(r"[0-9a-f]{64}", r.get("sha256") or ""):
                # Zenodo-style record: pin the downloaded file/archive; keep the record URL in notes
                r["notes"] = f"Record {r['repo']}. " + (r.get("notes") or "")
                r["repo"], archive = r["download_url"], r["sha256"]
            if not r["pcb_path"] or not (r["pcb_path"].endswith(".kicad_pcb") or import_format(r["pcb_path"])):
                continue
            if not archive and not re.fullmatch(r"[0-9a-f]{40}", r.get("commit") or ""):
                continue
            r["repo"] = r["repo"].rstrip("/").removesuffix(".git")
            if (r["repo"].lower(), r["pcb_path"]) in existing:
                continue
            lic = norm_license(r.get("license") or "")
            tier = tier_of(lic) if lic else None
            if not tier:
                rejected.append((r["repo"], r["pcb_path"], lic))
                continue
            rid = make_id(r)
            base, i = rid, 2
            while rid in ids:
                rid, i = f"{base}-{i}", i + 1
            ids.add(rid)
            existing.add((r["repo"].lower(), r["pcb_path"]))
            rows.append(dict(id=rid, source="zip" if archive else source_of(r["repo"]), repo=r["repo"],
                             commit=None if archive else r["commit"], archive_sha256=archive,
                             pcb_path=r["pcb_path"],
                             sch_path=r["sch_path"] if re.search(r"\.(kicad_sch|sch|schdoc)$", str(r.get("sch_path") or ""), re.I)
                             and (r["sch_path"].endswith(".kicad_sch") or import_format(r["pcb_path"])) else None,
                             license=lic, license_evidence=r.get("license_evidence"), license_tier=tier,
                             dataset={"pcbcorpus": "pcb-corpus", "kicad-happy": "kicad-happy"}.get(sector, f"direct-{sector}"),
                             notes=" ".join(x for x in (r.get("name"), r.get("notes")) if x).strip(),
                             extra_tags=[r["category"]] if r.get("category") else []))
    print(f"{len(rows)} rows to enrich; {len(rejected)} rejected by licence normaliser", file=sys.stderr)
    return rows, rejected


def main():
    found_glob, out_path, workdir = sys.argv[1:4]
    workdir = str(Path(workdir).resolve())
    jobs = int(sys.argv[sys.argv.index("-j") + 1]) if "-j" in sys.argv else 4
    skip = sys.argv[sys.argv.index("--skip") + 1].split(",") if "--skip" in sys.argv else []
    rows, rejected = build_rows(found_glob, skip)
    if "--only" in sys.argv:
        keep = set(open(sys.argv[sys.argv.index("--only") + 1]).read().split())
        rows = [r for r in rows if r["id"] in keep]
        print(f"--only: {len(rows)} rows", file=sys.stderr)
    if "--reverse" in sys.argv:  # lets a second host work the same list from the other end
        rows = rows[::-1]
    for rj in rejected:
        print("  reject", rj, file=sys.stderr)
    kver = tools.versions().get("kicad_cli", "10") if hasattr(tools, "versions") else "10"
    kver = re.sub(r"[^0-9.].*", "", str(kver)) or "10"
    done = []
    with cf.ThreadPoolExecutor(jobs) as ex:
        futs = {ex.submit(process, r, workdir, kver): r for r in rows}
        for i, fu in enumerate(cf.as_completed(futs), 1):
            res = fu.result()
            done.append(res)
            print(f"[{i}/{len(rows)}] {res['id']} {'ok' if res.get('_ok') else res.get('_error')}", file=sys.stderr,
                  flush=True)
    good = sorted((r for r in done if r.get("_ok")), key=lambda r: r["id"])
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for r in good:
            f.write(json.dumps({k: r.get(k) for k in KEYS}) + "\n")
    with open(out_path + ".failed", "w") as f:
        for r in done:
            if not r.get("_ok"):
                f.write(json.dumps({k: r.get(k) for k in ("id", "repo", "commit", "pcb_path", "_error", "_trace")}) + "\n")
    print(f"wrote {len(good)} ok, {len(done) - len(good)} failed", file=sys.stderr)


if __name__ == "__main__":
    main()
