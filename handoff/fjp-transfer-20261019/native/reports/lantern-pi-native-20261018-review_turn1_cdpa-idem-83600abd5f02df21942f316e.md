# REVIEW turn 1 — Spec 001 T1 guard (independent)

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 1  
Workspace: `E:\git-project\lantern\.wt\lantern-bot` (G6 device)  
Branch: `feat/lantern-bot`  
HEAD: `b2ffd886795840f0db570b8c07a913b406e68e80`; `main...HEAD = 0/0`.  
Disposition: **ACCEPT source-level REVIEW of Slice A, ROUTE TEST** for a separately owned independent TEST gate. Not a Spec 004 acceptance or integration clearance. No commit in this review.

## Sources independently inspected

- `AGENTS.md`, PLAN turn 1 and DEV turn 1 handoffs; `specs/001-terminal-ime-markdown-export/{spec,plan,tasks}.md`; `specs/004-pi-native-harness/{spec,plan,tasks,research,CHAT_UX_AUDIT_2026-10-17}.md`; `specs/002-lantern-foundation/verification.md`.
- Worktree `git status`, full `git diff -- tests/test_terminal_ui.py`, `git diff --check`, actual `tests/test_terminal_ui.py` Node fake-xterm test around lines 391–500, and `static/terminal_scm.js` around lines 22–25, 48–49, 115–116.
- Loaded device skills `ponytail-review` (avoid speculative/duplicated machinery) and `verification-before-completion` (fresh command evidence).
- The original archival private `.plan` UniKey physical trace is unavailable; historical T0-A/T0-B status is sourced to spec, not newly verified as physical evidence.

## Diff/contract review (Slice A only)

- **IMPLEMENTED:** `tests/test_terminal_ui.py:445–446` retains the real callback arguments passed by production `attachCustomKeyEventHandler` and `onData`. Fake `textarea={}` is unchanged. This is exactly the needed fake-harness interface, not new keyboard logic.
- **IMPLEMENTED:** `tests/test_terminal_ui.py:470–480` asserts both callbacks were registered, acknowledges `terminal_created` so the fake is genuinely out of `pending`, then invokes keydown 231 and Backspace 8 and asserts both return `true` (xterm ownership). This matches the preserved production custom handler in `static/terminal_scm.js:115`.
- **IMPLEMENTED:** `tests/test_terminal_ui.py:481–490` uses the expected `['a', '·', DEL, DEL, 'á']` code points `[97,183,127,127,225]`; invokes the captured `onData` callback; asserts the WebSocket `terminal_input.data` sequence is exact and ordered, with no parallel `terminal_key` message. It runs the actual `static/terminal_scm.js` within the Node fake environment. No separate JSON trace fixture was added; the raw-JSON DEL-escape fixture rule is not invoked.
- **PRESERVED:** Only `tests/test_terminal_ui.py` differs from HEAD: 25 insertions, 3 deletions. No terminal product logic, vendored xterm, PTY, WS, application, Pi RPC, chatbot, security, LAN, Markdown parser/diff/Crop/Milkdown, dependency, or live process modifications. `git diff --name-only` returns this one test file.
- **Boundary:** These assertions characterize Lantern's registered callbacks and forwarding, **not** browser xterm synthesis, a physical FJP UniKey trace, PTY rendering, or net terminal screen result. That is intentionally below the T0-C gate. Spec 001 T0-C remains **NOT_MEASURED/deferred**; T2 is **BLOCKED** and must not be implemented on this evidence.
- **004 ownership:** This slice neither implements nor purports to verify PI-T000–PI-T016. Native interactive Pi via existing TerminalManager/WS/xterm, opaque independent session IDs, one writer/resize owner, scoped multitab output, lossless replay, F5 detach/reattach, Pi/extension parity, accessible dock/fullscreen, context/filesystem integration, localhost/LAN constraints and normal Terminal regression remain later task gates. No duplicate protocol/catalog/history/session mechanism was introduced.
- **YAGNI / maintainability:** Reuses one existing fake terminal and its actual production callbacks, adding no package, helper layer, parser, transport or parallel implementation (net complexity acceptable; no supported lines to delete without weakening assertions). The new guard is embedded in a test still named `test_reopening_existing_terminal_refocuses_xterm` (`tests/test_terminal_ui.py:391`); discoverability could improve with a descriptive test name in a future maintenance pass, but this is **non-blocking**, and duplication of the Node scaffold solely to rename it would be worse.
- **UI/UX, scalability/performance, isolation:** This test-only diff has no runtime/UI cost or altered concurrency/ownership; future Spec 004 UX/viewport/IME/scaling/isolation/parity *cannot* be signed off from this diff. Mature upstream/native Pi and xterm replay choices remain to be measured in Phase 0 rather than invented here.

## Fresh independent verification on G6 (this REVIEW turn)

Commands used `uv run python -m unittest discover -s tests -p PATTERN -q`, with these exact patterns:
- `test_terminal_ui.py`: **12 tests, OK**, process exit 0, 2.295 s.
- `test_terminal_scm.py`: **15 tests, OK**, process exit 0, 4.660 s.
- `test_pi_chat.py`: **15 tests, OK**, process exit 0, 1.909 s.
- `test_pi_chat_ws.py`: **8 tests, OK**, process exit 0, 0.206 s.
- `test_chat_ui.py`: **4 tests, OK**, process exit 0, 0.021 s.

**54 focused tests, all OK;** focused failed-suite count 0. `git diff --check` exit 0. `git status --short --branch`: `## feat/lantern-bot...origin/feat/lantern-bot`; ` M tests/test_terminal_ui.py` only. `git rev-list --left-right --count main...HEAD`: `0 0`. Node `v22.22.2`, uv `0.11.8`. No full repository test suite, real-browser/PTY test, FJP manual typing test, measured resource/performance benchmark, or Pi-native acceptance was run in this review; these remain **INCOMPLETE** / **NOT_MEASURED**, never PASS.

## Findings, decision, and next hop

**No material reproducible implementation defect** found in Slice A. The guard is sufficient for the narrow Spec 001 T1 *fake-xterm / Lantern-layer* contract, not for physical T0-C or any Spec 004 criterion. No code edits, git commit, reset/stash/clean, live Lantern :9999 restart, CDPA interaction, or unrelated work were made by REVIEW.

**ROUTE TEST** because the contract requires a separate independent TEST acceptance before accepting/committing this DEV slice. TEST should independently inspect the five-payload/231/Backspace guard and rerun the focused tests; classify missing physical T0-C and later Pi parity as NOT_MEASURED, not as regressions blocking T1. After separate TEST sign-off, return to PLAN to coordinate an accepted selective test-file commit and next dependency-ordered Spec 004 characterization (PI-T000/001), without bypassing the Pi replay proof stop gate.
