# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import sys,json
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[4] / 'kae' / 'src'))
from kae.board import kicad_file
from kae.place import edge_check as E
from pathlib import Path
out={}
for bid in open(sys.argv[1]).read().split():
    p=Path.home()/'kae-boards'/'boards'/bid/'board.kicad_pcb'
    try:
        b=kicad_file.load(str(p),rules=False)
        ep=E.edge_parts(b)
        by={fp.uuid:fp for fp in b.footprints}
        out[bid]=[k for u,(r,k) in ep.items() if not by[u].locked]
    except Exception as e:
        out[bid]=f"ERR {e}"
json.dump(out,open(sys.argv[2],'w'),indent=0)
pin=[b for b,v in out.items() if isinstance(v,list) and any(k in E.PIN_KINDS for k in v)]
print(len(out),'pin boards',len(pin),'any edge',sum(1 for v in out.values() if isinstance(v,list) and v),'err',sum(1 for v in out.values() if isinstance(v,str)))
open(sys.argv[3],'w').write('\n'.join(pin)+'\n')
