import os, pathlib
"""Paired analysis of a kaeres experiment: per method vs the first (or --base), per-board outcomes
averaged over attempts, sign-flip / McNemar tests (bench/src/kaebench/stats.py), errors by type,
hazards from the method's last-JSON-line report (kae place) where present.

  python3 ab_analyze.py EXP [--base NAME_SUBSTR] [--json OUT]
"""
import sys, json, gzip, re, argparse, collections
from pathlib import Path
WT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(WT / 'tools/kaeres'))
sys.path.insert(0, str(WT / 'bench/src'))
import kaeres as K
from kaebench import stats as ST
import functools
K.corpus_rows = functools.lru_cache(maxsize=None)(K.corpus_rows)

ap = argparse.ArgumentParser()
ap.add_argument('exp'); ap.add_argument('--base'); ap.add_argument('--json')
a = ap.parse_args()
e = K.load_exp(a.exp)
boards = (K.exp_dir(a.exp) / 'boards.txt').read_text().split()
ms = e['methods']
drc_eval = e['evaluators']['drc']


def last_json(run_dir):
    p = Path(run_dir) / 'adapter.log.gz'
    if not p.exists():
        return None
    try:
        lines = gzip.open(p, 'rt', errors='replace').read().splitlines()
    except Exception:
        return None
    for l in reversed(lines):
        l = l.strip()
        if l.startswith('{') and l.endswith('}'):
            try:
                return json.loads(l)
            except Exception:
                continue
    return None


def outcome(bid, m, att):
    kind = K._run_kind(dict(method_id=m['id']))
    d, r = K.find_run(bid, m['id'], att, K.exp_task_id(e, bid, kind))
    if d is None:
        return None
    ev = K.evals_of(d).get(drc_eval) or {}
    s = ev.get('score') or {}
    o = dict(status=r.get('status'), runtime_s=r.get('runtime_s'), kind=kind)
    if kind in K.PLACE_KINDS:
        o.update(legal=s.get('legal'), legal_strict=s.get('legal_strict'), hpwl_ratio=s.get('hpwl_ratio'),
                 perr=s.get('placement_errors') or {}, perr_strict=s.get('placement_errors_strict') or {})
        pr = (ev.get('probe') or {}).get('score') or {}
        o.update(clean=pr.get('clean'), clean_strict=pr.get('clean_strict'), completion=pr.get('completion'),
                 unconnected=pr.get('unconnected'), errs=pr.get('errors_by_type') or {})
        rep = last_json(d) or {}
        hz = collections.Counter((h.get('code') or '?') + ':' + str(h.get('severity')) for h in (rep.get('hazards') or []) if isinstance(h, dict))
        o.update(hazards=dict(hz), kae_legal=rep.get('legal'))
    else:
        o.update(clean=s.get('clean'), clean_strict=s.get('clean_strict'), completion=s.get('completion'),
                 unconnected=s.get('unconnected'), errs=s.get('errors_by_type') or {},
                 track=s.get('track_length_mm'), vias=s.get('vias'))
    if o.get('clean') is None and r.get('status') != 'ok':
        o['clean'] = False
    return o


data = {m['name']: {b: [outcome(b, m, t) for t in range(e['attempts'])] for b in boards} for m in ms}
base = next((m['name'] for m in ms if a.base and a.base in m['name']), ms[0]['name'])
_rows = K.corpus_rows()
repo = {b: (_rows.get(b) or {}).get('repo') for b in boards}


def per_board(name, key, agg='mean'):
    out = {}
    for b, os_ in data[name].items():
        v = [o.get(key) for o in os_ if o is not None]
        v = [x for x in v if x is not None]
        if len(v) < e['attempts']:   # incomplete board: leave out (finish both arms before concluding)
            continue
        v = [float(x) for x in v]
        out[b] = (sum(v) / len(v)) if agg == 'mean' else (max(v) if agg == 'any' else v[0])
    return out


def summary(name):
    runs = [o for os_ in data[name].values() for o in os_ if o is not None]
    errs, perr, hz = collections.Counter(), collections.Counter(), collections.Counter()
    for o in runs:
        errs.update(o.get('errs') or {}); perr.update(o.get('perr_strict') or o.get('perr') or {}); hz.update(o.get('hazards') or {})
    def mean(k):
        v = [float(o[k]) for o in runs if o.get(k) is not None]
        return round(sum(v) / len(v), 4) if v else None
    return dict(runs=len(runs), status=dict(collections.Counter(o['status'] for o in runs)),
                legal=mean('legal'), legal_strict=mean('legal_strict'), clean=mean('clean'), clean_strict=mean('clean_strict'),
                completion=mean('completion'), hpwl_ratio=mean('hpwl_ratio'), unconnected=mean('unconnected'),
                errors_by_type=dict(errs.most_common(12)), placement_errors=dict(perr.most_common(12)), hazards=dict(hz.most_common(15)))


res = dict(exp=a.exp, base=base, attempts=e['attempts'], boards=len(boards), methods={})
keys = [('legal', True), ('legal_strict', True), ('clean', True), ('clean_strict', True), ('completion', False),
        ('unconnected', False), ('hpwl_ratio', False)]
for m in ms:
    n = m['name']
    r = dict(summary=summary(n))
    if n != base:
        for k, binary in keys:
            A, B = per_board(base, k), per_board(n, k)
            if not A or not B:
                continue
            common = sorted(set(A) & set(B))
            if e['attempts'] == 1 and binary:
                p = ST.paired({b: A[b] for b in common}, {b: B[b] for b in common}, binary=True, clusters=repo)
            else:
                p = ST.paired({b: A[b] for b in common}, {b: B[b] for b in common}, clusters=repo)
            if binary and e['attempts'] > 1:   # any-clean (cpk-style) as McNemar too
                Aa, Ba = per_board(base, k, 'any'), per_board(n, k, 'any')
                c2 = sorted(set(Aa) & set(Ba))
                p['any'] = ST.paired({b: Aa[b] for b in c2}, {b: Ba[b] for b in c2}, binary=True, clusters=repo)
                p['any'].pop('gained'); p['any'].pop('lost')
                p['any_gained'] = [b for b in c2 if Ba[b] > Aa[b]]; p['any_lost'] = [b for b in c2 if Ba[b] < Aa[b]]
            r[k] = p
    res['methods'][n] = r

if a.json:
    Path(a.json).write_text(json.dumps(res, indent=1, default=str))


def fmt(p):
    if not p:
        return '-'
    s = f"{p['mean_a']}->{p['mean_b']} d={p['diff']:+} CI{p['ci']} p={p['p']} n={p['n']}"
    if 'any' in p:
        s += f" | any: {p['any']['mean_a']}->{p['any']['mean_b']} p={p['any']['p']} +{len(p['any_gained'])}/-{len(p['any_lost'])}"
    elif 'gained' in p:
        s += f" +{len(p['gained'])}/-{len(p['lost'])}"
    return s


print(f"== {a.exp}: {len(boards)} boards, k={e['attempts']}, base = {base}")
for n, r in res['methods'].items():
    s = r['summary']
    print(f"-- {n}: runs={s['runs']} status={s['status']}")
    print(f"   legal={s['legal']} legal_strict={s['legal_strict']} clean={s['clean']} clean_strict={s['clean_strict']} completion={s['completion']} hpwl_ratio={s['hpwl_ratio']} unconnected={s['unconnected']}")
    print(f"   errors={s['errors_by_type']}")
    if s['placement_errors']:
        print(f"   placement_errors={s['placement_errors']}")
    if s['hazards']:
        print(f"   hazards={s['hazards']}")
    for k, _ in keys:
        if k in r:
            print(f"   {k:13s} {fmt(r[k])}")
