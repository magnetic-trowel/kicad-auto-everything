# Designs

Boards designed from plain-language briefs with [`kaesynth`](../synth/README.md). Each folder has:

- `DESIGN.md`: requirements, hazards, trade study, calculations, parts, placement;
- `CONNECTIONS.md`: net tables and naming rules;
- `parts.py` and `design.py`: the circuit as code;
- `REVIEW.md`: an independent review and the designer's response;
- `out/`: the generated KiCad 10 project, `intent.yaml`, BOM and `report.md`.

Rebuild with `kaesynth build designs/<slug>/design.py -v`.

| Design | What it is | Parts | Status |
|---|---|---|---|
| [rpi-mains-relay](rpi-mains-relay/) | Pi Zero 2 W switching six 120 V receptacles, one polycarbonate enclosure, on-board listed 5 V supply, hardware heartbeat watchdog | ~70 | Reviewed twice. Checks pass; 4 blocking questions |
| [liion-balancer](liion-balancer/) | 13–16S home-pack active balancer: per-cell isolated flyback (LT8584) + ADBMS1818, hardware trips, BMS-OK enable | 448 | Reviewed. Checks pass; 6 blocking questions |
| [leadacid-balancer](leadacid-balancer/) | 2–4 × 12 V lead-acid switched-capacitor balancer, MCU-free, fail-safe alarm | ~390 | Reviewed. Checks pass; 4 blocking questions |
| [prius-solar-mppt](prius-solar-mppt/) | 2017 Prius Prime roof solar: 2 × 32 C60 strings, MPPT, isolated step-up into the Li-ion pack, car on or off, current-capped, 3-layer OV; main and battery-end boards | 485 | Reviewed. Checks pass; 6 blocking questions |

"Checks pass" means 0 errors, a clean KiCad ERC, and a schematic netlist identical to
the design. Remaining check findings are waived with written reasons in `out/report.md`.

**None of these is ready to fabricate.** Each has blocking questions that only the owner, an
installer or a certification body can answer, listed in its `out/report.md`. They have not
been simulated in SPICE, built, or reviewed by a licensed engineer.
