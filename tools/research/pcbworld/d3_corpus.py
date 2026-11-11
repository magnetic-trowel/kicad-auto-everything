# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a kaeres corpus (KAE_CORPUS layout) from PCBWorld's D3 boards.

PCBWorld (github.com/LGAI-Research/PCBWorld, BSD-3) rebuilds its D3 boards from PCBench with its own
chain (tools/quickstart/prepare_pcbench.sh: KiCad 5 -> 9.0.8 conversion, .kicad_pro severity/rule
edits, per-net guide widths). Each D3 board folder holds processed_v9_guide_v3.kicad_pcb (routed,
the reference) and processed_v9_guide_v3.kicad_pro (the rules PCBWorld scores with). This script
copies the boards of the given suites into

    OUT/manifest.jsonl                 one row per board (kaeres corpus_rows)
    OUT/boards/<id>/board.kicad_pcb    the guide board, routed (kaebench prepare strips the copper)
    OUT/boards/<id>/board.kicad_pro    its project, PCBWorld's rules
    OUT/boards/<id>/row.json           the manifest row

so kaeres can run route experiments on them with KAE_CORPUS=OUT. Board files keep their upstream
licences (PCBench collects third-party boards; many have none): never commit OUT.

    python3 d3_corpus.py --exacad $PCBWORLD_DATA_ROOT/pcbench/exacad_sorted --out DIR \
        --suite d3a=bench/suites/pcbworld-d3a-test.txt --suite d3b=bench/suites/pcbworld-d3b-test.txt
"""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

STEM = "processed_v9_guide_v3"


def board_id(split, folder):
    return f"pcbw-{split}-" + re.sub(r"[^a-z0-9]+", "-", folder.lower()).strip("-")


def stats(text):
    """Footprints, copper layers and nets of a .kicad_pcb (text counts; KiCad 9 format)."""
    layers = 0
    m = re.search(r"\n\t\(layers\n(.*?)\n\t\)", text, re.S)
    if m:
        layers = len(re.findall(r'^\t\t\(\d+ "[^"]*\.Cu"', m.group(1), re.M))
    nets = len(re.findall(r'^\t\(net \d+ "', text, re.M))
    fps = len(re.findall(r"^\t\(footprint ", text, re.M))
    return dict(footprints=fps, layers=layers, nets=max(0, nets - 1))  # net 0 is "no net"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--exacad", required=True, type=Path, help="PCBWorld's pcbench/exacad_sorted")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--suite", action="append", required=True, metavar="SPLIT=FILE")
    a = ap.parse_args()
    rows = []
    for spec in a.suite:
        split, _, f = spec.partition("=")
        folders = [l.strip() for l in Path(f).read_text().splitlines() if l.strip() and not l.startswith("#")]
        for folder in folders:
            src = a.exacad / folder
            pcb, pro = src / f"{STEM}.kicad_pcb", src / f"{STEM}.kicad_pro"
            if not pcb.exists() or not pro.exists():
                raise SystemExit(f"{folder}: {pcb.name} or {pro.name} missing under {src}")
            bid = board_id(split, folder)
            d = a.out / "boards" / bid
            d.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pcb, d / "board.kicad_pcb")
            shutil.copy2(pro, d / "board.kicad_pro")
            text = pcb.read_text()
            meta = {}
            if (src / "metadata.json").exists():
                try:
                    meta = json.loads((src / "metadata.json").read_text())
                except ValueError:
                    meta = {}
            row = dict(id=bid, path=f"boards/{bid}", source="pcbworld-d3", pcbworld_split=split,
                       pcbworld_folder=folder, pcb_sha256=hashlib.sha256(pcb.read_bytes()).hexdigest(),
                       pro_sha256=hashlib.sha256(pro.read_bytes()).hexdigest(),
                       repo=meta.get("source") or "https://github.com/PCBench/PCBench", collection=f"pcbworld-{split}",
                       license=((meta.get("licenses") or {}).get("spdx_id") if isinstance(meta.get("licenses"), dict)
                                else None) or "unknown (PCBench third-party board)",
                       license_tier="unknown", tags=["pcbworld", f"pcbworld-{split}"], **stats(text))
            (d / "row.json").write_text(json.dumps(row, indent=1) + "\n")
            rows.append(row)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"{len(rows)} boards -> {a.out}")


if __name__ == "__main__":
    main()
