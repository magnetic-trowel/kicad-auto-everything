# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import json, re, sys
PAT = [("CERN-OHL-S-2.0", r"CERN Open Hardware Licence Version 2 - Strongly Reciprocal|CERN-OHL-S"),
       ("CERN-OHL-W-2.0", r"CERN Open Hardware Licence Version 2 - Weakly Reciprocal|CERN-OHL-W"),
       ("CERN-OHL-P-2.0", r"CERN Open Hardware Licence Version 2 - Permissive|CERN-OHL-P"),
       ("CERN-OHL-1.2", r"CERN OHL v1\.2|CERN Open Hardware Licence v1\.2"),
       ("CC-BY-SA-4.0", r"Attribution-ShareAlike 4\.0|CC[- ]BY[- ]SA[- ]4|by-sa/4\.0"),
       ("CC-BY-SA-3.0", r"Attribution-ShareAlike 3\.0|by-sa/3\.0"),
       ("CC-BY-4.0", r"Attribution 4\.0 International|by/4\.0"),
       ("CC0-1.0", r"CC0 1\.0|Creative Commons Zero|CC0"),
       ("GPL-3.0", r"GNU GENERAL PUBLIC LICENSE\s+Version 3"),
       ("GPL-2.0", r"GNU GENERAL PUBLIC LICENSE\s+Version 2"),
       ("LGPL-3.0", r"GNU LESSER GENERAL PUBLIC LICENSE\s+Version 3"),
       ("AGPL-3.0", r"GNU AFFERO"),
       ("Apache-2.0", r"Apache License,?\s+Version 2\.0"),
       ("MIT", r"Permission is hereby granted, free of charge"),
       ("BSD-3-Clause", r"Neither the name"),
       ("BSD-2-Clause", r"Redistribution and use in source and binary forms"),
       ("Unlicense", r"This is free and unencumbered"),
       ("MPL-2.0", r"Mozilla Public License"),
       ("TAPR-OHL-1.0", r"TAPR Open Hardware")]
BAD = r"non-?commercial|\bNC\b|-NC-|by-nc|NoDeriv|by-nd|all rights reserved|personal use"
def classify(a):
    found = []
    for p, t in a.get("license_files", {}).items():
        for spdx, rx in PAT:
            if re.search(rx, t, re.I):
                found.append((p, spdx)); break
    bad = []
    for p, t in a.get("license_files", {}).items():
        if re.search(BAD, t, re.I): bad.append(f"{p}: NC/ND in licence file")
    for p, ls in a.get("readme_license_lines", {}).items():
        for l in ls:
            if re.search(BAD, l, re.I): bad.append(f"{p}: {l[:160]}")
    return found, bad
if __name__ == "__main__":
    for line in open(sys.argv[1]):
        a = json.loads(line)
        if "error" in a: print("ERR", a["repo"], a["error"][:100]); continue
        f, b = classify(a)
        print(json.dumps({"repo": a["repo"], "commit": a["commit"], "found": f, "bad": b,
                          "readme": {k: v[:5] for k, v in a["readme_license_lines"].items()}}))
