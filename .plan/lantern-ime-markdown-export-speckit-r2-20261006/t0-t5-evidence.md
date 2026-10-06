# T0/T5 Evidence — Lantern terminal IME + Markdown/Mermaid export

Date: 2026-10-06 JST
Repository baseline: `main` at `5ba0ed9` before product implementation.
Status: **research/evidence only; no Lantern product code changed.**

## T0-A — vendored xterm internals

Vendored asset:
- File: `static/vendor/xterm.js`
- Size: 488,664 bytes
- SHA-256: `f68403f92e5552d69fab42d98571c8e16b6f03cba3e5233b4c8a99d3eb9d4653`

Upstream comparison:
- npm package: `@xterm/xterm@6.0.0`
- npm dist integrity: `sha512-TQwDdQGtwwDt+2cgKDLn0IRaSxYu1tSUjgKarSDkUM0ZNiSRXFpjxEsvc/Zgc5kq5omJ+V0a8/kIM2WD3sMOYg==`
- upstream `package/lib/xterm.js`: 488,663 bytes
- upstream SHA-256: `14903579ff54664cd72f8e8699e6961a6272c21863ec1c3b118cdc8af5d4a972`
- after normalizing vendored CRLF to LF, vendored bytes are exactly equal to upstream `@xterm/xterm@6.0.0`; normalized SHA-256 is the upstream hash above.

Verified directly in the vendored minified source:
1. `_keyDown` sets `_keyDownSeen=true`, invokes the custom key handler first, and only then calls `_compositionHelper.keydown(e)`.
2. `_keyUp` resets `_keyDownSeen=false` and later resets `_keyPressHandled=false`.
3. `_inputEvent` accepts `insertText` only when `(!e.composed || !this._keyDownSeen)`, and suppresses if `_keyPressHandled`.
4. CompositionHelper's `keydown` has a keyCode-229 path and calls `_handleAnyTextareaChanges()`.

Conclusion: T0-A passes. The prior spec's xterm-internals assumptions are now source-grounded.

## T0-B — Windows / UniKey evidence

Environment:
- Windows: `Microsoft Windows NT 10.0.26200.0`
- Chromium: `154.0.8037.93`
- Lantern: `http://localhost:9999/agent-mcp-device/`
- terminal: xterm.js -> Lantern WebSocket -> ConPTY

UniKey:
- official download URL: `https://www.unikey.org/assets/release/unikey46RC2-230919-win64.zip`
- ZIP size: 721,044 bytes
- ZIP SHA-256: `667b8d31b0d85fdc2ca17d54c4eab870ba7269063c1dd53acec7897a97af04e3`
- executable: `UniKeyNT.exe`, ProductVersion `4.6 RC2 - Build 230919`, FileVersion `4.6.2.0`
- executable SHA-256: `b732b1c198e7b0ebfcb0ef2f5d99f1888b5900460c1fa36ea27d47e8386684b1`
- UI state read from the real UniKey control dialog:
  - code page: Unicode
  - typing method: Telex
  - spelling check: ON
  - automatic restore for invalid words: ON
  - always use clipboard for Unicode: OFF
  - language toggle: Ctrl+Shift
  - per-application on/off: OFF

### Proven native rewrite shape

A Windows native key injection probe was accepted only after the UniKey hook visibly rewrote the stream. This is not treated as equivalent to physical keyboard hardware, but it is sufficient to establish UniKey's actual browser/xterm event shape.

Typing `as` with UniKey Vietnamese mode ON produced:

DOM/native order:
- ordinary `keydown a / keyCode 65`
- ordinary `keyup a`
- synthetic `keydown "·" / keyCode 231`
- synthetic `keyup Unidentified / keyCode 231`
- Backspace down/up
- Backspace down/up
- synthetic `keydown "á" / keyCode 231`
- synthetic `keyup Unidentified / keyCode 231`
- final physical `keyup s`

No `composition*`, `beforeinput`, or `input` event occurred in this trace.

Lantern WebSocket terminal payloads for the same input:
```json
["a", "·", "\u007f", "\u007f", "á"]
```

The raw event capture is stored in:
- `.plan/lantern-ime-markdown-export-speckit-r2-20261006/t0b-unikey-as-trace.json`

This directly falsifies the prior proposed terminal design as a general UniKey fix: the observed UniKey path is **not** a `Process/keyCode 229 -> beforeinput/input` transaction. It is a rewrite using synthetic keyCode 231 characters plus Backspace events, and Lantern currently forwards the intermediate rewrite characters to ConPTY.

### User-reported `start -> stsar`

Direct single-run probes:
- normal-speed `start`: correct
- fast `start`: correct

Stress automation is **not accepted as proof of the user defect** because injected-key delivery itself occasionally lost later key events before they reached the DOM. One targeted run stopped at `sta` with no DOM events for `r/t`; that is a harness/injection failure, not a Lantern/UniKey reorder.

Therefore:
- exact `start -> stsar` reproduction: **NOT_MEASURED**
- T0-B does **not** pass the prior one-claim/229 design gate.
- Per the reviewed stop condition, terminal implementation must be re-reviewed before code.

## T5 — Mermaid dependency research

### Mermaid 11.17.2

- npm dist integrity: `sha512-V6K3C8EBdEsPFZXSKMJe6ppQOENxuHARr9GvHX4hh47lAbhMRD9qf4oEK7LoaRQxULMa80/qt5gHO73aCleBBg==`
- package license: MIT
- `dist/mermaid.min.js`: 3,572,661 bytes
- SHA-256: `581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8`
- literal dynamic `import(` hits in the browser bundle: 0
- package includes one top-level Mermaid LICENSE; source map identifies 55 bundled packages.
- bundled package/license inventory is stored in:
  - `.plan/lantern-ime-markdown-export-speckit-r2-20261006/mermaid-bundled-package-inventory.tsv`

Fresh `npm audit` on the exact dependency graph:
- critical: 0
- high: 0
- moderate: 0
- low: 2
- both low findings are the same KaTeX chain:
  - `GHSA-238p-pmpm-9mq7`: "KaTeX: Existing prototype pollution can bypass trust restrictions"
  - installed/bundled KaTeX: `0.16.47`
  - affected range reported by npm: `>=0.11.0 <0.18.2`

The browser bundle visibly includes KaTeX code.

### Mermaid 12.1.0 comparison

Current npm latest observed during this research: `12.1.0`.

- npm dist integrity: `sha512-wlVCp+8eTupfCeeFvoZNNiTuHrvag0P2jz/ILgb/f/6jkVokUefOcujefi8qUe/j2asHiSePncVsz/xzzA80LQ==`
- package license: MIT
- `dist/mermaid.min.js`: 5,493,176 bytes
- SHA-256: `6484afc32872a3aa16cac9a76ba1816a1ed4cc870a6593cc2e17757750f518b2`
- literal dynamic `import(` hits: 0
- audit: same 2 low KaTeX-chain findings; no high/moderate/critical improvement.
- 12.1.0 adds a substantially larger bundle and additional dependencies such as ELK/Chevrotain.

Decision pending review:
- There is no current security-audit advantage to 12.1.0 for this use case.
- 11.17.2 is materially smaller and remains a plausible intentional pin for Lantern's small-footprint requirement.
- Because 11.17.2 is no longer npm latest, the final implementation must document the deliberate pin and the KaTeX low-severity residual risk; it must not claim "latest Mermaid".
