[Reading 163 lines from start (total: 163 lines, 0 remaining)]

# Terminal IME + Markdown Preview/Export Implementation Plan

Status: aligned to the latest Opus UniKey re-review and lane-split review. T0-A PASS; T0-B PASS only as falsification of the retired Process/229 design. The Win32 SendInput automation probe cannot exercise UniKey and is non-evidence for T0-C; the physical gate remains NOT_MEASURED and the original UniKey registry settings were restored. Terminal code is blocked on T0-C and classification-specific review; Markdown/Mermaid T3-T7 is independent and may proceed now.
Source contract: `specs/001-terminal-ime-markdown-export/spec.md`.

## Architecture

Keep the existing ownership boundaries.

- Terminal: baseline Option A preserves today's boundary. xterm owns all keydown paths, including keyCode 231 synthetic characters and IME-injected Backspace; the existing custom handler stays unchanged; `term.onData` is forwarded unchanged/in order. `static/terminal_scm.js`, `lantern_ws.py`, `lantern_terminal.py`, `lan_drive.py`, protocol framing, replay/reconnect, and `static/vendor/xterm.js` remain unchanged unless T0-C classification plus a focused review explicitly reopens a boundary.
- Markdown: `plugin.py` remains parser/page owner. New `static/markdown_preview.js` owns Back, Mermaid render/export, and Print / Save as PDF.
- No Markdown framework, server PDF engine, new Python runtime dependency, CDN, or process-restart terminal persistence.

## Terminal track — evidence before terminal code

The terminal track is now **T0-A PASS -> T0-B PASS-as-falsification -> T0-C physical reproduction/classification -> conditional review**. T1 is baseline guard coverage and may proceed without inventing a fix. T2 is blocked unless T0-C is class (ii) and a new focused review defines a changed contract.

This terminal track does not block Markdown/Mermaid T3-T7.

### T0-A — vendored xterm internals: PASS

Authoritative evidence identifies the vendored file as upstream `@xterm/xterm@6.0.0` after CRLF normalization and proves the relevant key-handler/input ordering. Keep `static/vendor/xterm.js` read-only.

### T0-B — UniKey rewrite trace: PASS only as falsification

The accepted `as` trace contains keyCode 231 synthetic characters and two Backspaces, with no Process/229, composition, `beforeinput`, or `input` events. The WebSocket sequence is baseline data forwarded in order and the captured screen result is correct. This retires the previous 229 / one-claim / `beforeinput`-`input` / `compositionSendPending` design; it does not reproduce the reported defect.

Before any trace becomes a runnable test fixture, DEL must be encoded in raw JSON as `\u007f`; replacement characters are invalid. Do not alter the authoritative `.plan` evidence during this spec-only revision.

### T0-C — physical real-keyboard gate

Use physical keyboard input. A wrong net result—exact `start -> stsar` or another clearly wrong terminal result—is mandatory before terminal product code.

For every candidate reproduction, record simultaneously:

1. hook/raw-key log or keyboard-viewer evidence;
2. DOM events;
3. WebSocket payloads;
4. PTY echo/screen.

Also record shell, `chcp`/code page, `LANG` where applicable, Chromium/UniKey versions, UniKey code page/typing method, spell-check, auto-restore, clipboard-for-Unicode, typing speed, and relevant placeholder options. Run the same physical typing in Windows Terminal/conhost with the same shell, a plain Chromium `<textarea>`, and Lantern.

Run at least 50 physical `start` attempts across the recorded settings/speed matrix. If no wrong net result occurs, close the terminal item NOT_REPRODUCED with no terminal product-code change. Re-run the known `as -> á` shape with auto-restore off and clipboard-for-Unicode on, and re-classify the prior `sta` observation with hook-level evidence.

## Terminal decision tree and baseline guards

Baseline Option A remains in force unless evidence justifies a reviewed change:

- xterm owns every keydown, including keyCode 231 synthetic characters and IME-injected Backspace;
- the current custom key handler is unchanged;
- `term.onData` is forwarded unchanged and in order;
- no suppression, compaction, reconciliation, buffering, debounce, batching, or delay;
- no UniKey-specific frontend state.

Classify any T0-C reproduction at the earliest divergence:

- **(i) before DOM:** UniKey/Windows/input-source issue -> workaround/documentation only; no Lantern code.
- **(ii) DOM -> payload:** xterm/Lantern browser boundary -> new focused design review before changed-behavior tests or product code.
- **(iii) payload -> screen:** shell/ConPTY/PTY/code-page issue -> separate backend/PTY review before reopening backend scope.

T1 is baseline guard coverage only. In the existing fake harness, capture the custom handler and `onData` callbacks, then assert that keyCode 231 and Backspace remain xterm-owned (handler returns `true`) and that emitted data is forwarded unchanged/in order. Update the fake `textarea={}` only if those guard tests require a listener/value API. A runnable copy of the `as` trace must encode DEL as JSON `\u007f` and prove the baseline payload/net result; fake-xterm tests remain Lantern-layer evidence only.

T2 is **BLOCKED**. It has no approved fix design. It may be reopened only after T0-C class (ii) plus a new focused review. If T0-C is NOT_REPRODUCED or class (i), no terminal product code changes. If class (iii), use the separate backend/PTY review instead.

## Markdown parser and URL design

Keep the one-pass parser and escape-first model.

URL handling order:

1. remove ASCII tab/newline parser whitespace;
2. trim leading/trailing C0 controls/spaces;
3. `html.unescape` once;
4. treat backslash as slash;
5. split path/query/fragment;
6. URL-unquote path exactly once;
7. reject encoded `%2e%2e` / `%2f` residue case-insensitively;
8. reject protocol-relative `//host`;
9. classify scheme/local path.

Links allow confined relative/root-relative, fragments, http, https, mailto. Author images allow confined relative/root-relative only; remote/data images render as safe text/alt. Relative local paths use the Markdown parent's resolved path, reject root escape, encode each decoded segment exactly once, preserve query/fragment, and never emit `<base>`.

Parser invariants:

- remove literal NUL before parsing;
- parse image before link;
- classify URL after `html.unescape`, emit attributes only through `h(..., quote=True)`;
- stash generated link/image HTML before emphasis processing and restore stash in reverse order or recursively;
- fence close uses same character, length >= opener, no closing info;
- first info token matches `mermaid` case-insensitively;
- unclosed Mermaid fence renders as ordinary escaped code;
- test adversarial output with stdlib `html.parser`; every emitted tag, attribute, and URL scheme is explicitly allowlisted.

## Shared preview CSP

Every plugin preview kind uses exactly:

`default-src 'none'; script-src 'nonce-{random}'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'none'; base-uri 'none'; object-src 'none'; form-action 'none'`

Generate a fresh per-response nonce with Python `secrets`. The same nonce must appear in the CSP and every app-owned `<script>` tag. Do not add `'self'`, `'strict-dynamic'`, `'unsafe-inline'`, or `'unsafe-eval'` to `script-src`.

Replace `javascript:history.back()` with a normal button wired by local JS. `markdown_preview.js` sets `window.opener=null` before Mermaid work.

Iframe sandboxing remains deferred only as partial containment: the same preview also has same-tab and `window.open` paths, and Lantern already serves uploaded HTML/SVG same-origin. Release requires security-owner sign-off on this residual risk plus a follow-up ticket covering both preview iframe sandboxing and same-origin uploaded HTML/SVG serving.

## Mermaid dependency and runtime

The Mermaid track is independent of T0-C. T5 accepts a deliberate 11.17.2 pin, subject to complete pin/advisory/license documentation:

- verify the official Mermaid 11.17.2 package/source, SHA-256, and npm integrity;
- record that 11.17.2 is an intentional "not latest" pin and why its smaller bundle is preferred;
- record `GHSA-238p-pmpm-9mq7`, bundled KaTeX 0.16.47, affected range `>=0.11.0 <0.18.2`, and the fact that the checked 12.1.0 graph has no critical/high/moderate audit advantage;
- record explicit lodash-es and Chevrotain versions/presence/reachability for 11.17.2 rather than inferring reachability from npm audit;
- include Mermaid and bundled third-party notices, with the pin rationale/advisory record in the same notice artifact;
- record that the bundle has no literal dynamic `import(` hits/planned runtime chunks, but treat T7's zero-extra-request network log as the binding self-contained proof;
- never enable a KaTeX trust option; record the residual-risk reasoning and re-audit when an applicable Mermaid release ships KaTeX >=0.18.2.

Only after the dependency gate, vendor the bundle.

Runtime config:

- `startOnLoad:false`;
- `securityLevel:"strict"`;
- `suppressErrorRendering:true`;
- fixed light theme and `htmlLabels:false`;
- `maxTextSize:60000`, `maxEdges:500`;
- conservative `dompurifyConfig`;
- secure list includes `secure`, `securityLevel`, `startOnLoad`, `suppressErrorRendering`, `maxTextSize`, `maxEdges`, `theme`, `themeCSS`, `themeVariables`, `fontFamily`, `htmlLabels`, `dompurifyConfig`.

Cap at 24 diagrams/page, render sequentially with yields, isolate malformed/oversized blocks, and use a light diagram container. The 100 ms responsiveness rule includes initial Mermaid parse/compile plus render/export work. Do not load/parse Mermaid on pages with no Mermaid fence; lazily load the nonce-authorized local bundle only when at least one Mermaid fence exists. If first-load parse/compile or any render/export task exceeds 100 ms on accepted Chromium evidence, re-review the loading/pin/caps strategy rather than waiving the limit.

## PNG and Print / PDF

PNG:

- clone SVG and derive dimensions from `viewBox`;
- set explicit numeric width/height + xmlns;
- fill white canvas;
- target 2x density within 8192 px/side and about 32 MP;
- `toBlob` must succeed; name `<doc>-diagram-N.png`; revoke URLs after use.

Print / Save as PDF waits for pending Mermaid renders before `window.print()`. Print CSS explicitly uses `color-scheme:light`, white background/dark text, hides UI/source fallback for successful diagrams, sets `.table-wrap,.md-code{overflow:visible}`, `th{position:static}`, `pre{white-space:pre-wrap;overflow:visible}`, and responsive SVG.

## Verification

Before parser implementation: security tests for normalized URL allowlists, nonce CSP, same-origin uploaded JS blocked, nested stash restoration, fence rules, and structural `html.parser` invariant.

Before Mermaid acceptance: Lantern origin remains reachable while internet is absent or every non-Lantern origin is blocked; assert zero extra/non-Lantern requests (the binding proof the bundle is self-contained) and no unexpected CSP console violations. Do not use DevTools Offline if it blocks localhost.

Terminal manual acceptance before any code is T0-C only: physical reproduction/classification with the four-channel evidence and native/textarea/Lantern contrasts. The full Vietnamese/CJK/Korean/AltGr/dead-key/emoji/paste/shortcut/touch/reconnect matrix is required only if a class-(ii) review ultimately authorizes terminal code changes.

T8 runs per lane: the Markdown lane may complete its own regression/scope gate independently; the combined T8 runs only after both the terminal and Markdown lanes reach their exits.

Final automated gates: full Python suite, terminal/plugin focused tests, `node --check` for changed JS, `git diff --check`, and scope inspection confirming `static/terminal_scm.js` stays unchanged unless T0-C class (ii) plus focused review authorized a change, and `lantern_ws.py`, `lantern_terminal.py`, `lan_drive.py`, `requirements.txt`, and `static/vendor/xterm.js` remain unchanged unless their classification-specific review explicitly reopened them.