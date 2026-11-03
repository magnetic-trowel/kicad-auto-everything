#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mechanical fixes for upstream .kicad_dru files that KiCad 10 rejects.

KiCad 10.0.x drops a whole custom-rules file on one parse error, and kicad-cli DRC then
runs silently without it (docs/topics/kicad/drc-rule-language-reference.md). These boards
ship such files. Each fix is the smallest edit that makes KiCad load the rules the author
wrote, keeping their meaning; a file that is not rules at all is removed (the board then
has no custom rules, which is what KiCad applied before the fix anyway).

corpus.py applies FIXES when it copies a board. To fix an existing corpus in place:

    python dru_fixes.py apply ~/kae-boards [--ids a,b] [--dry-run]

Each fixed board's row.json (and its manifest.jsonl row) gets `dru_fix`: reason, edits,
sha256 before and after. Its drc.json is deleted (it was made under the broken rules);
re-run DRC with corpus.py --drc. kaeres puts `dru_fix` into the task recipe, so runs on
a fixed board get a new task id and do not mix with runs made under the broken file.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

# id -> (reason, action). action: list of (old, new) exact replacements, "prepend:<text>",
# or "remove".
FIXES = {
    "andreagiulianini-lira-lira": (
        "chained property A.Parent.Reference is rejected; footprint Reference is inherited by its items",
        [("A.Parent.Reference", "A.Reference")]),
    "baochip-dabao-dabao-v3c": (
        "chained property A.Net.Name is rejected; the property is NetName",
        [("A.Net.Name", "A.NetName")]),
    "fcoury-knuckles-knuckles-integrated-left": (
        "bare number without unit is rejected; the file's other values are mm",
        [("(constraint clearance (min 0.15)))", "(constraint clearance (min 0.15mm)))")]),
    "h0lad-solarlorabox-solarlorabox": (
        "typo: unknown property Pad_Typep (Pad_Type)",
        [("A.Pad_Typep", "A.Pad_Type")]),
    "jsenzel1-petrock-petrockmain1": (
        "two (layer) clauses in one rule are rejected; one wildcard layer covers both silkscreens",
        [('(layer "F.Silkscreen") (layer "B.Silkscreen")', '(layer "?.Silkscreen")')]),
    "mbouyer-domotique-linky-serial": (
        "upstream file is one orphan (condition ...) line: no rule, no constraint, nothing to recover",
        "remove"),
    "rainbowlabsde-usb2speakon-usb2speakon-pcb": (
        "upstream file is one orphan (condition ...) line: no rule, no constraint, nothing to recover",
        "remove"),
    "slimcdk-multical-eye-driver-board": (
        "file is the target path of a git symlink into a submodule the repo does not declare, not rules",
        "remove"),
    "slimcdk-wisweep-driver-board": (
        "file is the target path of a git symlink into submodule Cimos/KiCad-CustomDesignRules@2d4d70d1 "
        "(no licence, so not fetched), not rules",
        "remove"),
    "technikweber-convertible-keyboard-pcb-convertible-keyboard-pcb": (
        "bare numbers without unit are rejected; the file's comments give the values in mm",
        [("(constraint edge_clearance (min 0.5)))", "(constraint edge_clearance (min 0.5mm)))"),
         ("(constraint edge_clearance (min 0.2)))", "(constraint edge_clearance (min 0.2mm)))")]),
}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def apply_fix(bid: str, board_dir: Path, dry_run=False):
    """Fix board_dir/board.kicad_dru if FIXES lists bid. Returns the dru_fix record or None.
    Raises if the file does not hold what the fix expects (upstream changed: review it)."""
    if bid not in FIXES:
        return None
    reason, action = FIXES[bid]
    f = board_dir / "board.kicad_dru"
    if not f.exists():
        raise FileNotFoundError(f"{bid}: no board.kicad_dru to fix")
    before = f.read_bytes()
    text = before.decode("utf-8", errors="replace")
    edits = []
    if action == "remove":
        after = None
        edits.append("removed")
    elif isinstance(action, str) and action.startswith("prepend:"):
        add = action[len("prepend:"):]
        if text.startswith(add):
            raise ValueError(f"{bid}: already starts with {add!r}")
        text = add + text
        edits.append(f"prepended {add.strip()!r}")
        after = text.encode()
    else:
        for old, new in action:
            n = text.count(old)
            if n == 0:
                raise ValueError(f"{bid}: {old!r} not found; the upstream file changed, review the fix")
            text = text.replace(old, new)
            edits.append(f"{old!r} -> {new!r} x{n}")
        after = text.encode()
    rec = dict(reason=reason, edits=edits, sha256_before=sha(before), sha256_after=sha(after) if after else None)
    if not dry_run:
        if after is None:
            f.unlink()
        else:
            f.write_bytes(after)
        (board_dir / "drc.json").unlink(missing_ok=True)  # made under the broken rules
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("apply", help="fix an existing corpus in place")
    s.add_argument("corpus")
    s.add_argument("--ids", help="comma-separated board ids (default: every board in FIXES)")
    s.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    root = Path(a.corpus).expanduser()
    ids = a.ids.split(",") if a.ids else sorted(FIXES)
    done = {}
    for bid in ids:
        d = root / "boards" / bid
        rowp = d / "row.json"
        row = json.loads(rowp.read_text())
        if row.get("dru_fix"):
            print(f"{bid}: already fixed ({row['dru_fix']['sha256_after']})")
            continue
        rec = apply_fix(bid, d, a.dry_run)
        print(f"{bid}: {'would fix' if a.dry_run else 'fixed'}: {'; '.join(rec['edits'])}")
        if not a.dry_run:
            row["dru_fix"] = rec
            rowp.write_text(json.dumps(row, indent=1))
            done[bid] = rec
    if done:
        man = root / "manifest.jsonl"
        rows = [json.loads(l) for l in man.read_text().splitlines() if l.strip()]
        for r in rows:
            if r["id"] in done:
                r["dru_fix"] = done[r["id"]]
        tmp = man.with_suffix(".jsonl.tmp")
        tmp.write_text("".join(json.dumps(r) + "\n" for r in rows))
        tmp.replace(man)
        print(f"updated {len(done)} rows in {man}")


if __name__ == "__main__":
    sys.exit(main())
