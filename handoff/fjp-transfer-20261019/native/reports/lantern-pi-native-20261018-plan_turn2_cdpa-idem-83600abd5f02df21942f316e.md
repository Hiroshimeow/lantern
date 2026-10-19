# PLAN turn 2 — accept Spec 001 T1, restore branch freshness, continue Spec 004

Task: `cdpa-idem-83600abd5f02df21942f316e`
Role: PLAN, turn 2
Workspace: `E:\git-project\lantern\.wt\lantern-bot`
Incoming TEST handoff: `.plan/lantern-pi-native-20261018/lantern-pi-native-20261018-test_turn1_cdpa-idem-83600abd5f02df21942f316e.md`
Disposition: **ROUTE DEV.** Spec 001 T1 is independently accepted and complete. Spec 004 remains materially incomplete and has legally actionable work. Do not route DONE.

## Durable acceptance carried forward

Independent REVIEW turn 1 accepted the Slice A test-only change with no material defect. Independent TEST turn 1 then re-inspected the production callback path and executed the accepted guard, reporting:

- `test_terminal_ui.py`: 12/12 PASS, including explicit discovery of the guard-bearing test.
- `test_terminal_scm.py`: 15/15 PASS.
- `test_pi_chat.py`: 15/15 PASS.
- `test_pi_chat_ws.py`: 8/8 PASS.
- `test_chat_ui.py`: 4/4 PASS.
- Focused total: **54/54 PASS**.
- `git diff --check`: PASS.
- Changed tracked path: **only `tests/test_terminal_ui.py`**; no staged files and no untracked product files at TEST handoff.
- Accepted behavior: the fake xterm captures the actual callbacks registered by `static/terminal_scm.js`; keydown 231 and Backspace remain xterm-owned; the exact `a, ·, DEL, DEL, á` sequence is forwarded through `terminal_input.data` unchanged and in order; no parallel `terminal_key` is created.
- No terminal product code, PTY/WS source, vendored xterm, Markdown implementation, Pi runtime, UI, dependency, security policy, live process, or CDPA change was introduced.

Therefore **Spec 001 T1 = COMPLETE / ACCEPTED**. Do not repeat REVIEW/TEST for the same unchanged diff merely because main advanced.

Spec 001 invariants remain unchanged:
- T0-A historical inspection: PRESERVE.
- T0-B historical physical trace: PRESERVE as falsification evidence only.
- T0-C physical >=50-attempt four-channel evidence: **NOT_MEASURED / DEFERRED**.
- T2 terminal product fix: **BLOCKED** unless T0-C first reproduces and classifies a Lantern DOM-to-payload fault and a new focused review authorizes a fix.
- Markdown T3-T7 remain outside this team's implementation ownership.

## Fresh repository truth on PLAN turn 2

Verified on G6 device `desktop-b5e4iue-87cea2af`:

- Branch: `feat/lantern-bot`.
- Feature HEAD: `b2ffd886795840f0db570b8c07a913b406e68e80`.
- Worktree: one tracked modification, `tests/test_terminal_ui.py`, the already accepted T1 guard.
- Current local `main`: `ffe3decb4469cff36bb98f8afd6ba8e9e89af089`.
- `main...HEAD = 2 0`: feature is two commits behind current local main.
- Main-only commits:
  - `3bfaa2e test(markdown): define typed preview CSP profiles`
  - `ffe3dec test(markdown): harden preview CSP evidence`
- Main-only tracked changes are confined to `specs/001-terminal-ime-markdown-export/{spec,plan,tasks}.md`, `tests/test_plugin.py`, and `tests/test_preview_csp_e2e.py`.
- Diff inspection shows the spec changes are the Markdown preview CSP/profile contract and security acceptance wording. They do **not** alter Terminal T0/T1/T2 obligations or the accepted T1 guard path. `tests/test_terminal_ui.py` is not touched by those main commits.

This is a freshness/integration condition, not a new defect in accepted Slice A. Preserve the accepted test; do not reset/stash/clean it.

## Remaining owned scope

Spec 004 remains incomplete. No evidence yet proves the required native interactive Pi TUI, native slash/provider/settings/skills/extensions parity, opaque independent sessions, one writer+resize owner with read-only viewers, two-session isolation, F5 detach/reattach without resend, lossless screen-state replay, native session history reopen, editor-side dock/expand/fullscreen UX, filesystem-based Markdown edits, FJP/Edge/IME parity, performance/resource ceilings, or normal Terminal regression under the new architecture.

The existing legacy RPC/chat tests remain baseline regressions only. They are not Spec 004 acceptance.

The dependency and stop-gate contract from PLAN turn 1 remains in force:

1. Pi must run as native interactive TUI through the existing PTY/ConPTY + xterm stack, with structured argv and native Pi session semantics; no replacement transcript/model/command catalog.
2. Session identity is opaque and independent of tab/file. Exactly one input/resize owner; multiple viewers; explicit takeover; session/generation isolation.
3. F5/close tab detaches, does not resend or silently kill. Restart may reopen native saved history but must not pretend an in-flight process survived.
4. A bounded raw ANSI tail is not accepted as lossless TUI replay. Phase-0 proof must cover screen cells/styles/cursor, normal+alternate screen, relevant modes, broken escape boundaries and viewer geometry. No hand-written ANSI emulator or permanent duplicate terminal service.
5. Pi edits the real file through native filesystem tools. Do not edit Markdown fidelity/diff/Crop/Milkdown/source implementation except a separately justified narrow shared loading/contract boundary.
6. Preserve Spec 001 Option A exactly; no UniKey-specific filtering/reordering/delay and no terminal product fix without T0-C.
7. No new LAN exposure/security/policy/token quota/auth/sandbox behavior without separate approval.

## Next DEV turn — smallest actionable work

**ROUTE DEV** with the following sequence. Administrative commit/rebase work does not count as a substantive Spec 004 subtask; the substantive cap remains two coherent items.

### A. Preserve the already accepted Slice A and restore branch freshness

1. Reconfirm `git diff --check` and that the only pre-commit tracked diff is `tests/test_terminal_ui.py`.
2. Selectively stage **only** `tests/test_terminal_ui.py`; never `git add -A`.
3. Commit the independently accepted T1 guard with a narrow test-focused commit message. Do not amend unrelated commits.
4. Rebase `feat/lantern-bot` onto current local `main` only after the accepted test is committed and the worktree is clean. Do not reset, stash, clean, merge, push, or touch the live Lantern `:9999`.
5. If main advances again before rebase, use the newest local main after verifying its changes do not alter Terminal/Pi ownership. If a real conflict appears, stop the rebase safely and route PLAN rather than resolving across Markdown ownership by guesswork.
6. After rebase, rerun the narrow T1 regression at minimum: `test_terminal_ui.py` and `test_terminal_scm.py`; record the new HEAD/base relationship and exact commit hash.

This step preserves accepted evidence while satisfying the repository rule to develop from latest main.

### B. Continue Spec 004 with **PI-T000 + PI-T001 only**

These are the next two coherent substantive items.

- **PI-T000 UX baseline:** characterize the existing bot/editor layout at 390/1280/1920 and record focus/keyboard/viewport problems. Use disposable/ephemeral serving only; never restart or attach to the user's live `:9999`. If the required FJP browser path is unavailable, mark that part **NOT_MEASURED**, not PASS.
- **PI-T001 native Pi CLI/config baseline:** on the actual FJP host, record installed Pi version, interactive/TUI flags and defaults, native session options, provider/model/settings/help/goal/new/fork/resume behavior, installed skills/extensions and any version-supported native event/session hooks. Do not send a paid AI prompt merely to discover commands. G6 Pi 1.3.0 help may be used only as provisional comparison, never as FJP acceptance.
- If FJP remains unavailable or its shell broker is broken, preserve **NOT_MEASURED** for FJP-specific evidence and still record all locally actionable source/CLI characterization. That external gap does **not** justify an IME fix, fake Pi parity, or DONE.
- Do not modify production Pi/Terminal/WS/UI source during T000/T001 characterization unless a separate later DEV slice is explicitly routed after evidence. No Markdown implementation edits.

After PI-T000/T001 evidence, route independent REVIEW for scope/UX/native-parity/YAGNI/upstream assessment, then TEST for genuine acceptance of what was actually measurable. Only after that return to PLAN for the PI-T002/T003 PTY/replay proof slice.

## Classification after this PLAN turn

- Spec 001 T1: **COMPLETE / independently accepted**, pending selective commit/rebase housekeeping only.
- Spec 001 T0-C: **NOT_MEASURED / deferred**.
- Spec 001 T2: **BLOCKED**.
- Spec 004 PI-T000/T001: **ACTIONABLE / INCOMPLETE**.
- Spec 004 PI-T002/T003: **ACTIONABLE next after T000/T001 acceptance; not yet proven**.
- Spec 004 PI-T004-T013: **DEPENDENT / not yet authorized for implementation until PTY/replay proof passes**.
- Spec 004 PI-T014/T015/T016: **INCOMPLETE / release acceptance not yet measured**.
- Overall team objective: **NOT DONE**.

No PLAN source implementation changes were made in this turn. The required report is the only PLAN artifact written.
