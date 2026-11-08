<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# PCB cooling: sources

Parts: [overview and decision rules](pcb-cooling.md) · [thermal vias, pours, convection](pcb-cooling-vias-pours.md) · [placement, heat sinks, trace heating, algorithms](pcb-cooling-placement-algorithms.md) · [sources](pcb-cooling-sources.md). Numbers in brackets cite the [sources](pcb-cooling-sources.md); [calc] values come from [pcb_cooling_calc.py](../../../tools/research/physics/pcb_cooling_calc.py).

## Sources

1. TI SNVA419C, "AN-2020 Thermal Design By Insight, Not Hindsight" (2013). https://www.ti.com/lit/an/snva419c/snva419c.pdf
2. TI SNVA183B, "AN-1520 A Guide to Board Layout for Best Thermal Resistance for Exposed Packages" (2013). https://www.ti.com/lit/an/snva183b/snva183b.pdf
3. TI SPRA953D, "Semiconductor and IC Package Thermal Metrics" (2024). https://www.ti.com/lit/an/spra953d/spra953d.pdf
4. TI SLMA002H, "PowerPAD Thermally Enhanced Package" (2018). https://www.ti.com/lit/an/slma002h/slma002h.pdf
5. TI SLUA271B, "QFN and SON PCB Attachment". https://www.ti.com/lit/an/slua271b/slua271b.pdf
6. Nexperia AN90003, "LFPAK MOSFET thermal design guide" Rev 3.1 (2021). https://assets.nexperia.com/documents/application-note/AN90003.pdf
7. R. Bornoff (Mentor/Siemens), "A little goes a long way, but a lot doesn't go much further" (2012). https://blogs.sw.siemens.com/simulating-the-real-world/2012/05/03/a-little-goes-a-long-way-but-a-lot-doesnt-go-much-further/
8. Y. Shen, H. Wang, F. Blaabjerg, H. Zhao, T. Long, "Thermal Modeling and Design Optimization of PCB Vias and Pads", IEEE TPEL, DOI 10.1109/TPEL.2019.2915029. https://tenglong.eng.cam.ac.uk/files/thermalmodelinganddesignoptimizationofpcbviasandpads.pdf
9. Cree LED CLD-AP37, "Optimizing PCB Thermal Performance for Cree XLamp LEDs". https://downloads.cree-led.com/files/da/x/XLamp-PCB-Thermal.pdf
10. J. Olson, "Determining Circuit Board Current Carrying Capability" (IPC-2152 tutorial). https://blog.mbedded.ninja/pdfs/JackOlson-HowTo2152.pdf
11. onsemi AND9596/D, "A Quick PCB Thermal Calculation for Power Electronic Devices with Exposed Pad Packages". https://www.onsemi.com/pub/Collateral/AND9596-D.PDF
12. Electronics Cooling, "Thermal Vias – A Packaging Engineer's Best Friend" (2004). https://www.electronics-cooling.com/2004/08/thermal-vias-a-packaging-engineers-best-friend/
13. Univ. of Waterloo ECE309 Tutorial 10, natural convection from a PCB. https://www.mhtlab.uwaterloo.ca/courses/ece309/tutorials/pdffiles/Spring2016/tutorial10_s16.pdf
14. Electronics Cooling, "Adjusting Temperatures for High Altitude" (1999). https://www.electronics-cooling.com/1999/09/adjusting-temperatures-for-high-altitude/
15. ROHM, "Heat dissipation effect of thermal via in exposed pad type package" (65AN044E) and two-resistor model notes. https://fscdn.rohm.com/en/products/databook/applinote/ic/common/heat_dissipation_effect_of_thermal_via_in_exposed_pad_type_package_an-e.pdf
16. Analog Devices AN-772, LFCSP design and manufacturing guide, and ADL5605/ADL5243/AD7265 datasheet layout sections. https://www.analog.com/en/resources/app-notes/an-772.html
17. C. Hillman / Circuits Assembly, BTC voiding and IPC-7093 discussion; IPC-7093A TOC. https://www.circuitsassembly.com/ca/features-itemid-fix/415-test-and-inspection/31866-test-and-inspection-bernard-1909.html ; https://www.ipc.org/TOC/IPC-7093A-toc.pdf
18. Cadence, "IPC-2152 vs. IPC-2221". https://resources.system-analysis.cadence.com/blog/ipc-2152-vs-ipc-2221-which-to-use-for-pcb-thermal-analysis
19. bestpcbs / allpcb thermal via guides (vias as conduits; simplified array math). https://www.bestpcbs.com/blog/?p=32709
20. EDN, "Simple equations simplify convection cooling" / two-sided vs 4-layer copper. https://www.electronicdesign.com/content/article/21186455/simple-equations-simplify-convection-cooling
21. Thermally constrained placement of ICs/MCMs with precomputed thermal matrices plus SA (abstract). https://manuscript.isc.ac/Inventory/49/1643185.htm
22. T. Suwa, H. Hadim, "Multidisciplinary placement optimization of heat generating electronic components on a PCB", J. Electronic Packaging (2007). https://researchwith.stevens.edu/en/publications/multidisciplinary-placement-optimization-of-heat-generating-elect/
23. Electronics Cooling, "Thermal conductivity of printed wiring boards" (1995). https://www.electronics-cooling.com/1995/10/thermal-conductivity-of-printed-wiring-boards/
24. JLCPCB / AtlasPCB thermal relief guides. https://jlcpcb.com/blog/FAQ%20about%20Thermal%20Relief%20Pad
25. Volupe, "Empirical correlations for convective heat transfer coefficients". https://volupe.com/?p=14363
26. Boise State, "Natural convection and passive heat rejection from two heat sources…" and KMUTT stacked PCBA study. https://experts.boisestate.edu/en/publications/natural-convection-and-passive-heat-rejection-from-two-heat-sourc/ ; https://kirim.kmutt.ac.th/converis/portal/detail/Publication/601475628?lang=en_GB
27. Bar-Shalom, MIT thesis on altitude effects on electronics cooling. https://dspace.mit.edu/bitstream/handle/1721.1/39011/20404614-MIT.pdf?sequence=2
28. Würth Elektronik SN008 (electrolytic lifetime); ROHM TechWeb electrolytic life example. https://www.we-online.com/components/media/o173043v410%20SN008a%20EN.pdf ; https://techweb.rohm.com/?p=3177
29. Microchip AN1258, "Op Amp Precision Design: PCB Layout Techniques". https://developerhelp.microchip.com/xwiki/bin/view/products/amplifiers-linear/operational-amplifier-ics/precision-design/
30. TI SNVA951, LM61460-Q1 family thermal layout note. https://ti.com/document-viewer/lit/html/SNVA951/GUID-4A0FB708-6544-4F61-933F-CB170EFEA793
31. Vishay AN827 (TO-220 mounting), Bergquist SP600 data, diyaudio bench test. https://dtsheet.com/doc/1509629/package-application-note-an827 ; https://www.diyaudio.com/community/threads/thermal-pad-tests.420355/latest
32. poealex/kicad_thermal_sim (KiCad 2.5D thermal plugin); KiCad forum on thermal analysis. https://awesome.ecosyste.ms/projects/github.com%2Fpoealex%2Fkicad_thermal_sim ; https://forum.kicad.info/t/thermal-analysis-using-kicad/36805
33. Univ. of Waterloo MHTL spreading-resistance papers (Yovanovich, Muzychka, Culham). https://uwaterloo.ca/microelectronics-heat-transfer-laboratory/sites/default/files/uploads/documents/spreading_resistance_3-mhtl03-1.pdf
34. KAIST study on SA/tabu/GA placement for reliability; CLPSO PCB thermal placement (ICAE 2017). https://dspace.kaist.ac.kr/handle/10203/69819?mode=full ; https://content.iospress.com/articles/integrated-computer-aided-engineering/ica536
34b. TI SZZA017A, "Thermal Characteristics of Linear and Logic Packages Using JEDEC PCB Designs". https://www.ti.com/lit/an/szza017a/szza017a.pdf
35. B. Goplen, S. Sapatnekar, "Thermal via placement in 3D ICs", ISPD 2005. https://typeset.io/pdf/thermal-via-placement-in-3d-ics-3dkbm90kj8.pdf
36. J. Cong, Y. Zhang, "Thermal via planning for 3-D ICs", ICCAD 2005 (and follow-ups). https://aminer.org/pub/53e9a396b7602d9702ca57dc/thermal-via-planning-for-d-ics
37. Ansys Icepak/Sherlock ECAD workflow; Cadence Celsius overview. https://ansys.com/resource-center/webinar/ansys-icepak-sherlock-temperature-cycling ; https://ema-eda.com/product-overview/celsius-thermal-solver
38. TI LMH6321 datasheet, thermal section (diminishing returns at ~1 in² of 1 oz copper). https://ti.com/document-viewer/LMH6321/datasheet/GUID-CBBA3168-A5E9-47F5-B771-6EC5B2ADEA65

Calculation script for the [calc] numbers: [pcb_cooling_calc.py](../../../tools/research/physics/pcb_cooling_calc.py)
(via resistance table, annular-fin floors, h_rad, effective in-plane k).
