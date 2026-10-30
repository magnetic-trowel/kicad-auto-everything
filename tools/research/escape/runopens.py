# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Open connections of my runs by package kind / BGA ring (pads from the human dump)."""
import json, sys, os, glob
from collections import Counter
sys.path.insert(0, os.path.dirname(__file__))
import pkg
for b in sys.argv[1:]:
    H = pkg.load(os.environ.get('ESC_WORK', '.') + f'/dump/{b}.human.json')
    cls = {f['ref']: pkg.classify(f) for f in H['fps']}
    for d in sorted(glob.glob(os.environ.get('ESC_WORK', '.') + f'/runs/{b}/*/final/drc.json')):
        rep = json.load(open(d))
        c = Counter()
        for u in rep['unconnected_items']:
            k = 'other'
            for i in u['items']:
                it = pkg.parse_item(i['description'])
                if it['kind'] == 'pad':
                    cl = cls.get(it['ref'])
                    if cl and cl['dense'] and it['n'] in cl['sig']:
                        k = cl['kind'] + (f" r{min(cl['rings'].get(it['n'], 0), 4)}" if cl['kind'] in ('bga', 'wlcsp') else '')
                        break
            c[k] += 1
        print(f"{b[:24]} {d.split('/')[-3]:10s} {len(rep['unconnected_items']):4d}", dict(sorted(c.items())))
