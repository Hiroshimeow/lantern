# REVIEW turn 9 — PI-T003 real-Pi cross-stack replay STOP result

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 9  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `9d39a0f08fcf73678f3cf9b3033cfb96beb76863`  
Disposition: **clean REVIEW of a reproduced PI-T003 FAIL/STOP; ROUTE TEST** for independent reproduction of the stop condition before PLAN disposition. No implementation edits made by REVIEW.

## Inputs independently checked

- PLAN turn 5 PI-T003 contract.
- REVIEW turn 8 R8-1/R8-2.
- DEV turn 9 handoff.
- Current `tests/test_pi_reconnect_e2e.py` in full.
- Accepted PI-T002 real WinConPty capture:
  - `.plan/.../evidence-turn4/pi-t002-g6-winconpty-raw.txt`
  - `.plan/.../evidence-turn4/pi-t002-g6-winconpty.json`
- Scoped xterm 6 serializer source/options.
- Exact vendored browser xterm path `static/vendor/xterm.js`.
- Current Git state and preservation boundaries.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / scope truth

Fresh REVIEW observations:
- `HEAD = 9d39a0f08fcf73678f3cf9b3033cfb96beb76863`.
- local `main = 1e3b77cda8d1d7e31019ccc79c38a6f63516817b`.
- `main...HEAD = 1/2`.
- only uncommitted candidate remains `?? tests/test_pi_reconnect_e2e.py`.
- no production Terminal/WS/Pi/UI/Markdown source is dirty.
- `package.json`, `uv.lock`, and `package-lock.json` are clean.
- `git diff --check` passes.
- the external main-only commit is Markdown/Mermaid owner work and does not alter the PI-T003 terminal proof contract.

Preserved Spec 001 boundary:
- T1 COMPLETE / independently accepted / committed.
- T0-C physical >=50-attempt evidence NOT_MEASURED / deferred.
- T2 BLOCKED.
- no terminal/IME product fix.

No PI-T004/005/006 implementation, registry, WS ownership protocol, production replay service, bot UI replacement, custom ANSI engine, Markdown implementation, LAN/security policy, reset/stash/clean/merge/push, live Lantern :9999 restart, or CDPA action was introduced.

## R8-1 — real Pi native stream: RESOLVED

The new `test_real_pi_native_stream_serializes_into_exact_vendored_xterm` uses the already accepted PI-T002 native WinConPty capture and asserts provenance:
- argv includes `--offline`;
- argv resolves the installed `@earendil-works/pi-coding-agent`;
- captured stream contains native Pi UI markers including settings/resume/new/session/status surfaces.

No paid AI prompt is used.

This satisfies the PLAN requirement to exercise a real legally available Pi-native state rather than only synthetic ANSI fixtures.

## R8-2 — exact vendored-browser reconstruction: RESOLVED as a failing gate

The new cross-stack path:
1. reads the accepted real Pi native stream;
2. feeds it into `@xterm/headless@6.0.0` at canonical 120x40;
3. serializes with `@xterm/addon-serialize@0.14.0` and `scrollback=8000`;
4. loads the repository's exact `static/vendor/xterm.js` in headless Edge;
5. creates two vendored browser terminals at 120x40:
   - reference receives the original Pi stream;
   - reconstruction receives the serializer artifact;
6. compares cells/width, colors/color modes, style flags, cursor x/y, active buffer, base/viewport, exposed modes, and geometry.

The mature serializer candidate **does not reproduce the exact real-Pi vendored-browser state**.

Fresh REVIEW enabled run:
`LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -v tests.test_pi_reconnect_e2e`

Actual:
- `test_current_raw_tail_replay_is_not_lossless`: PASS
- `test_manager_detach_replay_orders_output_without_resending_input`: PASS
- `test_upstream_serializer_is_lossless_for_tested_same_geometry_state`: PASS
- `test_real_pi_native_stream_serializes_into_exact_vendored_xterm`: **FAIL**
- 4 tests total, 3 pass / 1 fail
- enabled-suite exit **1**
- failure is exactly the required equality assertion.

Observed cross-stack mismatch from the normal proof path:
- reference: 120x40, normal buffer, cursor 0,35, base/viewport 294/294;
- reconstruction: 120x40, normal buffer, cursor 3,35, base/viewport 20/20;
- exposed modes match, including bracketed paste and send-focus.

This is a required acceptance failure, not an incidental test break.

## Independent check against newline-normalization false positive

Python `Path.read_text()` performs universal-newline normalization on the retained capture. REVIEW therefore independently reproduced the cross-stack proof while preserving the capture's exact decoded byte/newline content instead of using `Path.read_text()`.

That independent reproduction still returned:
- `equal=false`;
- reference cursor 0,35;
- reconstruction cursor 3,35;
- reference base/viewport 16/16;
- reconstruction base/viewport 20/20;
- exposed modes still match.

So newline normalization can change scrollback magnitude in this fixture, but it **does not explain away the serializer failure**. The cursor and screen-state mismatch persists with exact newline preservation.

This strengthens the STOP classification rather than introducing a new implementation defect.

## Serializer option sanity check

REVIEW inspected the installed `@xterm/addon-serialize@0.14.0` source/types. Its `scrollback` option serializes up to the requested number of available scrollback rows, and DEV requests 8000. The real capture is much smaller than that bound. No missing obvious scrollback option explains the failure.

The earlier synthetic same-geometry cases still pass and cross-width remains false. Those are useful diagnostics but cannot override the real-Pi exact-client failure.

## Other fresh verification

Ordinary gated replay suite with `LANTERN_PI_REPLAY_E2E` unset:
- 4 tests
- all skipped with the explicit environment gate
- exit 0.

Focused Terminal SCM regression:
- 15 tests
- OK
- 5.709 s
- exit 0.

`uv run python -m py_compile tests\test_pi_reconnect_e2e.py`: exit 0.  
`git diff --check`: exit 0.

DEV also reports an ordinary full-suite PASS with the replay proof gated off. REVIEW does not need that ordinary PASS to classify the enabled PI-T003 gate: the enabled proof is intentionally red and independently reproduced here.

## Required review dimensions

- **Correctness:** the test now exercises the actual required real-Pi -> headless serializer -> exact vendored-browser path and fails at exact state equality. STOP condition is reproducible.
- **Over-engineering/YAGNI:** proof-only code uses upstream xterm 6 packages and exact vendored xterm; no production abstraction or custom ANSI parser exists. Ponytail: **Lean already. Ship.**
- **Scope drift:** none into PI-T004+, PI-T005/006, Markdown implementation, LAN/security, or bot UI.
- **UX/end-user:** exact same-geometry state already fails; arbitrary-width equivalence was previously disproven. No reconnect UX can be accepted on this representation.
- **Maintainability/module ownership:** no duplicate owner implemented. The proposed serializer remains only a failed feasibility candidate.
- **Scalability/extensibility:** no snapshot architecture is implemented after a failed proof gate.
- **Native/upstream alternatives:** mature upstream serializer was tested against real Pi and exact client, not replaced by a custom engine.
- **Session/concurrency isolation:** still INCOMPLETE; sequence-boundary fixture does not establish writer/viewer policy.
- **Regression/performance:** ordinary focused terminal regression is green; CPU/RSS/latency remain NOT_MEASURED.
- **Acceptance honesty:** browser F5/live WS reconnect, physical FJP input, cursor visibility beyond exposed API, session ownership and PI-T004+ remain INCOMPLETE/NOT_MEASURED.

## Findings

No new DEV implementation defect is present. The material result is the **expected, evidence-backed PI-T003 FAIL/STOP** required by the PLAN gate. Routing back to DEV would invite bypassing the stop condition, which is forbidden.

## Route

**ROUTE TEST.** Independent TEST must reproduce the enabled PI-T003 failure and verify that the failure is specifically the real-Pi exact-vendored-browser equivalence gate, while the synthetic/transport cases and ordinary terminal regressions retain their stated classifications. If TEST reproduces the STOP, PLAN must decide the project path; PI-T004/005/006 must not begin under the current replay representation.
