# Respin and fab-hold statistics: what actually goes wrong

**TL;DR**
- No rigorous, public root-cause breakdown of PCB respins exists; all quantitative data comes via vendors or surveys.
- Even experienced designers respin routinely: about 2.8–2.9 respins per project (Lifecycle Insights, via vendors), and nearly 60% of designers produce 1–5 respins a year.
- Only "less than 2–20%" of designs reach manufacturing without technical queries (Dana Korf).
- Vendor hold data puts stackup, impedance and fab-note ambiguity at the top, ahead of geometry violations.
- So critics should be ordered: documentation/spec completeness → geometry rules → physics.

## Key facts

Tags: [P] primary read; [S] snippet/secondary; [V] vendor self-report; [I] inference.

### Respin counts and costs

| Source | Figure | Tag |
|---|---|---|
| Lifecycle Insights 2018 (via PCD&F/Mentor) | "the average number of design respins is 2.9 per project, which amounts to approximately 16 days of unplanned development time and more than $82,000 in additional costs"; "58% of all new product design projects incur added costs and time delays"; respins average "8.5 days … $44,000 (USD) per re-spin" ([PCD&F](https://pcdandf.com/pcdesign/index.php/editorial/menu-news/design-news/13176-new-mentor-xpedition-pcb-design-platform-provides-upfront-multi-dimensional-verification), [Electronic Design](https://www.electronicdesign.com/industrial-automation/article/21807687/the-new-shiftleft-multidimensional-pcb-designverification-platform)) | [P, vendor context] |
| Same study via iCD / Altium | "$28,482" per respin and $82,598 per product (iCD); "2.8 board respins per project, each costing a staggering $46,000" (Altium) | [P, vendor context] |
| Aberdeen (Feb 2010) via Siemens | Prototypes were "31% of the overall product cost"; "14.1 physical prototypes" in a non-integrated flow vs 3.8 for best-in-class ([Siemens](https://blogs.sw.siemens.com/electronic-systems-design/2014/02/27/less-is-more-fewer-prototypes-equals-more-savings/)) | [P, vendor context] |
| PCD&F/Circuits Assembly survey (2025-09-30) | "Nearly 60% produce just 1–5 respins a year, and 81% say that hasn't increased in the past 12 to 18 months"; 29% of respondents have >30 years' experience; 83% handle 4–6 layers; 55% HDI; 55% high-speed; 54% BGAs ([Circuits Assembly](https://www.circuitsassembly.com/ca/editorial/menu-features/42616-among-pcb-design-raises-are-up-benefits-are-down-and-deadlines-don-t-budge.html)) | [P] |

### DFM and fab holds

| Source | Figure | Tag |
|---|---|---|
| Dana Korf (2019) | "less than 2–20% of the designs transfer to manufacturing perfectly without any deviation requests or TQs"; "Often, 25–50% of a PCB fabricator's front-end engineering capacity" goes to pre-release DFM reviews (expert estimate) ([I-Connect007](https://design.iconnect007.media/article/120585/dana-on-data-the-dfmdata-transfer-process-is-broken/120588/design)) | [P] |
| AtlasPCB (10,000+ orders, 12 months) | Holds: missing/ambiguous stackup 28%; undefined impedance 22%; drill-to-copper 18%; incomplete fab notes 15%; BGA annular ring 12%. Claims "95% of holds are preventable with a 15-minute pre-submission check" ([AtlasPCB](https://atlaspcb.com/blog/pcb-dfm-check-pre-order-verification)) | [V] |
| dev.to vendor (~200 designs/month) | "Over 60% have at least one DFM issue": trace/space 45%, annular ring 38%, drill-to-copper 32%, mask dam 28%, acid traps 22%, copper balance 20%, outline-to-copper 18%, via aspect ratio 15%, silk over pad 12%, thermal relief 10%, panel tabs 8%, impedance feasibility 8% ([dev.to](https://dev.to/abc_8b09c7009ee0029b85665/pcb-dfm-check-12-point-verification-before-ordering-with-failure-rates-from-200-monthly-reviews-1n9f)). Anonymous, low confidence | [V] |
| PCB Power | ⚠ items are "the most common causes of production holds, rejections, and respins": RS-274X, separate PTH/NPTH, 1:1 scale, consistent units/offsets, Gerber viewed before submission, no chained-drill slots, annular rings, trace/space, copper from edge, slivers, stackup drawing, symmetric copper, mask openings/dams, legend height and polarity marks ([PDF](https://www.pcbpower.com/static/base/images/resources/DFM_Checklist.pdf)) | [P] |

### Qualitative causes

- **Sierra:** "tombstoning, solder bridging, component misalignment, and wrong polarity markings are among the most common challenges faced during assembly" [P].
- **Flux:** "Most PCB design mistakes come from poor component placement, incorrect routing, and weak grounding"; return-path errors are "the source of a disproportionate share of EMI failures" [P].
- **MacroFab:**
  - "Common error is getting SOT-23 transistor and MOSFET package pinouts flipped around".
  - "Some manufacturers draw the mechanical layout of the part from the bottom" [P].
- **VSE:**
  - "it is not unusual for a PCB to be sent to manufacturing without all the parts placed and routed".
  - "Many board designs have been ruined because the schematic still contained preliminary library parts" [P].
- **Adom:** "Never trust a clean ERC": "MCU VCAP pins with no capacitors. Board dead, ERC green"; and a controlled-impedance net matching no class ("classic: USB D+/D−") [P].
- **Failure-log checklists:**
  - azonenberg: "school of hard knocks".
  - colinb: "Every time I make an error, I add an item to the checklist".
  - Tanner: "Update this list as fails occurs".
  - henrikh: "Has the correct/latest files been uploaded? Yes, this does happen" [P].

## Recommendations for our system

- **Critic priority**: documentation and specification completeness (stackup, impedance table, fab notes, output formats) → geometry rules → physics. This catches the cheapest and most common failures first ([critic-stack.md](critic-stack.md)) [I].
- **Footprint/pinout and connector-orientation checks** are high-value pre-fab critics [I].
- **Keep an escaped-error log** that adds checklist items, as practitioners do [I].

## Conflicts and open questions

- Secondary citations of Lifecycle Insights conflict on per-respin cost ($28.5k / $44k / $46k) and count (2.8 vs 2.9). The original report was not found, and every citation is from a vendor marketing context.
- The two vendor DFM rankings disagree, as expected from different populations. Neither publishes methodology.
- "Up to 60% of prototype failures from footprints" appears only in uncited snippets and is not used here [S].

## Sources

- research notes: [expert_workflow_and_checklists.md § Q5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md)

See also: [review-checklist.md](review-checklist.md), [critic-stack.md](critic-stack.md)
