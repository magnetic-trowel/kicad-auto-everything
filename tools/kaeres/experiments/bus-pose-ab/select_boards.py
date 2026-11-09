#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Boards of bus-pose-ab: where a bus runs between two movable ICs.

Pool (written to stdout, deterministic, one per repo_family, `usable_route_test`, at most MAX_PADS pads):
 A: tag bus_ddr (DDR byte lanes or address buses found by the bus detector).
 B: at least one bus of width >= 8 between two ICs (neither end a header, ffc_fpc, board_to_board or
    unknown connector), not in A.
Order within a pool is sha256(SEED + id); the first NA of A and NB of B are taken. Tag sources:
the board-tags directory (structural/usability, bus/tags, bus/buses; $KAE_BOARD_TAGS).
"""
import collections, getpass, hashlib, json, os, sys

SEED = 'bus-pose-ab-2026-11-09'
ROOT = os.environ.get('KAE_BOARD_TAGS') or f'/var/tmp/{getpass.getuser()}/board-tags'
NA, NB, MAX_PADS = 80, 60, 2000
CONN = {'header', 'ffc_fpc', 'board_to_board', None}


def main():
    usable, family, pads = {}, {}, {}
    for l in open(f'{ROOT}/structural/usability.jsonl'):
        d = json.loads(l)
        if d['usable_route_test']:
            usable[d['id']] = d
    for l in open(f'{ROOT}/structural/features.jsonl'):
        d = json.loads(l)
        pads[d['id']] = d.get('n_pads') or 0
    ddr = set()
    for l in open(f'{ROOT}/bus/tags.jsonl'):
        d = json.loads(l)
        if 'bus_ddr' in d['tags']:
            ddr.add(d['id'])
    icic = collections.Counter()
    for l in open(f'{ROOT}/bus/buses.jsonl'):
        r = json.loads(l)
        if r['width'] >= 8 and r['a_cls'] not in CONN and r['b_cls'] not in CONN:
            icic[r['board']] += 1
    def pool(ids):
        ids = [b for b in ids if b in usable and pads.get(b, 0) <= MAX_PADS]
        ids.sort(key=lambda b: hashlib.sha256((SEED + b).encode()).hexdigest())
        return ids
    fam_seen, out_a, out_b = set(), [], []
    for b in pool(ddr):
        f = usable[b]['repo_family']
        if f in fam_seen:
            continue
        fam_seen.add(f)
        out_a.append(b)
        if len(out_a) >= NA:
            break
    for b in pool([b for b in icic if b not in ddr]):
        f = usable[b]['repo_family']
        if f in fam_seen:
            continue
        fam_seen.add(f)
        out_b.append(b)
        if len(out_b) >= NB:
            break
    print('\n'.join(out_a + out_b))
    print(f'# A (bus_ddr) {len(out_a)}, B (ic-ic >=8) {len(out_b)}; pads <= {MAX_PADS}', file=sys.stderr)


if __name__ == '__main__':
    main()
