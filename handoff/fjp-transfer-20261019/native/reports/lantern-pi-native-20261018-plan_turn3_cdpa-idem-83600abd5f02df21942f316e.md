# PLAN turn 3 — accept corrected PI-T000/T001 review, route independent TEST

Task: `cdpa-idem-83600abd5f02df21942f316e`
Role: PLAN, turn 3
Workspace: `E:\git-project\lantern\.wt\lantern-bot`
Incoming handoff: `.plan/lantern-pi-native-20261018/lantern-pi-native-20261018-review_turn3_cdpa-idem-83600abd5f02df21942f316e.md`
Disposition: **ROUTE TEST.** REVIEW turn 3 is clean and resolves the only two evidence defects from REVIEW turn 2. The measurable PI-T000/T001 characterization still requires independent TEST acceptance before PLAN may authorize PI-T002/T003.

## Verified repository state

Fresh PLAN check on G6 `desktop-b5e4iue-87cea2af`:

- Branch: `feat/lantern-bot`.
- HEAD: `c1ee6cc0d128451304172c84ec00574117091850`.
- Local `main`: `ffe3decb4469cff36bb98f8afd6ba8e9e89af089`.
- `main...HEAD = 0 1`.
- Tracked worktree is clean.
- `main..HEAD` contains only the already accepted Spec 001 T1 guard in `tests/test_terminal_ui.py`.
- No product Terminal/WS/Pi/UI/Markdown implementation change was introduced by DEV turn 3 or REVIEW turn 3.

The branch remains one feature commit ahead of local main. No reset, stash, clean, merge, push, live Lantern `:9999` restart, or CDPA action is authorized.

## REVIEW turn 3 disposition carried forward

REVIEW turn 3 independently verified both required evidence corrections and found no new implementation defect:

1. **R2-1 RESOLVED:** the legacy chatbot bottom-sheet breakpoint is correctly recorded as **<=700px**, matching `static/chatbot.css`.
2. **R2-2 RESOLVED:** G6 Pi 1.3.0 no longer falsely claims a built-in `/help` slash command. The evidence now records the installed built-ins actually verified and keeps FJP `/help` **NOT_MEASURED**.

REVIEW also confirmed:
- no speculative session registry, replay model, command catalog, compatibility shim, dependency, or product source change;
- FJP-specific Pi/browser/physical acceptance remains NOT_MEASURED;
- concurrency/session isolation, native Pi replay, performance, viewport accessibility, and release parity remain INCOMPLETE;
- the accepted Spec 001 T1 commit remains complete and unchanged.

Therefore there is no DEV correction to route now. The smallest required role is independent TEST.

## Independent TEST assignment — PI-T000/T001 characterization only

TEST must validate the evidence actually claimed, without broadening it into native Pi release acceptance.

### PI-T000 — G6 legacy UX characterization

Independently inspect the retained artifacts in:
`.plan/lantern-pi-native-20261018/evidence-turn2/`

At minimum verify:
- the three screenshot artifacts exist, are non-empty, and correspond to the recorded 390x844, 1280x900, and 1920x1080 viewports;
- the screenshots show the existing legacy HTML chatbot, not a native Pi TUI;
- source truth matches the corrected evidence:
  - desktop drawer width is bounded by the existing chatbot CSS;
  - chatbot bottom-sheet breakpoint is **<=700px**;
  - opening the chatbot focuses its input;
  - the source editor does not reserve desktop drawer width;
  - legacy provider/model/transcript/sessionStorage ownership exists;
  - no native dock/expand/fullscreen Pi TUI exists;
  - compose hint versus actual Enter-key behavior is recorded accurately.
- G6 evidence is classified only as characterization. It does not prove FJP, IME, accessibility, or native Pi parity.

Do not restart or attach to the user's live Lantern `:9999`. Re-launching a browser/server is unnecessary if the durable screenshots plus source are sufficient to independently verify the claims; do not redo completed substantive work merely for duplication.

### PI-T001 — G6 provisional native Pi CLI/config characterization

Independently verify the retained characterization against the installed G6 Pi 1.3.0 package/CLI/source where practical, without sending a paid AI prompt.

Required facts to validate:
- installed Pi version/package identity;
- native interactive/TUI/session-related CLI flags recorded in the evidence;
- the verified native slash-command surface includes the commands actually present in installed 1.3.0;
- installed 1.3.0 built-in slash-command source does **not** expose `/help`;
- versioned native session transition hooks recorded by DEV exist as claimed;
- `pi-goal-x` installation is not incorrectly promoted to live `/goal` availability for this worktree;
- FJP-specific Pi version/config/extensions/`/help` remain **NOT_MEASURED** because the FJP shell broker failure prevented execution.

TEST must not invent Lantern shims, command catalogs, compatibility behavior, or architectural decisions from the provisional G6 data.

### Regression / workspace checks

Because this slice is evidence-only, TEST should verify:
- tracked worktree remains clean;
- feature diff against main remains only the accepted `tests/test_terminal_ui.py` guard;
- no new Terminal/WS/Pi/UI/Markdown product source has appeared;
- no TEST action mutates source, rebases, merges, pushes, resets, stashes, cleans, restarts `:9999`, or modifies/reloads CDPA.

The already accepted Spec 001 T1 unit/runtime checks need not be repeated unless TEST observes branch/source drift that could invalidate them.

## Acceptance boundaries

A TEST PASS for this turn means only:
- corrected PI-T000 G6 legacy UX characterization is durable and accurate;
- corrected PI-T001 G6 provisional Pi 1.3.0 characterization is durable and accurate;
- missing FJP evidence is explicitly preserved as NOT_MEASURED;
- no unsupported native Pi/session/replay/release claim is made.

A TEST PASS does **not** satisfy PI-T002/T003 or any later implementation/release gate.

After independent TEST acceptance, return to PLAN. PLAN may then authorize the next two coherent subtasks, **PI-T002 native PTY parity proof + PI-T003 lossless replay proof**, with the existing stop gate: no session registry/WS/UI implementation may proceed if native TUI/replay equivalence cannot be demonstrated without a duplicate ANSI/terminal stack.

## Current classification

- Spec 001 T1: **COMPLETE / independently accepted / committed**.
- Spec 001 T0-C: **NOT_MEASURED / deferred**.
- Spec 001 T2: **BLOCKED**.
- PI-T000: **PARTIALLY MEASURED on G6; awaiting independent TEST acceptance; FJP NOT_MEASURED**.
- PI-T001: **G6 provisional characterization corrected; awaiting independent TEST acceptance; FJP NOT_MEASURED**.
- PI-T002/T003: **INCOMPLETE; next actionable proof slice only after TEST returns to PLAN**.
- PI-T004-T013: **DEPENDENT / not yet authorized**.
- PI-T014/T015/T016: **INCOMPLETE / NOT_MEASURED where applicable**.
- Overall objective: **NOT DONE**.

No substantive source implementation was performed by PLAN turn 3. This required PLAN report is the only artifact written by this role.
