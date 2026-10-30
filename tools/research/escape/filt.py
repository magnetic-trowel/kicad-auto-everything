# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import json, os
B={b['board']:b for b in json.load(open(os.environ.get('BOARDS_JSON', 'boards.json')))}
def pins():
    P=[json.loads(l) for l in open(os.path.join(os.environ.get('ESC_WORK', '.'), 'pins.jsonl'))]
    cap={n for n,b in B.items() if (b['route'].get('unconnected') or 0)>=499}
    bad={n for n,b in B.items() if (b['human_drc'].get('unconnected') or 0)>3}
    return [p for p in P if p['board'] not in cap and p['board'] not in bad], cap, bad
