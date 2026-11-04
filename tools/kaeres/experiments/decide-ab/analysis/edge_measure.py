import os, pathlib
"""Edge distance and facing of panel connectors on each run's output board (edge-ab).
   edge_measure.py OUT.json RUN_DIR..."""
import sys, json, gzip, tempfile, os
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[5] / 'kae/src'))
from kae.board import kicad_file
from kae.place import edge_check as E
out = {}
for d in sys.argv[2:]:
    p = os.path.join(d, 'output.kicad_pcb.gz')
    if not os.path.exists(p):
        continue
    with tempfile.NamedTemporaryFile(suffix='.kicad_pcb', delete=False) as f:
        f.write(gzip.open(p).read()); tmp = f.name
    try:
        b = kicad_file.load(tmp, rules=False)
        ol = E._outline(b); by = {fp.uuid: fp for fp in b.footprints}
        rows = []
        for u, (ref, k) in E.edge_parts(b).items():
            fp = by[u]
            try:
                fc = E.facing(fp, ol)
            except Exception:
                fc = None
            rows.append(dict(ref=ref, kind=k, pin=k in E.PIN_KINDS, dist=round(E.distance(fp, ol), 2), facing=fc if not isinstance(fc, float) else round(fc, 2)))
        out[d] = rows
    except Exception as e:
        out[d] = f"ERR {type(e).__name__}: {e}"
    finally:
        os.unlink(tmp)
json.dump(out, open(sys.argv[1], 'w'), indent=0)
