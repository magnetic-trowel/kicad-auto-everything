# KiCad, GPL and the surrounding ecosystem: licensing facts that still matter under GPL-3.0-or-later

**TL;DR**
- **We can link KiCad (SWIG, PNS, DRC), vendor IPC `.proto` files and port KiCad or Freerouting code.** The GPL-combo constraints in the earlier survey no longer bind us. Keep copyright notices [I].
- **Still relevant:**
  - AGPL §13 network obligations if we copy Konnect code.
  - The KiCad library exception only covers designs, not redistributed library collections.
  - CC BY-SA demos.
  - Freerouting's murky 2014 provenance, which matters if we upstream to KiCad [P].
- **The KiCad PCM requires GPL-compatible code licenses.** GPL-3.0-or-later qualifies [P].
- **Users' boards and `kicad-cli` outputs are not covered by KiCad's GPL**, so our GPL license doesn't touch users' designs [P].
- **The AI-assisted porting rule narrows.** Porting GPL code is fine. Feeding AGPL, unlicensed, non-commercial or proprietary source into prompts for core code is not [I].

## Key facts
- **KiCad lead developers on plugins.** Seth Hillbrand: "If you distribute a plug-in that links to the KiCad Python library, your code must be GPL or compatible licensed. If you use the new IPC plugin framework, it does not need to be" (2025-07-17) [P] ([forum](https://forum.kicad.info/t/process-to-integrate-a-tool-plugin-in-kicad-distribution/62462/5)). Both paths are open to us.
- **kipy was relicensed to MIT** after a user worried that GPL kipy would "taint" plugins. Jon Evans: "we're discussing just relicensing this repo". On the generated stubs' GPL headers: "The intent is that this library is MIT, but upstream KiCad is GPL … I'll look into it" (issue #134, open) [P] ([issue #9](https://gitlab.com/kicad/code/kicad-python/-/work_items/9); [#134](https://gitlab.com/kicad/code/kicad-python/-/work_items/134)).
- **PCM rules:** "Packages containing code (Python plugins) must be licensed under an open-source license compatible with the GNU GPL". Data packages "should be licensed under a Creative Commons or similar license". Closed packages may use third-party repositories [P] ([add-ons](https://dev-docs.kicad.org/en/addons/)).
- **KiCad licensing:**
  - The core is "GPLv3 or later". Third-party code inside includes Apache-2.0, Boost, ISC, MIT, BSD, MPL-2.0 (Eigen), LGPL and CC0. "A combined works as is will be governed under the terms of the GPLv3 (or later)" [P] ([LICENSE.README](https://gitlab.com/kicad/code/kicad/-/blob/master/LICENSE.README)).
  - KiCad requires source files to carry copyright: "source files must be copyrighted and not be released into the public domain" [P] ([code style](https://dev-docs.kicad.org/en/rules-guidelines/code-style/)).
  - Docs: GPL-3.0+ or CC-BY-3.0+. Demos: CC BY-SA 4.0.
- **Library exception:** "the copyright holder waives article 3 of the license with respect to these designs and any generated files". Redistributing "the KiCad libraries, or parts thereof … as a collection" is **not** covered (SPDX `KiCad-libraries-exception`, list 3.29.0) [P] ([kicad.org](https://www.kicad.org/libraries/license/)).
  - Jon Evans: "If someone extracts the footprint from your design, that extracted footprint is no longer part of your design and the original KiCad license should apply"; the same applies to 3D models. "A project-local library that you distribute next to your design is not [part of your design]" [P].
- **Outputs:** "copyright law does not give you any say in the use of the output people make from their data using your program … if my program is used to develop hardware designs" [P] ([GPLOutput](https://www.gnu.org/licenses/gpl-faq.html#GPLOutput)).
- **Porting is modification:** "translation of a work is considered a kind of modification … the translated program must be covered by the same versions" ([TranslateCode](https://www.gnu.org/licenses/gpl-faq.html#TranslateCode)).
  - Seth Hillbrand (2026-10-19), to a project that AI-ported KiCad's stroke font: "you don't have the right to re-license the work of others … you must license your code under the GPL".
  - On a Freerouting rewrite: "your use of Freerouting as the base remains the controlling license regardless of how much code you replaced" [P] ([forum](https://forum.kicad.info/t/freerouting-modernization/69547/42)).
  - Under GPL-3.0-or-later this is satisfied automatically, provided notices are kept [I].
- **Freerouting provenance (unverified hearsay):** "legal status is unclear. There was accusations about stealing intellectual property … a derivative or a port … will not be accepted as a part of KiCad" (a community member, not official). Linked 2014 EEVblog threads mention Zuken; the sources were not fetched [S].
- **AGPL:** covers programs "expressly designed to accept user requests and send responses over a network". GPLv3 §13 lets GPLv3 combine with AGPLv3, but "the special requirements of the GNU Affero General Public License, section 13 … will apply" to the combination. Konnect's README goes further ("anything you build on or around Konnect … be open-sourced"), which exceeds the FSF's aggregation analysis [P] ([AGPLGPL](https://www.gnu.org/licenses/gpl-faq.html#AGPLGPL)).
- **Plain GPL has no network clause:** a company running a modified version on a website "does not have to release the modified sources" ([UnreleasedMods](https://www.gnu.org/licenses/gpl-faq.html#UnreleasedMods)). Internal use needs no source release [P].
- **Separate programs:** the FSF calls pipes, sockets and command-line arguments communication "normally used between two separate programs", unless the semantics are "intimate enough". Wrappers do not launder GPL code ([MereAggregation](https://www.gnu.org/licenses/gpl-faq.html#MereAggregation), [GPLWrapper](https://www.gnu.org/licenses/gpl-faq.html#GPLWrapper)) [P]. Now relevant mainly to permissive downstream users of our formats.
- **Patents:** GPL-3.0 §11 grants only contributors' "essential patent claims", plus §10 retaliation. No license protects against third-party patents ([patents-watchlist.md](../landscape/patents-watchlist.md)) [P].
- **Repo history:** the earlier repo had one human commit plus AI-authored notes. AI-only material may lack copyright: "prompts alone do not provide sufficient human control" (USCO Part 2, Jan 2025). A license file is still useful [P].

## Recommendations for our system
- **Publish IPC-runtime plugins to the PCM under GPL-3.0-or-later.** That satisfies the GPL-compatibility rule [I].
- **Keep Konnect reference-only** so our HTTP MCP server never inherits AGPL §13 [I].
- **Before upstreaming anything Freerouting-derived to KiCad, resolve provenance with the KiCad maintainers** [I].
- **Contribution rule:** no AGPL, unlicensed, non-commercial or proprietary source in prompts or diffs for core code. Disclose AI use. Ported GPL code keeps its headers ([compliance-checklist.md](compliance-checklist.md)) [I].
- **Keep extracted footprint and 3D-model corpora separate**, under CC-BY-SA-4.0 WITH the exception ([data-rulepacks-weights.md](data-rulepacks-weights.md)) [I].

## Conflicts and open questions
- No enforcement history or court ruling on protobuf-over-socket clients of GPL programs; it matters only to downstream permissive users.
- The KiCad trademark policy for "kicad" in our project name was not researched.
- The KiCad developers mailing list was not searched.

## Sources
- research notes:
  - [licensing.md § 2, § 4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md)
  - [patents_and_industry.md § 8 (GPL boundary precedent)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/patents_and_industry.md)
- primary: [GPL-3.0 text](https://www.gnu.org/licenses/gpl-3.0.txt), [IPC API docs](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/), [USCO Part 2](https://www.copyright.gov/ai/Copyright-and-Artificial-Intelligence-Part-2-Copyrightability-Report.pdf)

See also: [reuse-matrix.md](reuse-matrix.md), [compliance-checklist.md](compliance-checklist.md), [../../../LICENSING.md](../../../LICENSING.md)
