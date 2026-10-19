# PLAN turn 5 — accept PI-T002 proof, preserve it, route PI-T003 lossless replay gate

Task: `cdpa-idem-83600abd5f02df21942f316e`
Role: PLAN, turn 5
Workspace: `E:\git-project\lantern\.wt\lantern-bot`
Incoming handoff: `.plan/lantern-pi-native-20261018/lantern-pi-native-20261018-test_turn3_cdpa-idem-83600abd5f02df21942f316e.md`
Disposition: **ROUTE DEV.** PI-T002 now has clean independent REVIEW and TEST acceptance for its narrow measurable TerminalManager/WinConPty native-TUI proof. The next dependency gate is PI-T003 lossless replay feasibility. Do not start PI-T004+ session/WS/UI implementation until PI-T003 is independently accepted.

## Fresh repository truth

PLAN verified on G6 `desktop-b5e4iue-87cea2af`:

- Branch: `feat/lantern-bot`.
- HEAD: `c1ee6cc0d128451304172c84ec00574117091850`.
- Local `main`: `ffe3decb4469cff36bb98f8afd6ba8e9e89af089`.
- `main...HEAD = 0 1`.
- Committed feature diff against main remains only `M tests/test_terminal_ui.py`, the accepted Spec 001 T1 guard.
- Working tree has one new untracked acceptance file: `tests/test_pi_tui_e2e.py`.
- No production Terminal/WS/Pi/UI/Markdown source is dirty.
- Local main has not advanced since the accepted rebase.

The untracked file is not disposable scratch: REVIEW turn 5 and TEST turn 3 both independently accepted it as the runnable PI-T002 proof. Preserve it selectively; do not reset/stash/clean.

## Accepted evidence carried forward

### Spec 001 Terminal lane

- T1: **COMPLETE / independently accepted / committed**.
- T0-C physical >=50-attempt four-channel UniKey evidence: **NOT_MEASURED / deferred**.
- T2 product fix: **BLOCKED**.
- No IME/keyboard product fix, vendored xterm edit, input filtering/reordering/delay, or backend terminal change is authorized from current evidence.

### PI-T000 / PI-T001

- PI-T000 G6 legacy UX characterization: **accepted**.
- FJP browser/focus/IME/accessibility viewport acceptance: **NOT_MEASURED**.
- PI-T001 exact FJP 1.3.0 CLI/package/config/source characterization was independently supported by REVIEW turn 4:
  - installed Pi 1.3.0 and package identity;
  - configured package inventory;
  - native session/TUI CLI family;
  - built-ins including settings/model/new/resume/fork/hotkeys;
  - no built-in `/help` in installed 1.3.0 source;
  - UI extension APIs and image-paste/keybinding documentation;
  - no unsupported live `/goal` PASS claim.
- Live model/provider/custom-extension/goal/physical-input parity and PI-SC01 remain incomplete.

### PI-T002

REVIEW turn 5 resolved R4-1/R4-2 with no production source expansion:
- `tests/test_pi_tui_e2e.py` hosts real installed Pi 1.3.0 through production `TerminalManager(..., pty_factory=...)` and production `WinConPty`.
- Structured Pi argv remains inside the existing test injection seam; no shell `-Command` or `/C` wrapper.
- Manager owns create/input/resize/replay/list/kill.
- No Pi-only PTY service, ANSI emulator, command/model catalog, registry, protocol, production structured-spawn seam, replay implementation, or UI replacement was introduced.

Independent TEST turn 3 freshly ran:
- enabled native proof: 1 test PASS, real Pi TUI via TerminalManager/WinConPty;
- ordinary ungated run: correctly skipped, not falsely promoted to native PASS;
- `test_terminal_ui.py`: 12 PASS;
- `test_terminal_scm.py`: 15 PASS;
- syntax and `git diff --check`: PASS;
- workspace preservation: PASS.

Accepted PI-T002 claims are deliberately narrow:
- native Pi startup/local TUI;
- settings/resume/session surfaces;
- local shell marker;
- Unicode/bracketed-paste bytes;
- Alt/Ctrl byte routing without physical semantic claim;
- /new transition;
- manager resize metadata;
- retained-output generation/sequence metadata;
- cleanup.

Still **not accepted** from PI-T002:
- browser xterm -> WS -> manager end-to-end;
- FJP physical IME/AltGr/image paste;
- model/goal/custom-extension parity;
- reconnect/F5 equivalence;
- alternate-screen/cell/style/cursor/mode parity;
- multiple viewer widths;
- one-writer/session isolation;
- resource/performance/release acceptance.

## Next DEV turn

The substantive DEV task is **PI-T003 only**. Preservation/commit of the already accepted PI-T002 test is required housekeeping and does not authorize a second feature slice.

### A. Preserve accepted PI-T002 test before new proof work

1. Reconfirm:
   - `git diff --check`;
   - no tracked dirty files;
   - only untracked `tests/test_pi_tui_e2e.py`.
2. Selectively stage **only** `tests/test_pi_tui_e2e.py`; never `git add -A`.
3. Commit it with a narrow test/proof message. Do not amend the already accepted Spec 001 T1 commit.
4. Verify `main...HEAD` and a clean worktree after commit.
5. If local main unexpectedly advances before the next substantive source change, report the drift and rebase only under the existing safe rules; do not resolve a Markdown-owner conflict by guesswork.

Do not rerun the entire prior acceptance merely to justify the commit. A quick enabled PI-T002 smoke plus `git diff --check` is sufficient if unchanged.

### B. PI-T003 — evidence-first lossless replay proof

Goal: determine whether Lantern can detach/reconnect a native TUI without screen/state loss using mature xterm/upstream mechanisms. This is a **proof gate**, not session-registry/WS/UI implementation.

Create the smallest runnable `tests/test_pi_reconnect_e2e.py` plus ignored evidence helpers/artifacts only as needed.

#### Required baseline falsification

First prove what the existing mechanism can and cannot do:
- current `TerminalManager.replay_one()` returns a bounded raw-output tail + generation/sequence;
- current browser replay path resets xterm and writes retained bytes;
- do not assume this reconstructs a native TUI screen.

Use the repository's exact vendored xterm build for screen comparison. Do **not** write an ANSI parser.

At minimum compare a pre-detach reference state and a reconstructed state for:
- visible cells/text;
- cell attributes/styles needed for equivalence;
- cursor position/visibility where public xterm state permits;
- normal versus alternate screen/buffer;
- relevant terminal modes exposed by the actual xterm API;
- geometry.

The test must fail honestly if a required state cannot be captured or reconstructed.

#### Required stress cases

Exercise deterministic cases through the same terminal/xterm stack:
1. output split across chunk boundaries, including escape sequences split mid-sequence;
2. alternate-screen enter/write/cursor/exit behavior;
3. cursor movement/erase/style sequences;
4. bounded-tail truncation across a control sequence or before screen-establishing history;
5. resize before detach and reconnect at same geometry;
6. reconnect/viewer at a different width, proving whether state is reusable or must be geometry-scoped;
7. detach while output is still arriving, with ordered generation/sequence accounting and no duplicated input.

Use real Pi local/native UI states where legally available without paid-provider requests (for example native selectors/status) and a deterministic terminal fixture for terminal-state edge cases that Pi cannot reliably trigger locally. A deterministic fixture is acceptable for terminal semantics only if it runs through the same TerminalManager/xterm mechanisms; it must not masquerade as Pi feature parity.

Actual F5 browser automation is desirable only if a disposable browser/server harness can be used without touching `:9999`. If unavailable, mark browser F5 **NOT_MEASURED** and prove the transport/screen state contract below it; do not manufacture a PASS.

#### Upstream/native replay candidate evaluation

If raw-tail reset+write fails—and it is expected to be challenged, not presumed sufficient—evaluate mature xterm state mechanisms before inventing anything:
- inspect whether the exact vendored xterm exposes sufficient public buffer/state APIs;
- evaluate the version-compatible xterm headless/serialization mechanism already identified in prior planning as a candidate;
- if a temporary package is needed for feasibility, keep it outside the repository and do not modify `package.json`, lockfiles, vendored assets, or production dependencies in this proof turn;
- test known right-edge/cursor and alternate-screen cases explicitly rather than assuming serializer losslessness.

No permanent Node service, custom terminal state machine, custom ANSI emulator, duplicate history store, or HTML transcript is allowed.

#### Required decision from PI-T003

DEV must end with one of these evidence-backed outcomes:

**PASS candidate:** a mature mechanism reconstructs equivalent screen/cursor/mode state for the required deterministic cases at the supported geometry, with ordered no-resend detach/replay semantics. Record exactly what state artifact must later be owned by the server/session layer. Do not implement PI-T004/T006 yet.

**FAIL / STOP:** no mature mechanism available in the current stack can meet the equivalence contract, or equivalence breaks on alternate screen/cursor/modes/truncation/geometry. Preserve the failing runnable test/evidence and route REVIEW/PLAN. Do not bypass the gate with a custom parser or weaker acceptance.

A mere raw byte tail, matching visible text only, or successful `term.write()` without cell/cursor/mode comparison is **not** a PI-T003 PASS.

## Explicitly forbidden in this DEV turn

Do not implement:
- PI-T004 `PiSessionRegistry`;
- PI-T005 public production structured argv/env spawn seam;
- PI-T006 WS writer/resize ownership or replay protocol;
- PI-T007 lifecycle/restart;
- PI-T008+ bot UI/session picker/context;
- duplicate history/transcript/sessionStorage state;
- Markdown fidelity/diff/Crop/Milkdown/source changes;
- Spec 001 IME fix;
- new LAN/security/auth/policy/token controls.

Do not restart or attach to the live Lantern `:9999`; do not reset/stash/clean; do not modify/reload CDPA.

## REVIEW / TEST expectations after PI-T003

Independent REVIEW must evaluate:
- correctness of screen-equivalence oracle;
- whether the proof actually tests cells/styles/cursor/buffer/modes/geometry, not just strings;
- whether a mature upstream/native mechanism is used;
- YAGNI / no custom ANSI/state engine;
- scope drift and module ownership;
- future scalability/resource implications of the proposed state artifact;
- two-viewer geometry implications;
- no duplicated transcript/history/protocol;
- ordinary Terminal regression risk;
- whether missing browser/FJP/physical evidence is labeled NOT_MEASURED.

If REVIEW is clean, independent TEST must rerun the runnable PI-T003 proof and independently reproduce either PASS or the STOP failure. Only then may PLAN authorize PI-T005/T004 and later session/WS work.

## Classification after PLAN turn 5

- Spec 001 T1: **COMPLETE**.
- Spec 001 T0-C: **NOT_MEASURED / deferred**.
- Spec 001 T2: **BLOCKED**.
- PI-T000: **accepted G6 characterization; FJP browser/physical incomplete**.
- PI-T001: **exact FJP baseline materially supported; live parity matrix still incomplete for release**.
- PI-T002: **PASS for narrow TerminalManager/WinConPty proof; broader release parity incomplete**.
- PI-T003: **ACTIONABLE NOW / blocking proof gate**.
- PI-T004-T013: **DEPENDENT / not authorized until PI-T003 acceptance**.
- PI-T014/T015/T016: **INCOMPLETE / NOT_MEASURED where applicable**.
- Overall objective: **NOT DONE**.

No substantive source implementation was performed by PLAN turn 5. This required report is the only artifact written by PLAN.
