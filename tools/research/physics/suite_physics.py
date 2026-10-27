# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Batch runner: conductor passports and physics critics on every board of a suite, plus aggregation.

Report: docs/topics/physics/suite-physics-results.md. Physics numbers here are a separate scorecard: this
script never reads or writes cp1/cpk, never writes into kaebench results or score directories, and never
modifies bench/.

For each board:
  1. copy board.kicad_pcb and the reference rules (.kicad_pro, .kicad_dru; installed like the scorer does) to
     <out>/<id>/work/;
  2. refill zones with KiCad and save the copy (`kicad-cli pcb drc --refill-zones --save-board`); if that fails or
     times out, keep the saved fills and record why (critics and passports then read stale or missing fills);
  3. run suite_passports.py (roles, DC passports, HF hot loops; writes roles.json early) and pc_refplane.py
     (critics, with --roles from step 3 when present) in subprocesses, each with --timeout seconds and an
     resident-memory cap (--mem-gb; watchdog), OMP_NUM_THREADS=1;
  4. write <id>/passports.json, <id>/critics.json, <id>/roles.json, <id>/drc.json (from the refill run),
     <id>/meta.json (status, wall time, peak RSS per step, failure reason) and <id>/log.txt.
Then aggregate everything in <out> into summary.json and summary.md. With --compare-to HUMAN_OUT, also write
compare.json and compare.md: router and human layouts of the same task paired by id (only boards with
completion 1.0 are electrically comparable; the rest are reported separately).

Usage:
  python suite_physics.py --tasks kae-work/tasks --suite bench/suites/qualified-kicad-10.0.7.txt \\
         --out kae-work/physics/<run> [-j 3] [--timeout 600] [--mem-gb 4] [--only id1,id2]
  python suite_physics.py --tasks kae-work/tasks --out kae-work/physics/<router-run> --label freerouting \\
         --boards-glob 'kae-work/results/<run>/freerouting/route/*/attempt-0/work/output/board.kicad_pcb' \\
         [--compare-to kae-work/physics/<human-run>]
  python suite_physics.py --out DIR --aggregate-only [--compare-to HUMAN_OUT]
Re-running with the same --out skips boards that have meta.json (use --force to redo them).
"""
import argparse
import concurrent.futures as cf
import glob
import json
import math
import os
import re
import resource
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PASSPORTS = HERE / 'suite_passports.py'
CRITICS = HERE / 'pc_refplane.py'
STEM = 'board'


# ============================================================================ running one child
def rss_mb(pid):
    try:
        with open(f'/proc/{pid}/status') as f:
            for ln in f:
                if ln.startswith('VmRSS:'):
                    return int(ln.split()[1]) / 1024.0
    except (OSError, ValueError):
        pass
    return 0.0



def kicad_cli_argv(cmd=None):
    """kicad-cli as an argv list: an explicit command (shell-split, so it may carry a wrapper
    prefix), else KAE_KICAD_WRAP (e.g. an Apptainer exec prefix) + kicad-cli, else kicad-cli."""
    import shlex
    if cmd:
        return shlex.split(cmd)
    wrap = os.environ.get('KAE_KICAD_WRAP')
    return [*shlex.split(wrap), 'kicad-cli'] if wrap else ['kicad-cli']

def run_child(cmd, log_path, timeout, mem_gb, cwd=None, env=None):
    """Run cmd with a wall-clock timeout and a resident-memory cap; returns a record with rc, wall time,
    peak RSS (MB, from wait4) and status (ok, error, timeout, memory).

    The cap is enforced on resident memory by a watchdog (VmRSS polled every 0.25 s; the process group is killed
    past mem_gb). The address space is capped at 2.5 x mem_gb as a backstop: SuperLU grows its buffers by
    realloc, so a tight address-space cap fails factorizations whose resident memory is well inside mem_gb."""
    t0 = time.time()
    with open(log_path, 'ab') as lf:
        lf.write(f"\n$ {' '.join(map(str, cmd))}\n".encode())
        lf.flush()
        p = subprocess.Popen([str(c) for c in cmd], stdout=lf, stderr=subprocess.STDOUT, cwd=cwd, env=env, start_new_session=True)
        if mem_gb:     # set right after spawn (no preexec_fn: this runs in worker threads); Python start-up precedes any big allocation
            lim = int(2.5 * mem_gb * 1024 ** 3)
            try:
                resource.prlimit(p.pid, resource.RLIMIT_AS, (lim, lim))
            except (ProcessLookupError, OSError):
                pass
        killed = {'v': False}

        def kill():
            killed['v'] = True
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        timer = threading.Timer(timeout, kill)
        timer.start()
        over = {'v': False}
        done = threading.Event()

        def watch():
            while not done.wait(0.25):
                if mem_gb and rss_mb(p.pid) > mem_gb * 1024:
                    over['v'] = True
                    kill()
                    return
        if mem_gb:
            threading.Thread(target=watch, daemon=True).start()
        try:
            _, status, ru = os.wait4(p.pid, 0)
        finally:
            done.set()
            timer.cancel()
        p.returncode = os.waitstatus_to_exitcode(status)
    wall = time.time() - t0
    rec = dict(rc=p.returncode, wall_s=round(wall, 2), peak_rss_mb=round(ru.ru_maxrss / 1024.0, 1))
    tail = ''
    try:
        with open(log_path, 'rb') as f:
            f.seek(max(0, os.path.getsize(log_path) - 4000))
            tail = f.read().decode('utf-8', 'replace')
    except OSError:
        pass
    if over['v']:
        rec['status'], rec['reason'] = 'memory', f'resident memory passed {mem_gb} GB; killed'
    elif killed['v']:
        rec['status'], rec['reason'] = 'timeout', f'killed after {timeout} s'
    elif p.returncode == 0:
        rec['status'] = 'ok'
    elif 'MemoryError' in tail or 'Unable to allocate' in tail or 'std::bad_alloc' in tail or 'Cannot allocate memory' in tail:
        rec['status'], rec['reason'] = 'memory', f'allocation failed (address-space backstop {2.5 * mem_gb:g} GB)'
    else:
        last = [ln for ln in tail.splitlines() if ln.strip()]
        rec['status'], rec['reason'] = 'error', (last[-1][:300] if last else f'rc {p.returncode}')
    return rec


# ============================================================================ one board
def find_attempt_json(board):
    for d in Path(board).resolve().parents:
        if (d / 'attempt.json').exists():
            return d / 'attempt.json'
        if re.match(r'attempt-\d+$', d.name):
            return None
    return None


def board_items(args):
    items = []
    tasks = Path(args.tasks) if args.tasks else None
    if args.boards_glob:
        task_ids = {p.name for p in tasks.iterdir()} if tasks and tasks.exists() else set()
        for b in sorted(glob.glob(args.boards_glob)):
            parts = Path(b).resolve().parts
            tid = next((x for x in reversed(parts) if x in task_ids), None)
            stem = Path(b).parent.name if Path(b).stem == STEM else Path(b).stem
            bid = tid or re.sub(r'[^A-Za-z0-9_.-]+', '_', stem)
            k = 2
            while any(x['id'] == bid for x in items):
                bid = f"{tid or stem}-{k}"
                k += 1
            rules = tasks / tid / 'reference' if tid else Path(b).parent
            aj = find_attempt_json(b)
            items.append(dict(id=bid, board=str(Path(b).resolve()), rules=str(rules), task=tid,
                              task_json=str(tasks / tid / 'task.json') if tid else None,
                              attempt_json=str(aj) if aj else None))
    else:
        if args.only:
            ids = [x for x in args.only.split(',') if x]
        else:
            ids = [ln.strip() for ln in open(args.suite) if ln.strip() and not ln.startswith('#')]
        for i in ids:
            ref = tasks / i / 'reference'
            items.append(dict(id=i, board=str(ref / f'{STEM}.kicad_pcb'), rules=str(ref), task=i,
                              task_json=str(tasks / i / 'task.json'), attempt_json=None))
    if args.only and args.boards_glob:
        keep = set(args.only.split(','))
        items = [it for it in items if it['id'] in keep]
    return items


def process_board(it, args):
    out = Path(args.out) / it['id']
    meta_p = out / 'meta.json'
    if meta_p.exists() and not args.force:
        return json.loads(meta_p.read_text())
    if out.exists():
        shutil.rmtree(out)
    work = out / 'work'
    work.mkdir(parents=True)
    log = out / 'log.txt'
    meta = dict(id=it['id'], label=args.label, source_board=it['board'], task=it['task'], started=time.strftime('%Y-%m-%dT%H:%M:%S'),
                steps={})
    t0 = time.time()
    try:
        if it.get('task_json') and os.path.exists(it['task_json']):
            tj = json.loads(Path(it['task_json']).read_text())
            st = (tj.get('reference') or {}).get('stats') or {}
            meta.update(license=tj.get('license'), license_tier=tj.get('license_tier'), split=tj.get('split'), repo=tj.get('repo'),
                        copper_layers=st.get('copper_layers'), footprints=st.get('footprints'), pads=st.get('pads'))
        if it.get('attempt_json'):
            aj = json.loads(Path(it['attempt_json']).read_text())
            sc = aj.get('score') or {}
            meta.update(attempt_status=aj.get('status'), completion=sc.get('completion'), drc_errors=sc.get('errors'),
                        drc_unconnected=sc.get('unconnected'), drc_errors_by_type=sc.get('errors_by_type'), valid=sc.get('valid'))
        if not os.path.exists(it['board']):
            raise FileNotFoundError(it['board'])
        shutil.copy2(it['board'], work / f'{STEM}.kicad_pcb')
        for ext in ('.kicad_pro', '.kicad_dru'):
            src = Path(it['rules']) / f'{STEM}{ext}'
            if src.exists():
                shutil.copy2(src, work / f'{STEM}{ext}')
        board = work / f'{STEM}.kicad_pcb'
        # refill zones and save the private copy
        before = board.stat().st_mtime_ns
        keep = work / 'board.saved_fills.kicad_pcb'
        shutil.copy2(board, keep)
        r = run_child([*kicad_cli_argv(args.kicad_cli), 'pcb', 'drc', '--format', 'json', '--refill-zones', '--save-board', '--severity-all',
                       '--units', 'mm', '-o', str((out / 'drc.json').resolve()), str(board.resolve())],
                      log, args.refill_timeout or args.timeout, None, cwd=str(work))
        saved = board.exists() and board.stat().st_mtime_ns != before and r['status'] == 'ok'
        if saved:
            r['fills'] = 'refilled by KiCad and saved'
            keep.unlink()
        else:
            shutil.copy2(keep, board)
            r['fills'] = 'saved fills from the file (refill failed: ' + (r.get('reason') or 'board not saved') + ')'
        try:
            drc = json.loads((out / 'drc.json').read_text())
            byt = Counter(v.get('type') for v in drc.get('violations', []) if v.get('severity') == 'error')
            r['drc'] = dict(errors=sum(byt.values()), unconnected=len(drc.get('unconnected_items', [])),
                            errors_by_type=dict(byt))
        except (OSError, ValueError):
            pass
        meta['steps']['refill'] = r
        env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
        pcmd = [args.python, '-I', PASSPORTS, board, '--json', out / 'passports.json', '--roles-out', out / 'roles.json',
                '--budget-s', str(int(args.timeout * 0.85))] + args.passport_args
        meta['steps']['passports'] = run_child(pcmd, log, args.timeout, args.mem_gb, env=env)
        if meta['steps']['passports']['status'] in ('memory', 'timeout'):
            # second attempt with a smaller DC node budget and one HF cell; both attempts are recorded
            meta['steps']['passports_first'] = meta['steps']['passports']
            meta['steps']['passports'] = run_child(pcmd + ['--max-nodes', '100000', '--max-cells', '1'], log, args.timeout,
                                                   args.mem_gb, env=env)
            meta['steps']['passports']['retry'] = 'second attempt: --max-nodes 100000 --max-cells 1'
        meta['passport_args'] = [str(x) for x in args.passport_args]
        cmd = [args.python, '-I', CRITICS, board, '--json', out / 'critics.json']
        if (out / 'roles.json').exists():
            cmd += ['--roles', out / 'roles.json']
        meta['steps']['critics'] = run_child(cmd, log, args.timeout, args.mem_gb, env=env)
        meta['critics_roles'] = 'inferred+regex' if (out / 'roles.json').exists() else 'regex'
    except Exception as e:     # noqa: BLE001
        meta['error'] = f'{type(e).__name__}: {e}'
    meta['wall_s'] = round(time.time() - t0, 2)
    if not args.keep_work:
        for f in work.glob('*'):
            if f.suffix in ('.kicad_pcb', '.kicad_pro', '.kicad_dru', '.kicad_prl'):
                f.unlink()
    meta_p.write_text(json.dumps(meta, indent=1))
    return meta


# ============================================================================ aggregation
def q(vals, ps=(0, 10, 25, 50, 75, 90, 100)):
    v = sorted(x for x in vals if isinstance(x, (int, float)) and math.isfinite(x))
    if not v:
        return dict(n=0)
    out = dict(n=len(v))
    for p in ps:
        k = (len(v) - 1) * p / 100
        lo, hi = math.floor(k), math.ceil(k)
        out[f'p{p}'] = round(v[lo] + (v[hi] - v[lo]) * (k - lo), 6)
    return out


def load(p):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return None


def board_record(d):
    meta = load(d / 'meta.json') or {}
    pp = load(d / 'passports.json') or {}
    cr = load(d / 'critics.json') or {}
    rec = {k: meta.get(k) for k in ('id', 'label', 'license', 'license_tier', 'split', 'copper_layers', 'footprints', 'pads',
                                    'completion', 'drc_errors', 'drc_unconnected', 'wall_s', 'error')}
    st = meta.get('steps', {})
    rec['steps'] = {k: {kk: v.get(kk) for kk in ('status', 'reason', 'wall_s', 'peak_rss_mb', 'fills', 'retry')} for k, v in st.items()}
    rec['fills'] = (st.get('refill') or {}).get('fills')
    bi = pp.get('board_info') or {}
    rec['outline_mm2'] = bi.get('outline_mm2')
    rec['tracks'], rec['vias'], rec['zones'] = bi.get('tracks'), bi.get('vias'), bi.get('zones')
    rec['passport_coverage'] = pp.get('coverage')
    rec['passport_errors'] = [dict(stage=e.get('stage'), error=e.get('error')) for e in pp.get('errors', [])]
    rec['passport_timing'] = pp.get('timing')
    roles = pp.get('roles') or {}
    rails = roles.get('rails') or {}
    rec['roles'] = dict(
        ground=list((roles.get('ground') or {}).keys()),
        ground_confidence={n: r.get('confidence') for n, r in (roles.get('ground') or {}).items()},
        rails=Counter(r['confidence'] for r in rails.values()),
        sources=Counter(s['kind'] for r in rails.values() for s in r.get('sources', [])),
        source_confidence=Counter(s['confidence'] for r in rails.values() for s in r.get('sources', [])),
        rails_without_source=sum(1 for r in rails.values() if r['confidence'] != 'low' and 'sources' in r and not r['sources']),
        loads=sum(len(r.get('loads', [])) for r in rails.values()),
        loads_typed=sum(sum(1 for ld in r.get('loads', []) if ld.get('typed_power_in')) for r in rails.values()),
        decaps=sum(len(r.get('decaps', [])) for r in rails.values()),
        cells=Counter(c['type'] for c in roles.get('cells', [])),
        shunts=len(roles.get('shunts', [])), rejected_power=len(roles.get('rejected_power') or {}),
        switch_nodes=len(roles.get('switch_nodes') or []))
    dc = pp.get('dc') or {}
    rec['dc_model'] = dc.get('model')
    rr = []
    for n, r in (dc.get('rails') or {}).items():
        if r.get('status') != 'ok':
            rr.append(dict(net=n, status=r.get('status')))
            continue
        rr.append(dict(net=n, status='ok', confidence=r.get('confidence'), loads=r.get('loads_modelled'),
                       r_eff_mohm=r.get('r_eff_mohm'), r_eff_gnd_mohm=r.get('r_eff_gnd_mohm'),
                       worst_drop_mv_per_a=r.get('worst_drop_mv_per_a'), worst_load=r.get('worst_load'),
                       j_peak=r.get('j_peak_a_mm2_per_a'), necks=len(r.get('necks', [])),
                       via_bottlenecks=sum(1 for v in r.get('via_bottlenecks', []) if v.get('flagged')),
                       loads_through_one_via=r.get('loads_through_one_via'), dead_share=r.get('dead_share'),
                       avoidable_max=r.get('avoidable_max'), pour_mm2=r.get('pour_mm2'), series_faces=r.get('series_faces'),
                       lev_median=r.get('lev_median_top_faces')))
    rec['dc_rails'] = rr
    rec['dc_skipped_rails'] = dc.get('skipped_rails')
    g = dc.get('ground') or {}
    rec['ground'] = dict(dead_share=g.get('dead_share'), n_islands=g.get('n_islands'), weak_islands=g.get('n_weak_islands'),
                         floating_mm2=g.get('floating_mm2'), ep_without_vias=len(g.get('ep_without_vias', [])),
                         ep_power_ic_without_vias=sum(1 for e in g.get('ep_without_vias', []) if e.get('power_ic')))
    cells = []
    for c in (pp.get('hf') or {}).get('cells', []):
        cells.append(dict(ref=c.get('ref'), type=c.get('type'), status=c.get('status'), L_nH=c.get('L_esl_nH'),
                          swap=(c.get('swap_planes') or {}).get('change'), best_via=(c.get('best_added_via') or {}).get('change'),
                          median_via=(c.get('best_added_via') or {}).get('median_site_change'),
                          remove_plane=(c.get('remove_plane') or {}).get('ratio'), remove_plane_net=(c.get('remove_plane') or {}).get('net'),
                          foreign_share=c.get('foreign_net_current_share'), grid_mm=c.get('grid_mm'), cells=c.get('sheet_cells'),
                          t_s=c.get('t_s'), decaps=c.get('decaps_in_loop')))
    rec['hf_cells'] = cells
    rec['passport_findings'] = pp.get('findings_by_type') or {}
    m = rec.get('dc_model') or {}
    rec['unknowns'] = dict(dc_nodes=m.get('nodes'), dc_branches=m.get('branches'), dc_factor_s=m.get('t_factor_s'),
                           hf_sheet_cells=[c.get('cells') for c in cells if c.get('cells')],
                           hf_sheet_cells_total=sum(c.get('cells') or 0 for c in cells))
    fails = [f"{k}: {v.get('status')} ({v.get('reason')})" for k, v in rec['steps'].items() if v.get('status') not in ('ok', None)]
    fails += [f"passport stage {e['stage']}: {e['error']}" for e in rec['passport_errors']]
    if rec.get('fills') and not rec['fills'].startswith('refilled'):
        fails.append(rec['fills'])
    if meta.get('error'):
        fails.append(f"runner: {meta['error']}")
    rec['failure'] = '; '.join(fails) or None
    s = cr.get('summary') or {}
    res = cr.get('results') or {}
    planes = res.get('PLANE-PERF') or {}
    inner = [v for ly, v in planes.items() if ly not in ('F.Cu', 'B.Cu')]
    cav = [v.get('first_mode_ghz') for v in (res.get('CAVITY') or {}).values() if v.get('first_mode_ghz')]
    rec['critics'] = dict(
        error=s.get('error'), errors=len(cr.get('errors', [])), markers=s.get('markers_by_critic'),
        fast_nets=s.get('fast_nets'), fast_track_mm=s.get('fast_track_mm'), ret_cov_pct=s.get('ret_cov_primary_pct_lenweighted'),
        void_crossings=s.get('void_crossings'), ref_hops=s.get('ref_hops'), rpqf_worst=s.get('rpqf_lite_worst'),
        ret_via_checked=s.get('ret_via_checked'), planes=len(planes), inner_planes=len(inner),
        inner_foreign_track_mm=round(sum(v.get('foreign_track_mm') or 0 for v in inner), 2),
        inner_planes_perforated=sum(1 for v in inner if (v.get('foreign_track_mm') or 0) > 0),
        longest_slot_mm=max([v.get('longest_slot_mm') or 0 for v in planes.values()], default=0),
        pwr_trace_markers=(s.get('markers_by_critic') or {}).get('PWR-TRACE', 0),
        cavity_min_ghz=min(cav) if cav else None, role_changes=len(s.get('role_changes_vs_regex') or {}),
        role_change_list=s.get('role_changes_vs_regex'), markers_by_role_src=s.get('markers_by_role_src'), runtime_s=s.get('runtime_s'))
    return rec


def status_of(rec, step):
    return ((rec.get('steps') or {}).get(step) or {}).get('status')


def aggregate(out):
    out = Path(out)
    recs = [board_record(d) for d in sorted(out.iterdir()) if d.is_dir() and (d / 'meta.json').exists()]
    S = dict(boards=len(recs), label=Counter(r.get('label') for r in recs))
    S['status'] = {st: dict(Counter(status_of(r, st) for r in recs)) for st in ('refill', 'passports', 'critics')}
    S['fills'] = dict(Counter((r.get('fills') or 'none').split(' (')[0] for r in recs))
    S['failures'] = [dict(id=r['id'], step=st, status=status_of(r, st), reason=(r['steps'].get(st) or {}).get('reason'))
                     for r in recs for st in ('refill', 'passports_first', 'passports', 'critics') if status_of(r, st) not in ('ok', None)]
    S['failures'] += [dict(id=r['id'], step='runner', status='error', reason=r['error']) for r in recs if r.get('error')]
    S['passport_stage_errors'] = Counter(e['stage'].split(' ')[0] + ': ' + e['error'].split(':')[0]
                                         for r in recs for e in r.get('passport_errors') or [])
    S['coverage'] = dict(
        passports_json=sum(1 for r in recs if r.get('passport_coverage')),
        roles=sum(1 for r in recs if (r.get('passport_coverage') or {}).get('roles') == 'ok'),
        dc=sum(1 for r in recs if (r.get('passport_coverage') or {}).get('dc') == 'ok' and r.get('dc_rails')),
        dc_any_rail_ok=sum(1 for r in recs if any(x.get('status') == 'ok' for x in r.get('dc_rails') or [])),
        hf_cell_ok=sum(1 for r in recs if any(c.get('status') == 'ok' for c in r.get('hf_cells') or [])),
        boards_with_cell=sum(1 for r in recs if r.get('hf_cells')),
        critics_json=sum(1 for r in recs if r.get('critics', {}).get('markers') is not None),
        why_no_dc=Counter((r.get('passport_coverage') or {}).get('dc', 'no passports.json') for r in recs
                          if not any(x.get('status') == 'ok' for x in r.get('dc_rails') or [])),
        hf_status=Counter((c.get('status') or '').split(':')[0] + ((': ' + c['status'].split(':')[2].strip()[:60])
                                                                  if (c.get('status') or '').startswith('error') and c['status'].count(':') >= 2 else '')
                          for r in recs for c in r.get('hf_cells') or []))
    def steps(st, key):
        return [((r.get('steps') or {}).get(st) or {}).get(key) for r in recs]
    S['runtime_s'] = {st: q(steps(st, 'wall_s')) for st in ('refill', 'passports', 'critics')}
    S['runtime_s']['board_total'] = q([r.get('wall_s') for r in recs])
    S['runtime_s']['sum_all_boards'] = round(sum(x or 0 for x in [r.get('wall_s') for r in recs]), 1)
    S['peak_rss_mb'] = {st: q(steps(st, 'peak_rss_mb')) for st in ('passports', 'critics')}
    S['unknowns'] = dict(dc_nodes=q([(r.get('dc_model') or {}).get('nodes') for r in recs]),
                         dc_branches=q([(r.get('dc_model') or {}).get('branches') for r in recs]),
                         dc_factor_s=q([(r.get('dc_model') or {}).get('t_factor_s') for r in recs]),
                         hf_sheet_cells=q([c.get('cells') for r in recs for c in r.get('hf_cells') or []]),
                         hf_cell_s=q([c.get('t_s') for r in recs for c in r.get('hf_cells') or [] if c.get('status') == 'ok']))
    rails = [x for r in recs for x in r.get('dc_rails') or [] if x.get('status') == 'ok']
    S['rails'] = dict(n=len(rails), r_eff_mohm=q([x['r_eff_mohm'] for x in rails]),
                      r_eff_gnd_mohm=q([x['r_eff_gnd_mohm'] for x in rails]),
                      worst_drop_mv_per_a=q([x['worst_drop_mv_per_a'] for x in rails]),
                      j_peak_a_mm2_per_a=q([x['j_peak'] for x in rails]), dead_share=q([x['dead_share'] for x in rails]),
                      avoidable_max=q([x['avoidable_max'] for x in rails]),
                      necks=sum(x['necks'] or 0 for x in rails), rails_with_neck=sum(1 for x in rails if x['necks']),
                      via_bottlenecks=sum(x['via_bottlenecks'] or 0 for x in rails),
                      rails_with_via_bottleneck=sum(1 for x in rails if x['via_bottlenecks']),
                      loads_through_one_via=sum(x.get('loads_through_one_via') or 0 for x in rails),
                      loads_modelled=sum(x.get('loads') or 0 for x in rails),
                      by_confidence=dict(Counter(x['confidence'] for x in rails)))
    S['ground'] = dict(dead_share=q([r['ground']['dead_share'] for r in recs]),
                       boards_with_weak_island=sum(1 for r in recs if r['ground']['weak_islands']),
                       weak_islands=sum(r['ground']['weak_islands'] or 0 for r in recs),
                       ep_without_vias=sum(r['ground']['ep_without_vias'] or 0 for r in recs),
                       ep_power_ic_without_vias=sum(r['ground']['ep_power_ic_without_vias'] or 0 for r in recs))
    cells = [c for r in recs for c in r.get('hf_cells') or [] if c.get('status') == 'ok']
    S['hf'] = dict(n=len(cells), by_type=dict(Counter(c['type'] for c in cells)), L_nH=q([c['L_nH'] for c in cells]),
                   swap_change=q([c['swap'] for c in cells]), best_via_change=q([c['best_via'] for c in cells]),
                   median_via_change=q([c['median_via'] for c in cells]), remove_plane_ratio=q([c['remove_plane'] for c in cells]),
                   foreign_share=q([c['foreign_share'] for c in cells]))
    crs = [r['critics'] for r in recs if r['critics'].get('markers') is not None]
    S['critics'] = dict(n=len(crs), ret_cov_pct=q([c['ret_cov_pct'] for c in crs if c['fast_nets']]),
                        void_crossings=q([c['void_crossings'] for c in crs if c['fast_nets']]),
                        boards_with_void=sum(1 for c in crs if c['void_crossings']),
                        rpqf_worst=q([c['rpqf_worst'] for c in crs if c['fast_nets']]),
                        boards_with_fast_nets=sum(1 for c in crs if c['fast_nets']),
                        boards_with_inner_planes=sum(1 for c in crs if c['inner_planes']),
                        inner_planes_perforated=sum(c['inner_planes_perforated'] for c in crs),
                        inner_planes=sum(c['inner_planes'] for c in crs),
                        inner_foreign_track_mm=q([c['inner_foreign_track_mm'] for c in crs if c['inner_planes']]),
                        longest_slot_mm=q([c['longest_slot_mm'] for c in crs if c['planes']]),
                        cavity_min_ghz=q([c['cavity_min_ghz'] for c in crs]),
                        role_changes=sum(c['role_changes'] or 0 for c in crs),
                        role_change_kinds=dict(Counter(f"{a}->{b}" for c in crs for a, b in (c.get('role_change_list') or {}).values())),
                        markers_by_role_src=dict(sum((Counter(c.get('markers_by_role_src') or {}) for c in crs), Counter())))
    ft = Counter()
    fb = Counter()
    for r in recs:
        f = Counter(r.get('passport_findings') or {})
        f.update({k: v for k, v in (r['critics'].get('markers') or {}).items()})
        ft.update(f)
        fb.update({k: 1 for k, v in f.items() if v})
    S['findings_total'] = dict(ft)
    S['boards_with_finding'] = dict(fb)
    S['roles'] = dict(
        ground_confidence=dict(Counter(c for r in recs for c in (r['roles']['ground_confidence'] or {}).values())),
        boards_without_ground=sum(1 for r in recs if r.get('passport_coverage') and not r['roles']['ground']),
        rails=dict(sum((Counter(r['roles']['rails']) for r in recs), Counter())),
        sources=dict(sum((Counter(r['roles']['sources']) for r in recs), Counter())),
        source_confidence=dict(sum((Counter(r['roles']['source_confidence']) for r in recs), Counter())),
        rails_without_source=sum(r['roles']['rails_without_source'] for r in recs),
        loads=sum(r['roles']['loads'] for r in recs), loads_typed=sum(r['roles']['loads_typed'] for r in recs),
        decaps=sum(r['roles']['decaps'] for r in recs), cells=dict(sum((Counter(r['roles']['cells']) for r in recs), Counter())),
        shunts=sum(r['roles']['shunts'] for r in recs), rejected_power=sum(r['roles']['rejected_power'] for r in recs))
    S['per_board'] = recs
    (out / 'summary.json').write_text(json.dumps(S, indent=1, default=str))
    (out / 'summary.md').write_text(summary_md(S))
    return S


def fq(d, k=3):
    if not d or not d.get('n'):
        return 'n/a'
    return f"{fmt(d['p50'], k)} [{fmt(d['p10'], k)}-{fmt(d['p90'], k)}] (n={d['n']}, max {fmt(d['p100'], k)})"


def fmt(v, k=3):
    if v is None:
        return '-'
    if isinstance(v, float):
        return f"{v:.{k}g}"
    return str(v)


def summary_md(S):
    L = [f"# Suite physics summary ({S['boards']} boards; labels {dict(S['label'])})", '',
         'Separate physics scorecard: no cp1/cpk here. Values per ampere are per ampere of that load; HF inductances come',
         'from an uncalibrated stack-local model (use ratios and rankings). Distributions: median [p10-p90] (n, max).', '',
         '## Status and coverage', '', '| step | statuses |', '|---|---|']
    for st, c in S['status'].items():
        L.append(f"| {st} | {', '.join(f'{k}: {v}' for k, v in c.items())} |")
    L += ['', f"Fills: {S['fills']}", '', '| analysis | boards |', '|---|---|']
    for k, v in S['coverage'].items():
        L.append(f"| {k} | {dict(v) if isinstance(v, (dict, Counter)) else v} |")
    L += ['', '## Runtime, memory, unknowns', '', '| quantity | distribution |', '|---|---|']
    for k, v in S['runtime_s'].items():
        L.append(f"| wall s, {k} | {fq(v) if isinstance(v, dict) else v} |")
    for k, v in S['peak_rss_mb'].items():
        L.append(f"| peak RSS MB, {k} | {fq(v)} |")
    for k, v in S['unknowns'].items():
        L.append(f"| {k} | {fq(v)} |")
    L += ['', '## Roles', '', '```', json.dumps(S['roles'], indent=1, default=str), '```', '',
          '## DC passports (per rail)', '', '| quantity | distribution |', '|---|---|']
    for k, v in S['rails'].items():
        L.append(f"| {k} | {fq(v) if isinstance(v, dict) and 'n' in v else v} |")
    L += ['', '## Ground', '', '```', json.dumps(S['ground'], indent=1, default=str), '```', '',
          '## HF hot loops', '', '| quantity | distribution |', '|---|---|']
    for k, v in S['hf'].items():
        L.append(f"| {k} | {fq(v) if isinstance(v, dict) and 'n' in v else v} |")
    L += ['', '## Critics', '', '| quantity | distribution |', '|---|---|']
    for k, v in S['critics'].items():
        L.append(f"| {k} | {fq(v) if isinstance(v, dict) and 'n' in v else v} |")
    L += ['', '## Findings by type', '', '| type | total | boards |', '|---|---|---|']
    for k in sorted(S['findings_total'], key=lambda k: -S['boards_with_finding'].get(k, 0)):
        L.append(f"| {k} | {S['findings_total'][k]} | {S['boards_with_finding'].get(k, 0)} |")
    L += ['', '## Failures', '']
    for f in S['failures']:
        L.append(f"- {f['id']} {f['step']}: {f['status']} ({f['reason']})")
    if S['passport_stage_errors']:
        L += ['', 'Passport stage errors (caught, recorded in passports.json):', '']
        for k, v in Counter(S['passport_stage_errors']).most_common():
            L.append(f"- {k}: {v}")
    L += ['', '## Per board', '', '| id | lic | L | split | refill | pass s | crit s | RSS MB | DC nodes | rails ok | worst mV/A | HF L nH |'
          ' findings (passports) | markers (critics) |', '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for r in S['per_board']:
        st = r.get('steps') or {}
        worst = max([x['worst_drop_mv_per_a'] for x in r.get('dc_rails') or [] if x.get('worst_drop_mv_per_a') is not None], default=None)
        L.append(f"| {r['id']} | {r.get('license')} | {r.get('copper_layers')} | {r.get('split')} | {(st.get('refill') or {}).get('status')} |"
                 f" {(st.get('passports') or {}).get('wall_s')} {'' if (st.get('passports') or {}).get('status') == 'ok' else (st.get('passports') or {}).get('status')} |"
                 f" {(st.get('critics') or {}).get('wall_s')} | {(st.get('passports') or {}).get('peak_rss_mb')} |"
                 f" {(r.get('dc_model') or {}).get('nodes')} | {sum(1 for x in r.get('dc_rails') or [] if x.get('status') == 'ok')} |"
                 f" {fmt(worst)} | {', '.join(fmt(c['L_nH']) for c in r.get('hf_cells') or [] if c.get('L_nH'))} |"
                 f" {', '.join(f'{k} {v}' for k, v in sorted((r.get('passport_findings') or {}).items()))} |"
                 f" {', '.join(f'{k} {v}' for k, v in sorted((r['critics'].get('markers') or {}).items()))} |")
    return '\n'.join(L) + '\n'


# ============================================================================ router vs human
def compare(router_out, human_out):
    R = {r['id']: r for r in (load(Path(router_out) / 'summary.json') or aggregate(router_out))['per_board']}
    H = {r['id']: r for r in (load(Path(human_out) / 'summary.json') or aggregate(human_out))['per_board']}
    pairs = []
    for i in sorted(set(R) & set(H)):
        r, h = R[i], H[i]
        def fnd(x):
            f = Counter(x.get('passport_findings') or {})
            f.update(x['critics'].get('markers') or {})
            return f
        fr, fh = fnd(r), fnd(h)
        hl = {c['ref']: c['L_nH'] for c in h.get('hf_cells') or [] if c.get('L_nH')}
        rl = {c['ref']: c['L_nH'] for c in r.get('hf_cells') or [] if c.get('L_nH')}
        hr = {x['net']: x for x in h.get('dc_rails') or [] if x.get('status') == 'ok'}
        rr = {x['net']: x for x in r.get('dc_rails') or [] if x.get('status') == 'ok'}
        rails = {n: dict(human_worst=hr[n]['worst_drop_mv_per_a'], router_worst=rr[n]['worst_drop_mv_per_a'],
                         human_reff=hr[n]['r_eff_mohm'], router_reff=rr[n]['r_eff_mohm']) for n in set(hr) & set(rr)}
        pairs.append(dict(
            id=i, license=h.get('license'), split=h.get('split'), layers=h.get('copper_layers'), completion=r.get('completion'),
            router_drc_errors=r.get('drc_errors'), router_unconnected=r.get('drc_unconnected'),
            both_ok=status_of(r, 'critics') == 'ok' and status_of(h, 'critics') == 'ok',
            findings_human=dict(fh), findings_router=dict(fr),
            findings_new=dict((fr - fh)), findings_gone=dict((fh - fr)),
            hotloop=dict(human=hl, router=rl, ratio={k: round(rl[k] / hl[k], 3) for k in set(hl) & set(rl)}),
            ret=dict(human=dict(cov=h['critics'].get('ret_cov_pct'), voids=h['critics'].get('void_crossings'),
                                rpqf=h['critics'].get('rpqf_worst'), ret_via=(h['critics'].get('markers') or {}).get('RET-VIA', 0),
                                inner_foreign_mm=h['critics'].get('inner_foreign_track_mm'),
                                inner_perforated=h['critics'].get('inner_planes_perforated')),
                     router=dict(cov=r['critics'].get('ret_cov_pct'), voids=r['critics'].get('void_crossings'),
                                 rpqf=r['critics'].get('rpqf_worst'), ret_via=(r['critics'].get('markers') or {}).get('RET-VIA', 0),
                                 inner_foreign_mm=r['critics'].get('inner_foreign_track_mm'),
                                 inner_perforated=r['critics'].get('inner_planes_perforated'))),
            rails=rails))
    comp = [p for p in pairs if p['completion'] == 1.0 and p['both_ok']]
    inc = [p for p in pairs if not (p['completion'] == 1.0 and p['both_ok'])]

    def agg(ps):
        new, gone, bnew = Counter(), Counter(), Counter()
        for p in ps:
            new.update(p['findings_new'])
            gone.update(p['findings_gone'])
            bnew.update({k: 1 for k in p['findings_new']})
        ratios = [v for p in ps for v in p['hotloop']['ratio'].values()]
        dw = [rv['router_worst'] / rv['human_worst'] for p in ps for rv in p['rails'].values()
              if rv['human_worst'] and rv['router_worst'] is not None]
        return dict(n=len(ps), findings_new=dict(new), boards_with_new=dict(bnew), findings_gone=dict(gone),
                    hotloop_ratio=q(ratios), worst_drop_ratio=q(dw),
                    void_crossings_human=sum(p['ret']['human']['voids'] or 0 for p in ps),
                    void_crossings_router=sum(p['ret']['router']['voids'] or 0 for p in ps),
                    ret_via_human=sum(p['ret']['human']['ret_via'] or 0 for p in ps),
                    ret_via_router=sum(p['ret']['router']['ret_via'] or 0 for p in ps),
                    inner_perforated_human=sum(p['ret']['human']['inner_perforated'] or 0 for p in ps),
                    inner_perforated_router=sum(p['ret']['router']['inner_perforated'] or 0 for p in ps),
                    inner_foreign_mm_human=round(sum(p['ret']['human']['inner_foreign_mm'] or 0 for p in ps), 1),
                    inner_foreign_mm_router=round(sum(p['ret']['router']['inner_foreign_mm'] or 0 for p in ps), 1),
                    ret_cov_delta=q([(p['ret']['router']['cov'] or 0) - (p['ret']['human']['cov'] or 0) for p in ps
                                     if p['ret']['human']['cov'] is not None and p['ret']['router']['cov'] is not None]))
    C = dict(router=str(router_out), human=str(human_out), pairs=len(pairs), complete=agg(comp), incomplete=agg(inc), per_pair=pairs)
    Path(router_out, 'compare.json').write_text(json.dumps(C, indent=1, default=str))
    L = [f"# Router vs human physics ({len(pairs)} paired boards; {len(comp)} complete and analysed on both sides)", '']
    for name, a in (('complete (completion 1.0)', C['complete']), ('incomplete or failed', C['incomplete'])):
        L += [f"## {name}: {a['n']} boards", '', '| quantity | human | router |', '|---|---|---|',
              f"| void crossings (RET-COV) | {a['void_crossings_human']} | {a['void_crossings_router']} |",
              f"| RET-VIA markers | {a['ret_via_human']} | {a['ret_via_router']} |",
              f"| inner planes with foreign tracks | {a['inner_perforated_human']} | {a['inner_perforated_router']} |",
              f"| foreign track on inner planes (mm) | {a['inner_foreign_mm_human']} | {a['inner_foreign_mm_router']} |", '',
              f"Hot-loop L router/human: {fq(a['hotloop_ratio'])}. Worst rail drop router/human: {fq(a['worst_drop_ratio'])}."
              f" RET-COV coverage delta (router - human, %): {fq(a['ret_cov_delta'])}.", '',
              '| finding type | new in router (count) | boards | gone in router |', '|---|---|---|---|']
        for k in sorted(set(a['findings_new']) | set(a['findings_gone']), key=lambda k: -a['findings_new'].get(k, 0)):
            L.append(f"| {k} | {a['findings_new'].get(k, 0)} | {a['boards_with_new'].get(k, 0)} | {a['findings_gone'].get(k, 0)} |")
        L.append('')
    L += ['## Per pair', '', '| id | split | L | completion | new findings | gone | HF L human/router |', '|---|---|---|---|---|---|---|']
    for p in pairs:
        new = ', '.join(f'{k} {v}' for k, v in sorted(p['findings_new'].items()))
        gone = ', '.join(f'{k} {v}' for k, v in sorted(p['findings_gone'].items()))
        hh, hr_ = p['hotloop']['human'], p['hotloop']['router']
        hl = '; '.join(f'{k} {hh.get(k)}/{hr_.get(k)}' for k in hh)
        L.append(f"| {p['id']} | {p['split']} | {p['layers']} | {p['completion']} | {new} | {gone} | {hl} |")
    Path(router_out, 'compare.md').write_text('\n'.join(L) + '\n')
    return C


# ============================================================================ main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--tasks', help='kaebench tasks directory (kae-work/tasks)')
    ap.add_argument('--suite', help='suite file (one task id per line)')
    ap.add_argument('--only', help='comma-separated ids (overrides --suite; filters --boards-glob)')
    ap.add_argument('--boards-glob', help='arbitrary board files, e.g. router outputs; ids from the task id in the path')
    ap.add_argument('--label', default='human', help='label stored with each board (human, freerouting, ...)')
    ap.add_argument('--out', required=True)
    ap.add_argument('-j', type=int, default=3)
    ap.add_argument('--timeout', type=float, default=600.0, help='seconds per board per tool')
    ap.add_argument('--refill-timeout', type=float, default=None, help='seconds for the KiCad refill (default --timeout)')
    ap.add_argument('--mem-gb', type=float, default=4.0, help='resident-memory cap per tool process (GB; address space capped at 2.5x)')
    ap.add_argument('--python', default=sys.executable)
    ap.add_argument('--kicad-cli', default=os.environ.get('KAE_KICAD_CLI'),
                    help='kicad-cli command (may carry a wrapper prefix); default: KAE_KICAD_CLI, else '
                         'KAE_KICAD_WRAP + kicad-cli, else kicad-cli')
    ap.add_argument('--passport-args', default='', help='extra arguments for suite_passports.py (quoted)')
    ap.add_argument('--force', action='store_true', help='redo boards that already have meta.json')
    ap.add_argument('--keep-work', action='store_true', help='keep the refilled board copies')
    ap.add_argument('--aggregate-only', action='store_true')
    ap.add_argument('--compare-to', help='a human-reference output directory to pair with (writes compare.json/.md)')
    args = ap.parse_args(argv)
    args.passport_args = args.passport_args.split()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for bad in ('/results/', '/score', '/bench/'):
        if bad in str(out.resolve()) + '/':
            raise SystemExit(f'refusing to write under {out}: physics output never goes into kaebench results, score or bench/')
    if not args.aggregate_only:
        items = board_items(args)
        print(f"{len(items)} boards -> {out} (-j {args.j}, timeout {args.timeout} s, mem {args.mem_gb} GB)", flush=True)
        t0 = time.time()
        done = 0
        with cf.ThreadPoolExecutor(max_workers=args.j) as ex:
            futs = {ex.submit(process_board, it, args): it for it in items}
            for f in cf.as_completed(futs):
                done += 1
                it = futs[f]
                try:
                    m = f.result()
                    st = m.get('steps', {})
                    print(f"[{done}/{len(items)} {time.time() - t0:.0f}s] {it['id']}: refill {st.get('refill', {}).get('status')}"
                          f" passports {st.get('passports', {}).get('status')} {st.get('passports', {}).get('wall_s')} s"
                          f" critics {st.get('critics', {}).get('status')} {st.get('critics', {}).get('wall_s')} s"
                          + (f" ERROR {m['error']}" if m.get('error') else ''), flush=True)
                except Exception as e:      # noqa: BLE001
                    print(f"[{done}/{len(items)}] {it['id']}: runner error {e}", flush=True)
    S = aggregate(out)
    print(f"summary: {out / 'summary.json'} ({S['boards']} boards); findings {S['findings_total']}", flush=True)
    if args.compare_to:
        C = compare(out, args.compare_to)
        print(f"compare: {out / 'compare.json'} ({C['pairs']} pairs, {C['complete']['n']} complete)", flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
