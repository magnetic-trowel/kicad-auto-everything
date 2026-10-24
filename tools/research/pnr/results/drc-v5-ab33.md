boards in common: 33

| run | legal | clean | completion | len (all-complete boards) | vias | mean t (s) | top DRC errors |
|---|---|---|---|---|---|---|---|
| pnr-seq-v5 | 0.788 | 0.545 | 0.863 | 3327 (21 boards) | 54 | 58 | {'silk_overlap': 28, 'solder_mask_bridge': 9, 'shorting_items': 6} |
| pnr-grow-v5 | 0.788 | 0.545 | 0.861 | 3274 (21 boards) | 35 | 74 | {'items_not_allowed': 10, 'solder_mask_bridge': 9, 'silk_overlap': 4} |
| pnr-anneal-v5 | 0.848 | 0.576 | 0.874 | 3048 (21 boards) | 32 | 115 | {'silk_overlap': 39, 'solder_mask_bridge': 8, 'shorting_items': 5} |
| pnr-anneal_phys-v5 | 0.818 | 0.576 | 0.876 | 3145 (21 boards) | 32 | 191 | {'silk_overlap': 37, 'starved_thermal': 6, 'solder_mask_bridge': 4} |
| pnr-repair-v5 | 0.818 | 0.545 | 0.873 | 3054 (21 boards) | 33 | 118 | {'solder_mask_bridge': 8, 'silk_overlap': 6, 'copper_edge_clearance': 5} |
| pnr-grow_phys-v5 | 0.758 | 0.515 | 0.850 | 3253 (21 boards) | 49 | 24 | {'solder_mask_bridge': 9, 'silk_overlap': 6, 'shorting_items': 6} |
| pnr-negotiate-v5 | 0.818 | 0.545 | 0.897 | 3708 (21 boards) | 54 | 118 | {'solder_mask_bridge': 7, 'starved_thermal': 6, 'shorting_items': 5} |
| pnr-combo-v5 | 0.848 | 0.636 | 0.897 | 2881 (21 boards) | 21 | 116 | {'items_not_allowed': 10, 'copper_edge_clearance': 4, 'clearance': 3} |

per board: clean/completion/length
| board | split | pnr-seq-v5 | pnr-grow-v5 | pnr-anneal-v5 | pnr-anneal_phys-v5 | pnr-repair-v5 | pnr-grow_phys-v5 | pnr-negotiate-v5 | pnr-combo-v5 |
|---|---|---|---|---|---|---|---|---|---|
| azonenberg-dumptruck-emmc-interposer | B | - 0.00 0 | - 0.00 0 | - 0.00 0 | - 0.00 0 | - 0.00 0 | - 0.00 0 | - 0.00 0 | - 0.00 0 |
| d3a-c-biscuit-crowbar | A | C 1.00 59 | - 0.89 36 | C 1.00 49 | C 1.00 44 | C 1.00 45 | - 0.89 34 | C 1.00 41 | C 1.00 62 |
| d3a-kitspace-12v5a-breakout | A | C 1.00 104 | C 1.00 101 | C 1.00 99 | C 1.00 101 | C 1.00 101 | C 1.00 107 | C 1.00 112 | C 1.00 99 |
| d3a-kitspace-gas-sensor | B | C 1.00 195 | C 1.00 172 | C 1.00 158 | C 1.00 160 | C 1.00 130 | C 1.00 159 | C 1.00 181 | C 1.00 135 |
| d3a-kitspace-hum-temp-sensor | A | C 1.00 57 | C 1.00 42 | C 1.00 50 | C 1.00 43 | C 1.00 42 | C 1.00 40 | C 1.00 47 | C 1.00 40 |
| d3a-kitspace-temp-breakout | A | C 1.00 127 | C 1.00 117 | C 1.00 119 | C 1.00 124 | C 1.00 107 | C 1.00 119 | C 1.00 121 | C 1.00 110 |
| d3a-marlin-neopixel-bridge-attiny85-marn | A | C 1.00 95 | C 1.00 89 | C 1.00 74 | C 1.00 88 | C 1.00 86 | C 1.00 93 | C 1.00 90 | C 1.00 74 |
| d3a-pcb-serie-led-strip | A | L 1.00 42 | L 1.00 42 | C 1.00 7 | C 1.00 6 | C 1.00 36 | L 1.00 40 | C 1.00 25 | C 1.00 6 |
| d3a-starsynctrackers-reset-switch | A | C 1.00 30 | C 1.00 21 | C 1.00 18 | C 1.00 20 | C 1.00 27 | C 1.00 20 | C 1.00 20 | C 1.00 19 |
| d3a-z2amiller-sensorboard-programmer | A | C 1.00 64 | C 1.00 63 | C 1.00 55 | C 1.00 58 | C 1.00 58 | C 1.00 53 | C 1.00 59 | C 1.00 49 |
| kicad-demos-ecc83-ecc83-pp-v2 | B | L 1.00 145 | L 1.00 126 | L 1.00 135 | L 1.00 143 | L 1.00 118 | L 1.00 131 | L 1.00 129 | L 1.00 113 |
| olimex-dcdc-50-5-12-dcdc-50-5-12-rev-a1 | B | L 1.00 159 | C 1.00 220 | C 1.00 149 | C 1.00 180 | C 1.00 152 | L 1.00 210 | L 1.00 183 | C 1.00 153 |
| pcbcorpus-0rax-esphome-xiao-base-pcb | B | C 1.00 190 | C 1.00 188 | L 1.00 177 | L 1.00 179 | C 1.00 187 | C 1.00 196 | L 1.00 483 | C 1.00 175 |
| pcbcorpus-0xjmux-esp-prog-adapter-esppro | B | C 1.00 214 | C 1.00 213 | C 1.00 210 | C 1.00 211 | C 1.00 214 | C 1.00 213 | C 1.00 219 | C 1.00 207 |
| pcbcorpus-badjeff-paw3222-pcb-paw3222 | A | - 0.47 9 | - 0.47 6 | - 0.47 4 | - 0.47 5 | - 0.47 4 | - 0.47 8 | - 1.00 37 | C 1.00 45 |
| pcbcorpus-badjeff-paw3395-pcb-paw3395 | B | - 0.68 92 | L 0.75 90 | L 0.78 86 | - 0.72 99 | L 0.78 116 | - 0.50 60 | - 0.80 144 | L 0.82 91 |
| pcbcorpus-badjeff-pmw3610-pcb-pmw3610-pc | B | L 0.74 145 | L 0.77 172 | L 0.80 143 | L 0.86 190 | L 0.86 179 | L 0.66 139 | L 0.86 186 | - 0.86 199 |
| pcbcorpus-blueokiris-ch552g-dev-board-ch | B | C 1.00 138 | C 1.00 140 | C 1.00 131 | C 1.00 135 | C 1.00 132 | C 1.00 142 | C 1.00 143 | C 1.00 129 |
| pcbcorpus-electron271-tuxkeychain-expans | B | L 0.64 62 | L 0.42 84 | L 0.56 73 | L 0.64 101 | L 0.50 183 | L 0.47 128 | L 0.64 223 | L 0.64 115 |
| pcbcorpus-funkeleinhorn-sc14cvmdect-devb | B | L 0.95 161 | L 0.95 179 | L 0.98 157 | L 0.95 157 | L 0.98 154 | L 0.98 185 | C 1.00 174 | L 0.98 127 |
| pcbcorpus-fyralabs-suzyqboard-suzyqboard | B | - 0.00 0 | - 0.00 0 | - 0.00 0 | - 0.00 0 | - 0.00 0 | - 0.00 0 | - 0.00 0 | - 0.00 0 |
| pcbcorpus-jangtrinh-design-os-3d-blender | B | C 1.00 229 | C 1.00 238 | C 1.00 223 | C 1.00 223 | C 1.00 230 | C 1.00 249 | C 1.00 239 | C 1.00 196 |
| pcbcorpus-justbuchanan-oasis-ledboard | A | - 0.55 4 | - 0.64 18 | - 0.64 6 | - 0.64 10 | - 0.64 5 | - 0.55 4 | - 0.55 11 | - 0.55 11 |
| pcbcorpus-jvedder-biploar-power-supply-k | B | C 1.00 454 | C 1.00 438 | C 1.00 436 | C 1.00 433 | C 1.00 436 | C 1.00 440 | C 1.00 446 | C 1.00 434 |
| pcbcorpus-kabukiflux-pi-rgb-cable-sync-m | A | - 0.75 9 | - 0.88 9 | - 0.75 6 | - 0.75 7 | - 0.75 8 | - 0.88 9 | C 1.00 17 | - 0.88 5 |
| pcbcorpus-lambdakb-trackball-lt6c-lt6c-p | B | L 1.00 263 | L 1.00 265 | L 1.00 239 | L 1.00 261 | L 1.00 254 | L 1.00 233 | L 1.00 281 | L 1.00 209 |
| pcbcorpus-pcbcupid-kicad-7-series-schema | A | C 1.00 112 | C 1.00 97 | C 1.00 104 | C 1.00 99 | C 1.00 78 | C 1.00 97 | C 1.00 106 | C 1.00 90 |
| pcbcorpus-pcbcupid-kicad-7-series-schema | A | C 1.00 106 | C 1.00 94 | C 1.00 97 | C 1.00 100 | C 1.00 90 | C 1.00 94 | C 1.00 96 | C 1.00 85 |
| pcbcorpus-siderakb-pmw3360-pcb-pmw3360-p | B | C 1.00 211 | C 1.00 206 | C 1.00 196 | C 1.00 193 | C 1.00 199 | C 1.00 213 | C 1.00 217 | C 1.00 194 |
| pcbcorpus-siderakb-pmw3610-pcb-pmw3610-p | B | - 0.71 127 | - 0.71 143 | L 0.90 194 | L 0.90 230 | - 0.85 179 | - 0.71 145 | - 0.75 334 | L 0.90 205 |
| pcbcorpus-tcsullivan-noisecard-noisecard | B | L 0.98 264 | L 0.94 326 | L 0.98 259 | L 0.98 287 | L 1.00 271 | L 0.97 268 | L 1.00 298 | L 1.00 323 |
| pcbcorpus-tmarhguy-alu-gate-xnor-2in | B | C 1.00 194 | C 1.00 179 | C 1.00 184 | C 1.00 194 | L 1.00 190 | C 1.00 182 | L 1.00 238 | C 1.00 177 |
| pcbcorpus-tmarhguy-alu-gate-xor-2in | B | C 1.00 200 | C 1.00 223 | C 1.00 188 | C 1.00 194 | L 1.00 189 | C 1.00 223 | L 1.00 274 | C 1.00 187 |
