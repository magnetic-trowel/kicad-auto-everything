# LED drivers

**TL;DR**
- **LED drivers are switching converters.** Apply the buck, boost or buck-boost hot-loop rules by topology.
- **The LED-current sense pair (CSP/CSN)** runs parallel and short, away from SW and the ground shield, with the RC filter at the IC.
- **"Do not allow switching current to flow under the device."**
- **COMP cap at its pin.** Large GND copper and thermal vias for the IC. Separately, keep LED heat away from the sense and reference parts.

## Key facts
- **TI TPS922050/1** (65 V, 1–2 A buck LED driver; [datasheet](https://www.ti.com/lit/ds/symlink/tps922050.pdf)) [P]:
  - Large GND plane for electrical and thermal performance; VIN and GND traces as wide as possible; thermal vias to other layers.
  - Input caps as close as possible to VIN/GND; VCC cap at VCC.
  - SW trace as short as possible (spikes, EMI).
  - "Do not allow switching current to flow under the device."
  - CSN and CSP in parallel, short, away from the high-voltage switching trace and the ground shield.
  - Compensation cap as close as possible to COMP.
  - Design example: R_FLT 100 Ω at CSN (noise injection, robustness); optional C_FLT 1 nF / 50 V X7R across CSP–CSN.
- **TPS92201** (synchronous buck LED driver) [S]: input/output caps and the inductor as close as possible to the IC.

**Rules** (RPA §12) [I]:

| ID | Rule | Check | Sev |
|---|---|---|---|
| LED-01 | Hot-loop rules by topology (buck: CIN–IC–diode; boost: SW–D–COUT) | As PWR-01 / PWR-09 | S1 |
| LED-02 | CSP/CSN parallel pair, filter at the IC pins; ≤ a few mm unshielded near SW [I] | Diff-pair rule; coupling scan vs SW | S1 |
| LED-03 | No SW/hot-loop copper under the IC on adjacent layers | Zone/track intersection with the IC courtyard on L1/L2 | S2 |
| LED-04 | LED copper and thermal path sized for LED power; LEDs away from sense/reference parts | Thermal estimator | S2 |

## Recommendations for our system
- **Detector:** CSP/CSN (or ISP/ISN) pins → sense pair + R_FLT/C_FLT at the IC; SW keep-out under the IC.
- **LED power** (1 − η)·P goes into the [thermal screener](../thermal.md). LED V_f and lifetime are temperature-dependent.

## Conflicts and open questions
- **Not covered:** MCPCB/LED-board thermal guidance and high-voltage boost/SEPIC LED-driver layout notes.

## Sources
- research notes: [rules_power_rf_analog_dfm.md § 12](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md)

See also: [buck.md](buck.md), [boost.md](boost.md), [current-sense-kelvin.md](current-sense-kelvin.md)
