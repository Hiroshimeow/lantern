# DEV turn 1 — Spec 001 T1 guard; handoff to independent REVIEW
Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
HEAD (uncommitted): b2ffd886795840f0db570b8c07a913b406e68e80
Disposition: REVIEW; one coherent T1 test-only item implemented, not yet independently accepted or committed.

## Contract and source inspection
Read AGENTS.md and current PLAN handoff; Spec 001 spec/plan/tasks; Spec 004 spec/plan/tasks/research/CHAT_UX_AUDIT; Spec 002 verification. Inspected existing tests/test_terminal_ui.py Node fake-xterm harness and static/terminal_scm.js ownership, callbacks and terminal_created/pending flow. Worktree was clean and at specified baseline before edit. Existing linked worktree preserved.

## Changed file and implementation
Only tests/test_terminal_ui.py.
- FakeTerminal.attachCustomKeyEventHandler now retains the actual callback; onData retains actual callback without changing textarea mock.
- Existing reopen/focus test exercises real static/terminal_scm.js through Node. It acknowledges terminal_created to transition fake terminal from pending to ready, invokes custom handler with keyCode 231 and synthetic Backspace keydown and expects true for both, then invokes onData with ['a','·','\\u007f','\\u007f','á']. It checks code points [97,183,127,127,225], exact ordered websocket terminal_input.data and zero duplicate terminal_key messages.
- No terminal/PTY/UI/Markdown/Pi product source, vendored xterm, infrastructure, package or private original evidence changed. No speculative UniKey fix.

## Test-first evidence
RED: uv run python -m unittest discover -s tests -p test_terminal_ui.py -q: 12 run, 1 expected failure (callback undefined because fake did not retain callbacks).
Intermediate RED: after callback retention, same command 12 run, 1 failure (handler false while terminal still pending); corrected fake harness test setup by acknowledging terminal_created before exercising a ready terminal.
GREEN: same command 12 run, OK, then reran after adding explicit codepoint assertion and all five focused suites passed.

Exact final checks on G6 (uv run python -m unittest discover -s tests -p PATTERN -q):
- test_terminal_ui.py: 12 OK
- test_terminal_scm.py: 15 OK
- test_pi_chat.py: 15 OK
- test_pi_chat_ws.py: 8 OK
- test_chat_ui.py: 4 OK
- git diff --check: exit 0
- git diff --name-only: tests/test_terminal_ui.py only
- git status --short: M tests/test_terminal_ui.py only
Total 54 tests OK, no full repository suite executed. These are fake-xterm Lantern-layer guards, not real browser/UniKey/hardware confirmation.

## Review request / risks
Independent REVIEW must verify precise keydown ownership/onData ordering assertions, harness realism and test effectiveness, no YAGNI/over-engineering, scope drift, UI/UX impact, maintainability, module ownership/separation, scalability, native Pi/upstream parity boundaries, session/concurrency isolation, regression/performance, and acceptance sufficiency. Independent TEST still required before commit; DEV intentionally did not commit unaccepted slice. Reviewer should consider whether enhancing the existing focus test rather than adding a separately named guard test is sufficiently discoverable. No change to production static/terminal_scm.js.

Spec 001 T0-C physical 50+ UniKey start attempts and four channels: NOT_MEASURED, deferred. Spec 001 T2: BLOCKED. Spec 004 PI-T000 through T016: incomplete; no native TUI, FJP parity, viewport, replay or resource acceptance claimed. Proceed to Slice B only after T1 REVIEW/TEST acceptance under PLAN. No restart :9999, no CDPA modification, no reset/stash/clean, no commit/merge/push.

## Idempotent DEV re-entry verification
The identical task/hop was reissued with the same PLAN handoff. Verified on G6 that HEAD is still b2ffd886795840f0db570b8c07a913b406e68e80 and only tests/test_terminal_ui.py is modified; no independent review or acceptance report exists in the task .plan directory. Do not rerun or broaden implementation, do not commit before REVIEW/TEST acceptance. On this re-entry, freshly reran the exact five focused uv unittest suites: 12, 15, 15, 8, and 4 tests respectively, all OK (54 total); git diff --check exit 0; git status --short reports only M tests/test_terminal_ui.py. Earlier TDD RED evidence is historical to the initial DEV execution, not newly repeated. Full tests, physical UniKey FJP, native Pi parity and browser UX remain not measured.

Route: REVIEW.
