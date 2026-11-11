# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""DRC violations per code for every board of a PCBWorld cell, by PCBWorld's own scorer.

PCBWorld's pipeline keeps only violation counts in per_rollout.csv. This calls its scoring kernel
(eval.metrics.evaluate_one, the paper's reward config and angle check) on each board of CELL/boards/
and writes CELL/drv_codes.jsonl: board file, clean pass, error-level counts by error_type and the
promoted warnings. Run it with PCBWorld's interpreter from the PCBWorld checkout:

    cd PCBWORLD && PYTHONPATH=build_rl/pcbnew/python/rl:. python drv_codes.py CELL [WORKERS]
"""
import json
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path


def one(pcb):
    from eval.metrics import evaluate_one
    from eval.eval_utils import resolve_pro_path
    pro = resolve_pro_path(Path(pcb))
    m = evaluate_one(str(pcb), str(pro) if pro else None, reward_config_name="drc_dense_promoted", check_angle=45)
    v = m.get("drv_violations") or []
    err = Counter(x.get("error_type") for x in v if x.get("is_error"))
    prom = Counter(x.get("error_type") for x in v if x.get("is_promoted"))
    return dict(board=Path(pcb).name, clean_pass=bool(m.get("clean_pass")), success=bool(m.get("success")),
                routability=m.get("routability"), drv_errors=m.get("drv_errors_only_count"),
                errors_by_type=dict(err), promoted_by_type=dict(prom))


def main():
    cell = Path(sys.argv[1])
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    pcbs = sorted((cell / "boards").glob("*.kicad_pcb"))
    with ProcessPoolExecutor(workers) as ex, open(cell / "drv_codes.jsonl", "w") as f:
        for rec in ex.map(one, pcbs):
            f.write(json.dumps(rec) + "\n")
    print(f"{len(pcbs)} boards -> {cell / 'drv_codes.jsonl'}")


if __name__ == "__main__":
    main()
