# TEST turn 4 — PI-T003 real-Pi replay FAIL/STOP independently reproduced

Task: `cdpa-idem-83600abd5f02df21942f316e`  
Role: TEST, turn 4  
Incoming: `.plan/lantern-pi-native-20261018/lantern-pi-native-20261018-review_turn9_cdpa-idem-83600abd5f02df21942f316e.md`  
Disposition: **ROUTE PLAN**. The required real-Pi -> scoped upstream serializer -> exact vendored-browser xterm acceptance oracle fails, reproducibly. No implementation defect attributable to this uncommitted proof-only test was found. PI-T003 is **FAIL/STOP**; do not authorize PI-T004/005/006 under the existing replay representation.

## Environment / evidence identity

- Verified device: `desktop-b5e4iue-87cea2af` (`DESKTOP-B5E4IUE`), Windows `Microsoft Windows NT 10.0.26100.0`, PowerShell shell via device broker.
- Working directory: `E:\git-project\lantern\.wt\lantern-bot` (broker independently resolved this exact path).
- Local device time at final Git inspection: `2026-10-19T00:54:54.7347527+09:00`.
- Branch: `feat/lantern-bot`; HEAD: `9d39a0f08fcf73678f3cf9b3033cfb96beb76863`.
- Tools: `uv 0.11.8`, `node v22.22.2`, `Python 3.14.1`.
- Scoped temp packages exist at `C:\Users\admin\AppData\Local\Temp\lantern-pi-replay-proof6\node_modules`: `@xterm/headless@6.0.0` and `@xterm/addon-serialize@0.14.0`; no repository dependency changes.
- Exact client script: `static/vendor/xterm.js`, SHA256 `f68403f92e5552d69fab42d98571c8e16b6f03cba3e5233b4c8a99d3eb9d4653` (Windows `certutil -hashfile ... SHA256`).
- Candidate test `tests/test_pi_reconnect_e2e.py`, SHA256 `dbc88f8b19dae5fd018fa083e5a6519732162832e231f8c3b6443b4b05837d15`, untracked; this is the exact tested content.
- Accepted native capture `.plan/lantern-pi-native-20261018/evidence-turn4/pi-t002-g6-winconpty-raw.txt` SHA256 `8daa712a72788923fa36830b819410e72f54048a477be5083bc67f30ab3c0747`; metadata `pi-t002-g6-winconpty.json` SHA256 `9285b454284f328123205480043ced3db61ab547479e1204c9199f079f301fa9`.

## Executed commands, expectations, actuals

All commands below were run on the above verified device with working directory `E:\git-project\lantern\.wt\lantern-bot`. No live Lantern `:9999` or CDPA interaction.

### 1. Required enabled PI-T003 proof

```powershell
$env:LANTERN_PI_REPLAY_E2E='1'
uv run python -m unittest -v tests.test_pi_reconnect_e2e
Write-Output ('UNittestExit=' + $LASTEXITCODE)
exit $LASTEXITCODE
```

Expected: baseline raw-tail falsification, deterministic manager sequence and synthetic serializer tests should pass; real native Pi stream must produce **exact** matching vendored-browser cells/attributes/cursor/buffer/geometry/exposed modes to qualify as PI-T003 PASS. Any mismatch is the contractually required **FAIL/STOP**, not a test PASS.

Actual: **4 run, 3 PASS, 1 FAIL, process exit 1**, elapsed 9.725 s:
- `test_current_raw_tail_replay_is_not_lossless`: PASS (narrow synthetic falsification).
- `test_manager_detach_replay_orders_output_without_resending_input`: PASS (deterministic sequence/input fixture only).
- `test_upstream_serializer_is_lossless_for_tested_same_geometry_state`: PASS (narrow headless synthetic states only).
- `test_real_pi_native_stream_serializes_into_exact_vendored_xterm`: **FAIL at line 323**, equality assertion `assertTrue(result["browser"]["equal"])`.

Observed native-Pi cross-stack browser oracle (`equal=false`):

| Oracle component | Reference: original Pi capture | Reconstruction: upstream serialization |
| --- | --- | --- |
| Geometry | 120x40 | 120x40 |
| Active buffer | normal | normal |
| Cursor (x,y) | (0,35) | (3,35) |
| Buffer base / viewport | 294 / 294 | 20 / 20 |
| Exposed modes | bracketedPaste=true, sendFocus=true, other recorded modes | same |

The assertion compares complete browser snapshots including visible cells, width, colors/color modes, style flags, cursor, active buffer, base/viewport, exposed modes, and geometry; the failure is not merely text inequality. Native provenance reported true for offline CLI `--offline`, installed `@earendil-works/pi-coding-agent`, and settings/resume/new/status native UI markers. No paid-provider prompt was issued.

### 2. Independent universal-newline false-positive control

The test uses Python `Path.read_text()`, which normalizes native Windows newline sequences in the reference input, while the Node serializer reads the raw file without this normalization. To avoid attributing the failure solely to that mismatch, TEST executed a second cross-stack comparison with only the **reference capture read** patched to preserve original newlines; no repository files were changed:

```powershell
$py = @'
import json
from pathlib import Path
from unittest.mock import patch
from tests import test_pi_reconnect_e2e as t
raw_path = t.ROOT / '.plan' / 'lantern-pi-native-20261018' / 'evidence-turn4' / 'pi-t002-g6-winconpty-raw.txt'
original_read_text = Path.read_text
def preserve_capture_newlines(self, *args, **kwargs):
    if self.resolve() == raw_path.resolve():
        with self.open('r', encoding=kwargs.get('encoding', 'utf-8'), errors=kwargs.get('errors', 'replace'), newline='') as f:
            return f.read()
    return original_read_text(self, *args, **kwargs)
with patch.object(Path, 'read_text', preserve_capture_newlines):
    result = t._real_pi_cross_stack_results()
browser = result['browser']
print(json.dumps({'versions': result['versions'], 'provenance': result['provenance'], 'equal': browser['equal'], 'ref': browser['ref'], 'recon': browser['recon']}, sort_keys=True))
assert result['versions'] == {'headless':'6.0.0','serialize':'0.14.0'}
assert all(result['provenance'].values())
assert not browser['equal']
assert browser['ref']['cx'] != browser['recon']['cx']
assert browser['ref']['modes'] == browser['recon']['modes']
'@
$py | uv run python -
Write-Output ('ExactNewlineProbeExit=' + $LASTEXITCODE)
exit $LASTEXITCODE
```

Expected: if the mismatch were only a reference newline-normalization artifact, preserved capture could restore equality; otherwise mismatch remains. Actual: **probe exit 0; `equal=false` persists**. Reference cursor (0,35), base/viewport (16,16); reconstruction cursor (3,35), base/viewport (20,20). Provenance all true, versions 6.0.0/0.14.0, exposed modes equal. The changed scrollback magnitude confirms newline normalization changes the fixture but **cannot explain away the non-equivalence**.

### 3. Gated ordinary invocation, regressions, syntax and cleanliness

```powershell
Remove-Item Env:LANTERN_PI_REPLAY_E2E -ErrorAction SilentlyContinue
uv run python -m unittest -v tests.test_pi_reconnect_e2e
uv run python -m unittest discover -s tests -p test_terminal_scm.py -q
uv run python -m py_compile tests/test_pi_reconnect_e2e.py
git diff --check
uv run python -m unittest discover -s tests -p test_terminal_ui.py -q
```

Expected / actual:
- Unset replay gate: **4 skipped**, exit 0, not PASS evidence for PI-T003.
- `test_terminal_scm.py`: **15 run, OK**, 4.840 s, exit 0.
- `py_compile`: exit 0.
- `git diff --check`: exit 0 (covers tracked changes; untracked proof is separately syntax-tested and run).
- `test_terminal_ui.py`: **12 run, OK**, 2.232 s, exit 0.

No whole-repository full-suite run was independently repeated this turn. DEV turn 9's reported 323-test ordinary suite remains prior-role evidence only, **not independently TEST-verified**.

### 4. Preservation / branch drift

```powershell
hostname
[System.Environment]::OSVersion.VersionString
uv --version
node --version
uv run python --version
git branch --show-current
git rev-parse HEAD
git rev-parse main
git rev-list --left-right --count main...HEAD
git status --short
git diff --name-only
git diff --check
git log --oneline --max-count=10 HEAD..main
git log --oneline --max-count=10 main..HEAD
git ls-files --others --exclude-standard
certutil -hashfile static/vendor/xterm.js SHA256
certutil -hashfile tests/test_pi_reconnect_e2e.py SHA256
certutil -hashfile .plan/lantern-pi-native-20261018/evidence-turn4/pi-t002-g6-winconpty-raw.txt SHA256
certutil -hashfile .plan/lantern-pi-native-20261018/evidence-turn4/pi-t002-g6-winconpty.json SHA256
```

Expected: no implementation dirt, no unrelated edits or cleanup, no mutation to owned Markdown or production Terminal/UI/WS files. Actual: only `?? tests/test_pi_reconnect_e2e.py`; `git diff --name-only` empty, `git diff --check` exit 0. No package/lockfile tracked edits. This TEST made no implementation edits.

**Concurrent main drift:** During TEST, `main` is `0eed7ed92dd758f64fbaecd8f958b568d29c9d32`, ahead of the review's `1e3b77c...` by six additional Markdown-specific commits. `main...HEAD` currently reads **7 left / 2 right**. `HEAD..main` log shows Markdown-only change subjects; TEST did not rebase/reset/merge or touch other owner's files. PLAN must consider this drift before any authorized next work. A previous exploratory `Get-FileHash` failed because the cmdlet was unavailable; `certutil -hashfile` succeeded and hashes above are actual.

## Acceptance classification / routing

- **PI-T003: FAIL/STOP (verified).** The mature scoped serializer cannot exactly reconstruct the accepted native Pi state in the repository's vendored xterm at the **same** 120x40 geometry. Raw-tail truncation and cross-width equivalence remain demonstrably inadequate. Synthetic same-geometry and manager output-order fixture PASS claims are narrow and cannot override the required real-Pi failure.
- **PI-T002: previously independently accepted** native TerminalManager/WinConPty proof; reused accepted capture, not newly recreated physical evidence this turn.
- **Spec 001 T1: previously accepted/committed**; focused Terminal UI and SCM tests are green.
- **Spec 001 T0-C: NOT_MEASURED/deferred** (no >=50-attempt physical four-channel evidence). **T2: BLOCKED**, no IME fix.
- **Browser F5 and live WS reconnect: NOT_MEASURED.** Physical FJP UniKey/AltGr/image paste, native live /model-/goal-/extension parity, cursor visibility beyond exposed API, writer/viewer ownership/session concurrency, performance/resource acceptance: **INCOMPLETE or NOT_MEASURED**. PI-T004/005/006 not authorized or implemented by this TEST.
- **No new DEV implementation defect identified.** It is a verified upstream/current-stack replay feasibility STOP, not a reason to weaken the oracle or implement a custom parser.

**ROUTE PLAN** for acceptance-gate disposition and dependency path. Preserve uncommitted failing proof and all unrelated work; do not promote a PI-T003 PASS, do not start PI-T004/005/006 under this failed replay representation, do not touch live Lantern :9999 or CDPA.
