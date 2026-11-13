<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# PCBWorld's evaluation chain, for scoring our runs (report-only)

[PCBWorld](https://github.com/LGAI-Research/PCBWorld) (BSD-3; engine
[PCBWorld-Engine](https://github.com/LGAI-Research/PCBWorld-Engine), GPL-3.0, KiCad 9.0.8 with patches) is the
public routing benchmark behind the D3-A/B numbers ([topic doc](../../../docs/topics/routing/pcbworld.md)).
These scripts let its own scorer judge our runs beside our benchmark scorer. They change no kaebench score.

| File | Does |
|---|---|
| `d3_corpus.py` | PCBWorld's D3 board folders (`exacad_sorted/<NNNN>_<name>/processed_v9_guide_v3.*`) → a kaeres corpus (`KAE_CORPUS`), ids `pcbw-<split>-<name>` |
| `transplant_v9.py` | copies a routed board's tracks, arcs and vias (KiCad 9 or 10 file) onto PCBWorld's unrouted KiCad 9 input board, with KiCad 9's pcbnew; their engine cannot open KiCad 10 files |
| `score_pcbworld.py` | per kaeres method, a PCBWorld "cell" of transplanted boards, then their `eval.pipeline` with the paper's scoring flags (`drc_dense_promoted`, `final_potential` selection, 45° angles) |

## Building their chain

Their code is untrusted third-party code: keep it in its own directory, read the build scripts first, and run it
from there with paths as arguments. What we ran (2026-11, `docs/research/routing/pcbworld-d3-2611.md`):

1. Clone PCBWorld and PCBWorld-Engine (pinned as PCBWorld's `engine/` submodule), then the engine's `kicad-python`
   submodule (KiCad 9.0.8 from gitlab.com/kicad).
2. A conda env from their `environment.yml` (micromamba works; no conda needed), with their `requirements.txt`
   minus the GPU training stack (torch, CUDA, vllm, flash-attn, ray): scoring and the data chain do not import it.
3. `BUILD_CLI=1 BUILD_PCBNEW=1 bash engine/build_rl_router.sh` inside the env (cap ninja's `-j`; it otherwise
   takes every CPU), through kaeq.
4. `PCBWORLD_DATA_ROOT=<dir> bash tools/quickstart/prepare_pcbench.sh` (clones PCBench at dec3be75, converts,
   filters, writes the guide boards, sorts, writes DSN/ORP), through kaeq.

Then `d3_corpus.py` → `tools/kaeres/experiments/pcbworld-d3/setup.sh` → kaeres runs → `score_pcbworld.py`.
