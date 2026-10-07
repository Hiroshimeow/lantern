# DEV turn 1 report

## Scope/state
Workspace: C:\Users\DuongNH66\Desktop\git\lantern-wt-markdown-export
Branch: feature/lantern-markdown-export-20261006
Baseline/HEAD at intake: 387a5f17a30ab60f50ae290c8651511608f153d1

Implemented Markdown/Mermaid/export lane only. No terminal persistence, IME, or UniKey work. No immutable file changed.

Changed files:
- plugin.py
- test_plugin.py (new)
- static/markdown_preview.js (new)
- static/vendor/mermaid-11.17.2.min.js (new)
- static/vendor/mermaid-11.17.2.LICENSES.txt (new)

No commit, merge, or push was performed because acceptance/TEST is not green.

## Implementation
T3/T4:
- Added adversarial parser/security tests for raw HTML escaping, C0/NUL handling, URL normalization/allowlist, local/root/fragment/http/https/mailto links, local-only author images, no base tag, nested stash restoration, fence closing rules, Mermaid placeholder recognition, stdlib html.parser structural allowlist, exact nonce CSP, same-origin nonce-less author script containment, and normal Back button.
- Added bounded stdlib-only Markdown parser: headings, paragraphs, inline code/emphasis, lists/task lists, blockquotes, HR, tables, images, fenced code, Mermaid placeholders.
- Raw author HTML is escaped.
- Local links are confined under root and normalized once; unsafe/protocol-relative/data/javascript/vbscript/traversal targets do not become active links.
- Remote/data/protocol-relative author images are not emitted as img elements.
- Mermaid uses first info token case-insensitively; unclosed Mermaid fences remain escaped code.
- Mermaid placeholders are capped at 24/page.
- Added exact per-page nonce CSP as in-document meta policy while preserving immutable lan_drive.py:
  default-src 'none'; script-src 'nonce-{random}'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'none'; base-uri 'none'; object-src 'none'; form-action 'none'
- Replaced javascript:history.back() with a normal button handled by nonce-authorized local JS.

T6:
- Vendored exact T5-reviewed Mermaid 11.17.2 standalone bundle.
- SHA256 verified: 581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8
- Added retained Mermaid license plus T5 bundled third-party package/license inventory and retained pin/advisory notes.
- markdown_preview.js sets window.opener=null before Mermaid work.
- Mermaid is lazy-loaded only when Mermaid placeholders exist; plain Markdown does not request/parse the bundle.
- Strict config includes startOnLoad:false, securityLevel:strict, suppressErrorRendering:true, fixed light/base theme, htmlLabels:false, maxTextSize:60000, maxEdges:500, conservative dompurifyConfig, and secure list containing secure, securityLevel, startOnLoad, suppressErrorRendering, maxTextSize, maxEdges, theme, themeCSS, themeVariables, fontFamily, htmlLabels, dompurifyConfig.
- Sequential render with event-loop yields; malformed/oversize blocks isolated.
- Browser testing exposed a real layout bug from rendering into display:none. Fixed by using an off-screen measurable 1200px container; all seven required Mermaid types then rendered.
- PNG export derives dimensions from SVG/viewBox, sets explicit SVG dimensions, white canvas, targets 2x while capping <=8192 px/side and ~32 MP, requires non-null toBlob, and names <doc>-diagram-N.png.
- Print waits for pending renders; print CSS hides UI chrome and removes overflow/sticky-header clipping rules.

## Checks actually run
Baseline before changes:
- Python full suite: 24/24 PASS.

T3 RED:
- Focused tests initially failed for the missing parser/security/CSP/helper behavior as intended. Test-fixture escaping artifacts were corrected before implementation evidence was relied on.

T3/T4 gate before Mermaid vendoring:
- python -m unittest -v test_plugin: 13/13 PASS.
- python -m unittest -v: 37/37 PASS.
Vendoring occurred only after this gate was green.

Final automated checks:
- node --check static/markdown_preview.js: PASS.
- node --check static/terminal_scm.js: PASS (read-only; unchanged).
- focused Python: 13/13 PASS.
- full Python: 37/37 PASS.
- git diff --check: PASS.
- Mermaid SHA256: exact reviewed hash PASS.
- Immutable scope check:
  git diff --exit-code 387a5f1 -- static/terminal_scm.js static/vendor/xterm.js lantern_terminal.py lantern_ws.py lan_drive.py requirements.txt
  => exit code 0. All immutable files are byte-identical to baseline.
- Worktree status at final check:
  M plugin.py
  ?? static/markdown_preview.js
  ?? static/vendor/mermaid-11.17.2.LICENSES.txt
  ?? static/vendor/mermaid-11.17.2.min.js
  ?? test_plugin.py

## T7 browser evidence
Runtime: local Lantern origin 127.0.0.1:18765 with Node Playwright Chromium. Non-Lantern requests were configured to abort.

Observed:
- 9 Mermaid blocks total: 7 valid types -> 7 SVGs; 1 malformed -> isolated render failure; 1 >60000 chars -> isolated oversize message.
- Seven required types rendered: flowchart, sequence, class, state, ER, Gantt, pie.
- 25-diagram fixture produced 24 Mermaid placeholders.
- Plain Markdown page: window.mermaid false and zero Mermaid-bundle requests.
- Normal render requests before deliberate CSP probe were preview HTML, local markdown_preview.js, and local Mermaid bundle only.
- No non-Lantern request observed; blocked-nonlocal list empty.
- Runtime CSP exactly matched required policy with fresh nonce.
- Deliberate same-origin /owned.js insertion without nonce: CSP violation observed as expected; window.__OWNED_SCRIPT_RAN remained false. No unexpected console errors in the final render run.
- PNG export: all-diagram-1.png, 4538 bytes; toBlob succeeded.
- Headless PDF output: 75353 bytes.
- Print media evidence: toolbar display none; pre white-space pre-wrap. Table/code computed values were NOT_MEASURED in that fixture because it contained no table/code block; explicit CSS rules are present and syntax-checked.

## INCOMPLETE / blocker
Binding responsiveness acceptance is INCOMPLETE:
- PerformanceObserver maximum Mermaid-related main-thread long task: 268 ms.
- Long tasks >100 ms: [268].
- This violates the explicit <=100 ms contract. tasks.md states any >100 ms Mermaid-caused main-thread task keeps acceptance INCOMPLETE and triggers re-review of loading/pin/caps. DEV did not waive or reinterpret the requirement.

Also INCOMPLETE/NOT_MEASURED:
- Binding parent-terminal responsiveness under worst-case Mermaid fixture was not independently proven; preview already violates the 100 ms threshold.
- Manual PDF proof of selectable text, visible arrowheads, visual readability, and no material clipping was not independently established.
- Manual PNG visual-legibility proof was not independently established (non-empty PNG/toBlob are proven).
- Security-owner residual-risk sign-off was unavailable.
- Required follow-up ticket for iframe sandboxing + same-origin uploaded HTML/SVG serving was not created because no issue-tracker integration/authorized ticket destination was available; no speculative PASS recorded.

## Required decision / route
Current implementation cannot satisfy T7 because the measured 268 ms long task exceeds the binding threshold. The authoritative plan explicitly calls for re-review of Mermaid loading/pin/caps in this condition. This requires PLAN re-review before DEV broadens loading architecture or changes the reviewed bundle strategy.

No commit or push should occur while this blocker remains.
