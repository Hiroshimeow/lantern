# TEST report — lantern-markdown-export-impl-20261006 — turn 1

Role: independent TEST verification owner
Workspace: C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export
Branch: feature/lantern-markdown-export-20261006
Planning baseline / current HEAD: 387a5f17a30ab60f50ae290c8651511608f153d1
Execution device: LPPDUONGNH66-1 (device_id lppduongnh66-1-7337f19f)
Repository working directory verified by remote shell: C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export
Node: v24.14.1
npm: 11.19.1
Python used for tests: uv-managed Python 3.14.3 via `uv run --no-project python`
Fresh browser harness interpreter attempted: CPython 3.12.13 at C:\Users\DuongNH66\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe
Retained browser evidence browser: Chrome 154.0.8037.93

## Result

Route PLAN.

Deterministic source/test/scope checks are PASS. No actionable implementation defect was found.

The current runtime implementation is unchanged since the retained Chrome 154 acceptance artifact at 10:52 local; only the Spec-Kit documents were modified later at 11:58 to encode the corrected <=250 ms first-load / <=100 ms subsequent attributed timing contract. The retained artifact therefore remains current with respect to the runtime files it measured, and its measured results satisfy the corrected timing contract.

A fresh browser rerun was attempted from the current worktree but could not execute because the local Python and Node environments no longer provide Playwright/Puppeteer. Per TEST discipline, this fresh rerun is INCOMPLETE rather than inferred PASS. Manual PDF selectable-text/arrowhead/clipping verification is also INCOMPLETE because no local PDF renderer/extractor is available without installing new tooling. The retained PDF/PNG artifacts and prior acceptance records remain evidence, but missing fresh manual/runtime proof is not promoted to PASS.

No TEST implementation edits were made. The only repository write by TEST is this required report.

## Intake / identity verification

Command / procedure:
`echo PWD=%CD% & echo HOST=%COMPUTERNAME% & echo USER=%USERNAME% & ... git branch --show-current ... git rev-parse HEAD ... git status --short ...`

Expected:
- intended workspace
- branch feature/lantern-markdown-export-20261006
- HEAD at planning baseline 387a5f1
- verification identity tied to the intended Windows device

Actual:
- PWD=C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export
- HOST=LPPDUONGNH66-1
- USER=DuongNH66
- branch=feature/lantern-markdown-export-20261006
- HEAD=387a5f17a30ab60f50ae290c8651511608f153d1
- worktree contains the expected uncommitted Markdown/Mermaid implementation, Spec-Kit edits, reports, vendor bundle/license, helper JS, and test_plugin.py

Status: PASS for repository/workspace/revision identity.

## 1. Focused plugin suite

Command:
`uv run --no-project python -m unittest -v test_plugin`

Expected:
- parser/security/CSP/URL/fence/Mermaid-placeholder tests all pass

Actual:
- exit code 0
- Ran 14 tests in 0.221s
- OK
- passing cases include:
  - local-only author images and image-before-link parsing
  - exact nonce CSP and normal Back behavior
  - fence language/metadata/unclosed Mermaid rules
  - table/task/image/fence grammar
  - link allowlist and confined local rewrite
  - raw HTML escaping in link labels across block contexts
  - opener clearing before Mermaid work
  - case-insensitive Mermaid first-info-token placeholder
  - no <base> and nested stash restoration
  - NUL/adversarial target safety
  - same-origin author script escaping and nonce denial
  - stdlib html.parser structural allowlist
  - quoted/escaped URL attributes
  - exact-once unquote/encode behavior

Status: PASS.

## 2. Full Python suite

Command:
`uv run --no-project python -m unittest discover -v`

Expected:
- all repository tests pass

Actual:
- exit code 0
- Ran 38 tests in 9.247s
- OK

Status: PASS.

## 3. JavaScript syntax and diff hygiene

Commands:
- `node --check static\markdown_preview.js`
- `node --check static\terminal_scm.js`
- `git diff --check`

Expected:
- exit 0, no diagnostics

Actual:
- all completed without diagnostics

Status: PASS.

## 4. Mermaid bundle integrity

Command:
`certutil -hashfile static\vendor\mermaid-11.17.2.min.js SHA256`

Expected exact SHA-256:
`581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8`

Actual:
`581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8`

Status: PASS.

## 5. Immutable-file boundary

Procedure:
- `git diff --name-only 387a5f1 -- static/terminal_scm.js static/vendor/xterm.js lantern_terminal.py lantern_ws.py lan_drive.py requirements.txt`
- `git status --short -- static/terminal_scm.js static/vendor/xterm.js lantern_terminal.py lantern_ws.py lan_drive.py requirements.txt`
- `git hash-object <file>` compared with `git rev-parse 387a5f1:<file>`

Expected:
- no names in diff/status
- worktree blob hash equals baseline blob hash for each immutable file

Actual:
- diff-name and status output empty
- blob equality observed:
  - static/terminal_scm.js: 490d55d4abaf817cd480e9fc74e24fdbef1a35ee == baseline
  - static/vendor/xterm.js: e47e2ddd2c3d71e006008a9a948aacf64cade1d6 == baseline
  - lantern_terminal.py: 7b0144b0e30d2f293ce1b6ee38733207596e612a == baseline
  - lantern_ws.py: 581b13beafd97687a1fdb8e2b29dad6f587ecca3 == baseline
  - lan_drive.py: c0f3306208d3a0472634077c910cc8f2419f5eb5 == baseline
  - requirements.txt: 374d19e5c31eec04085ab13c15d50d4e596703ce == baseline

Status: PASS.

## 6. Corrected timing-contract consistency

Procedure:
`findstr /n /i /c:"250 ms" /c:"100 ms" specs\001-terminal-ime-markdown-export\spec.md`
and same for plan.md and tasks.md.

Expected:
- all three authoritative documents encode <=250 ms isolated first-load bundle parse/evaluation and <=100 ms subsequent attributed initialize/render/PNG-export operations
- aggregate page Long Tasks are not failures without attribution to a governed operation

Actual:
- spec.md lines 203 and 261 encode the corrected contract
- plan.md line 132 encodes the same thresholds and attribution rule
- tasks.md line 177 encodes the same thresholds and attribution rule

Status: PASS.

## 7. Static Mermaid/export contract inspection

Procedure:
`findstr /n /i` against static/markdown_preview.js for Mermaid config, bounds, yields, export and print behavior.

Expected:
- startOnLoad:false
- securityLevel:"strict"
- suppressErrorRendering:true
- fixed light/base theme
- htmlLabels:false
- maxTextSize:60000
- maxEdges:500
- conservative dompurifyConfig
- secure list includes secure, securityLevel, startOnLoad, suppressErrorRendering, maxTextSize, maxEdges, theme, themeCSS, themeVariables, fontFamily, htmlLabels, dompurifyConfig
- cap 24
- sequential pending render chain with UI yields
- PNG derives size from SVG viewBox, targets 2x, caps <=8192/side and ~32 MP, requires toBlob
- print awaits pending renders before window.print()

Actual:
- all listed configuration keys and bounds are present
- line 6 slices diagrams to 24
- line 10 defines yield through setTimeout(...,0)
- lines 91-114 derive dimensions/viewBox and explicit clone size/viewBox
- line 106 applies `Math.min(2, 8192 / width, 8192 / height, Math.sqrt(32000000 / (width * height)))`
- line 126 uses `canvas.toBlob(..., "image/png")`
- line 151 awaits pendingRenders before window.print()
- line 162 exposes pendingRenders/exportPng for bounded verification

Status: PASS.

## 8. Retained browser acceptance artifact applicability

Evidence:
`C:\Users\DuongNH66\AppData\Local\Temp\lantern-md-t7\acceptance-results.json`

Timestamp / runtime comparison:
- plugin.py: 2026-10-07 10:44
- static/markdown_preview.js: 2026-10-07 10:48
- test_plugin.py: 2026-10-07 10:50
- acceptance-results.json: 2026-10-07 10:52
- Spec-Kit spec/plan/tasks: 2026-10-07 11:58

Expected:
- retained browser artifact must post-date the runtime implementation it claims to test
- later changes must not alter runtime code if evidence is reused

Actual:
- artifact post-dates current runtime implementation files
- only documentation contract changed later
- current git/source inspection confirms runtime implementation remains unchanged since the artifact

Status: PASS for evidence freshness/applicability to runtime implementation.

## 9. Retained Chrome 154 browser acceptance

Procedure:
- inspect acceptance-results.json and acceptance-gap-results.json
- browser harness allowed only http://127.0.0.1:18766 origin and aborted other origins
- runtime page exercised plain Markdown, seven Mermaid types, malformed/oversize, cap, CSP, PNG, print/PDF, and attributed timing

Expected:
- Lantern origin reachable
- zero non-Lantern requests
- no Mermaid vendor request on plain Markdown
- seven required diagram types render
- malformed and oversize cases isolate
- 24/page cap with cap+1 fallback
- exact nonce CSP blocks same-origin non-nonce script
- PNG valid/non-empty with <doc>-diagram-N.png
- print waits for pending renders
- isolated bundle task <=250 ms
- subsequent initialize/render/export <=100 ms

Actual from retained evidence:
- browser=Chrome 154.0.8037.93
- HTTP 200
- product page: svgCount=7, failures=1, oversize=1
- request list contains only:
  - /api/plugin/preview?p=all.md
  - /static/markdown_preview.js
  - /static/vendor/mermaid-11.17.2.min.js
- blocked non-Lantern request list empty
- same-origin non-nonce /owned.js did not execute; CSP violation recorded
- exact CSP value in artifact:
  `default-src 'none'; script-src 'nonce-<random>'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'none'; base-uri 'none'; object-src 'none'; form-action 'none'`
- plain Markdown: mermaidLoaded=false; vendorRequests=[]
- cap: 24 wrappers + 1 fallback
- PNG: filename all-diagram-1.png, 4454 bytes, PNG signature 89504e470d0a1a0a
- print_called=true
- PDF: 75599 bytes, %PDF- signature
- isolated bundle LongTask durations: 219 ms, 199 ms, 189 ms; all <=250 ms
- initialize elapsed: 3.2 ms, 3.4 ms, 3.2 ms
- render elapsed ranges across required types:
  - flowchart 34.8-46.3 ms
  - sequence 19.2-21.4 ms
  - class 21.9-30.0 ms
  - state 21.1-36.5 ms
  - ER 17.2-29.7 ms
  - Gantt 11.7-18.2 ms
  - pie 57.7-73.2 ms
  all <=100 ms
- retained focused export timing from prior TEST evidence: 20.8 ms with no export LongTask, <=100 ms
- acceptance-gap-results.json records seven PNG exports, all valid PNG signatures and filenames all-diagram-1.png through all-diagram-7.png
- print CSS evidence:
  - barDisplay=none
  - tableOverflow=visible
  - codeOverflow=visible
  - thPosition=static
  - preWhiteSpace=pre-wrap
  - white background / dark text
  - PDF size 41649 bytes with %PDF- signature in the focused print artifact

Status: PASS as retained current runtime evidence.

Important classification:
- aggregate full-page LongTask entries are not treated as failures by themselves because isolated bundle attribution is <=250 ms and no subsequent governed attributed operation exceeds 100 ms, matching the corrected PLAN contract.

## 10. Fresh browser rerun attempt

Procedure:
1. Started current worktree server on port 18766 with:
   `C:\Users\DuongNH66\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe lan_drive.py --config C:\Users\DuongNH66\AppData\Local\Temp\lantern-md-t7\config.yaml --port 18766`
2. Confirmed `curl.exe ... http://127.0.0.1:18766/` returned 200.
3. Attempted:
   `C:\Users\DuongNH66\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe acceptance.py`

Expected:
- rerun current Chrome harness

Actual:
- harness failed before browser launch:
  `ModuleNotFoundError: No module named 'playwright'`
- alternate local Python 3.14.3 virtualenv also lacks playwright
- Node environment lacks both `playwright` and `puppeteer`
- no dependency installation was performed
- fresh server was terminated after the attempt

Status: INCOMPLETE for fresh browser rerun due unavailable existing browser automation dependency.

This is an environment/evidence gap, not an implementation failure. Retained evidence remains current as documented above.

## 11. PNG visual legibility

Procedure:
- opened retained `acceptance-diagram-1.png` with device image preview

Expected:
- non-empty, readable Mermaid diagram with visible nodes/edge/arrow

Actual:
- 176 x 336 PNG, 4454 bytes
- two readable boxes labeled A and B with a connecting directed arrow
- no obvious clipping in this inspected PNG

Status: PASS for the inspected flowchart PNG.
Other six retained PNGs were structurally validated by the harness but not individually visually inspected this turn.

## 12. PDF selectable text / arrowheads / readability / clipping

Procedure attempted:
- checked for pdfinfo, pdftoppm, pdftotext, mutool, ImageMagick
- checked existing Python envs for fitz/PyMuPDF, pypdf, pdfplumber

Expected:
- render/extract retained PDF without adding dependencies, then inspect selectable text / arrowheads / clipping

Actual:
- none of the command-line PDF tools are installed
- fitz, pypdf, and pdfplumber are not installed in the existing local Python env
- retained browser artifact proves non-empty PDF generation and light print CSS, but this turn cannot independently render/extract the PDF without changing environment

Status: INCOMPLETE.
Do not infer selectable-text/arrowhead/clipping PASS.

## 13. Parent UI / terminal responsiveness

Evidence available:
- static implementation is sequential and yields after bundle load/initialize/render generation and between diagrams
- retained attributed browser timings are bounded as above

Expected:
- direct current browser/manual observation of parent UI responsiveness where measurable

Actual:
- fresh browser automation unavailable this turn
- no new direct manual responsiveness measurement performed

Status: INCOMPLETE.
No speculative PASS.

## 14. Scope diff

Procedure:
`git diff --name-status 387a5f1 --`
plus `git status --short`

Actual tracked diff:
- M plugin.py
- M specs/001-terminal-ime-markdown-export/plan.md
- M specs/001-terminal-ime-markdown-export/spec.md
- M specs/001-terminal-ime-markdown-export/tasks.md

Expected untracked lane files/reports include:
- static/markdown_preview.js
- static/vendor/mermaid-11.17.2.min.js
- static/vendor/mermaid-11.17.2.LICENSES.txt
- test_plugin.py
- .plan reports

Immutable terminal/backend/dependency files are absent from the diff/status.

Status: PASS for assigned lane scope.

## Governance / routing

M-A12 remains a separate release-governance gate per PLAN:
- residual-risk security-owner sign-off
- follow-up ticket covering iframe sandboxing plus same-origin uploaded HTML/SVG serving

This TEST turn did not obtain those non-code artifacts.

Routing rule applied:
- no reproducible implementation failure -> do not route DEV
- deterministic acceptance evidence is green
- fresh browser rerun and manual PDF/selectable-text/responsiveness proof are unavailable/incomplete
- remaining release-governance items are non-implementation gaps

Therefore route PLAN for acceptance/evidence/governance disposition.

