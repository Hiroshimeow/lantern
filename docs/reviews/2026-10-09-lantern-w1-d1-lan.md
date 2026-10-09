# Lantern W1 + D1 — multi-client LAN performance

Date: 2026-10-09 JST. FJP source repository: `C:\Users\DuongNH66\Desktop\git\lantern`, main base HEAD `a45971b42dcda5bb87f03cc911bf94bdf53507c6`.
W1/D1 and the previously approved R1 changes are accepted for a local Git checkpoint. No push, deployment, or operator-server restart; the running port 9999 is not changed.

## Supported topologies
- One server, many browser clients (PCs/mobile/multiple tabs): one TerminalManager/PTy state per server, many WebSocket peers. New browser clients connect with `/ws?v=2`, receive terminal metadata on connect, and subscribe to output only when a terminal drawer is visible. A client closing its view unsubscribes without killing another client's shared terminal.
- Separate Lantern server instances sharing a remote filesystem/NAS: separate PTY/session managers, separate preview concurrency limits/caches. The filesystem is not a distributed coordinator; no promise of cross-instance PTY sync, distributed quotas, conflict-free concurrent file writes or globally consistent cache/SCM events.

## W1 behavior
- Changes: `lantern_terminal.py`, `lantern_ws.py`, `static/terminal_scm.js`.
- Server handshake metadata-only for v2 clients, lazy xterm mount, single subscribed PTY per peer, sequenced output generation and browser buffering/deduplication across snapshot races. No full replay for idle/drawer-closed v2 clients.
- Old browser JS using unversioned `/ws` still receives one legacy snapshot after 0.7s. Legacy display tail limited to last 20,000 characters per terminal to remain under the 8 MiB WebSocket queue even with 64 sessions of ANSI control characters. Warning displayed if truncated; server-held history is not modified. New clients see the retained tail for the active terminal up to 800,000 characters per replay; larger configured histories show an explicit truncation marker rather than overflowing an 8 MiB WebSocket queue. Default server retention is 204,800 characters; stored server output is unaffected.
- One client unsubscribing does not kill server PTY or remove subscriptions of other peers. No guarantee of per-keystroke arbitration between two clients typing into the **same** shared PTY; last resize writer still wins.

## D1 behavior
- Changes: `plugin.py`, `lan_drive.py`.
- DOCX XML bounded decompression + SAX streaming text extraction. XLSX worksheet bounded rows/cells and streaming sharedStrings with correct late indices; missing out-of-budget values are explicitly marked, not silently mapped to incorrect strings.
- PDF external pdftotext first 25 pages, bounded process stdout to 1 MiB and timeout 12 seconds with process kill; bounded 4 MiB fallback inflate.
- Per Lantern **process** maximum 2 concurrent heavy DOCX/XLSX/PDF previews across all clients. Additional calls are rejected with HTTP 503 to prevent unbounded queued parsing work. Separate server instances have independent two-slot limits.
- Preview is purposefully partial beyond declared limits. Worker tasks run in-process except pdftotext; **no OS-enforced hard RSS limit**. Per-process RAM/CPU, NAS contention and network rate still need physical multi-host measurements; no claim that every malicious archive format is safe.

## Verification
Exact reproducible manifest (tracked with this review): `docs/reviews/2026-10-09-lantern-w1-d1-verification.json`; working evidence also remains in `.plan/lantern-w1-d1-lan-20261009/final-verification.json`. Source/test SHA256 values matched before/after all checks.
- Python compile: PASS. Node terminal JS syntax: PASS. `git diff --check`: PASS (also rerun after README changes).
- `python -m unittest -v`: 80 discovered, **58 executed PASS**, 22 opt-in browser tests skipped only during ordinary discovery. No skipped test counted as PASS.
- Isolated, real Edge two-context E2E: **2/2 PASS**, v2 metadata-only/hidden xterm and unversioned older-client fallback.
- Isolated Edge R1 E2E: **20/20 PASS**, source unchanged across entire run.
- New deterministic LAN/distributed-domain/concurrency/parser cases are within the 58 ordinary executed tests. They include shared PTY independent subscribers, late snapshot sequencing, a 64-term legacy frame under 8 MiB, a configured 5-million-character PTY history with active replay under 8 MiB while retained output stays intact, XLSX sharedStrings including deep index #999, DOCX/PDF resource bounds, Node pending-terminal race, and four concurrent preview requests (2 x200, 2 x503). Two new XLSX 250,000-element fixtures verify traced allocation stays below 12 MiB and truncated results are labeled; prior source reached 20,516,783 bytes (>12 MiB) and failed the missing-marker assertion.
- **Not proven:** two actual physical machines over Wi-Fi/Tailscale/SMB; real native PTY cross-browser output in live multi-host environment; long-duration soak and exact WAN/CPU/RSS speedup. The browser E2E intentionally avoids live PTYs and uses isolated loopback server/temporary files.
- First attempted browser E2E that spawned a native PTY failed before subscription could be established (test harness/environment), not counted as a passing test. Final valid two-client browser suite tests metadata only; shared PTY output sequencing is checked independently with fake PTYs.

## Independent review
**Opus 5.5: APPROVE for exact final snapshot; source/evidence review only.** Continued the existing conversation at `https://m365.cloud.microsoft/chat/conversation/3adee003-351c-4b7b-92ee-51dec0434920`.
- Review round 1 job `61686840-m365-20261009-162338-a036919c` returned REVISE for D1-P1: an XLSX worksheet iterator retained unbounded XML elements. The reply was recovered by reading the persisted exact conversation after the runner emitted BINDING_UNVERIFIABLE. Raw source: `.plan/lantern-w1-d1-lan-20261009/opus-review-round1.raw.md`; initial review SHA plugin.py `8f9bf517...`.
- Round 2 job `61686840-m365-20261009-164241-f6bc01d9`: **COMPLETED, Opus 5.5, APPROVE**, reviewer explicitly bound findings to new plugin.py SHA `dd83f25b...`, lantern_ws.py `0ca1e0ae...`, terminal_scm.js `657f02bf...`. Saved response in `C:\Users\DuongNH66\AppData\Local\m365-copilot2dom\jobs\61686840-m365-20261009-164241-f6bc01d9\response.md`.
- Review notes (P2, not blocking the reviewed source): a rejected terminal_create can leave a pending ghost tab; reusing a Git terminal ID can flicker; a capped ANSI replay may begin mid-escape; busy preview 503 does not auto-retry; consider bounding total worksheet preview data further and handling parser edge cases. Do not mistake APPROVE for production rollout or validation on real multi-host LAN/SMB.
- No additional M365 Send after final job COMPLETED. Existing chat preserved.

## Operational safety
The operator's Lantern port 9999 was not restarted; it still serves the previous runtime until an explicitly approved deployment. Running terminals and transfers were not touched. The approved changes are checkpointed in the local main branch only; no remote push.
