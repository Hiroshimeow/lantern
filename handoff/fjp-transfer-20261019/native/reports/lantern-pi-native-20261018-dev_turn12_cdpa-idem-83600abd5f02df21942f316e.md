# DEV turn 12 — fix TEST T5-1 snapshot size metric only

Task: cdpa-idem-83600abd5f02df21942f316e
Workspace: E:\git-project\lantern\.wt\lantern-bot
Branch: feat/lantern-bot
Disposition: REVIEW

## Scope

Read TEST turn 5 and verified T5-1 against tests/test_pi_reconnect_e2e.py. The defect was exactly as reported: browser-side serialized.length was labeled snapshotBytes even though it is a UTF-16 code-unit count.

No production Terminal/WS/Pi/UI/session/Markdown code changed. No PI-T004/005/006 work, no gap-marker implementation, no dependency/vendor change, no reset/stash/clean/merge/push, no Lantern :9999 action, and no CDPA change.

## TDD correction

RED:
- extended test_real_pi_exact_client_snapshot_round_trips to require snapshotUtf8Bytes=6130 and snapshotUtf16CodeUnits=5708, with UTF-8 bytes strictly greater than UTF-16 code units for this Unicode-bearing Pi snapshot
- targeted run failed with KeyError snapshotUtf8Bytes

GREEN:
- replaced mislabeled snapshotBytes: serialized.length with:
  - snapshotUtf8Bytes: new TextEncoder().encode(serialized).length
  - snapshotUtf16CodeUnits: serialized.length
- targeted test then passed

## Regenerated evidence

Re-ran .plan/lantern-pi-native-20261018/evidence-turn11/regenerate_evidence.py.

Fresh exact-client metrics:
- snapshotUtf8Bytes: 6130
- snapshotUtf16CodeUnits: 5708
- browser equal=true
- ordered delta equal=true
- byte-faithful capture provenance remains true

All prior PI-T003 classifications remain unchanged:
- bounded raw-tail replay: NOT LOSSLESS
- server-headless real-Pi -> exact browser: FAIL/STOP representation
- exact vendored-client same-geometry snapshot: narrow PASS
- complete ordered short delta: narrow PASS
- public retained-output gap signaling: FAIL/BLOCKER
- full PI-T003: PARTIAL/BLOCKED, not PASS

## Verification actually run

Targeted corrected test:
- LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -v tests.test_pi_reconnect_e2e.PiReconnectProof.test_real_pi_exact_client_snapshot_round_trips
- 1 test OK

Full enabled PI-T003 proof:
- 6 tests OK in 13.314s

Gate-off semantics:
- 6 tests skipped, exit 0

Focused regressions:
- test_terminal_scm.py: 15 tests OK in 5.075s
- test_terminal_ui.py: 12 tests OK in 3.149s
- py_compile tests/test_pi_reconnect_e2e.py: exit 0
- git diff --check: exit 0

Fresh full repository suite:
- Ran 332 tests in 73.673s
- OK (skipped=122)
- existing ResourceWarning HTTPError cleanup warnings only
- evidence: .plan/lantern-pi-native-20261018/evidence-turn12-full.err

## Changed files

Untracked acceptance candidate:
- tests/test_pi_reconnect_e2e.py

Ignored evidence/report only:
- evidence-turn11 regenerated JSON now contains correct UTF-8/code-unit metrics
- evidence-turn12-full.*
- this report

No production source or repository dependency file is dirty.

## Final repository state

- HEAD: 18a8743003c19a719f000166c42c66197e6e80f7
- main: 98056f7a55383441518b16b4dbe816490ca6abbc
- main...HEAD = 3/2
- only worktree candidate: ?? tests/test_pi_reconnect_e2e.py
- candidate SHA256: dd396bed28f9a0587034a52963ab5cf2e8aa865e6c2383e88200538434f7b853
- package.json / uv.lock / package-lock.json diff: none

Main remains concurrently ahead by unrelated Markdown-owner commits. This TEST-directed turn authorized only proof metadata correction, so DEV did not rebase again.

## Preserved boundaries

Spec 001:
- T1 COMPLETE / accepted / committed
- T0-C NOT_MEASURED / deferred
- T2 BLOCKED
- no IME product fix

Spec 004:
- PI-T002 accepted
- PI-T003 remains PARTIAL/BLOCKED
- PI-T004/005/006+ remain blocked/not started
- browser F5/live reconnect, physical FJP input, multi-view ownership, resource acceptance remain INCOMPLETE/NOT_MEASURED

## REVIEW request

Independent REVIEW should verify the corrected UTF-8 byte metric and that no functional acceptance classification changed. If accepted, route according to the existing PI-T003 PARTIAL/BLOCKED architecture stop gate; do not route DONE.

Route: REVIEW.