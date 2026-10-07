[Reading 182 lines from start (total: 182 lines, 0 remaining)]

[Reading 200 lines from start (total: 288 lines, 88 remaining)]

# Terminal IME + Markdown Preview/Export Increment

Status: Opus UniKey re-review incorporated. T0-A PASS. T0-B PASS only as falsification of the retired Process/229 design. The Win32 SendInput automation probe cannot exercise UniKey and is non-evidence for T0-C; the physical gate remains NOT_MEASURED and the original UniKey registry settings were restored. Terminal product code is blocked on T0-C; the Markdown/Mermaid track is independent and may proceed after this document review.
Product-code baseline: `main` at `5ba0ed9c0a29332a219531787d4ee9f6b6c92c45`. Implementation-diff baseline: planning-only commit `387a5f17a30ab60f50ae290c8651511608f153d1`, which adds Spec-Kit docs but no product-code change.

## Outcome

Deliver one bounded Lantern increment that:

1. diagnoses the reported Windows UniKey/Telex terminal corruption; changes Lantern terminal code only if T0-C physically reproduces a wrong net result and classifies it as DOM -> payload (class ii), without regressing CJK IME, touch keyboards, shortcuts, paste, AltGr/dead keys, emoji, latency, or reconnect behavior;
2. improves the existing lightweight Markdown preview;
3. renders fenced Mermaid diagrams fully offline;
4. exports each rendered diagram to PNG;
5. exposes whole-document **Print / Save as PDF** through Chromium.

## Verified ownership

| Area | Owner / boundary |
| --- | --- |
| Browser terminal input | `static/terminal_scm.js`; baseline Option A: xterm owns all keydown paths, including keyCode 231 synthetic characters and IME-injected Backspace; Lantern adds no new input interception |
| Vendored xterm internals | `static/vendor/xterm.js`; read-only unless a separately reviewed fallback is triggered |
| Terminal transport / PTY | `lantern_ws.py`, `lantern_terminal.py`; preserve |
| Process lifecycle | `lan_drive.py`; preserve; no process-restart terminal persistence |
| Markdown parser/page | `plugin.py` |
| Markdown browser helper | new `static/markdown_preview.js` |
| Mermaid runtime | new versioned local asset under `static/vendor` after dependency gate |

Repository facts checked for this revision: `render_preview_page` is shared by plugin preview kinds and currently hard-codes a `javascript:history.back()` link; `serve_file` serves uploaded files same-origin; the current terminal fake in `test_terminal_ui.py` uses `textarea={}` and does not yet capture the custom key handler or `onData` callback; current `static/terminal_scm.js` returns `true` from its custom handler for unclaimed ordinary keydowns and forwards `term.onData` as `terminal_input` without data transformation. `lantern_ws.py` passes `terminal_input.data` directly to `TerminalManager.input`, and `lantern_terminal.py` writes that string directly to the PTY.

Authoritative evidence records T0-A PASS against vendored xterm 6.0.0 and T0-B PASS only as falsification of the old design: the accepted UniKey `as` trace contains keyCode 231 synthetic characters plus two Backspaces, no Process/229, composition, `beforeinput`, or `input` events, and WebSocket payloads `['a','·','\u007f','\u007f','á']` net to `á` on the captured screen. Exact `start -> stsar` remains NOT_MEASURED and must not be claimed reproduced.

## Scope

### PRESERVE

- Preserve `static/vendor/xterm.js`, `lantern_ws.py`, `lantern_terminal.py`, `lan_drive.py`, WebSocket framing, and PTY behavior unless the classification-specific review below explicitly reopens one of those boundaries.
- No terminal persistence across Lantern process restart.
- No new keydown interception and no `term.onData` suppression, compaction, filtering, buffering, debounce, or delay.
- Existing copy/paste, mobile extra keys, focus, selection, resize, replay, refresh/reconnect behavior.
- Raw Markdown HTML remains escaped.
- Existing configured-root confinement.
- No new Python runtime dependency.
- No Mermaid CDN or other runtime network dependency.

### FIX / ADD

- Physical T0-C reproduction/classification evidence and baseline terminal guard tests; no terminal fix is designed yet.
- Safe Markdown URL normalization/rewrite, bounded grammar additions, nonce CSP.
- Local Mermaid 11.17.2 after dependency/advisory/license gate.
- Per-diagram PNG and Chromium Print / Save as PDF.

## Hard terminal evidence gates

Terminal and Markdown/Mermaid are separate tracks. Terminal evidence order is **T0-A PASS -> T0-B PASS-as-falsification -> T0-C physical reproduction/classification -> conditional review/code only if justified**. Markdown/Mermaid T3-T7 does not wait for T0-C.

### T0-A — xterm internals: PASS

The authoritative evidence identifies the vendored asset as upstream `@xterm/xterm@6.0.0` after CRLF normalization and proves the custom key-handler ordering, key state lifecycle, `_inputEvent` condition, and the vendored 229 textarea-diff path. This is source evidence only. `static/vendor/xterm.js` remains unchanged.

### T0-B — UniKey rewrite trace: PASS only as falsification

The accepted Windows trace proves the prior Process/229 / one-claim / `beforeinput`-`input` design does not match the observed UniKey path. For `as`, UniKey emitted a keyCode 231 placeholder, two Backspace pairs, and a keyCode 231 final character; there were no Process/229, composition, `beforeinput`, or `input` events. Lantern/xterm forwarded the baseline byte sequence in order, and the captured net screen result was correct.

Therefore T0-B is **not** proof of the reported defect and is **not** a terminal implementation gate. The old 229 claim design, its one-claim consumer rules, `compositionSendPending`, special `deleteContentBackward` handling, and Process-key recovery are retired.

Any runnable copy of the trace used by tests must represent DEL in raw JSON as the escape `\u007f`; replacement characters are invalid evidence. The authoritative `.plan` evidence remains read-only during this revision.

### T0-C — physical real-keyboard reproduction gate

A wrong net result from a physical keyboard is mandatory before any terminal product code. The target is exact `start -> stsar` or another clearly wrong net terminal result.

For each candidate reproduction, capture these four channels simultaneously:

1. hook-level/raw-key log or keyboard-viewer evidence showing what UniKey injected or swallowed;
2. ordered DOM key/composition/input events;
3. WebSocket terminal payloads;
4. PTY echo / terminal screen.

Record the same run's shell identity, code page (`chcp`) and `LANG` where applicable, Chromium version, UniKey version, typing method/code page, spell-check, auto-restore, "always use clipboard for Unicode", typing speed, and any setting that may control the placeholder behavior.

Use the same physical typing for three contrasts: native Windows Terminal/conhost running the same shell, a plain Chromium `<textarea>`, and Lantern. Re-run the known `as -> á` shape with auto-restore off and with clipboard-for-Unicode on. Re-classify the prior `sta` stress observation using hook/raw-key evidence; do not label it harness loss without that evidence.

Attempt at least 50 physical `start` entries across the recorded settings/speed matrix. If none produces a wrong net result, close the terminal item **NOT_REPRODUCED** with no terminal product-code change.

Classify any reproduced defect at the earliest divergence:

- **(i) before DOM:** UniKey/Windows/input-source behavior. Produce workaround/documentation as appropriate; no Lantern code.
- **(ii) DOM -> payload:** xterm/Lantern browser boundary. Stop for a new focused design review before tests that demand changed behavior or any product code.
- **(iii) payload -> screen:** shell/ConPTY/PTY/code-page behavior. Stop for a separate backend/PTY review before reopening the preserved backend scope.

CJK/Korean/dead-key/Ctrl+C/Ctrl+V/touch traces are required as a full regression matrix only if T0-C ultimately leads to terminal code changes.

## Terminal baseline contract

Baseline Option A is the terminal contract unless a T0-C class-(ii) focused review replaces it:

- xterm owns **all keydown paths**, including keyCode 231 synthetic characters and IME-injected Backspace;
- the existing custom key handler in `static/terminal_scm.js` stays unchanged;
- `term.onData` is forwarded unchanged and in order through Lantern;
- Lantern adds no UniKey-specific input state;
- do not suppress, compact, reconcile, buffer, debounce, batch, reorder, or delay keyCode 231 characters or IME-injected Backspace;
- do not change `static/vendor/xterm.js`, `lantern_ws.py`, or `lantern_terminal.py` without the classification-specific re-review that explicitly opens that boundary.

T1 protects this baseline with guard tests only. T2 remains blocked unless T0-C is class (ii) and a new focused review defines a safe changed contract.

## Markdown URL and parser contract

Raw HTML remains escaped. Literal NUL is removed before parsing.

URL normalization/classification order:

1. remove ASCII tab/newline parser whitespace;
2. trim leading/trailing C0 controls and spaces;
3. `html.unescape` once so `&#106;avascript:` classifies as `javascript:`;
4. treat backslash as slash;
5. split path/query/fragment;
6. URL-unquote path exactly once;
7. reject encoded `%2e%2e` / `%2f` residue case-insensitively before normalization;
8. reject protocol-relative `//host`;
9. classify scheme / local path.

Allowed links: confined relative, root-relative, fragment, http, https, mailto.
Allowed author images: confined relative or root-relative only.
Rejected targets render escaped plain text/alt, never `href="#"`.

For relative local paths:
- normalize with POSIX semantics against the Markdown parent;
- the parent is derived from `Path.resolve()`, so symlinks affect the resolved parent;
- reject root escape, never clamp;
- percent-encode each decoded segment exactly once;
- preserve query/fragment;
- never emit `<base>`.

Inline/parser rules:
- parse images before links;
- stash generated anchor/image HTML before emphasis processing;
- restore stash entries in reverse order or recursively so `` [`x`](u) `` leaves no internal NUL token;
- classified URL attributes are emitted only through `h(..., quote=True)`;
- fences close only with same character, adequate length, no closing info;
- first fence-info token is matched case-insensitively against `mermaid`;
- an unclosed Mermaid fence renders as ordinary escaped code, never a diagram;
- bounded tables/tasks/images/fence language metadata remain lightweight.

## Preview CSP and residual risk

Every plugin preview kind uses the shared-shell CSP:

`default-src 'none'; script-src 'nonce-{random}'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'none'; base-uri 'none'; object-src 'none'; form-action 'none'`

`{random}` is a fresh per-response nonce generated with Python `secrets`. The CSP nonce must exactly equal the nonce on every app-owned `<script>` tag. `script-src` must not add `'self'`, `'strict-dynamic'`, `'unsafe-inline'`, or `'unsafe-eval'`.

The same normal Back button replaces `javascript:history.back()` for every plugin preview kind. `markdown_preview.js` sets `window.opener=null` before Mermaid work.

A nonce-only script source blocks injected script tags, inline handlers, `javascript:` links, and uploaded same-origin scripts without the nonce. Mermaid uses `securityLevel:"strict"` and no eval.

Iframe sandboxing remains out of scope only as partial containment: it would protect the side-pane path but not same-tab navigation or the existing `window.open(previewUrl,'_blank')` path, and Lantern already serves uploaded `.html`/`.svg` same-origin. Residual risk remains that parent/opener capabilities are not contained and `connect-src` could be bypassed through them if script execution were ever achieved.

Release therefore requires:
- security-owner sign-off on this residual risk;
- a follow-up ticket covering both preview iframe sandboxing and existing same-origin uploaded `.html`/`.svg` serving.

## Structural HTML invariant

Parse adversarial rendered output with stdlib `html.parser`. Every emitted tag, every attribute, and every URL scheme must be explicitly allowlisted.

## Mermaid contract

Pin Mermaid **11.17.2** locally only after T5.

T5 records:
- official Mermaid 11.17.2 source/tag, SHA-256, and npm integrity hash;
- deliberate pin rationale: 11.17.2 is intentionally not npm latest and is materially smaller than the checked 12.1.0;
- `GHSA-238p-pmpm-9mq7`, bundled KaTeX `0.16.47`, and affected range `>=0.11.0 <0.18.2`;
- that the checked 12.1.0 dependency graph has no critical/high/moderate audit advantage over 11.17.2;
- explicit lodash-es and Chevrotain presence/version/reachability status for Mermaid 11.17.2; do not infer this from npm audit alone;
- Mermaid plus bundled third-party license notices, with the pin/advisory rationale recorded alongside them;
- static inspection that the selected browser bundle has no literal dynamic `import(` / planned runtime chunks, while treating T7's zero-extra-request network log as the binding proof that no runtime fetch is required;
- re-audit trigger: reconsider the pin when an applicable Mermaid release ships KaTeX >=0.18.2.

Do not enable a KaTeX trust option. The KaTeX advisory requires an existing prototype-pollution foothold; document the remaining exposure as residual risk constrained by `securityLevel:"strict"`, the nonce CSP, and no eval rather than claiming the advisory is absent.

Initialize once with:
- `startOnLoad:false`;
- `securityLevel:"strict"`;
- `suppressErrorRendering:true`;
- fixed light theme;
- `htmlLabels:false`;
- `maxTextSize:60000`;
- `maxEdges:500`;
- fixed font/theme values and conservative `dompurifyConfig`;
- secure list: `secure`, `securityLevel`, `startOnLoad`, `suppressErrorRendering`, `maxTextSize`, `maxEdges`, `theme`, `themeCSS`, `themeVariables`, `fontFamily`, `htmlLabels`, `dompurifyConfig`.

Mermaid secure sanitization is recursive, so `htmlLabels` covers `flowchart.htmlLabels`.

Cap rendering at 24 diagrams, render sequentially with yields, isolate malformed/oversized blocks, remove failed temporary nodes, and use a light Mermaid container on the dark screen.

Required types: flowchart, sequence, class, state, ER, Gantt, pie.

Performance acceptance uses attributed Chromium timings with a statistical first-load guardrail. The reviewed 3.57 MB Mermaid standalone bundle is loaded **lazily at most once per preview page** and only when at least one Mermaid fence exists; pages without Mermaid must never request or parse it. Diagram input stays bounded by `maxTextSize:60000`, `maxEdges:500`, and 24 diagrams/page. Rendering is sequential, never concurrent, and Lantern yields after bundle load, after initialize, after each `mermaid.render()` before DOM insertion, and between diagrams. In the accepted **FJP Playwright Chromium** harness, use the actual served product preview HTML and nine fresh browser contexts. Isolate the attributable first-load Mermaid bundle parse/evaluation task by preventing helper initialize/render work from contaminating the measurement. First-load PASS requires **the median of the nine isolated samples <=300 ms and no individual sample >500 ms**. Every subsequent Mermaid initialize, diagram render, and PNG/export main-thread task attributable to the governed operation must be **<=100 ms**. A larger aggregate full-page Long Task entry is not by itself a Mermaid failure unless evidence attributes the over-budget task to bundle parse/evaluation or another governed Mermaid operation. A first-load median >300 ms, any individual first-load sample >500 ms, any subsequent governed task >100 ms, or loss of the lazy/bounded/sequential/yield invariants keeps acceptance INCOMPLETE and triggers re-review.

## PNG contract

For each successful diagram:
- clone SVG;
- derive dimensions from SVG `viewBox`, not `width="100%"`;
- set explicit numeric width/height and `xmlns`;
- rasterize on white canvas;
- target 2x density within 8192 px/side and ~32 MP;
- export PNG with `toBlob`;
- name `<doc>-diagram-N.png` with 1-based index;
- revoke object URLs only after use.

## Print / PDF contract

The button is **Print / Save as PDF** and waits for current Mermaid renders before `window.print()`.

Print CSS includes:
- `color-scheme:light`;
- white background / dark text;
- hidden toolbar/notes/export controls/source fallback for successful diagrams;
- `.table-wrap,.md-code{overflow:visible}`;
- `th{position:static}`;
- `pre{white-space:pre-wrap;overflow:visible}`;
- responsive SVG and practical break avoidance.

Chromium PDF acceptance: selectable text, visible arrowheads, readable diagrams/vector SVG where Chromium preserves it, no UI chrome, no material clipping.

## Acceptance

### Terminal

- T-A1: T0-A, T0-B, and T0-C status/evidence are recorded; T0-B is labeled only as falsification, and T0-C never claims a reproduction that was not physically observed.
- T-A2: at least 50 physical `start` attempts across the recorded matrix are exact, yielding NOT_REPRODUCED/no code, **or** a wrong net result is captured and classified with the required four-channel evidence.
- T-A3: class (i) yields workaround/documentation and no Lantern terminal code; class (iii) triggers a separate backend/PTY review before scope change; class (ii) triggers a new focused browser-boundary review before code.
- T-A4: if terminal code changes after class (ii), Vietnamese Telex commits once and the full IME/manual regression matrix is green.
- T-A5: if terminal code changes, Pinyin/Japanese punctuation, Korean, AltGr/dead keys, emoji, touch/Gboard, shortcuts, paste, latency, and reconnect remain correct.
- T-A6: copy/interrupt/paste semantics remain correct under any reviewed terminal change.
- T-A7: with UniKey and each CJK IME enabled but not composing, Enter, Tab, arrows, and Backspace remain correct under any reviewed terminal change.
- T-A8: Android Chrome + Gboard remains on the xterm-owned path under any reviewed terminal change.
- T-A9: baseline guard tests prove the existing custom key handler returns `true` for keyCode 231 synthetic characters and Backspace, and `term.onData` payload data is forwarded unchanged and in order.
- T-A10: refresh/reconnect preserves the same live PTY without duplicate input.
- T-A11: no UniKey-specific suppression, compaction, buffering, debounce, batching, reorder delay, or general `term.onData` filter is introduced under Option A.
- T-A12: the accepted UniKey `as` trace has baseline payload sequence `["a","·","\u007f","\u007f","á"]` and a net line result of `á`; any runnable JSON fixture stores DEL as the literal escape `\u007f`, not a replacement character.

### Markdown / security / export

- M-A1: raw HTML remains escaped; bounded grammar works.
- M-A2: adversarial URL corpus includes C0, mixed case, `&#106;avascript:`, data SVG, protocol-relative, traversal, double-encoding cases.
- M-A3: stdlib `html.parser` structural allowlist invariant passes.
- M-A4: no `<base>`; local relative URLs rewrite exactly once.
- M-A5: CSP nonce matches every app script nonce; uploaded same-origin JS without nonce does not execute; preview-realm WebSocket is blocked; no unexpected CSP violations.
- M-A6: with Lantern origin reachable but **no internet route** (or every non-Lantern origin blocked), all seven Mermaid types render; the T7 network log shows zero extra/non-Lantern requests.
- M-A7: malformed/over-limit/page-cap+1 cases are isolated.
- M-A8: all seven types export non-empty PNGs with correct filenames and no `SecurityError`.
- M-A9: Print / Save as PDF meets the Chromium contract.
- M-A10: no CDN and no new Python runtime dependency.
- M-A11: non-Mermaid pages make zero Mermaid-bundle requests; Mermaid loads lazily at most once per Mermaid preview page; in the accepted FJP Playwright Chromium harness, measure nine fresh contexts using actual served product HTML with helper initialize/render excluded from first-load attribution, and require the median isolated first-load bundle parse/evaluation task <=300 ms with no individual sample >500 ms; every subsequent initialize/render/PNG-export main-thread task attributable to the governed Mermaid operation is <=100 ms; aggregate page Long Tasks count as failures only when attribution ties them to a governed over-budget Mermaid operation.
- M-A12: residual-risk owner sign-off and follow-up ticket exist before release.

### Release gates

**Markdown lane release:** M-A1 through M-A12 apply. The Markdown/Mermaid/PNG/PDF lane may be released independently when those gates are satisfied; it does not wait for terminal IME evidence.

**Terminal IME lane:** deferred by operator on 2026-10-07 because reliable physical UniKey trace collection was becoming disproportionately expensive. T0-C remains NOT_MEASURED and no terminal product code may change under this increment. A future terminal-specific increment must resume from T0-A/T0-B/T0-C evidence before any IME fix.

Missing manual/runtime evidence is INCOMPLETE, never PASS.

## Non-goals

- Terminal persistence across Lantern process restart.
- Backend terminal/WebSocket/PTY redesign without a T0-C class-(iii) review.
- Suppressing, compacting, reconciling, or buffering IME-injected keystrokes.
- Vendored xterm modification without separately reviewed fallback evidence.
- Full CommonMark or trusted raw HTML.
- Server-side Mermaid/PNG/PDF rendering.
- Remote Markdown image fetching/proxying.
- New Python runtime framework/dependency.
