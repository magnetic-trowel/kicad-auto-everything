# KiCad, GPL and the surrounding ecosystem: licensing facts that still matter under GPL-3.0-or-later

Scope: KiCad's own licensing (core, plugins, PCM, libraries, outputs) and GPL/AGPL facts that bind a GPL-3.0-or-later project. Not here: per-component verdicts -> [reuse-matrix](reuse-matrix.md); contribution and release mechanics -> [compliance-checklist](compliance-checklist.md).
Keys: plugin licensing, IPC plugin, kipy relicense, PCM rules, KiCad-libraries-exception, GPLOutput, porting is modification, Freerouting provenance, AGPL §13, MereAggregation, USCO Part 2

Why GPL lets us link KiCad (SWIG, PNS, DRC), vendor IPC `.proto` files and port KiCad or Freerouting code: [LICENSING.md](../../../LICENSING.md#why-gpl-for-code); the permissive-core survey's constraints no longer bind ([reuse-matrix](reuse-matrix.md#summary-rules)). Still binding: AGPL §13 (Konnect), library-exception limits, CC BY-SA demos, Freerouting provenance (only for upstreaming to KiCad) [I].

## KiCad plugins and PCM

- Seth Hillbrand (2025-07-17): "If you distribute a plug-in that links to the KiCad Python library, your code must be GPL or compatible licensed. If you use the new IPC plugin framework, it does not need to be" [P] ([forum](https://forum.kicad.info/t/process-to-integrate-a-tool-plugin-in-kicad-distribution/62462/5)). Both paths are open to us.
- kipy relicensed to MIT after a user worried GPL kipy would "taint" plugins. Jon Evans: "we're discussing just relicensing this repo"; on the generated stubs' GPL headers: "The intent is that this library is MIT, but upstream KiCad is GPL … I'll look into it" (issue #134, open) [P] ([issue #9](https://gitlab.com/kicad/code/kicad-python/-/work_items/9); [#134](https://gitlab.com/kicad/code/kicad-python/-/work_items/134)). Version, date and stub counts -> [../kicad/kipy-and-swig-bindings.md](../kicad/kipy-and-swig-bindings.md).
- PCM rules: "Packages containing code (Python plugins) must be licensed under an open-source license compatible with the GNU GPL"; data packages "should be licensed under a Creative Commons or similar license"; closed packages may use third-party repositories [P] ([add-ons](https://dev-docs.kicad.org/en/addons/)). GPL-3.0-or-later qualifies: publish IPC-runtime plugins to the PCM under it [I].

## KiCad core licensing

- Core: "GPLv3 or later"; third-party code inside includes Apache-2.0, Boost, ISC, MIT, BSD, MPL-2.0 (Eigen), LGPL, CC0; "A combined works as is will be governed under the terms of the GPLv3 (or later)" [P] ([LICENSE.README](https://gitlab.com/kicad/code/kicad/-/blob/master/LICENSE.README)).
- "source files must be copyrighted and not be released into the public domain" [P] ([code style](https://dev-docs.kicad.org/en/rules-guidelines/code-style/)).
- Docs: GPL-3.0+ or CC-BY-3.0+. Demos: CC BY-SA 4.0.

## KiCad libraries and outputs

- Library exception: "the copyright holder waives article 3 of the license with respect to these designs and any generated files". Redistributing "the KiCad libraries, or parts thereof … as a collection" is **not** covered (SPDX `KiCad-libraries-exception`, list 3.29.0) [P] ([kicad.org](https://www.kicad.org/libraries/license/)).
- Jon Evans: "If someone extracts the footprint from your design, that extracted footprint is no longer part of your design and the original KiCad license should apply"; same for 3D models; "A project-local library that you distribute next to your design is not [part of your design]" [P]. Consequence: keep extracted footprint and 3D-model corpora separate ([data-rulepacks-weights](data-rulepacks-weights.md#tiers-for-board-bundles)) [I].
- Outputs: "copyright law does not give you any say in the use of the output people make from their data using your program … if my program is used to develop hardware designs" [P] ([GPLOutput](https://www.gnu.org/licenses/gpl-faq.html#GPLOutput)). Users' boards and `kicad-cli` outputs are outside KiCad's GPL, so our GPL licence does not touch users' designs [P].

## Porting and Freerouting provenance

- "translation of a work is considered a kind of modification … the translated program must be covered by the same versions" ([TranslateCode](https://www.gnu.org/licenses/gpl-faq.html#TranslateCode)) [P].
- Seth Hillbrand (2026-10-19), to a project that AI-ported KiCad's stroke font: "you don't have the right to re-license the work of others … you must license your code under the GPL". On a Freerouting rewrite: "your use of Freerouting as the base remains the controlling license regardless of how much code you replaced" [P] ([forum](https://forum.kicad.info/t/freerouting-modernization/69547/42)). Under GPL-3.0-or-later this is satisfied automatically if notices are kept [I].
- Freerouting provenance (unverified hearsay): "legal status is unclear. There was accusations about stealing intellectual property … a derivative or a port … will not be accepted as a part of KiCad" (a community member, not official); linked 2014 EEVblog threads mention Zuken; sources not fetched [S]. Before upstreaming anything Freerouting-derived to KiCad, resolve provenance with the KiCad maintainers [I].

## AGPL, network use and separate programs

- AGPL covers programs "expressly designed to accept user requests and send responses over a network". GPLv3 §13 lets GPLv3 combine with AGPLv3, but "the special requirements of the GNU Affero General Public License, section 13 … will apply" to the combination. Konnect's README goes further ("anything you build on or around Konnect … be open-sourced"), exceeding the FSF's aggregation analysis [P] ([AGPLGPL](https://www.gnu.org/licenses/gpl-faq.html#AGPLGPL)). Keep Konnect reference-only so our HTTP MCP server never inherits AGPL §13 ([reuse-matrix](reuse-matrix.md#routers-placers-agents-mcp-servers)) [I].
- Plain GPL has no network clause: a company running a modified version on a website "does not have to release the modified sources" ([UnreleasedMods](https://www.gnu.org/licenses/gpl-faq.html#UnreleasedMods)); internal use needs no source release [P].
- Separate programs: FSF calls pipes, sockets and command-line arguments communication "normally used between two separate programs", unless semantics are "intimate enough"; wrappers do not launder GPL code ([MereAggregation](https://www.gnu.org/licenses/gpl-faq.html#MereAggregation), [GPLWrapper](https://www.gnu.org/licenses/gpl-faq.html#GPLWrapper)) [P]. Now relevant mainly to permissive downstream users of our formats.

## Patents and copyrightability

- GPL-3.0 §11 grants only contributors' "essential patent claims", plus §10 retaliation; no licence protects against third-party patents ([patents-watchlist](../landscape/patents-watchlist.md)) [P].
- Earlier repo had one human commit plus AI-authored notes. AI-only material may lack copyright: "prompts alone do not provide sufficient human control" (USCO Part 2, Jan 2025). A licence file is still useful [P].

## Open questions

- No enforcement history or ruling on protobuf-over-socket clients of GPL programs; matters only to downstream permissive users.
- KiCad trademark policy for "kicad" in our project name not researched.
- KiCad developers mailing list not searched.

## Sources

- research notes: [licensing.md § 2, § 4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md); [patents_and_industry.md § 8 (GPL boundary precedent)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/patents_and_industry.md)
- primary: [GPL-3.0 text](https://www.gnu.org/licenses/gpl-3.0.txt), [IPC API docs](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/), [USCO Part 2](https://www.copyright.gov/ai/Copyright-and-Artificial-Intelligence-Part-2-Copyrightability-Report.pdf)
- related: [LICENSING.md](../../../LICENSING.md)
