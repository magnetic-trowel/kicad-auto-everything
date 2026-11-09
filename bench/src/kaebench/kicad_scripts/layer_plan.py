# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Which copper layers a benchmark task may use (no pcbnew needed: pcbnew_ops imports it too).

A board's declared copper layer count is not always its design: Eagle imports declare all 16
copper layers, and others keep inner layers they never drew on. A router then has free layers
the design does not have, the task is easier than the human one, and the copper would cost
real money. `plan` decides, from what pcbnew_ops' layer-use reports, the task's copper:

  - A layer is used if it has tracks or arcs, copper zones (keepouts do not count), copper
    graphics or text, pads of its own, or a blind/buried via that ends on it. Through vias and
    stitching pass every layer and say nothing about it; any other copper counts, however
    little, because a human reference must stay intact.
  - Only trusted evidence changes a task: the board has copper and the human layout is
    complete or nearly so (open connections at most NEAR_COMPLETE of open + routing items), so
    the layers it left empty were not needed; one forgotten stub on a 1000-track board does
    not leave its inner layers open. Unfinished or empty boards keep their declaration,
    except the Eagle default: 16 layers, no stackup block, no inner layer named or used,
    which is 2 layers.
  - Fabs build even copper counts, and removing a layer may not renumber those kept (layer
    names are the contract with rules, zones and vias). So the stack is cut from the bottom
    of the inner layers to the smallest even count that keeps the last used inner layer and
    every layer the rules file names. Unused layers still inside it are forbidden with a
    board-wide rule area (no tracks, no pours); through vias still pass.
"""
import re

ZONE_NAME = "kae_unused_layer"
NEAR_COMPLETE = 0.05  # a human layout with at most this share open still shows what layers it needs
_INNER = re.compile(r"In(\d+)\.Cu")


def inner_index(name):
    m = _INNER.fullmatch(name)
    return int(m.group(1)) if m else None


def layers_named(text):
    """Inner layer indices a rules file (or any text) names."""
    return {int(n) for n in _INNER.findall(text or "")}


def eagle_default(use):
    return (use["copper_layers"] == 16 and not use["has_stackup"] and not use["inner_used"]
            and not use["named_inner"])


def plan(use, dru_text=None, unconnected=None):
    """The task's layer restriction from a layer-use report: None when the board keeps its
    declaration, else {declared, used, copper_layers, forbidden, reason}. unconnected may be
    None while it is not yet known (see needs_completeness); then None is returned unless the
    Eagle default decides."""
    n = use["copper_layers"]
    if n <= 2:
        return None
    used = sorted(inner_index(l) for l in use["inner_used"])
    has_copper = use["routing_items"] > 0 or use["copper_zones"] > 0
    if eagle_default(use):
        reason = "eagle-16-default"
    elif has_copper and unconnected is not None and unconnected <= NEAR_COMPLETE * (unconnected + use["routing_items"]):
        reason = "complete-human-copper" if unconnected == 0 else "near-complete-human-copper"
    else:
        return None
    keep_top = max([0, *used, *[i for i in layers_named(dru_text) if i <= n - 2]])
    count = keep_top + 2
    count = min(n, count + count % 2)
    forbidden = [f"In{i}.Cu" for i in range(1, count - 1) if i not in used]
    if count == n and not forbidden:
        return None
    return dict(declared=n, used=len(used) + 2, copper_layers=count, forbidden=forbidden, reason=reason)


def needs_completeness(use):
    """Whether plan() depends on the human copper being complete (else the DRC can be skipped)."""
    n = use["copper_layers"]
    return n > 2 and not eagle_default(use) and len(use["inner_used"]) < n - 2


def _blocks(text, start):
    """Spans of the direct child s-expressions of the expression opening at text[start]."""
    spans, depth, i, opened = [], 0, start, None
    while True:
        c = text[i]
        if c == '"':
            i += 1
            while text[i] != '"':
                i += 2 if text[i] == "\\" else 1
        elif c == "(":
            depth += 1
            if depth == 2:
                opened = i
        elif c == ")":
            depth -= 1
            if depth == 1:
                spans.append((opened, i + 1))
            elif depth == 0:
                return spans, i + 1
        i += 1


_THICK = re.compile(r"\(thickness ([-\d.]+)")
_NAME = re.compile(r'\(layer "([^"]+)"')


def merge_stackup(text, count):
    """Cut a board file's stackup block to `count` copper layers, keeping its total thickness.

    KiCad writes the layer table from the enabled layers but the stackup from its stored list,
    which names the layers removed. The inner layers kept are the first ones; the dielectrics
    between them stay; everything from the last kept inner layer down to B.Cu (dielectrics and
    the copper removed) becomes one dielectric, of the thickest merged one's material, so the
    finished board is as thick as declared. No stackup block: the text is unchanged."""
    a = text.find("(stackup")
    if a < 0:
        return text
    spans, _ = _blocks(text, a)
    rows = [(s, e, _NAME.match(text, s).group(1)) for s, e in spans if text.startswith("(layer", s)]
    names = [r[2] for r in rows]
    if "F.Cu" not in names or "B.Cu" not in names:
        return text
    first, last = names.index("F.Cu"), names.index("B.Cu")
    kept_inner = {f"In{i}.Cu" for i in range(1, count - 1)}
    # the first dielectric after the last kept copper starts the merge
    cut = max([first] + [i for i, n in enumerate(names) if n in kept_inner])
    body = rows[cut + 1:last]  # dielectrics and removed copper
    diel = [r for r in body if r[2].startswith("dielectric")]
    if not diel:
        return text
    def thick(s, e):
        m = _THICK.search(text, s, e)
        return float(m.group(1)) if m else 0.0
    total = sum(sum(float(x) for x in _THICK.findall(text[s:e])) for s, e, _ in body)
    s, e, _ = max(diel, key=lambda r: thick(r[0], r[1]))
    idx = 1 + sum(1 for r in rows[first:cut + 1] if r[2].startswith("dielectric"))
    block = text[s:e]
    sub = block.find("addsublayer")  # merged into one layer: the source's sublayers no longer apply
    if sub >= 0:
        block = block[:sub].rstrip() + "\n\t\t\t)"
    block = _THICK.sub(f"(thickness {round(total, 6):g}", block, count=1)
    block = _NAME.sub(f'(layer "dielectric {idx}"', block, count=1)
    return text[:rows[cut + 1][0]] + block + text[rows[last - 1][1]:]
