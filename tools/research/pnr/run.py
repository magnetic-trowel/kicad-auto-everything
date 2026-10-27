# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point for kaebench --command:

    python run.py METHOD {input} {output} [--seed N] [--grid MM] [--budget S]

Extracts the board with KiCad's Python, runs METHOD from methods.py, writes poses and
copper back with KiCad's Python. Logs and a summary JSON go next to the output.

Anytime (anytime.py): while the method runs, the best legal board so far is written to
the output (atomically), so a killed attempt keeps it; a complete legal board ends the run
early (--stop-when-routed 0 keeps going); PathFinder passes stop at budget x (1 + overrun)
CPU s. PNR_ANYTIME=0 PNR_STOP_WHEN_ROUTED=0 PNR_OVERRUN=-1 run as before this module.
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
    env = os.environ.get
    ap.add_argument("--anytime", type=int, default=int(env("PNR_ANYTIME", "1")),
                    help="1: write the best legal board so far while the method runs")
    ap.add_argument("--anytime-every", type=float, default=float(env("PNR_ANYTIME_EVERY", "30")),
                    help="wall s between writes that only lower the cost (fewer open connections: at once)")
    ap.add_argument("--stop-when-routed", type=int, default=int(env("PNR_STOP_WHEN_ROUTED", "1")),
                    help="1: end the method at the first legal board with every connection routed")
    ap.add_argument("--overrun", type=float, default=float(env("PNR_OVERRUN", "0.1")),
                    help="PathFinder stops its passes past budget x (1 + overrun) CPU s; < 0: never")
    a = ap.parse_args()
    t0 = time.time()
    out = Path(a.output)
    work = out.parent
    work.mkdir(parents=True, exist_ok=True)
    ext = work / "extract.json"
    kicad("extract", a.input, ext)
    data = json.loads(ext.read_text())
    import anytime
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
    writer = anytime.Writer(kicad, a.input, out)
    at = anytime.install(world, writer, a.budget, log, every_s=a.anytime_every, overrun=a.overrun,
                         stop_when_routed=bool(a.stop_when_routed), enabled=bool(a.anytime), t0=t0)
    try:
        router = fn(world, seed=a.seed, budget=a.budget, log=log, **opts)
    except anytime.Routed as e:
        router = e.router
    inflight = at.close()
    res = anytime.export(world, router)
    st = router.stats()
    kept = "final"
    if at.best_payload is not None:
        # a checkpoint on disk with fewer open connections than the method's final state
        # (or the final state illegal) stays the output
        fin = (0 if anytime.legal(world, router) else 1, st["unrouted"])
        if (0, at.best[0]) < fin:
            log(f"anytime: final state {fin} is worse than the best checkpoint {at.best}; writing that")
            res, kept = at.best_payload, "checkpoint"
            st.update(final_unrouted=st["unrouted"], unrouted=at.best[0])
    (work / "result.json").write_text(json.dumps(res))
    writer.commit(writer(res, final=True))
    if inflight is not None:
        inflight.join()  # its checkpoint is discarded, not committed
    st["anytime"] = dict(at.summary(), output=kept)
    st.update(method=a.method, seed=a.seed, runtime_s=round(time.time() - t0, 1), hpwl=round(world.hpwl(), 2))
    log(f"done {st}")
    (work / "pnr_summary.json").write_text(json.dumps(st))
    print(json.dumps(st))


if __name__ == "__main__":
    main()
