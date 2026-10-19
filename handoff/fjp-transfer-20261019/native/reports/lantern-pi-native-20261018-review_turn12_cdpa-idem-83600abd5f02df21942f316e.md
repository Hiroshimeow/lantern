# REVIEW turn 12 — verify TEST T5-1 snapshot byte-metric correction

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 12  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `18a8743003c19a719f000166c42c66197e6e80f7`  
Current local main: `1eeba4910d1e34e4045b514849b8625c9bb3234a`  
Disposition: **clean correction; ROUTE PLAN**. TEST T5-1 is resolved exactly. No functional replay classification changed, no new product defect was introduced, and PI-T003 remains PARTIAL/BLOCKED at the already-proven public retention-gap contract.

## Inputs checked

- TEST turn 5 finding T5-1.
- PLAN turn 7 acceptance boundary / future continuity decision.
- DEV turn 12 handoff.
- Current `tests/test_pi_reconnect_e2e.py`.
- Regenerated `.plan/lantern-pi-native-20261018/evidence-turn11/pi-t003-byte-faithful-and-ws-gap.json`.
- Current Git state / main drift.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / preservation truth

Fresh REVIEW checks:
- `HEAD = 18a8743003c19a719f000166c42c66197e6e80f7`.
- local `main = 1eeba4910d1e34e4045b514849b8625c9bb3234a`.
- `main...HEAD = 4/2`.
- only worktree candidate is `?? tests/test_pi_reconnect_e2e.py`.
- current candidate SHA256 = `dd396bed28f9a0587034a52963ab5cf2e8aa865e6c2383e88200538434f7b853`.
- `git diff --check`: exit 0.
- no production Terminal/WS/Pi/UI source is dirty.

Main continued to advance only in Markdown-owner work after the prior review:
- `18896d2 test(markdown): lock live edit and external change contracts`;
- `5afb9d0 test(markdown): cover missing-file recovery race`;
- `98056f7 test(markdown): freeze live document change contract`;
- `1eeba49 fix(markdown): show missing file status in preview`.

DEV correctly did not rebase this still-unaccepted proof during the TEST-directed metadata-only correction. No reset/stash/clean/merge/push, dependency/vendor change, live Lantern :9999 action, CDPA change, Markdown implementation by this lane, PI-T004/005/006 work, gap-marker implementation, or Spec 001 T2 fix occurred.

## T5-1 — snapshot size metric: RESOLVED

TEST turn 5 proved that the prior field:

`snapshotBytes: serialized.length`

was mislabeled because JavaScript string `.length` is UTF-16 code units, not UTF-8 bytes.

The corrected browser instrumentation is now:

`snapshotUtf8Bytes: new TextEncoder().encode(serialized).length`  
`snapshotUtf16CodeUnits: serialized.length`

The old ambiguous `snapshotBytes` field is absent from the current test/evidence.

The acceptance test now asserts:
- `snapshotUtf8Bytes == 6130`;
- `snapshotUtf16CodeUnits == 5708`;
- UTF-8 byte count is greater than UTF-16 code-unit count for this Unicode-bearing Pi snapshot.

The regenerated JSON records exactly:
- `snapshotUtf8Bytes: 6130`;
- `snapshotUtf16CodeUnits: 5708`.

A targeted search found no stale `snapshotBytes` claim in the current runnable proof or regenerated acceptance evidence.

## Fresh independent verification

REVIEW independently called the actual exact-client helper and observed:

- UTF-8 bytes = **6130**;
- UTF-16 code units = **5708**;
- exact-client browser equality = **true**;
- ordered delta equality = **true**.

The command asserted all four facts and exited 0.

Fresh enabled PI-T003 suite:

`LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -v tests.test_pi_reconnect_e2e`

Result:
- 6 tests;
- all 6 OK;
- 14.363 s;
- exit 0.

Fresh focused regressions:
- `test_terminal_scm.py`: 15 tests, OK, 5.480 s.
- `test_terminal_ui.py`: 12 tests, OK, 2.530 s.
- `git diff --check`: exit 0.

DEV also reported a 332-test full suite PASS after the correction. This REVIEW turn did not need to repeat that expensive whole-suite run because the change is one proof-metric expression plus assertions/evidence, and the corrected helper plus full PI-T003 gate and focused terminal regressions were freshly executed here.

## Functional acceptance boundary remains unchanged

The T5-1 correction is evidence labeling/measurement only. It does not change any terminal-state result.

Current supported PI-T003 facts remain:

- bounded raw-tail reset+write: **NOT LOSSLESS**;
- server-headless serializer -> exact vendored browser: **FAIL / STOP representation**;
- byte-faithful exact vendored-browser snapshot -> exact vendored-browser restore at canonical 120x40: **narrow PASS**;
- exact-client snapshot + complete ordered short post-S delta: **narrow PASS**;
- deterministic manager no-input-resend/sequence fixture: **narrow PASS**;
- different-width equivalence: **FALSE / geometry-scoped**;
- public `terminal_replay` under internal retained-output loss: **FAIL / unsafe**, because the incomplete suffix can be sent with latest seq and top-level `truncated=false` and without a retained-start watermark;
- browser F5/live reconnect: **NOT_MEASURED**;
- full PI-T003: **PARTIAL / BLOCKED**, not PASS.

The corrected artifact size for the exact-client snapshot is **6,130 UTF-8 bytes**; 5,708 is explicitly retained only as the UTF-16 code-unit count.

## Required review dimensions

- **Correctness:** T5-1 is fixed and independently reproduced. Functional replay equality/negative classifications are unchanged.
- **Over-engineering / YAGNI:** the fix is two explicit metrics and three assertions; no new abstraction or production code. Ponytail: **Lean already. Ship.**
- **Scope drift:** none into Markdown implementation, LAN/security, PI-T004+, PI-T005, PI-T006, session registry, writer/takeover behavior, or Spec 001 T2.
- **UX:** no new UI path; same-geometry short-detach feasibility and geometry dependence remain as previously measured.
- **Maintainability/module separation:** metric semantics are now explicit; upstream serializer and exact vendored xterm ownership remain unchanged.
- **Scalability/resource:** the corrected 6,130-byte snapshot metric is now trustworthy for this measured sample only. Snapshot distribution, CPU/RSS/latency and retention resource limits remain NOT_MEASURED.
- **Native Pi parity:** byte-faithful accepted Pi stream remains the source. FJP physical IME/AltGr/image paste and live model/goal/custom extension parity remain incomplete.
- **Concurrency isolation:** no new claim; sequence/no-resend fixture does not establish one-writer/multiview policy.
- **Regression/performance:** enabled replay proof and focused terminal regressions are fresh green; no production runtime path changed.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed.
- T0-C NOT_MEASURED / deferred.
- T2 BLOCKED.
- no IME product fix.

Spec 004:
- PI-T002 accepted.
- PI-T003 PARTIAL / BLOCKED on public replay continuity gap.
- PI-T004/005/006+ not started / blocked pending PLAN disposition.
- browser F5/live reconnect, physical FJP input, multi-view ownership and resource acceptance remain INCOMPLETE/NOT_MEASURED.
- overall objective NOT DONE.

## Findings

No concrete reproducible defect remains in DEV turn 12. TEST T5-1 is resolved exactly; no additional repair is warranted.

## Route

**ROUTE PLAN.** The proof metadata is corrected and the prior functional acceptance boundary is stable. PLAN should resume the architecture decision recorded in turn 7: PI-T003 must remain PARTIAL/BLOCKED until a permitted minimal continuity-watermark slice makes retained-output gaps safe and non-silent and is independently reviewed/tested. Do not route into PI-T004/005/006 or promote the current proof to full PI-T003 PASS.
