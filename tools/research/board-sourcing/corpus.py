#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""corpus.py OUT_DIR NAME=ROWS.jsonl[@WORKDIR] ... [-j N] [--fetch-missing] [--drc]

Build a local board corpus: one folder per board in the bench's board.* layout,
plus OUT_DIR/manifest.jsonl. Rows come from enrich results or bench manifests; each
NAME becomes the row's `collection`. Later arguments win for the same id, so list the
benchmark manifest last to keep its rows. Boards are copied from WORKDIR/cache/<id>
(as left by enrich.py or `kaebench fetch`); with --fetch-missing, boards not in the
cache are fetched into WORKDIR/cache first. With --drc, boards without a DRC report get one (KiCad DRC as saved, under
the board's own rules, the same command enrich.py runs). Boards are never committed (licences).

    python corpus.py ~/kae-boards \\
      sourcing-batch1=results/wobbly-tibia.jsonl@$HOME/kae-sourcing-work \\
      sourcing-batch2=results/wobbly-tibia-2.jsonl@$HOME/kae-sourcing-work \\
      sourcing-fabacademy=results/wobbly-tibia-2-fabmirror.jsonl@$HOME/kae-sourcing-work \\
      candidates=../../../bench/manifests/candidates.jsonl@$HOME/kicad-auto-everything/kae-work
"""
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
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    jobs = int(sys.argv[sys.argv.index("-j") + 1]) if "-j" in sys.argv else 16
    if "-j" in sys.argv:
        args.remove(sys.argv[sys.argv.index("-j") + 1])
    out, specs = Path(args[0]).expanduser(), args[1:]
    rows = {}
    for spec in specs:
        name, rest = spec.split("=", 1)
        path, work = rest.split("@", 1) if "@" in rest else (rest, ".")
        for line in open(path):
            if line.strip():
                r = json.loads(line)
                prev = rows.get(r["id"])
                rows[r["id"]] = (name, r, Path(work).expanduser(), prev[0] if prev else None)
    boards = out / "boards"
    boards.mkdir(parents=True, exist_ok=True)
    flags = ("--fetch-missing" in sys.argv, "--drc" in sys.argv)
    with cf.ThreadPoolExecutor(jobs) as ex:
        res = list(ex.map(lambda kv: copy_board(kv[0], *kv[1][:3], boards, *flags), sorted(rows.items())))
    ok = [r for _, r in res if isinstance(r, dict)]
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
