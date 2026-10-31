# SPDX-License-Identifier: GPL-3.0-or-later
# Re-run the bridge's post-route stage (repair.loop: repair rounds, then the last mile) on a routed board.
# usage: rl.py <task input> <routed board> <outdir> <seconds> <seed> [KEY=JSON ...]
import sys, time, json, shutil
from pathlib import Path
from kae.board import pcbnew_io
from kae.route import constraints, drc, repair, bridge
inp, board, od, T, seed = sys.argv[1], sys.argv[2], Path(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5])
if od.exists(): shutil.rmtree(od)
od.mkdir(parents=True)
t0 = time.monotonic()
opts = dict(bridge.DEFAULT_OPTS, seed=seed)
for kv in sys.argv[6:]:
    k, _, v = kv.partition('='); opts[k] = json.loads(v)
info = pcbnew_io.export_dsn(inp, od / 'kicad.dsn')
opts['severities'] = bridge.severities(inp)
plan = constraints.plan(info, inp, opts)
plan.plane_policy = bridge.plane_policy(opts); plan.plane_cost = opts.get('plane_cost'); plan.pad_shapes = opts.get('pad_shapes') or 'kicad'
out = od / 'out.kicad_pcb'; shutil.copy2(board, out)
deadline = time.monotonic() + T
r = repair.loop(inp, out, od, plan, info, opts, deadline, log=lambda m: print(m, flush=True))
rep = drc.run(drc.stage_board(out, inp, od / 'score'), od / 'score' / 'drc.json', timeout=1800)
s = drc.summary(rep)
base = repair.input_errors(inp, od, time.monotonic() + 900)
print('RESULT final', s['unconnected'], s['errors'], s['by_type'], 'excess', drc.excess(s, base), f'{time.monotonic()-t0:.0f}s', flush=True)
json.dump(dict(final=s, excess=drc.excess(s, base), rounds=r.get('rounds')), open(od / 'result.json', 'w'), indent=1, default=str)
