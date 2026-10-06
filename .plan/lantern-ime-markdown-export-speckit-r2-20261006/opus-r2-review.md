[Reading 84 lines from start (total: 84 lines, 0 remaining)]

Reasoning completed in 1 step

VERDICT: APPROVE_WITH_REQUIRED_EDITS

The ownership boundaries, the T0-first ordering and most of the security direction are right. The revision is still not implementation-ready. Several earlier required edits were neither added nor explicitly rejected (R6, R8, R11, R16, plus most of R4). The documents also contradict each other on the one control that carries the R2 security argument: the preview CSP. These are documentation fixes, not redesigns. The verdict becomes REJECT if any blocker below is still open when product code starts.

REMAINING_BLOCKERS

B1 – The CSP differs between documents. This is what decides R2.
The spec requires a per-response nonce: script-src 'nonce-…'. It also requires acceptance proof that an uploaded same-origin .js without the nonce does not run.
sharepoint
The plan and T4 specify script-src 'self', and T3 tests that "exact" policy.
sharepoint
+1
Under 'self', any file uploaded to the drive is an allowed script source. That breaks the spec's own M-A5 check, and an implementer following tasks.md will ship the weaker policy.
B2 – R2 (iframe sandbox) was moved to out-of-scope without a written justification. I accept leaving the sandbox out, but only if B1 is resolved to the nonce policy and the reasoning below goes into the spec:
A nonce-only script-src (no 'self', 'strict-dynamic', 'unsafe-inline' or 'unsafe-eval') stops injected <script> tags, inline event handlers, javascript: links and uploaded same-origin scripts. The only path left is a gadget inside nonced code (Mermaid or markdown_preview.js), and securityLevel:"strict" plus no-eval narrows that.
The sandbox would only protect the side-pane path. The preview also opens through window.open(previewUrl,'_blank'), which keeps window.opener, and through a same-tab navigation.
sharepoint
The existing serve_file already serves any uploaded .html/.svg same-origin, with full access to /ws. So the extra protection from sandboxing only the preview iframe is small until that is fixed.
sharepoint
The spec currently says only "would require a lan_drive.py change". That describes the work, not why it is safe to skip. The reasoning above has to be stated in the spec, along with the conditions in RE-1.
B3 – R4 is not incorporated, so keys can be lost.
The claim rule matches every Windows desktop keydown with keyCode 229 or key "Process" that has no modifiers. There is no exclusion by code.
Any keydown matched this way returns false, which skips xterm's own keydown handling. Under the inputType table, anything other than insertText or deleteContentBackward then sends nothing.
So an IME-on 229 keydown for Enter, Tab, an arrow, Home/End, PageUp/PageDown, Escape or Delete is dropped. The UniKey/CJK acceptance rows for these keys that I asked for are also missing (T-A7 does not specify the IME state).
B4 – The offline acceptance test (R16) uses the method I flagged as invalid.
M-A6 and T7 say "with network disabled" / "browser network disabled".
sharepoint
+1
Chromium's offline mode usually blocks the localhost Lantern origin as well, so the test either fails or proves nothing.

REQUIRED_EDITS

RE-1 (CSP, all three docs):
Use one policy everywhere: default-src 'none'; script-src 'nonce-{random}'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'none'; base-uri 'none'; object-src 'none'; form-action 'none'. Do not add 'strict-dynamic'.
Generate the nonce with secrets for every response.
The T3 exact-policy test must assert the nonce form, and that the nonce in the policy equals the nonce on every app <script> tag.
Apply the same CSP and Back button to all plugin preview kinds, because render_preview_page is shared and currently hard-codes javascript:history.back() for every kind. Otherwise, state explicitly that non-Markdown kinds stay unchanged.
sharepoint
markdown_preview.js must set window.opener = null before any Mermaid processing.
Add a residual-risk entry: no protection for the parent or opener page, and connect-src can be bypassed through parent.WebSocket or opener. It needs an owner sign-off and a follow-up ticket covering both the sandbox and the existing same-origin .html/.svg serving.
RE-2 (R4):
Exclude code ∈ {Backspace, Delete, Enter, NumpadEnter, Tab, Escape, Arrow*, Home, End, PageUp, PageDown} from the claim unless T0 shows that one of them carries the corrupted text.
The deleteContentBackward → \x7f row may stay only if T0 shows a 229-coded Backspace whose own handling fails.
Add T-A rows covering Enter, Tab, arrows and Backspace with UniKey on, and with each CJK IME on but not composing.
RE-3 (R6, xterm internals gate): Add a step before T1 that records the vendored xterm version and quotes its source for each of the following:
the order of the custom key handler versus compositionHelper.keydown;
_keyDownSeen / _keyPressHandled;
the condition in _inputEvent (insertText && (!composed || !_keyDownSeen));
the deferred 229 textarea diff.

Fallback mode must also prove that xterm's own input handler does not emit too. Reason: xterm registers its listener first, and resets _keyDownSeen on keyup. If any claimed input arrives after keyup, both handlers send the text and it is duplicated. T0 must record the order of keyup versus beforeinput/input. If input arrives after keyup, stop and re-review.

RE-4 (R7, T0 contents):
Add the Chromium version, the UniKey version and its settings (spell-check/auto-restore on and off, clipboard-for-Unicode on and off), and Windows' built-in Vietnamese Telex as a contrast case.
The UniKey "start" ×N acceptance must be run with auto-restore both on and off.
Either run the T1 harness against the real vendored xterm.js, or relabel T1 as Lantern-layer contract tests and require replay of the trace in a real Chromium for every claim that depends on xterm. A fake xterm cannot show that a test fails "for the intended reason".
RE-5 (R8): The existing FakeTerminal has textarea={} with no addEventListener. Make the new listener binding null-safe, or update the fake, and remove the statement that existing tests stay unchanged. Bind the claim check after the existing mobile-modifier, Ctrl/Cmd+V and selection Ctrl+C branches.
RE-6 (R18 T-9): Add an explicit acceptance criterion and unit test: with the IME off, non-229 keydowns follow exactly the baseline path and the handler returns true.
RE-7 (R11): Add a structural invariant test. Parse rendered output from an adversarial corpus with the stdlib html.parser, and assert that every tag, every attribute and every URL scheme is on an allowlist. It must not be missing from the spec and tasks.
RE-8 (R10, stash restore):
Today a code-span token inside a link label is restored before the link fragment that contains it. The token is then left literally in the output, with NUL characters. Restore stash entries in reverse order, or recursively, and add a test for [`x`](u).
sharepoint
Classify URLs after html.unescape, and output them only through h(quote=True).
Add the entity-encoded scheme case (&#106;avascript:) from R1 to the URL test corpus.
RE-9 (R3, encoding): Define how a path is decoded before it is normalised: unquote once, check for %2e%2e / %2f, then encode each segment exactly once. This avoids %2520 double-encoding and catches encoded traversal. Note that rel comes from resolve(), so symlinks change the parent directory.
RE-10 (R12): The fence info string's first token is matched against mermaid case-insensitively. An unclosed mermaid fence renders as plain code, never as a diagram.
RE-11 (R13, consistency and freezing):
Make the plan and T6 secure list match the spec. It must include secure, dompurifyConfig and htmlLabels. Mermaid's sanitize step applies the list recursively, so htmlLabels also covers flowchart.htmlLabels.
Add M-11: while the worst-case fixture renders in the side pane, the parent Lantern terminal stays responsive, within a stated limit on long tasks. If that limit is exceeded, lower the caps.
Give the Mermaid output a light container in the dark screen CSS.
RE-12 (R14): Take export dimensions from the SVG viewBox, not from width="100%". Name downloads <doc>-diagram-N.png.
RE-13 (R15): Record the npm integrity hash as well as the SHA-256. Confirm the bundle is a single file that never loads chunks or uses dynamic import() at runtime, because the nonce CSP would block those loads.
RE-14 (R16): Replace "network disabled" with either "no internet route" or "block every non-Lantern origin". Assert zero cross-origin requests, and that the CSP console shows nothing unexpected.
RE-15 (R17): Make the print CSS explicit: .table-wrap,.md-code{overflow:visible}, th{position:static}, and color-scheme:light for print.

IMPLEMENTATION_READY_SUMMARY

Can proceed now: T0 trace capture (evidence only, nothing persisted in production) and the RE-3 source read of xterm; the T5 Mermaid dependency, advisory and licence gate (research only, nothing vendored).
Can proceed after B1, B2 and RE-1 and RE-7 to RE-10 are applied: T3 security tests, then T4 parser, URL rewrite and CSP.
Gated on T5 passing plus RE-11 to RE-15: T6 and T7 (Mermaid, PNG export, PDF).
Gated on T0, the RE-3 evidence, and B3 plus RE-2, RE-4, RE-5 and RE-6: all terminal code (T1 and T2). If T0 shows more than one input transaction per keydown, input arriving after keyup, or a path other than Process/229, stop and re-review.
These files must stay unchanged: lantern_terminal.py, lantern_ws.py, lan_drive.py, requirements.txt, static/vendor/xterm.js.