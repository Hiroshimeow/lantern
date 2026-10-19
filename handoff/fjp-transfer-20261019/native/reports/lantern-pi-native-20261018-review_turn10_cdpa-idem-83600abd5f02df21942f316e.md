# REVIEW turn 10 — exact-client PI-T003 candidate + bounded-delta blocker

Task: cdpa-idem-83600abd5f02df21942f316e  
Role: REVIEW, turn 10  
Workspace: `E:\git-project\lantern\.wt\lantern-bot`  
Branch: `feat/lantern-bot`  
HEAD reviewed: `18a8743003c19a719f000166c42c66197e6e80f7`  
Main reviewed: `0eed7ed92dd758f64fbaecd8f958b568d29c9d32`  
Disposition: **ROUTE DEV**. The exact-client upstream snapshot mechanism is materially distinct and independently works for the tested real-Pi same-geometry snapshot + short ordered delta. The bounded-retention gap blocker is also real. However two acceptance-proof defects remain: the runnable “real Pi” exact-client case normalizes PTY CR/CRLF bytes, and the “public gap marker” test stops at TerminalManager instead of asserting the actual WS payload consumed by the browser.

No implementation edits were made by REVIEW.

## Inputs checked

- PLAN turn 6 in full, especially the exact-client snapshot, ordered post-S delta, and required truncation/gap rules.
- TEST turn 4 PI-T003 STOP evidence.
- DEV turn 10 handoff.
- Current untracked `tests/test_pi_reconnect_e2e.py`.
- `lantern/terminal.py` retention, `output_offset`, `_info()`, and `replay_one()`.
- `lantern/ws.py` `terminal_subscribe` / `terminal_replay` path.
- `static/terminal_scm.js` replay handling.
- Accepted PI-T002 native WinConPty capture and metadata.
- Temporary `@xterm/addon-serialize@0.14.0` package source/types.
- Loaded `ponytail-review` and `verification-before-completion`.

## Repository / rebase truth

Fresh REVIEW checks:
- branch `feat/lantern-bot`;
- `HEAD = 18a8743003c19a719f000166c42c66197e6e80f7`;
- `main = 0eed7ed92dd758f64fbaecd8f958b568d29c9d32`;
- `main...HEAD = 0/2`;
- feature committed diff relative to main remains exactly:
  - `A tests/test_pi_tui_e2e.py`
  - `M tests/test_terminal_ui.py`
- only current worktree candidate is `?? tests/test_pi_reconnect_e2e.py`;
- current candidate SHA256 = `607d52441961218a943781e86077740d5355c86f244b9a49f66023f2eb93b900`;
- `git diff --check` exit 0;
- no production Terminal/WS/Pi/UI/Markdown source is dirty.

The rebase performed by DEV is consistent with PLAN turn 6: no conflict is present, accepted feature paths remain isolated, and no cross-owner Markdown resolution appears in the feature diff.

## Fresh REVIEW verification

### Enabled PI-T003 candidate suite

`LANTERN_PI_REPLAY_E2E=1 uv run python -m unittest -v tests.test_pi_reconnect_e2e`

Fresh result:
- 6 tests;
- all 6 OK;
- 10.603 s;
- exit 0.

The six tests currently cover:
- bounded raw-tail non-losslessness;
- synthetic exact-vendored terminal edge states;
- preserved real-Pi server-headless serializer mismatch;
- exact-client real-Pi snapshot + deterministic short delta;
- bounded-retention characterization;
- deterministic manager seq/no-input-resend.

### Ordinary focused regressions

- `test_terminal_scm.py`: 15 tests, OK, 4.716 s.
- `test_terminal_ui.py`: 12 tests, OK, 2.136 s.
- `uv run python -m py_compile tests\test_pi_reconnect_e2e.py`: exit 0.
- `git diff --check`: exit 0.

### Full repository suite

Fresh REVIEW full discovery with the replay proof gate unset:
`uv run python -m unittest discover -s tests -q`

Result:
- 332 tests;
- OK;
- skipped=122;
- 52.558 s;
- process exit 0.
- Existing ResourceWarning lines for temporary HTTPError cleanup remain warnings, not unittest failures.

## Exact-client candidate — mechanism is distinct and works in the tested short-detach shape

The candidate genuinely differs from the failed server-headless representation:
- the accepted native Pi stream is parsed by the **exact repository vendored browser xterm**;
- `@xterm/addon-serialize@0.14.0` is loaded into that exact browser environment;
- the serializer snapshot is produced from that same exact client xterm instance;
- a fresh exact vendored xterm restores the snapshot;
- no private xterm buffer mutation, custom ANSI parser, hand-authored cell restore, permanent dependency, service, or production protocol is introduced.

The current test oracle compares visible cells/width, color values/modes, style flags, cursor x/y, active buffer, base/viewport, exposed modes and geometry. It also applies eight post-snapshot chunks including a split escape, style, cursor movement, DEC 1049 alternate-screen enter/write/exit, bracketed-paste mode, and normal-screen continuation.

Fresh enabled test reports exact equality for the candidate and its short delta at 120x40.

REVIEW additionally ran a disposable stricter oracle over **every active-buffer row, including scrollback**, while preserving the original capture's newline bytes. It independently found:
- exact-client snapshot: equal=true;
- full active buffer lengths: 56 / 56;
- cursor 0,35 / 0,35;
- base/view 16/16 / 16/16;
- snapshot artifact 5,708 bytes;
- after the same eight delta chunks: full-buffer equal=true;
- cursor 10,1 / 10,1;
- base/view remains 16/16;
- normal buffer restored after alternate-screen exit.

So the mature exact-client representation is a valid short-detach candidate at canonical geometry. Different-width equivalence remains disproven and must stay geometry-scoped.

## Finding R10-1 — runnable exact-client “real Pi stream” silently normalizes PTY CR/CRLF

**Location:** `tests/test_pi_reconnect_e2e.py:274` and the equivalent retained-capture read used by the exact-client helper.

**Contract violated:** PLAN turn 6 requires feeding the **accepted real Pi native stream** into the exact vendored client. Terminal output control bytes are semantic data; newline translation is not a benign text-format conversion.

**Reproducible evidence:** the retained capture bytes contain:
- 173 CRLF pairs;
- 364 CR bytes total;
- 173 LF bytes total.

But `Path.read_text(...)` uses universal-newline translation:
- resulting Python string has 0 CR;
- 364 LF;
- re-encoding is not byte-identical to the capture.

This materially changes terminal history behavior. DEV's retained exact-client evidence using the normalized stream reports base/view **294/294** and snapshot size **14,223 bytes**. REVIEW's byte-faithful/newline-preserving run of the same candidate reports base/view **16/16** and snapshot size **5,708 bytes**.

The candidate still passes under the exact original newline content (snapshot and delta both equal), so this finding does **not** invalidate the mechanism. It does invalidate the claim that the current runnable acceptance test is feeding the exact captured Pi stream.

**Required correction:** read the capture without universal-newline translation, preferably:
- `raw_path.read_bytes().decode("utf-8")`, since REVIEW verified the capture is strict UTF-8 and byte-round-trips exactly; or
- `open(..., newline="")` with strict UTF-8.

Then regenerate the turn-10 candidate evidence and keep the byte-faithful state as the acceptance result. Do not alter the capture itself.

## Bounded post-snapshot gap — blocker is real

Production retention behavior:
- `TerminalEntry.output_offset` increments when retained output is dropped.
- `TerminalManager._info()` does not expose it.
- `replay_one()` returns only `(_info, retained_output, seq)`.

With `max_output=8`, snapshot boundary seq 1 and an 11-character seq-2 output:
- retained replay becomes `DEFGHIJK`;
- returned seq is 2;
- metadata contains no output offset, oldest sequence, or internal-retention truncation marker.

Therefore a client holding snapshot boundary S cannot prove that all post-S bytes still exist.

The current WS path adds a top-level `truncated` flag, but that flag means something different: `lantern/ws.py` sets it only when already-retained output exceeds the active replay transport/display cap. It does not reflect `TerminalEntry.output_offset`.

REVIEW independently drove the actual `terminal_subscribe`/WS dispatch with the same internal-retention gap and observed:

`{"output":"DEFGHIJK","seq":2,"truncated":false,...}`

while the replay metadata still contained no offset/gap marker.

So the long-detach blocker is concrete: the current client-visible protocol can silently present an incomplete post-snapshot delta as non-truncated.

## Finding R10-2 — the acceptance test named “public gap marker” does not exercise the public WS replay payload

**Location:** `tests/test_pi_reconnect_e2e.py:459-481`.

**Contract violated:** PLAN turn 6 requires a safe/non-silent disposition for post-snapshot retention gaps. The browser's public replay surface is the `terminal_replay` WS payload, not the private `TerminalManager.replay_one()` tuple.

**Evidence:** the current test calls `manager.replay_one()` directly and asserts only that `meta` lacks `outputOffset`, `oldestSeq`, and `truncated`. It never observes the top-level WS `truncated` flag used by `static/terminal_scm.js`.

That omission matters because there **is** a public top-level `truncated` field, but it is false for this internal-retention gap. REVIEW reproduced exactly that public behavior through `dispatch()`.

**Required correction:** extend the proof through the existing `WebSocketHub/dispatch(... terminal_subscribe ...)` path and assert:
- replay output is the retained incomplete tail;
- seq is the latest seq;
- top-level `truncated is False` for the internal-retention loss;
- replay meta exposes no offset/oldest-seq/internal-gap marker.

Do not change production code in this correction. The purpose is to prove the blocker on the actual client-visible surface and to prevent the transport-cap `truncated` flag from being mistaken for a retention-gap signal.

## PI-T003 disposition

With the independent checks above:

- bounded raw-tail reset+write: **NOT LOSSLESS**;
- server-headless xterm serializer -> exact browser: **FAIL/STOP representation**;
- exact vendored-browser snapshot -> exact vendored-browser restore at same owner geometry: **works for tested real Pi state**, including byte-faithful capture in REVIEW;
- exact-client snapshot + complete ordered post-S delta: **works for tested short-detach case**;
- different-width equivalence: **false / geometry-scoped**;
- bounded post-snapshot delta gap with current public replay protocol: **unsafe / blocker**;
- full PI-T003: **PARTIAL, not PASS**.

The remaining gap is not permission to begin PI-T004/005/006. A short-detach PASS with no safe long-detach/gap disposition cannot satisfy PLAN turn 6.

## Required review dimensions

- **Over-engineering / YAGNI:** no production abstraction, custom ANSI/state engine, parallel terminal protocol, duplicate transcript/history store, permanent dependency, or service was introduced. Ponytail: **Lean already. Ship.** Production net reduction opportunity: 0 lines.
- **Scope drift:** none into Markdown fidelity/diff/Crop/Milkdown, Spec 001 T2, LAN/security, PI-T004+, PI-T005, PI-T006, bot UI, or live :9999/CDPA.
- **UX/end-user:** same-geometry short-detach reconstruction is promising; arbitrary viewer width remains unsupported. Browser F5 UX is still NOT_MEASURED.
- **Maintainability/module separation:** exact browser xterm remains the state parser; upstream serializer is used rather than a Lantern renderer. The blocker sits at the existing retained-output/public replay contract.
- **Scalability/resource:** an unbounded raw log is explicitly not proposed. CPU/RSS/latency and snapshot-frequency/cost remain NOT_MEASURED.
- **Native Pi parity:** accepted native Pi output is used, but FJP physical IME/AltGr/image paste and live /model-/goal-/extension parity remain incomplete.
- **Session/concurrency isolation:** deterministic seq accounting/no-input-resend is narrow proof only; one-writer/multiview ownership remains unaccepted.
- **Regression:** focused Terminal tests and the fresh 332-test repository suite are green.
- **Evidence honesty:** the current exact-client test needs byte-faithful capture input, and the gap test needs the actual WS payload before those claims are accepted as runnable proof.

## Preserved classifications

Spec 001:
- T1 COMPLETE / accepted / committed.
- T0-C NOT_MEASURED / deferred.
- T2 BLOCKED.
- no IME product fix.

Spec 004:
- PI-T002 narrow TerminalManager/WinConPty proof remains accepted.
- PI-T003 remains PARTIAL/BLOCKED as above.
- browser F5/live WS reconnect NOT_MEASURED.
- FJP physical input NOT_MEASURED.
- cursor visibility beyond exposed API NOT_MEASURED.
- PI-T004/005/006+ not started / blocked.
- overall objective NOT DONE.

## Route

**ROUTE DEV.** Correct R10-1 and R10-2 in the proof only:
1. preserve the real Pi capture bytes exactly in the exact-client candidate and regenerate evidence;
2. prove the bounded-retention gap on the actual WS `terminal_replay` payload.

Do not add a production gap marker, snapshot protocol, unbounded history, PI-T004/005/006 work, or any forbidden cross-owner implementation. After those proof corrections, return to REVIEW. If the same PARTIAL/blocker disposition remains, REVIEW should route PLAN for architecture/stop-gate disposition rather than downstream implementation.
