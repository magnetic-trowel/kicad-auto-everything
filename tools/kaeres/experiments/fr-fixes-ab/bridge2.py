# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read fr-fixes-bridge2: per arm, first-wave failures and causes, restart attempts, repair rounds,
final opens, per-type DRC, clean, CPU; paired per board."""
import collections
import glob
import json
import os
import statistics as st

BASE = os.path.expanduser('~/kae-baselines/')
EXP = 'fr-fixes-bridge2'
boards = open(BASE + f'experiments/{EXP}/boards.txt').read().split()
ARMS = {'fr-fx2-bridge-2e1125a': 'ctl', 'fr-fx2-bridge-c219253': 'fix'}


def load(b, slug):
    for r in glob.glob(f'{BASE}boards/{b}/runs/{slug}.*.a0'):
        j = json.load(open(r + '/run.json'))
        if j.get('experiment') != EXP:
            continue
        s = None
        for ev in glob.glob(r + '/evals/*.json'):
            x = json.load(open(ev))
            if x.get('score'):
                s = x['score']
        rj = json.load(open(r + '/restarts.json')) if os.path.exists(r + '/restarts.json') else {}
        rep = json.load(open(r + '/restart-report.json')) if os.path.exists(r + '/restart-report.json') else {}
        return dict(run=r, s=s or {}, rj=rj, rep=rep, status=j.get('status'))
    return None


rows = []
for b in boards:
    a = {arm: load(b, slug) for slug, arm in ARMS.items()}
    if a['ctl'] and a['fix']:
        rows.append((b, a))
    else:
        print('MISSING', b, {k: bool(v) for k, v in a.items()})
print('paired boards', len(rows))

for arm in ('ctl', 'fix'):
    fw_fail, causes, attempts, rounds_n, rsec, cpu, opens, errs, clean = 0, collections.Counter(), [], [], [], [], 0, collections.Counter(), 0
    fail_any = 0
    for b, a in rows:
        x = a[arm]
        al = x['rj'].get('attempt_log', [])
        first = [t for t in al if isinstance(t.get('k'), int) and t['k'] < 4 and not t.get('resumed_from')]
        for t in al:
            if t.get('rc') not in (0, None):
                fail_any += 1
                f = t.get('failure') or {}
                err = (f.get('error') or f.get('status') or '?')
                causes[err.split(':')[0][:60]] += 1
        fw_fail += sum(1 for t in first if t.get('rc') not in (0, None))
        attempts.append(x['rj'].get('attempts') or 0)
        rr = (x['rep'].get('repair') or {}).get('rounds') or []
        rounds_n.append(len(rr))
        rsec.append(sum((r.get('router') or {}).get('seconds') or 0 for r in rr))
        cpu.append(x['rj'].get('cpu_s') or 0)
        opens += x['s'].get('unconnected') or 0
        errs.update(x['s'].get('errors_by_type') or {})
        clean += bool(x['s'].get('clean'))
    print(f'== {arm}: first-wave failures {fw_fail}, all non-zero attempts {fail_any}, causes {dict(causes)}')
    print(f'   attempts median {st.median(attempts)} total {sum(attempts)}; repair rounds (kept attempt) median {st.median(rounds_n)}; '
          f'repair router s total {round(sum(rsec))}; CPU h {round(sum(cpu) / 3600, 1)} (median {round(st.median(cpu))} s)')
    print(f'   clean {clean}/{len(rows)}; opens {opens}; errors {sum(errs.values())} {dict(errs.most_common(8))}')

# paired
d_open = [a['fix']['s'].get('unconnected', 0) - a['ctl']['s'].get('unconnected', 0) for b, a in rows]
d_cpu = [(a['fix']['rj'].get('cpu_s') or 0) - (a['ctl']['rj'].get('cpu_s') or 0) for b, a in rows]
print('paired opens fix-ctl: better', sum(x < 0 for x in d_open), 'worse', sum(x > 0 for x in d_open), 'equal', sum(x == 0 for x in d_open))
print('paired CPU fix-ctl: lower', sum(x < 0 for x in d_cpu), 'higher', sum(x > 0 for x in d_cpu), 'median diff s', round(st.median(d_cpu)))
# Freerouting state of the first routing in the kept attempt, by arm
for arm in ('ctl', 'fix'):
    st_ = collections.Counter(((a[arm]['rep'].get('router') or {}).get('report') or {}).get('final_state') for b, a in rows)
    pr = sum(1 for b, a in rows if ((((a[arm]['rep'].get('router') or {}).get('report') or {}).get('telemetry') or {}).get('pour_connected')))
    print(arm, 'kept attempt Freerouting final_state', dict(st_), 'with pour groups connected', pr)
