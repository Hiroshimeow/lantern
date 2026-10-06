[Reading 191 lines from start (total: 191 lines, 0 remaining)]

# Terminal IME + Markdown Preview/Export Tasks

Status: aligned to the latest Opus UniKey re-review and lane-split review. T0-A PASS; T0-B PASS only as falsification; the Win32 SendInput automation probe cannot exercise UniKey and is non-evidence for T0-C. T0-C remains NOT_MEASURED; the original UniKey registry settings were restored.
Rule: **terminal and Markdown/Mermaid are independent tracks**. T1 is guard-tests-only and may proceed without changing `static/terminal_scm.js`. T2 is blocked unless T0-C physically reproduces a wrong net result, classifies it as (ii), and a new focused review approves a changed contract. T3-T7 may proceed now on a separate Markdown branch/worktree. At every Markdown commit, verify the diff contains no changes to `static/terminal_scm.js`, `static/vendor/xterm.js`, `lantern_terminal.py`, `lantern_ws.py`, `lan_drive.py`, or `requirements.txt`.

## T0-A — Record vendored xterm internals — COMPLETE / PASS

Files:
- Read only: `static/vendor/xterm.js`.
- Authoritative evidence: `.plan/lantern-ime-markdown-export-speckit-r2-20261006/t0-t5-evidence.md`.

Recorded result:
1. Vendored xterm is upstream `@xterm/xterm@6.0.0` after CRLF normalization.
2. Evidence covers custom key-handler order, key state lifecycle, `_inputEvent` gating, and the vendored keyCode-229 textarea-diff path.
3. This is source evidence only; `static/vendor/xterm.js` stays unchanged.

Exit: **PASS**. No further T0-A work unless a later review reopens xterm.

## T0-B — UniKey rewrite trace — COMPLETE / PASS AS FALSIFICATION ONLY

Files:
- Read only: `.plan/lantern-ime-markdown-export-speckit-r2-20261006/t0-t5-evidence.md`.
- Read only: `.plan/lantern-ime-markdown-export-speckit-r2-20261006/t0b-unikey-as-trace.json`.
- If a runnable repository fixture is needed for T1, create a separate test fixture; do not mutate the authoritative `.plan` evidence.

Recorded result:
1. The accepted `as` trace contains keyCode 231 synthetic characters and two Backspace pairs.
2. It contains no Process/229, composition, `beforeinput`, or `input` events.
3. Baseline WebSocket payloads are `["a","·","\u007f","\u007f","á"]` and the captured net screen result is `á`.
4. This falsifies the prior 229 / one-claim / `beforeinput`-`input` / `compositionSendPending` fix design; it does not reproduce `start -> stsar`.

Fixture requirement before replay:
- DEL must be serialized in raw JSON as the escape `\u007f`; replacement characters are invalid.
- Verify the fixture's raw bytes/text representation before a replay test consumes it.

Exit: **PASS only as falsification**. Exact reported defect remains NOT_MEASURED.

## T0-C — Physical real-keyboard reproduction and classification

Gate: mandatory before any terminal product code.

Evidence only; do not change Lantern product code while running this task.

Steps:
1. Use a physical keyboard and attempt exact `start -> stsar`, accepting another clearly wrong net terminal result only if it is captured completely.
2. For each candidate reproduction, capture simultaneously:
   - hook-level/raw-key log or keyboard-viewer evidence;
   - DOM events;
   - WebSocket payloads;
   - PTY echo/screen.
3. Record shell identity, `chcp`/code page, `LANG` where applicable, Chromium version, UniKey version, UniKey code page/typing method, spell-check, auto-restore, clipboard-for-Unicode, typing speed, and any placeholder-related UniKey option.
4. Run the same physical typing in:
   - Windows Terminal/conhost with the same shell;
   - a plain Chromium `<textarea>`;
   - Lantern.
5. Re-run `as -> á` with auto-restore off and with clipboard-for-Unicode on.
6. Re-classify the prior `sta` stress observation using hook/raw-key evidence; do not call it harness loss without that evidence.
7. Run at least 50 physical `start` attempts across the recorded settings/speed matrix.
8. Classify a reproduced wrong result at the earliest divergence:
   - (i) before DOM -> workaround/documentation; no Lantern terminal code;
   - (ii) DOM -> payload -> stop for a new focused browser-boundary review before code;
   - (iii) payload -> screen -> stop for a separate backend/PTY review before scope change.
9. If none of the >=50 physical attempts reproduces a wrong net result, close terminal defect work as **NOT_REPRODUCED** with no terminal product-code change.

Exit: one of NOT_REPRODUCED, class (i), class (ii), or class (iii), backed by the four-channel evidence. Never claim reproduction without physical evidence.

## T1 — Add baseline terminal guard tests

Gate: may proceed after this document review; it does not require a reproduced defect and must not encode a speculative fix.

Files:
- Modify: `test_terminal_ui.py`.
- Modify `test_terminal_scm.py` only if an existing transport assertion is truly needed.
- Optional new runnable fixture: `testdata/unikey-as-baseline.json` if a JSON replay is clearer than an inline test vector. Do not read the untracked `.plan` evidence at test runtime.

Steps:
1. Extend the fake terminal only enough to retain the callback passed to `attachCustomKeyEventHandler` and the callback passed to `onData`.
2. Keep the fake `textarea={}` unchanged unless these guard tests actually require listener/value methods.
3. Invoke the captured custom handler with a keyCode 231 synthetic-character keydown and with an IME-injected Backspace keydown; assert the existing handler returns `true` for both so xterm owns them.
4. Feed `onData` the baseline sequence `["a","·","\u007f","\u007f","á"]`; assert emitted `terminal_input.data` values are byte-for-character unchanged and in the same order.
5. If using the JSON fixture, assert its raw serialized form uses `\u007f` escapes rather than replacement characters before parsing/replay.
6. Keep existing mobile modifier, Ctrl/Cmd+V, selected-text Ctrl+C, replay, hidden-document, and reconnect semantics unchanged.
7. Treat fake-xterm tests as Lantern-layer guard evidence only; they do not prove native browser/UniKey behavior.

Exit: baseline Option A is pinned by tests without changing `static/terminal_scm.js`.

## T2 — Terminal product change — BLOCKED

Gate: **T0-C class (ii) + new focused design review**.

Files:
- None approved yet.

Rules:
1. Do not implement the retired Process/229 / one-claim / `beforeinput`-`input` / `compositionSendPending` design.
2. Do not suppress, compact, reconcile, buffer, debounce, batch, reorder, or delay keyCode 231 characters or IME-injected Backspace.
3. Do not change `static/terminal_scm.js`, `static/vendor/xterm.js`, `lantern_ws.py`, or `lantern_terminal.py` until the classification-specific review names the exact allowed boundary and contract.
4. NOT_REPRODUCED or class (i) closes with no terminal product-code change. Class (iii) routes to a separate backend/PTY review, not this task.

Exit: remains BLOCKED until a class-(ii) review supplies an executable design.

## T3 — Add Markdown security/parser tests first

File: new `test_plugin.py`.

Required baseline/adversarial tests:

- raw HTML remains escaped;
- C0-prefixed and mixed-case JavaScript schemes;
- `&#106;avascript:` after `html.unescape`;
- `data:image/svg+xml`, protocol-relative hosts, encoded traversal;
- local/root/fragment/http/https/mailto link allowlist;
- image allowlist local/root only; remote/data images do not load;
- URL-unquote exactly once and segment encoding exactly once;
- no `<base>`;
- image-before-link parsing;
- nested stash restoration such as `` [`x`](u) `` leaves no NUL/internal token;
- URL attributes emitted only after classification through quoted escaping;
- fence character/length/closing-info rules;
- first info token matches Mermaid case-insensitively;
- unclosed Mermaid stays escaped code;
- table/task/image/fence-language grammar.

Structural invariant: parse adversarial rendered HTML with stdlib `html.parser`; every output tag, attribute, and URL scheme is explicitly allowlisted.

Preview/CSP tests must assert exactly:

`default-src 'none'; script-src 'nonce-{random}'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'none'; base-uri 'none'; object-src 'none'; form-action 'none'`

Also assert CSP nonce equals the nonce on every app script, uploaded same-origin JS without nonce cannot execute, all plugin preview kinds use the same CSP and normal Back button, and `markdown_preview.js` clears `window.opener`.

## T4 — Implement bounded Markdown parser + shared preview CSP

File: `plugin.py`.
Create later browser helper: `static/markdown_preview.js`.

Steps:
1. Implement URL normalization/allowlist and server-side relative rewrite; never emit `<base>`.
2. Remove NUL before parsing; parse images before links; stash generated link/image HTML and restore reverse/recursive.
3. Add bounded table/task/image/fence metadata and Mermaid placeholders.
4. Generate per-response nonce with Python `secrets`; apply exact nonce CSP to every plugin preview kind and nonce every app-owned script.
5. Replace `javascript:history.back()` with a normal button.
6. Keep remote/data author images from loading.
7. Do not add new Python/runtime dependencies.

Security gate: T3 must be green before feature grammar is considered complete.

## T5 — Mermaid dependency/advisory/license gate — COMPLETE / PASS

Gate result: independent of terminal T0-C and PASS per `.plan/lantern-ime-markdown-export-speckit-r2-20261006/t5-mermaid-research.md`. The deliberate 11.17.2 pin, npm audit, lodash-es runtime reachability, Chevrotain non-runtime result, license-normalization notes, KaTeX residual-risk decision, and offline self-containment checks are recorded before vendoring.

Steps:
1. Reuse the recorded official Mermaid 11.17.2 source/package, SHA-256, and npm integrity; do not call it "latest".
2. In the notice/pin-rationale artifact, state that 11.17.2 is an intentional pin and record why its smaller bundle is preferred to the checked 12.1.0.
3. Record `GHSA-238p-pmpm-9mq7`, bundled KaTeX `0.16.47`, affected range `>=0.11.0 <0.18.2`, and that the checked 12.1.0 graph has no critical/high/moderate audit advantage.
4. Record exact lodash-es and Chevrotain versions/presence/reachability for Mermaid 11.17.2 from the dependency graph/bundle inventory; mark any unverified reachability INCOMPLETE rather than inferring it from npm audit.
5. Include Mermaid and bundled third-party license notices. Do not enable a KaTeX trust option. Record the residual-risk reasoning and re-audit trigger for an applicable Mermaid release shipping KaTeX >=0.18.2.
6. Record static evidence that the selected browser bundle has no literal dynamic `import(` / planned runtime chunks, but make T7's zero-extra-request network log the binding proof of self-containment.

Exit: deliberate pin, advisory/reachability, and license evidence complete.

## T6 — Vendor Mermaid and implement render/PNG/PDF

Gate: T3/T4 security gates green and T5 passed. No terminal T0-C dependency.

Files:
- Create `static/vendor/mermaid-11.17.2.min.js`.
- Create `static/vendor/mermaid-11.17.2.LICENSES.txt`.
- Create `static/markdown_preview.js`.

Steps:
1. Set `window.opener=null` before Mermaid work.
2. Initialize Mermaid with strict/local config from spec: startOnLoad false, strict security, suppress errors, light theme, htmlLabels false, maxTextSize 60000, maxEdges 500, conservative DOMPurify config, and matching secure list.
3. Cap at 24 diagrams/page; render sequentially with yields; isolate failures and oversize inputs.
4. Keep parent terminal responsive; the 100 ms rule includes initial Mermaid parse/compile and render/export work. Do not load/parse Mermaid when no Mermaid fence exists; lazily load the nonce-authorized local bundle only when needed. Any >100 ms Mermaid-caused main-thread task keeps acceptance INCOMPLETE and triggers re-review of loading/pin/caps.
5. PNG export derives from viewBox, explicit dimensions, white canvas, <=8192 px/side and about 32 MP, 2x target, `toBlob`, `<doc>-diagram-N.png`.
6. Print / Save as PDF waits for pending renders and uses explicit light print CSS: `.table-wrap,.md-code{overflow:visible}`, `th{position:static}`, wrapped pre, responsive SVG.

## T7 — Browser acceptance

Run with Lantern origin reachable but no internet route, or block every non-Lantern origin. Do not use an offline mode that also blocks localhost.

Verify:

- zero extra/non-Lantern requests and no unexpected CSP console violations; this network log is the binding proof that the Mermaid bundle is self-contained;
- all seven Mermaid types render; malformed/oversized blocks are isolated;
- uploaded same-origin JS without nonce does not run;
- PNG files are non-empty/legible and `toBlob` succeeds;
- parent terminal remains responsive under worst-case Mermaid fixture;
- Print / Save as PDF has selectable text, visible arrowheads, readable diagrams, no UI chrome/clipping.

Security release gate: record owner sign-off on residual preview containment risk and create a follow-up ticket for iframe sandboxing + same-origin uploaded HTML/SVG serving.

## T8 — Full regression and scope check

Lane rule: Markdown T8 may run after T7 for the Markdown worktree; the combined T8 runs only after both the Markdown and terminal lanes reach their exits.

Run:

- full Python suite;
- focused terminal/plugin tests;
- `node --check static/terminal_scm.js`;
- `node --check static/markdown_preview.js`;
- `git diff --check`;
- `git status --short` and `git diff --stat`.

Confirm `static/terminal_scm.js` is unchanged unless T0-C class (ii) plus a focused review explicitly authorized a change. Confirm no unintended changes to `lantern_terminal.py`, `lantern_ws.py`, `lan_drive.py`, `requirements.txt`, or `static/vendor/xterm.js`; class (iii) requires its own backend/PTY review before any exception. Process-restart terminal persistence remains out of scope.