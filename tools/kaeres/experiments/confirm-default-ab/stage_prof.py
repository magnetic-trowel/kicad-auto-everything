# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-stage samples from py-spy --subprocesses --idle raw output: the stage is the innermost kae
process's subcommand (route attempt / lastmile / finish / restart judge) and, inside a process, the
kae module on the stack; idle samples (waiting on a child: Freerouting, kicad-cli) count as wall."""
import sys, re, collections
st, fn = collections.Counter(), collections.Counter()
tot = 0
for raw in open(sys.argv[1], 'rb'):
    line = raw.decode('utf-8', 'replace').rstrip()
    stack, _, n = line.rpartition(' ')
    try:
        n = int(n)
    except ValueError:
        continue
    tot += n
    fr = stack.split(';')
    procs = [f for f in fr if f.startswith('process ')]
    p = procs[-1][:160] if procs else ''
    if 'restart.py' in p: p = 'restart.py'
    if 'kae.route.cli finish' in p: proc = 'finish'
    elif 'kae.route.cli lastmile' in p: proc = 'final lastmile'
    elif 'kae.route.cli route' in p: proc = 'route attempt'
    elif 'restart.py' in p: proc = 'restart.py (judge, wait)'
    else: proc = 'other'
    mods = [m.group(1) for f in fr for m in [re.search(r'\((?:.*/)?kae/(?:src/kae/)?([\w/]+)\.py', f)] if m]
    part = None
    for key in ('taut', 'pad_reroute', 'power_copper', 'journal', 'repair', 'lastmile', 'freerouting', 'drc', 'critical_grid', 'escape', 'blocked', 'board_hazards'):
        if any(m.endswith(key) for m in mods):
            part = key
            if key not in ('drc',):
                break
    st[(proc, part)] += n
    if proc == 'finish':
        leaf = fr[-1]
        fn[re.sub(r':\d+\)', ')', leaf)[:110]] += n
print(f'total samples {tot}')
for (p, k), v in st.most_common(25):
    print(f'{100 * v / tot:5.1f}%  {p:28s} {k}')
print('--- finish leaves')
ft = sum(fn.values())
for k, v in fn.most_common(15):
    print(f'{100 * v / max(1, ft):5.1f}%  {k}')
