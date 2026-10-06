[Reading 154 lines from start (total: 154 lines, 0 remaining)]

Reasoning completed in 1 step

VERDICT: MORE_EVIDENCE_REQUIRED

TERMINAL_ROOT_CAUSE

The old design no longer applies. The UniKey trace contains no keyCode 229, no Process key, no composition events, and no beforeinput or input events. The one-claim beforeinput/input contract has nothing to claim. The stop condition for an event shape the design can't represent has fired.
sharepoint
+1
sharepoint
What UniKey actually does. It never lets the physical s keydown reach the DOM; only the final s keyup arrives. In its place it injects:
a synthetic keyCode-231 character ·
two Backspace down/up pairs
a synthetic keyCode-231 character á
Each keydown shows defaultPrevented:true, so xterm 6.0.0 handled every one on keydown. Lantern forwarded ["a","·","\x7f","\x7f","á"] in order.
sharepoint
This trace shows no defect. In a line-edited shell, that byte stream nets out to á. The captured screen ends with á. xterm turned each keystroke into the matching bytes, and Lantern forwards onData unchanged. Passing the intermediate rewrite bytes through is how UniKey's keystroke-level rewriting works. It's only a bug if a measured case gives the wrong net result.
sharepoint
sharepoint
Not yet proven: whether a native console (conhost / Windows Terminal) gets the same · + Backspace×2 + á sequence from UniKey. If it does, Lantern behaves like a native console.
The start -> stsar cause is unknown and NOT_MEASURED. There are three possible places for it, and none has been tested:
(i) Before the DOM: UniKey or Windows. Examples: a physical key interleaving with UniKey's injected burst, or UniKey's word buffer getting out of sync.
(ii) DOM → payload: xterm or Lantern.
(iii) Payload → screen: shell, ConPTY or code page. Examples: cmd.exe on Japanese Windows code page 932 (CP932) mishandling · or á, or Backspace on ambiguous-width characters.
The "harness loss" ruling is unproven. The stress run that stopped at sta with no DOM events for r/t was rejected as injection failure. But r is a Telex tone key, and this trace shows UniKey can swallow a physical keydown. That run is consistent with UniKey consuming keys, which is close to the user's defect. Without a hook-level log it can't be classified either way.
sharepoint

REVISED_TERMINAL_DIRECTION

There is no safe fix design yet. The baseline ownership is Option A:
xterm owns every keydown path, including keyCode-231 synthetic characters and IME-injected Backspace.
The custom key handler stays as it is.
sharepoint
onData is forwarded unchanged and in order.
Lantern adds no input state.
The smallest correct frontend boundary for UniKey's rewrite is the one that exists today: zero new state.
B (suppress/reconcile proven UniKey bursts): rejected.
The frontend can't tell UniKey's · from a real U+00B7, or an injected Backspace from a real one. Neither event carries an isTrusted difference or a source flag.
It can't see the shell's line-editing state, and bytes already sent can't be pulled back.
Any detector is a key-sequence heuristic that would eat real Backspace or Unicode.
C (brief buffering): rejected.
It breaks the no-debounce rule.
sharepoint
The rewrite fires on the next tone key, about 150 ms after a in the trace and possibly seconds later in real typing. You can't hold a safely for that long.
Squashing only the ~6 ms burst (·, DEL → nothing) changes how things look, not the result. It doesn't justify the risk.
D (upgrade xterm): rejected for now.
xterm handled the measured events correctly. An upgrade can't change what UniKey injects, and it would mean re-running the full IME, shortcut, touch and reconnect matrix.
Reconsider only if T0-C (below) places the defect in class (ii) and a specific upstream change fixes that exact path.
E (no Lantern code): the default outcome unless T0-C shows class (ii).
Class (i): document the UniKey setting or workaround; no Lantern code.
Class (ii): new focused design review, then code.
Class (iii): fix at the shell/PTY level (UTF-8 code page / shell environment). That reopens the "preserve backend" constraint and needs explicit review first. Don't patch around it in the frontend.
Protected paths stay safe. Under A, CJK composition, dead keys/AltGr, Ctrl/Cmd shortcuts, paste, touch/Gboard, latency and reconnect keep exactly today's paths.

MANDATORY_EVIDENCE_BEFORE_CODE

The two questions have different answers:
The as -> á trace is enough to invalidate the 229/one-claim design.
It is not enough to design any fix, because it shows no defect.
A real-keyboard reproduction of the user's defect is mandatory before any terminal code. That means the exact start -> stsar, or another observed wrong net result. If at least 50 physical attempts across the settings matrix don't reproduce it, close the terminal item as NOT_REPRODUCED with no code. Don't ship a speculative fix.
T0-C: capture these four channels at the same time for each reproduction:
Hook-level or raw key log, or a keyboard-viewer recording. This shows what UniKey injected or swallowed.
DOM key events.
WebSocket payloads.
PTY echo / screen.
Classify the result as (i), (ii) or (iii).
Environment to record:
shell identity (cmd / pwsh / PSReadLine / Git Bash)
chcp code page and LANG
UniKey spell-check and auto-restore on/off
UniKey's "always use clipboard for Unicode" on/off
typing speed
any UniKey option controlling the · placeholder (it's unverified whether the placeholder depends on a setting)
Contrasts for the same physical typing:
Windows Terminal/conhost running the same shell
a plain <textarea> in the same Chromium
Lantern
If the native console also corrupts, the cause isn't Lantern.
Re-run as -> á with auto-restore off and with the clipboard option on.
Re-classify the sta stress run with the hook-level log. Don't keep calling it harness loss without proof.
Fix the fixture encoding. The JSON shows DEL as U+FFFD replacement characters ("��"), while the evidence doc says \u007f. Store DEL as an escaped \u007f and verify the raw bytes before any replay test uses the fixture.
sharepoint
sharepoint
CJK/Korean/dead-key/Ctrl+C/V traces are needed only if T0-C leads to a code change. Under Option A they're regression checks on unchanged paths.

SPEC_PLAN_TASK_EDITS

spec.md
Status: "T0-A PASS. T0-B PASS as falsification of the Process/229 design. Terminal code is blocked on T0-C. The Markdown/Mermaid track is not blocked by the terminal gates."
Outcome, bullet 1: replace "fixes the reported…corruption" with "diagnoses the reported Windows UniKey/Telex terminal corruption; changes Lantern terminal code only if T0-C reproduces it and classifies it as (ii)".
Ownership, browser terminal input: "xterm owns all keydown paths, including keyCode-231 synthetic characters and IME-injected Backspace; Lantern adds no input interception."
FIX/ADD: delete "Trace-derived Windows desktop IME ownership".
Delete entirely: the "Terminal input contract" and "InputType contract" sections. That covers:
the Process/229 claim
the beforeinput/input consumers
compositionSendPending
the DEL-on-deleteContentBackward rule
Process-key recovery
Replace with "Terminal baseline contract": custom key handler unchanged; onData forwarded unchanged and in order; no suppression, compaction, buffering or delay of keyCode-231 or Backspace; any change needs T0-C class (ii) plus a new review.
Add the T0-C gate: physical reproduction, four-channel capture, native/textarea contrast, classification (i)/(ii)/(iii). If T0-C finds class (iii), backend/PTY scope must be explicitly reopened before any change.
Acceptance:
T-A1 → "T0-A, T0-B, T0-C recorded".
T-A2 → "physical start ×50 is exact, or the defect is classified with evidence".
T-A9 → "custom key handler returns true for keyCode 231 and Backspace; onData payloads unchanged".
Add T-A12: "UniKey as → net line shows á; payload sequence equals baseline".
Remove the 229-specific wording.
Non-goals: add "suppressing, compacting, or buffering IME-injected keystrokes".
plan.md
Phase 0: add T0-C after T0-B.
Delete "Terminal design after T0". Replace it with the (i)/(ii)/(iii) decision tree above.
T1 becomes baseline guard tests only.
Decouple the Markdown/Mermaid phases from the terminal gate.
Verification: the full IME manual matrix applies only if terminal code changes.
tasks.md
T0-B: exit = done (falsification), plus the fixture DEL-encoding fix.
New T0-C with the evidence steps listed above.
T1: replace with guard tests on the existing fake harness. These assert that the handler returns true for keyCode 231 and Backspace, and that onData payloads are forwarded unchanged and in order. Fix the fake textarea={} only if the tests need it.
sharepoint
T2: "BLOCKED. Conditional on T0-C class (ii) and a new review."
T3–T6: remove the dependency on the terminal T0-B gate.
T5 additions:
an explicit lodash-es/chevrotain reachability statement for 11.17.2 (the spec requires it; the evidence only gives npm audit)
sharepoint
the pin-rationale file
T8: static/terminal_scm.js stays unchanged unless T0-C finds class (ii).

MERMAID_DECISION

Accept the deliberate 11.17.2 pin, with residual-risk documentation. T5 introduces no real blocker:
0 critical, high or moderate findings.
The 2 low findings are the same KaTeX advisory (GHSA-238p-pmpm-9mq7), and 12.1.0 has them too.
12.1.0 is about 54% larger (5.49 MB vs 3.57 MB).
sharepoint
Upgrading gives no security benefit.
Conditions:
A pin-rationale/license file states the pin is intentional ("not latest"), and records the GHSA ID, bundled KaTeX 0.16.47, and the affected range <0.18.2.
The advisory needs an existing prototype-pollution foothold. Its reach is limited by securityLevel:"strict", the nonce CSP and no eval. Lantern must not enable any KaTeX trust option.
Re-audit trigger: bump when a Mermaid release ships KaTeX ≥0.18.2.
Explicitly record the lodash-es/chevrotain status for 11.17.2.
Count of import( = 0 is necessary but not sufficient. T7's zero-extra-request network log is the binding proof the bundle is self-contained.
Clarification only, not a scope reopen: the 100 ms responsiveness rule should state whether parse/compile of the 3.57 MB bundle counts. If it does, load Mermaid only when a mermaid fence is present, using the same nonce.

IMPLEMENTATION_GATE

Apply the spec/plan/tasks edits: retire the 229 contract and adopt the Option A baseline.
Markdown/Mermaid track proceeds on its own: T3 security tests green → T4 → T5 pin documentation → T6 → T7 → security sign-off and follow-up ticket.
Terminal track:
Fix the fixture encoding.
Run T0-C: physical reproduction, four-channel capture, native/textarea contrast, classification.
Not reproduced → close with no terminal code; only the T1 guard tests land.
Class (i) → document the UniKey workaround; no code.
Class (iii) → separate backend/PTY review.
Class (ii) → new focused design review, then T1 red tests from the real trace, then T2 code, then the full IME/touch/shortcut/reconnect matrix.
T8: full regression and scope check. xterm.js, lantern_ws.py and lantern_terminal.py stay unchanged unless step 3 explicitly approves a change.