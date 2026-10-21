# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Board manifests: one JSON object per line pointing at a board in a public repo.

Boards are never redistributed; the harness fetches them at a pinned commit.
"""
import json
import re
from pathlib import Path

REQUIRED = ("id", "repo", "pcb_path", "license")
KEYS = REQUIRED + ("source", "sch_path", "pcb_sha256", "license_evidence", "license_tier",
                   "kicad_file_version", "layers", "footprints", "nets", "tracks", "vias", "zones",
                   "board_mm", "routed", "tags", "dataset", "notes", "archive_sha256")
# Least to most restrictive. noncommercial rows are for private,
# non-commercial evaluation only and never feed redistributed data products.
TIERS = ("permissive", "weak-copyleft", "copyleft", "reciprocal-hardware", "noncommercial")
# Non-KiCad board formats that `kicad-cli pcb import` converts at fetch time.
# .brd is Eagle XML or Cadence Allegro binary; kicad-cli detects which.
IMPORT_FORMATS = {".brd": "auto", ".pcbdoc": "altium", ".asc": "pads", ".cpa": "cadstar"}


def import_format(pcb_path):
    """kicad-cli import format for a non-KiCad board path, or None for .kicad_pcb."""
    return IMPORT_FORMATS.get(Path(pcb_path).suffix.lower())


class ManifestError(ValueError):
    pass


def validate(entry, lineno=0):
    where = f"line {lineno} ({entry.get('id', '?')})"
    missing = [k for k in REQUIRED if not entry.get(k)]
    if missing:
        raise ManifestError(f"{where}: missing {missing}")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", entry["id"]):
        raise ManifestError(f"{where}: id must be a slug")
    if entry.get("archive_sha256"):
        # zip download (vendor design-file archives): pinned by the archive hash instead of a commit
        if not re.fullmatch(r"[0-9a-f]{64}", entry["archive_sha256"]) or entry.get("commit"):
            raise ManifestError(f"{where}: archive rows need a 64-hex archive_sha256 and commit null")
    elif not re.fullmatch(r"[0-9a-f]{40}", entry.get("commit") or ""):
        raise ManifestError(f"{where}: commit must be a full 40-hex SHA")
    if not entry["pcb_path"].endswith(".kicad_pcb") and not import_format(entry["pcb_path"]):
        raise ManifestError(f"{where}: pcb_path must be a .kicad_pcb file or one of {sorted(IMPORT_FORMATS)}")
    tier = entry.get("license_tier")
    if tier is not None and tier not in TIERS:
        raise ManifestError(f"{where}: license_tier must be one of {TIERS}")
    return entry


def load(path, only=None, tiers=None, tags=None, limit=None):
    """Load and validate a manifest; optional filters by id, license tier and tag."""
    entries, seen = [], set()
    with open(path) as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            e = validate(json.loads(line), i)
            if e["id"] in seen:
                raise ManifestError(f"line {i}: duplicate id {e['id']}")
            seen.add(e["id"])
            if only and e["id"] not in only:
                continue
            if tiers and e.get("license_tier") not in tiers:
                continue
            if tags and not set(tags) & set(e.get("tags") or []):
                continue
            entries.append(e)
    return entries[:limit] if limit else entries


def project_paths(entry):
    """Sibling project files with the same stem as the board (may not exist upstream)."""
    pcb = Path(entry["pcb_path"])
    if import_format(pcb):
        return {}
    return {"kicad_pro": str(pcb.with_suffix(".kicad_pro")),
            "kicad_dru": str(pcb.with_suffix(".kicad_dru"))}
