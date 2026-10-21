#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""corpus.py OUT_DIR NAME=ROWS.jsonl[@WORKDIR] ... [-j N] [--fetch-missing] [--drc]
             [--no-fetch-tag TAG] [--prune]

Build a local board corpus: one folder per board in the bench's board.* layout,
plus OUT_DIR/manifest.jsonl. Rows come from enrich results or bench manifests; each
NAME becomes the row's `collection`. Later arguments win for the same id, so list the
benchmark manifest last to keep its rows. Boards are copied from WORKDIR/cache/<id>
(as left by enrich.py or `kaebench fetch`); with --fetch-missing, boards not in the
cache are fetched into WORKDIR/cache first, except rows carrying a --no-fetch-tag tag
(e.g. host-robots-restricted), which are included only when already cached. With --drc,
boards without a DRC report get one (KiCad DRC as saved, under the board's own rules, the
same command enrich.py runs). --prune deletes folders whose id is no longer in the inputs.
Boards are never committed (licences).

    python corpus.py ~/kae-boards --fetch-missing --drc --no-fetch-tag host-robots-restricted \\
      wide=../../../bench/manifests/wide.jsonl@$HOME/kae-boards-work \\
      wide-noncommercial=../../../bench/manifests/wide-noncommercial.jsonl@$HOME/kae-boards-work \\
      candidates=../../../bench/manifests/candidates.jsonl@$HOME/kae-boards-work
"""
import argparse
import collections
import concurrent.futures as cf
import json
import shutil
import subprocess
import sys
from pathlib import Path

from kaebench import fetch as kfetch, tools


def drc(d, timeout=1800):
    cmd = [*tools.kicad_cli(), "pcb", "drc", "--format", "json", "--severity-all", "--units", "mm",
           "-o", "drc.json", "board.kicad_pcb"]
    try:
        subprocess.run(cmd, cwd=d, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        pass
    for junk in [*d.glob("~board.*.lck"), *d.glob("board.kicad_prl")]:  # kicad-cli's lock and UI-state files
        junk.unlink()
    return (d / "drc.json").exists()


def copy_board(bid, name, row, work, boards, fetch_missing, run_drc):
    cache = Path(work) / "cache"
    meta_path = cache / bid / "fetch.json"
    if not meta_path.exists():
        if not fetch_missing:
            return bid, "not in cache"
        try:
            kfetch.fetch(row, cache)
        except Exception as e:  # noqa: BLE001
            return bid, f"fetch failed: {type(e).__name__}: {e}"[:200]
    meta = json.loads(meta_path.read_text())
    for k in ("kicad_pcb", "kicad_pro", "kicad_dru", "source_pcb"):
        if meta.get(k):  # paths may be relative to wherever kaebench ran; the files sit in cache/<id>/
            meta[k] = cache / bid / Path(meta[k]).name
    if row.get("pcb_sha256") and meta.get("pcb_sha256") != row["pcb_sha256"]:
        return bid, "cache holds a different version"
    d = boards / bid
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy2(meta["kicad_pcb"], d / "board.kicad_pcb")
    for k in ("kicad_pro", "kicad_dru"):
        if meta.get(k):
            shutil.copy2(meta[k], d / f"board.{k}")
    if meta.get("source_pcb"):
        shutil.copy2(meta["source_pcb"], d / ("source" + Path(meta["source_pcb"]).suffix.lower()))
    rep = Path(work) / "drc" / bid / "saved.json"  # enrich's DRC report under the board's own rules
    if rep.exists():
        shutil.copy2(rep, d / "drc.json")
    elif run_drc and not (d / "drc.json").exists():
        drc(d)  # a board whose DRC fails or times out is kept, just without drc.json
    row = dict(row, collection=name, path=f"boards/{bid}")
    (d / "row.json").write_text(json.dumps(row, indent=1))
    return bid, row


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("specs", nargs="+", metavar="NAME=ROWS.jsonl[@WORKDIR]")
    ap.add_argument("-j", type=int, default=16)
    ap.add_argument("--fetch-missing", action="store_true")
    ap.add_argument("--drc", action="store_true")
    ap.add_argument("--no-fetch-tag", action="append", default=[], metavar="TAG",
                    help="never fetch rows with this tag; they are included only if already cached")
    ap.add_argument("--prune", action="store_true", help="delete board folders not in the inputs")
    a = ap.parse_args()
    out = Path(a.out).expanduser()
    rows = {}
    for spec in a.specs:
        name, rest = spec.split("=", 1)
        path, work = rest.split("@", 1) if "@" in rest else (rest, ".")
        for line in open(path):
            if line.strip():
                r = json.loads(line)
                prev = rows.get(r["id"])
                rows[r["id"]] = (name, r, Path(work).expanduser(), prev[0] if prev else None)
    boards = out / "boards"
    boards.mkdir(parents=True, exist_ok=True)
    no_fetch = set(a.no_fetch_tag)

    def one(kv):
        bid, (name, row, work, _) = kv
        fetch_ok = a.fetch_missing and not no_fetch & set(row.get("tags") or [])
        return copy_board(bid, name, row, work, boards, fetch_ok, a.drc)

    with cf.ThreadPoolExecutor(a.j) as ex:
        res = list(ex.map(one, sorted(rows.items())))
    ok = [r for _, r in res if isinstance(r, dict)]
    if a.prune:
        keep = {r["id"] for r in ok}
        stale = [d for d in boards.iterdir() if d.name not in keep]
        for d in stale:
            shutil.rmtree(d)
        print(f"pruned {len(stale)} folders not in the inputs")
    for r in ok:
        if rows[r["id"]][3] and rows[r["id"]][3] != r["collection"]:
            r["also_in"] = rows[r["id"]][3]
    with open(out / "manifest.jsonl", "w") as f:
        for r in ok:
            f.write(json.dumps(r) + "\n")
    print(f"{len(ok)} boards in {out}", dict(collections.Counter(r["collection"] for r in ok)))
    bad = [(b, r) for b, r in res if not isinstance(r, dict)]
    if bad:
        print(f"{len(bad)} skipped, e.g.", bad[:5], file=sys.stderr)


if __name__ == "__main__":
    main()
