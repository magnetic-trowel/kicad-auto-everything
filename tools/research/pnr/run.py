# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point for kaebench --command:

    python run.py METHOD {input} {output} [--seed N] [--grid MM] [--budget S]

Extracts the board with KiCad's Python, runs METHOD from methods.py, writes poses and
copper back with KiCad's Python. Logs and a summary JSON go next to the output.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
KICAD_PY = os.environ.get("KAE_KICAD_PYTHON", "/usr/bin/python3")


def kicad(*args):
    r = subprocess.run([KICAD_PY, str(HERE / "kicad_io.py"), *map(str, args)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-3000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("method")
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--grid", type=float, default=0.1)
    ap.add_argument("--budget", type=float, default=300.0)
    ap.add_argument("--spokes", action="store_true", help="reserve thermal spoke corridors")
    ap.add_argument("--zone-nets", default="route", choices=["route", "skip"])
    ap.add_argument("--opt", action="append", default=[], help="key=value method options")
    a = ap.parse_args()
    t0 = time.time()
    out = Path(a.output)
    work = out.parent
    work.mkdir(parents=True, exist_ok=True)
    ext = work / "extract.json"
    kicad("extract", a.input, ext)
    data = json.loads(ext.read_text())
    import methods
    from world import World
    world = World(data, g=a.grid, spokes=a.spokes, zone_nets=a.zone_nets)
    logf = open(work / "pnr.log", "w")

    def log(msg):
        logf.write(f"[{time.time() - t0:7.1f}s] {msg}\n")
        logf.flush()

    log(f"{world.R} grid {world.W}x{world.H}x{world.nl} nets={len(world.net_pins)} parts={len(world.parts)}")
    opts = {}
    for kv in a.opt:
        k, v = kv.split("=", 1)
        try:
            v = json.loads(v)
        except ValueError:
            pass
        opts[k] = v
    if ":" in a.method:  # plug-in: /path/to/module.py:function (or module:function on sys.path)
        import importlib.util
        mod_path, fname = a.method.rsplit(":", 1)
        if mod_path.endswith(".py"):
            sys.path.insert(0, str(Path(mod_path).resolve().parent))
            spec = importlib.util.spec_from_file_location(Path(mod_path).stem, mod_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        else:
            mod = importlib.import_module(mod_path)
        fn = getattr(mod, fname)
    else:
        fn = getattr(methods, a.method.replace("-", "_"))
    router = fn(world, seed=a.seed, budget=a.budget, log=log, **opts)
    tracks, vias = router.export()
    poses = {}
    for pi, (cx, cy, ri) in world.pose.items():
        p = world.parts[pi]
        if p.locked or pi in world.fixed:
            continue
        x, y = world.xy(cx, cy)
        from world import ROTS
        poses[str(pi)] = dict(x=x, y=y, rot=ROTS[ri], uuid=p.uuid)
    res = dict(poses=poses, tracks=tracks, vias=vias)
    (work / "result.json").write_text(json.dumps(res))
    kicad("apply", a.input, work / "result.json", out)
    st = router.stats()
    st.update(method=a.method, seed=a.seed, runtime_s=round(time.time() - t0, 1), hpwl=round(world.hpwl(), 2))
    log(f"done {st}")
    (work / "pnr_summary.json").write_text(json.dumps(st))
    print(json.dumps(st))


if __name__ == "__main__":
    main()
