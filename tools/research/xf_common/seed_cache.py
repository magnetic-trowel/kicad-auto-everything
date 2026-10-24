# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Seed a kaebench fetch cache from the local board corpus instead of the network.

    python seed_cache.py MANIFEST SUITE CORPUS_BOARDS_DIR CACHE_DIR

For each suite id, copies CORPUS/<id>/board.kicad_pcb (and .kicad_pro/.kicad_dru when
present) to CACHE/<id>/ under the manifest's file names and writes the fetch.json that
kaebench.fetch.fetch() would write. A board is seeded only when its sha256 equals the
manifest's pcb_sha256, so `kaebench prepare` then sees exactly the pinned upstream file.
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path


def main(manifest, suite, corpus, cache):
    rows = {}
    for line in open(manifest):
        if line.strip():
            r = json.loads(line)
            rows[r["id"]] = r
    ids = [s.strip() for s in open(suite) if s.strip() and not s.startswith("#")]
    seeded = skipped = 0
    for i in ids:
        r, src, dst = rows.get(i), Path(corpus) / i, Path(cache) / i
        if (dst / "fetch.json").exists():
            continue
        pcb = src / "board.kicad_pcb"
        if r is None or not pcb.exists():
            print(f"missing {i}", file=sys.stderr)
            skipped += 1
            continue
        digest = hashlib.sha256(pcb.read_bytes()).hexdigest()
        if digest != r.get("pcb_sha256"):
            print(f"sha256 mismatch {i}", file=sys.stderr)
            skipped += 1
            continue
        dst.mkdir(parents=True, exist_ok=True)
        stem = Path(r["pcb_path"])
        meta = {}
        for key, ext in (("kicad_pcb", ".kicad_pcb"), ("kicad_pro", ".kicad_pro"), ("kicad_dru", ".kicad_dru")):
            f = src / f"board{ext}"
            if f.exists():
                out = dst / stem.with_suffix(ext).name
                shutil.copy2(f, out)
                meta[key] = str(out)
        meta.update(id=i, pcb_sha256=digest, repo=r["repo"], commit=r["commit"])
        (dst / "fetch.json").write_text(json.dumps(meta, indent=1))
        seeded += 1
    print(f"seeded {seeded}, skipped {skipped}, suite {len(ids)}")
    return 1 if skipped else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
