# TEST turn 5 — PI-T003 exact-client continuity proof independently rerun; byte-count evidence defect

Task: `cdpa-idem-83600abd5f02df21942f316e`  
Role: TEST, turn 5  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Incoming: `.plan/lantern-pi-native-20261018/lantern-pi-native-20261018-plan_turn7_cdpa-idem-83600abd5f02df21942f316e.md`  
Disposition: **ROUTE DEV (proof metadata defect T5-1)** under the role continuation contract. The six substantive PI-T003 proof categories reproduce, including the exact-client same-geometry positive and the real public retention-gap negative; however, the untracked proof labels a JavaScript UTF-16 code-unit count as **bytes**. Independent browser instrumentation measured **6,130 actual UTF-8 bytes**, not the reported 5,708. No product runtime defect is newly found. PI-T003 remains **PARTIAL / BLOCKED**, not PASS.

## Environment and immutable candidate identity

- Verified owned device: `desktop-b5e4iue-87cea2af`, hostname `DESKTOP-B5E4IUE`, Windows `Microsoft Windows NT 10.0.26100.0`; device-broker working directory resolved exactly to `E:\git-project\lantern\.wt\lantern-bot`.
- Verified `uv 0.11.8`, `node v22.22.2`, `Python 3.14.1`; local clock observed `2026-10-19T01:36:09.8316376+09:00` initially and `2026-10-19T01:40:10.1805520+09:00` on final inspection.
- Branch `feat/lantern-bot`, HEAD `18a8743003c19a719f000166c42c66197e6e80f7`.
- Untracked candidate `tests/test_pi_reconnect_e2e.py`: 25,818 bytes; SHA256 `a1fd3f7a1ee6edc5344d5e1361bc25b6b03fe16e0ae41b96e5920960df716298` (unchanged from REVIEW turn 11 and independently rechecked at the end).
- Exact repository browser script `static/vendor/xterm.js`: SHA256 `f68403f92e5552d69fab42d98571c8e16b6f03cba3e5233b4c8a99d3eb9d4653`.
- Scoped `@xterm/headless@6.0.0` and `@xterm/addon-serialize@0.14.0` packages available outside the repository at `%TEMP%\lantern-pi-replay-proof6\node_modules`.
- Browser proof uses disposable headless Edge HTML + exact repository vendored xterm, not the running Lantern browser/server. No paid AI requests.

## Commands and expected/actual results

All commands ran in the verified workspace on the verified device, without editing production or proof source.

### A. Identity, scope, branch movement

```powershell
Get-Location
hostname
[System.Environment]::OSVersion.VersionString
Get-Date -Format o
uv --version
node --version
uv run python --version
git branch --show-current
git rev-parse HEAD
git rev-parse main
git merge-base main HEAD
git rev-list --left-right --count main...HEAD
git status --short
git diff --name-only
git diff --check
git log --oneline HEAD..main
git log --oneline main..HEAD
(Get-Item tests/test_pi_reconnect_e2e.py).Length
certutil -hashfile tests/test_pi_reconnect_e2e.py SHA256
certutil -hashfile static/vendor/xterm.js SHA256
```

Expected: same reviewed proof hash; only an untracked proof, no dirty tracked production/dependencies/Markdown; concurrent main work kept intact. Actual: **PASS preservation**. `git diff --name-only` empty; `git diff --check` exit 0; only `?? tests/test_pi_reconnect_e2e.py`. HEAD unchanged. The local `main` advanced during TEST from `5afb9d095e3fbbd124c700cdfa6eb9719eaf73b7` to **`98056f7a55383441518b16b4dbe816490ca6abbc`**; current `main...HEAD = 3 left / 2 right`, merge base `0eed7ed92dd758f64fbaecd8f958b568d29c9d32`. Main-only commits:
- `18896d2 test(markdown): lock live edit and external change contracts`;
- `5afb9d0 test(markdown): cover missing-file recovery race`;
- `98056f7 test(markdown): freeze live document change contract` (modifies only `tests/test_live_markdown_e2e.py`).

No active feature-lane replay/Pi/Terminal/WS source conflict; no rebase/reset/stash/clean/merge/push attempted. No custom ANSI parser or private xterm buffer mutation in the proof; it uses upstream serializer and public browser xterm APIs. No permanent addon dependency, replay service, registry, duplicate terminal history store, or session/writer protocol has been added.

### B. Gated PI-T003 acceptance proof

```powershell
$env:LANTERN_PI_REPLAY_E2E='1'
uv run python -m unittest -v tests.test_pi_reconnect_e2e
$code=$LASTEXITCODE
Write-Output ('PI_T003_PROOF_EXIT='+$code)
exit $code
```

Expected: each positive category must pass, each known-negative representation must be asserted as false, and the public WS gap must be affirmatively reproduced. Actual: **6 executed / 6 OK / 0 skips**, 12.731 seconds, **exit 0**:
1. `test_current_raw_tail_replay_is_not_lossless` — OK; bounded tail is **NOT LOSSLESS**; complete-stream split escape, normal/alternate/alt-exit, styles, modes, same-geometry resize are narrower diagnostics; width mismatch explicitly false.
2. `test_upstream_serializer_is_lossless_for_tested_same_geometry_state` — OK for **synthetic headless-to-headless only**, not native Pi equivalence.
3. `test_real_pi_headless_serializer_mismatch_is_preserved` — OK as a **negative**: server-headless serializer -> exact vendored browser **equal=false**.
4. `test_real_pi_exact_client_snapshot_round_trips` — OK: exact vendored browser -> upstream serializer -> exact vendored browser **equal=true** at 120x40 under visible cell width/fg/bg/color-mode/styles, cursor, normal/alternate buffer, base/viewport, public modes and geometry oracle. Complete ordered eight-chunk post-snapshot deterministic delta also **equal=true**.
5. `test_public_ws_replay_cannot_signal_internal_retention_gap` — OK as a **negative**: public WS replay silently lacks retention-loss indication.
6. `test_manager_detach_replay_orders_output_without_resending_input` — OK: ordered seq 1..4, one sent input, no replay input resend, manager resize tracked in deterministic PTY fixture only.

A green suite is **not** a PI-T003 PASS: it intentionally asserts that two replay representations and the public gap are unsafe.

### C. Independent real-Pi browser-oracle diagnostic

TEST additionally piped a one-shot Python script through `uv run python -` (not a tracked file) that called both actual cross-stack helpers, read the native capture bytes, asserted the two opposing representations, and emitted the reported reference/reconstruction summaries:

```python
import json
from tests import test_pi_reconnect_e2e as t
p=t.ROOT / '.plan' / 'lantern-pi-native-20261018' / 'evidence-turn4' / 'pi-t002-g6-winconpty-raw.txt'
data=p.read_bytes()
head=t._real_pi_headless_cross_stack_results()
exact=t._real_pi_exact_client_results()
assert len(data)==25168 and data.count(b'\r\n')==173
assert head['provenance']['captureByteExact'] and exact['provenance']['captureByteExact']
assert not head['browser']['equal'] and exact['browser']['equal'] and exact['delta']['equal']
assert exact['browser']['ref']==exact['browser']['recon']
assert exact['delta']['ref']==exact['delta']['recon']
assert exact['delta']['chunks']==8
print(json.dumps({'capture':{'bytes':len(data),'crlf_pairs':data.count(b'\r\n')},'headless':head,'exact_client':exact},sort_keys=True))
```

Execution form: `$py = @' ...code above... '@; $py | uv run python -; exit $LASTEXITCODE`. Actual **exit 0**.

Expected/actual:
- native Pi capture **25,168 bytes**, **173 CRLF pairs**, strict UTF-8 capture round trip true, offline/native installed Pi UI provenance flags all true.
- server-headless serialization at 120x40: reference normal-buffer cursor **(0,35)**, base/viewport **16/16**; reconstruct cursor **(3,35)**, base/viewport **20/20**, `equal=false`.
- exact-browser serialization at 120x40: reference and reconstruction normal buffer, cursor **(0,35)**, base/viewport **16/16**, modes identical, full oracle `equal=true`.
- eight ordered delta chunks: reference and reconstruction normal buffer, cursor **(10,1)**, base/viewport **16/16**, modes identical, full oracle `equal=true`.
- Existing code's `browser.snapshotBytes` JSON entry prints `5708`; **do not interpret this as true byte length**; finding T5-1 below.

### D. Independent public production-path gap and display-cap diagnostic

Static production inspection, independently of the test assertions:
- `lantern/terminal.py:319-330`: `TerminalEntry.output_offset` exists; `:440-445`: retention truncation increments offset by `drop` after slicing `output` to `max_output`.
- `lantern/terminal.py:547-570`: `_info()` omits offset, and `replay_one()` returns exactly `(meta, output, seq)`; no retained-start position.
- `lantern/ws.py:424-439`: `terminal_subscribe` calls `replay_one`, computes `truncated = len(output) > _MAX_ACTIVE_REPLAY_CHARS` (normal cap **800,000 characters**), sends suffix and `seq`, not internal retention start.
- `static/terminal_scm.js:9,24-25,46`: replay resets/writes tail, applies displayed `truncated` banner, and merges buffered output by `seq`; there is no byte/codepoint/stream-start continuity marker or comparison to a snapshot position.

To avoid relying solely on the existing test, TEST ran a separate, non-persistent Python diagnostic through `$py | uv run python -`, constructing `TerminalManager(max_output=8)`, `WebSocketHub`, a disposable `FakePty` and `Peer`, emitting `SNAP` then `ABCDEFGHIJK`, then calling real `dispatch(... terminal_subscribe ...)`. It also temporarily patched only `ws._MAX_ACTIVE_REPLAY_CHARS=5` **within this disposable Python process**, reverting automatically afterwards, to independently distinguish the WS cap from earlier manager loss.

Key exact assertions in that diagnostic:
```python
assert entry.output_offset == 7
assert (output,seq)==('DEFGHIJK',2)
assert not any(k in meta for k in ('outputOffset','oldestSeq','truncated'))
assert replay['output']=='DEFGHIJK' and replay['seq']==2 and replay['truncated'] is False
assert not any(k in replay for k in ('outputOffset','retainedStart','startOffset','oldestSeq'))
# under with patch.object(ws, '_MAX_ACTIVE_REPLAY_CHARS', 5):
assert capped_replay['output']=='GHIJK' and capped_replay['truncated'] is True
assert capped_replay['seq']==2 and 'outputOffset' not in capped_replay['meta']
```

Actual: **`INDEPENDENT_PUBLIC_GAP_EXIT=0`**. Internal offset = **7**, public `seq=2`; normal replay `output="DEFGHIJK"`, `truncated=false`, no offset. When WS display cap is 5, output `"GHIJK"`, `truncated=true`, still no offset. Thus public `truncated` cannot detect earlier TerminalManager retention loss; seq cannot determine if a chunk was partly discarded.

### E. Focused regressions, syntax, gated-off semantics

```powershell
Remove-Item Env:LANTERN_PI_REPLAY_E2E -ErrorAction SilentlyContinue
uv run python -m unittest discover -s tests -p test_terminal_scm.py -q
uv run python -m unittest discover -s tests -p test_terminal_ui.py -q
uv run python -m py_compile tests/test_pi_reconnect_e2e.py
git diff --check
uv run python -m unittest -v tests.test_pi_reconnect_e2e
```

Actual:
- `test_terminal_scm.py`: **15 tests OK**, 5.783 s, exit 0.
- `test_terminal_ui.py`: **12 tests OK**, 2.322 s, exit 0.
- replay proof `py_compile`: exit 0.
- `git diff --check`: exit 0.
- without explicit gate, replay suite reports **6 SKIPPED**, exit 0; this is **not** evidence of PI-T003 PASS.
- Full repository suite **not independently repeated** (focused drift has not changed production Terminal/Pi paths); any full-suite claim from DEV/REVIEW remains prior-role evidence.

## T5-1: Reproduced test artifact size metric bug (non-equivalence behavior unaffected)

`tests/test_pi_reconnect_e2e.py:347` produces `snapshotBytes:serialized.length` inside JavaScript. `.length` is a UTF-16 code-unit count, **not** serialized UTF-8 byte length.

TEST instrumented **only the disposable headless-Edge HTML generated in a temporary directory**, without changing the tracked or untracked proof file, by wrapping `Path.write_text` for the ephemeral `compare.html` and adding browser-side properties:
```python
import json
from pathlib import Path
from unittest.mock import patch
from tests import test_pi_reconnect_e2e as t
original=Path.write_text
def record_utf8_size(self, text, *args, **kwargs):
    if self.name=='compare.html' and 'snapshotBytes:serialized.length' in text:
        text=text.replace(
            'snapshotBytes:serialized.length',
            'snapshotBytes:serialized.length,snapshotUtf8Bytes:new TextEncoder().encode(serialized).length,snapshotCodepoints:[...serialized].length'
        )
    return original(self, text, *args, **kwargs)
with patch.object(Path, 'write_text', record_utf8_size):
    result=t._real_pi_exact_client_results()
print(json.dumps({'snapshot_sizes': {k:v for k,v in result['browser'].items() if k.startswith('snapshot')},'browser_equal':result['browser']['equal'],'delta_equal':result['delta']['equal']},sort_keys=True))
```

Execution form: `$py = @' ...code above... '@; $py | uv run python -; exit $LASTEXITCODE`. Actual **`TEMP_HTML_BYTE_SIZE_PROBE_EXIT=0`**:

```json
{"browser_equal":true,"delta_equal":true,"snapshot_sizes":{"snapshotBytes":5708,"snapshotCodepoints":5707,"snapshotUtf8Bytes":6130}}
```

**Reproducible discrepancy: 5,708 code units vs 6,130 UTF-8 bytes (422 bytes / ~7.4% larger)** for this native-Pi snapshot. This invalidates the review/plan wording that the exact-client artifact is "5,708 bytes"; it does **not** invalidate terminal-state equivalence nor the eight-delta reconstruction. This is an **implementation defect in proof evidence labeling**, not a new production replay bug.

**DEV remediation only**: replace/rename the mislabeled measure with a true browser-side `TextEncoder().encode(serialized).length` UTF-8 byte count and, if useful, explicitly retain `utf16CodeUnits`; add/adjust a Unicode-bearing assertion and regenerate proof evidence. Keep all production Terminal/WS/UI/session/Markdown source untouched in this correction. Once fixed, independent REVIEW/TEST can accept the corrected evidence and route PLAN to the already identified continuity-watermark architecture decision. Do not treat this as permission for PI-T004/005/006.

## Acceptance classifications / next route

- **Measured PASS, narrowly**: exact vendored-client Pi 120x40 byte-faithful snapshot restore; complete ordered eight-chunk post-snapshot short delta; deterministic manager no-input-resend; synthetic same-geometry cases; focused ordinary Terminal regressions.
- **Measured FAIL**: bounded raw-tail replay losslessness; server-headless real-Pi -> exact browser equivalence; geometry-independent restore; existing public retained-output-gap signaling (internal offset 7 exists but is hidden from client).
- **PI-T003 remains PARTIAL / BLOCKED** until safe public replay continuity metadata and an independently accepted end-to-end proof exist; PI-T004/005/006 still blocked.
- **Not measured / incomplete**: browser F5/live reconnect, physical FJP UniKey/IME/AltGr/image paste, live model/goal/custom extension parity, terminal cursor visibility beyond public oracle, multi-writer/viewer ownership, resource/CPU/RSS/latency, full feature release.
- **Spec 001**: T1 previously accepted and committed; T0-C physical >=50-attempt four-channel evidence NOT_MEASURED/deferred; T2 BLOCKED. No IME fix performed.
- **Preservation**: no production code changed, no CDPA or Lantern :9999 action, no disallowed Git mutation; only the originally untracked proof remains.

**ROUTE DEV** specifically because independent TEST found a reproducible defect in proof output metadata (`snapshotBytes`); the functional acceptance boundary itself reproduces exactly. Correct the evidence label/measurement without changing replay architecture, then obtain renewed independent review/acceptance before PLAN authorizes the continuity seam. Never route DONE.
