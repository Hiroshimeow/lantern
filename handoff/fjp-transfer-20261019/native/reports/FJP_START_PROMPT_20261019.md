You are continuing the Lantern Native/Pi Terminal lane on FJP.

Workspace:
C:\Users\DuongNH66\Desktop\git\lantern-bot

Branch / implementation checkpoint (handoff commits may be on top):
feat/lantern-bot
3635c2e9010ecaf952fc1e2ad4bc3f01d9981964

Read FIRST, in order:
1. AGENTS.md
2. docs/architecture/FOUNDATION_CURRENT.md
3. docs/architecture/LANTERN_SYSTEM_ARCHITECTURE.md
4. docs/architecture/LANTERN_FUNCTION_FLOWS.md
5. specs/001-terminal-ime-markdown-export/spec.md
6. specs/001-terminal-ime-markdown-export/plan.md
7. specs/001-terminal-ime-markdown-export/tasks.md
8. specs/002-lantern-foundation/README.md
9. specs/002-lantern-foundation/spec.md
10. specs/002-lantern-foundation/plan.md
11. specs/002-lantern-foundation/tasks.md
12. specs/004-pi-native-harness/spec.md
13. specs/004-pi-native-harness/plan.md
14. specs/004-pi-native-harness/tasks.md
15. specs/004-pi-native-harness/CHAT_UX_AUDIT_2026-10-17.md
16. handoff/fjp-transfer-20261019/native/reports/FJP_TRANSFER_HANDOFF_20261019.md
17. handoff/fjp-transfer-20261019/native/reports/lantern-pi-native-20261018-dev_turn45_cdpa-idem-83600abd5f02df21942f316e.md
18. handoff/fjp-transfer-20261019/native/reports/lantern-pi-native-20261018-review_turn40_cdpa-idem-83600abd5f02df21942f316e.md
19. handoff/fjp-transfer-20261019/native/reports/lantern-pi-native-20261018-review_turn39_cdpa-idem-83600abd5f02df21942f316e.md

Mission:
Continue all legally actionable Native/Pi Terminal work remaining from Spec 001 Terminal/IME lane and Spec 004, plus shared Foundation work explicitly required by those contracts.

Ownership:
- Own native Pi session lifecycle, Terminal/PTY integration, terminal WebSocket contracts, replay/continuity, native UX/harness work.
- Do NOT take over Markdown fidelity/diff/Crop/Milkdown work except an explicitly justified shared contract boundary.
- Spec 003 is Markdown ownership.

Known RED at transfer:
Run:
py -3.12 -m unittest -q tests.test_pi_sessions tests.test_terminal_scm tests.test_pi_ws_contract

Expected transfer baseline:
70 tests, exactly 1 failure:
tests.test_pi_ws_contract.PiWsContractTests.test_current_writer_takeover_is_rejected_without_state_change

The current writer self-takeover must not be accepted as a mutating takeover. Existing review blocker R39-1 requires pi_session_takeover to be viewer-only/non-mutating for the current writer. Reproduce this RED first; then make the smallest existing-owner fix and drive GREEN.

Engineering rules:
- systematic root-cause debugging first
- TDD: RED -> minimal fix -> GREEN
- no speculative orchestration/state framework
- preserve replay continuity, generation and ownership ordering invariants
- preserve unrelated dirty/untracked work
- never reset/stash/clean/rewrite history
- report only checks actually run
- missing evidence is INCOMPLETE/NOT_MEASURED, never PASS

Historical CDPA note:
The old G6 task is BLOCKED at pre-send DEV122 and has no hop122 ledger/receipt. Hop121 is already accepted/routed and must never be replayed. Do not revive that workflow; continue source work from the FJP checkpoint/reports.

First actions:
1. Verify git status/HEAD.
2. Re-run the focused 70-test transfer suite.
3. Trace why current-writer takeover mutates/accepts instead of remaining viewer-only.
4. Fix with the smallest owner change and independent tests.
5. Continue remaining Spec 001/004 dependency-ordered items.
