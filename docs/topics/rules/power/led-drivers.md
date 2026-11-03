# LED drivers

Scope: LED-driver-specific sense pair, under-IC keep-out, COMP, LED thermal. Not here: hot loops by topology -> [hot-loops.md](hot-loops.md), [buck.md](buck.md), [boost.md](boost.md); sense routing -> [current-sense-kelvin.md](current-sense-kelvin.md).
Keys: LED driver, CSP, CSN, ISP, ISN, R_FLT, C_FLT, COMP, TPS922050, TPS92201, LED-01, LED-02, MCPCB

## LED driver rules
TI TPS922050/1 (65 V, 1–2 A buck LED driver; [datasheet](https://www.ti.com/lit/ds/symlink/tps922050.pdf)) [P]:
- Large GND plane (electrical + thermal); VIN and GND traces as wide as possible; thermal vias to other layers.
- Input caps as close as possible to VIN/GND; VCC cap at VCC; compensation cap as close as possible to COMP.
- SW trace as short as possible (spikes, EMI). "Do not allow switching current to flow under the device."
- CSN and CSP parallel, short, away from the HV switching trace and the ground shield; filter at the IC.
- Design example: R_FLT 100 Ω at CSN (noise injection, robustness); optional C_FLT 1 nF / 50 V X7R across CSP–CSN.

TPS92201 (synchronous buck LED driver) [S]: input/output caps and inductor as close as possible to the IC.

| ID | Rule (RPA §12) [I] | Check | Sev |
|---|---|---|---|
| LED-01 | Hot-loop rules by topology (buck: CIN–IC–diode; boost: SW–D–COUT) | As PWR-01 / PWR-09 | S1 |
| LED-02 | CSP/CSN (or ISP/ISN) parallel pair, R_FLT/C_FLT at the IC pins; ≤ a few mm unshielded near SW [I] | Diff-pair rule; coupling scan vs SW | S1 |
| LED-03 | No SW/hot-loop copper under the IC on adjacent layers | Zone/track intersection with IC courtyard on L1/L2 | S2 |
| LED-04 | LED copper and thermal path sized for LED power (1 − η)·P into the [thermal screener](../thermal.md); LEDs away from sense/reference parts (V_f and lifetime are temperature-dependent) | Thermal estimator | S2 |

## Open questions
- Not covered: MCPCB/LED-board thermal guidance; HV boost/SEPIC LED-driver layout notes.

## Sources
- [rules_power_rf_analog_dfm.md § 12](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md)
