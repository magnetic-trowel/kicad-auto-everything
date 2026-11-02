# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae's part table (kae/src/kae/excite/parts.json) from the datasheet library (datasheet_prompt.md):
for regulators, converters and power switches, the values the evaluator's cell model reads, each with
its datasheet and page. Only values datasheet_check.py verified on their cited page are used; entries
written by hand (without "from_library") are kept as they are.

    python build_part_table.py [LIBRARY] [--table kae/src/kae/excite/parts.json]
"""
import argparse
import glob
import json
import os
import re
import sys

# library value name -> part table name (the names kae.excite.params reads)
FIELDS = {"f_sw_Hz": "f_sw_Hz", "R_on_high_ohm": "r_on_ohm", "R_ds_on_ohm": "r_on_ohm", "V_sw_max_V": "v_sw_max_V",
          "C_oss_F": "c_sw_F"}
KINDS = ("switching_regulator", "charger", "mosfet", "driver", "load_switch")


def entry(f):
    """A part table entry for one facts file, or None (nothing verified that the cell model reads)."""
    if not f.get("identified") or f.get("kind") not in KINDS:
        return None
    pat = f.get("match") or re.escape(f.get("part") or "")
    try:
        if not pat or not re.search(pat, f.get("query") or "", re.I):
            pat = re.escape(f.get("part") or f.get("query") or "")
            if not pat:
                return None
    except re.error:
        return None
    pat = re.sub(r"\$$", r"\\b", pat)       # kae matches "value lib_id": the value is not the whole text
    ds = f.get("datasheet") or {}
    data, cites = {}, []
    for k, name in FIELDS.items():
        v = (f.get("values") or {}).get(k)
        if not isinstance(v, dict) or not v.get("verified") or name in data:
            continue
        nums = [v.get(x) for x in ("min", "typ", "max") if isinstance(v.get(x), (int, float))]
        if not nums:
            continue
        data[name] = nums[0] if len(nums) == 1 else [min(nums), max(nums)]
        cites.append(f"{k} p.{v.get('page')}")
    if not data:
        return None
    return dict(match=pat, data=data, from_library=os.path.basename(ds.get("pdf") or "") or True,
                source=f"{f.get('manufacturer') or ''} {f.get('part') or f.get('query')} datasheet "
                       f"{ds.get('url') or ''} ({'; '.join(cites)})".strip())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("library", nargs="?", default=os.environ.get("KAE_DATASHEETS", "~/kae-datasheets"))
    ap.add_argument("--table", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
                                                   "kae", "src", "kae", "excite", "parts.json"))
    a = ap.parse_args(argv)
    lib = os.path.expanduser(a.library)
    table = json.load(open(a.table))
    keep = [e for e in table.get("parts", []) if not e.get("from_library")]
    new = [e for e in (entry(json.load(open(p))) for p in sorted(glob.glob(f"{lib}/facts/*.json"))) if e]
    seen = {e["match"].lower() for e in keep}
    new = [e for e in new if e["match"].lower() not in seen]
    table["parts"] = keep + new
    with open(a.table, "w") as fh:
        json.dump(table, fh, indent=1)
        fh.write("\n")
    print(f"part table: {len(keep)} hand-written + {len(new)} from the datasheet library -> {a.table}")


if __name__ == "__main__":
    sys.exit(main())
