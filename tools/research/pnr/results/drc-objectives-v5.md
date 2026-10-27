boards in common: 33

| run | legal | clean | completion | len (all-complete boards) | vias | mean t (s) | top DRC errors |
|---|---|---|---|---|---|---|---|
| pnr-seq-v5 | 0.788 | 0.545 | 0.863 | 3117 (20 boards) | 40 | 58 | {'silk_overlap': 28, 'solder_mask_bridge': 9, 'shorting_items': 6} |
| pnr-seq_phys-v5 | 0.788 | 0.545 | 0.863 | 3152 (20 boards) | 44 | 108 | {'silk_overlap': 28, 'solder_mask_bridge': 9, 'shorting_items': 6} |
| pnr-anneal-v5 | 0.848 | 0.576 | 0.874 | 2852 (20 boards) | 22 | 115 | {'silk_overlap': 39, 'solder_mask_bridge': 8, 'shorting_items': 5} |
| pnr-anneal_phys-v5 | 0.818 | 0.576 | 0.876 | 2952 (20 boards) | 24 | 191 | {'silk_overlap': 37, 'starved_thermal': 6, 'solder_mask_bridge': 4} |
| pnr-combo_lv-v5 | 0.818 | 0.545 | 0.900 | 2695 (20 boards) | 16 | 436 | {'starved_thermal': 6, 'solder_mask_bridge': 4, 'items_not_allowed': 4} |
| pnr-combo-v5 | 0.848 | 0.636 | 0.897 | 2687 (20 boards) | 16 | 116 | {'items_not_allowed': 10, 'copper_edge_clearance': 4, 'clearance': 3} |
| pnr-tension-v5 | 0.788 | 0.545 | 0.871 | 3008 (20 boards) | 35 | 151 | {'silk_overlap': 28, 'solder_mask_bridge': 8, 'shorting_items': 5} |
| pnr-bloat-v5 | 0.727 | 0.576 | 0.748 | 2951 (20 boards) | 36 | 353 | {'silk_overlap': 5, 'solder_mask_bridge': 3, 'silk_over_copper': 2} |
| pnr-seq_margin-v5 | 0.727 | 0.545 | 0.860 | 3703 (20 boards) | 43 | 41 | {'solder_mask_bridge': 8, 'starved_thermal': 4, 'shorting_items': 4} |

per board: clean/completion/length
| board | split | pnr-seq-v5 | pnr-seq_phys-v5 | pnr-anneal-v5 | pnr-anneal_phys-v5 | pnr-combo_lv-v5 | pnr-combo-v5 | pnr-tension-v5 | pnr-bloat-v5 | pnr-seq_margin-v5 |
|---|---|---|---|---|---|---|---|---|---|---|
| azonenberg-dumptruck-emmc-interposer | B | - 0.00 0 | - 0.00 0 | - 0.00 0 | - 0.00 0 | - 0.00 0 | - 0.00 0 | - 0.00 0 | - 0.00 0 | - 0.00 0 |
| d3a-c-biscuit-crowbar | A | C 1.00 59 | C 1.00 59 | C 1.00 49 | C 1.00 44 | C 1.00 64 | C 1.00 62 | C 1.00 55 | C 1.00 41 | - 0.89 47 |
| d3a-kitspace-12v5a-breakout | A | C 1.00 104 | C 1.00 104 | C 1.00 99 | C 1.00 101 | C 1.00 100 | C 1.00 99 | C 1.00 103 | C 1.00 104 | C 1.00 130 |
| d3a-kitspace-gas-sensor | B | C 1.00 195 | C 1.00 195 | C 1.00 158 | C 1.00 160 | C 1.00 134 | C 1.00 135 | C 1.00 188 | C 1.00 159 | C 1.00 198 |
| d3a-kitspace-hum-temp-sensor | A | C 1.00 57 | C 1.00 57 | C 1.00 50 | C 1.00 43 | C 1.00 40 | C 1.00 40 | C 1.00 51 | C 1.00 57 | C 1.00 63 |
| d3a-kitspace-temp-breakout | A | C 1.00 127 | C 1.00 127 | C 1.00 119 | C 1.00 124 | C 1.00 110 | C 1.00 110 | C 1.00 125 | C 1.00 126 | C 1.00 155 |
| d3a-marlin-neopixel-bridge-attiny85-marn | A | C 1.00 95 | C 1.00 95 | C 1.00 74 | C 1.00 88 | C 1.00 75 | C 1.00 74 | C 1.00 91 | C 1.00 87 | C 1.00 141 |
| d3a-pcb-serie-led-strip | A | L 1.00 42 | L 1.00 42 | C 1.00 7 | C 1.00 6 | C 1.00 6 | C 1.00 6 | C 1.00 18 | C 1.00 4 | C 1.00 50 |
| d3a-starsynctrackers-reset-switch | A | C 1.00 30 | C 1.00 30 | C 1.00 18 | C 1.00 20 | C 1.00 19 | C 1.00 19 | C 1.00 30 | C 1.00 30 | C 1.00 45 |
| d3a-z2amiller-sensorboard-programmer | A | C 1.00 64 | C 1.00 64 | C 1.00 55 | C 1.00 58 | C 1.00 49 | C 1.00 49 | C 1.00 57 | C 1.00 62 | C 1.00 96 |
| kicad-demos-ecc83-ecc83-pp-v2 | B | L 1.00 145 | L 1.00 145 | L 1.00 135 | L 1.00 143 | L 1.00 114 | L 1.00 113 | L 1.00 141 | L 1.00 131 | L 1.00 158 |
| olimex-dcdc-50-5-12-dcdc-50-5-12-rev-a1 | B | L 1.00 159 | L 1.00 190 | C 1.00 149 | C 1.00 180 | C 1.00 153 | C 1.00 153 | C 1.00 138 | L 1.00 159 | C 1.00 249 |
| pcbcorpus-0rax-esphome-xiao-base-pcb | B | C 1.00 190 | C 1.00 190 | L 1.00 177 | L 1.00 179 | L 1.00 175 | C 1.00 175 | L 1.00 187 | C 1.00 187 | C 1.00 191 |
| pcbcorpus-0xjmux-esp-prog-adapter-esppro | B | C 1.00 214 | C 1.00 214 | C 1.00 210 | C 1.00 211 | C 1.00 204 | C 1.00 207 | C 1.00 214 | C 1.00 215 | C 1.00 221 |
| pcbcorpus-badjeff-paw3222-pcb-paw3222 | A | - 0.47 9 | - 0.47 9 | - 0.47 4 | - 0.47 5 | - 1.00 50 | C 1.00 45 | - 0.47 5 | - 0.47 9 | - 0.47 9 |
| pcbcorpus-badjeff-paw3395-pcb-paw3395 | B | - 0.68 92 | - 0.68 92 | L 0.78 86 | - 0.72 99 | L 0.85 123 | L 0.82 91 | - 0.70 103 | - 0.00 0 | - 0.62 47 |
| pcbcorpus-badjeff-pmw3610-pcb-pmw3610-pc | B | L 0.74 145 | L 0.77 147 | L 0.80 143 | L 0.86 190 | - 0.83 195 | - 0.86 199 | L 0.80 146 | - 0.00 0 | - 0.74 132 |
| pcbcorpus-blueokiris-ch552g-dev-board-ch | B | C 1.00 138 | C 1.00 138 | C 1.00 131 | C 1.00 135 | C 1.00 120 | C 1.00 129 | C 1.00 135 | C 1.00 132 | C 1.00 170 |
| pcbcorpus-electron271-tuxkeychain-expans | B | L 0.64 62 | L 0.64 62 | L 0.56 73 | L 0.64 101 | L 0.64 129 | L 0.64 115 | L 0.64 86 | L 0.64 62 | L 0.64 66 |
| pcbcorpus-funkeleinhorn-sc14cvmdect-devb | B | L 0.95 161 | L 0.95 161 | L 0.98 157 | L 0.95 157 | L 0.98 124 | L 0.98 127 | L 0.95 151 | L 0.95 161 | L 0.91 228 |
| pcbcorpus-fyralabs-suzyqboard-suzyqboard | B | - 0.00 0 | - 0.00 0 | - 0.00 0 | - 0.00 0 | - 0.00 0 | - 0.00 0 | - 0.00 0 | - 0.00 0 | - 0.00 0 |
| pcbcorpus-jangtrinh-design-os-3d-blender | B | C 1.00 229 | C 1.00 229 | C 1.00 223 | C 1.00 223 | C 1.00 194 | C 1.00 196 | C 1.00 222 | C 1.00 224 | C 1.00 293 |
| pcbcorpus-justbuchanan-oasis-ledboard | A | - 0.55 4 | - 0.55 4 | - 0.64 6 | - 0.64 10 | - 0.64 5 | - 0.55 11 | - 0.64 5 | - 0.64 9 | - 0.64 16 |
| pcbcorpus-jvedder-biploar-power-supply-k | B | C 1.00 454 | C 1.00 454 | C 1.00 436 | C 1.00 433 | C 1.00 434 | C 1.00 434 | C 1.00 442 | C 1.00 445 | C 1.00 455 |
| pcbcorpus-kabukiflux-pi-rgb-cable-sync-m | A | - 0.75 9 | - 0.75 9 | - 0.75 6 | - 0.75 7 | - 0.88 5 | - 0.88 5 | - 0.75 8 | - 0.00 0 | - 0.75 16 |
| pcbcorpus-lambdakb-trackball-lt6c-lt6c-p | B | L 1.00 263 | L 1.00 268 | L 1.00 239 | L 1.00 261 | L 1.00 222 | L 1.00 209 | L 1.00 259 | L 1.00 242 | L 1.00 291 |
| pcbcorpus-pcbcupid-kicad-7-series-schema | A | C 1.00 112 | C 1.00 112 | C 1.00 104 | C 1.00 99 | C 1.00 90 | C 1.00 90 | C 1.00 112 | C 1.00 112 | C 1.00 121 |
| pcbcorpus-pcbcupid-kicad-7-series-schema | A | C 1.00 106 | C 1.00 106 | C 1.00 97 | C 1.00 100 | C 1.00 85 | C 1.00 85 | C 1.00 104 | C 1.00 103 | C 1.00 131 |
| pcbcorpus-siderakb-pmw3360-pcb-pmw3360-p | B | C 1.00 211 | C 1.00 211 | C 1.00 196 | C 1.00 193 | C 1.00 189 | C 1.00 194 | L 1.00 205 | - 0.00 0 | C 1.00 218 |
| pcbcorpus-siderakb-pmw3610-pcb-pmw3610-p | B | - 0.71 127 | - 0.71 127 | L 0.90 194 | L 0.90 230 | L 0.90 222 | L 0.90 205 | - 0.79 170 | - 0.00 0 | - 0.71 152 |
| pcbcorpus-tcsullivan-noisecard-noisecard | B | L 0.98 264 | L 0.97 257 | L 0.98 259 | L 0.98 287 | L 1.00 356 | L 1.00 323 | L 1.00 272 | C 1.00 280 | L 1.00 347 |
| pcbcorpus-tmarhguy-alu-gate-xnor-2in | B | C 1.00 194 | C 1.00 194 | C 1.00 184 | C 1.00 194 | L 1.00 180 | C 1.00 177 | C 1.00 192 | C 1.00 184 | C 1.00 275 |
| pcbcorpus-tmarhguy-alu-gate-xor-2in | B | C 1.00 200 | C 1.00 200 | C 1.00 188 | C 1.00 194 | C 1.00 191 | C 1.00 187 | C 1.00 198 | C 1.00 186 | L 1.00 270 |
