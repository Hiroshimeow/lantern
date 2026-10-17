# Research — Foundation (read-only findings, 2026-10-17)
## Evidence
- HEAD clean reference (in `lantern-spec-review`): fb06c40758f406feb70bbb26ccd3cecb6476dacc.
- Real FJP `C:\Users\DuongNH66\Desktop\git\lantern` main has extensive UNCOMMITTED partially generated refactor. Do not claim this WIP works: it has moved 3,749-line lan_drive.py mechanically, rewritten multiple tests, partial new main.py; only CLI help + disposable HTTP smoke previously passed, not full regression.
- Port 9999 still serves previously committed code; 10099 untouched. Temporary own test port 50775 was stopped without touching production processes.
- Original lan_drive.py owned config+file operations+media+HTTP+HTML+startup; existing separate modules lantern/terminal.py, lantern/ws.py, lantern/pi_chat.py, lantern/live_markdown.py, lantern/scm.py and plugin.py are the candidates to preserve.
- Existing worktrees: lantern [main dirty], lantern-bot [feat clean], lantern-live-md-20261016 [feature clean], lantern-spec-review [spec branch clean baseline + docs only].
- Characterization tests currently missing as an immutable baseline oracle. All future refactor changes must compare against clean HEAD, not dirty main.

## Independent M365 Sonnet debate
M365 Worker doctor ready (FJP Chrome 9222). Sonnet 5.5 conversation: https://m365.cloud.microsoft/chat/conversation/181fd168-316e-4e07-bd5d-e99097960384
Round 1 ref 61686840-m365-worker-20261017-091358-6eb724d8: rejects mechanical AST split and fake Pi HTML parity; identifies singletons, oracle contamination, path/headers and process lifecycle.
Round 2 ref 61686840-m365-worker-20261017-091843-30a32a56: endorses one atomic cutover after clean characterization, no compatibility shim, exact-byte Markdown and native Pi.
Round 3 is an explicit challenge of path-as-session key, custom dirty-segment parser and terminal screen replay. Final decision ledger is in overview.

## Refactor risk checklist
- One-file CSS/HTML relocation silently changes ETag/cache/CSP/relative resource path.
- Changing `os.chdir(root)` affects sub-processes and path resolution; tests must cover process cwd and no cross-instance interference.
- Import-time Python globals become multiple service instances if main imported via distinct module names.
- Moving methods by AST doesn't establish ownership; service object 'self.app.services.*' used everywhere is a god-context.
- Tests that changed simultaneously with implementation may only prove both agree on new behavior; immutable fixtures separate from feature tests.
- Installer/launcher must be updated with main.py cutover, without leaving legacy shims.

## Benchmarks/gates not yet verified
FJP Windows Edge: HTTP snapshot, 1k directory entries, Preview 100KiB, terminal 200KiB replay, 2-instance independence; Linux smoke. Numbers will be collected in approved implementation phase, not guessed.
