<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Rigid array macros: LED matrices and series buses (2026-11-09)

Scope: J47: keeping lattices the netlist implies. Not here: radial arrays and daisy chains (the netlist does not state their shape).
Keys: array macros, LED matrix, series resistor bus, kae.place.arrays, array_macros, gecko5education, nekoink, J47

**Status:** implementation pushed; `array-macro-ab` waits for the detector's scan. No results yet.

## Mechanism
`kae.place.arrays` reads the netlist only. A matrix is a set of identical parts with a pair of pad numbers whose nets form a product (every row net meets every column net once, signal nets only, at least 80% of rows x columns filled); a bus is at least 6 identical two-pin parts each joining the same two parts by nets touching nothing else. Each group becomes a block with three candidate gaps (0.5, 0.25, 1.0 mm), and the placer pins it on a legal spot near the quadratic seed before anything else moves, as it does edge connectors. No later stage can break it.

## What the first check shows
On gecko5education the detector finds the 12 x 10 RGB matrix and one 8-resistor bus, and the placement comes out a perfect lattice (0 rms deviation, one rotation). A soft macro does not survive: with the annealer's macro moves only, the seed legalizer scattered the matrix (rms 11.8 mm). Pinning is therefore the design: the array cannot be nudged during annealing, so its position is whatever the seed picks.

## Assembly and manufacture
A straight lattice is what pick-and-place and AOI expect: short head paths, one orientation, regular solder joints. A scattered matrix costs placement time and inspection effort. Rigid rows also leave predictable routing channels.

## Open questions
Whether the seed's position is good enough without annealing the block; results when the experiment finishes.
