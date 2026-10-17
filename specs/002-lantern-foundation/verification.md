# Lantern Foundation — refactor verification (2026-10-17)

**Scope:** module ownership and lifecycle only; no new product features, UI, or auth rules.
**Source / platform:** G6 `E:\git-project\lantern`, Windows Python 3.12, disposable loopback test roots and Edge.
**Immutable pre-refactor HEAD:** `1b5939357bfd3748a1c56b5e491bc55026b0368b`.
**Review disposition:** **PENDING** independent M365 Sonnet review and final performance approval. Do not merge/push/deploy/restart live Lantern 9999 yet.

## Contract and regression evidence

| Gate | Before | Refactor | Verdict |
|---|---|---|---|
| Python unit/integration (ordinary environment) | 202 passed, 108 skipped, 21 subtests | 205 passed, 108 skipped, 42 subtests | PASS |
| Frozen HTTP legacy oracle (15 cases) | Captured from original `lan_drive.py` | 15/15 matches, including Range, Markdown live write/Accept, assets | PASS |
| File-manager inline HTML/CSS/JS parity | Original Git version | Byte-exact across `/`, `/docs`, `/docs/long%20name` | PASS |
| Two Application instances in one interpreter | Not previously exercised | Separate roots, WS, Terminal, Pi, Markdown store, preview and Crop locks | PASS |
| Upload/Crop focused suite | Structural change to shared lock | 18 passed, 1 skipped; same lock now owned by the Application instance | PASS |
| Visual Markdown Edge | 10 fail / 1 pass | 10 fail / 1 pass, same tests | Existing baseline failures; no confirmed new failure |
| Terminal/Terminal Auth Edge | 3 fail / 1 pass | 3 fail, same tests | Existing baseline failures; no confirmed new failure |
| Additional launcher/upgrade/browser tests | Existing fixtures | 16 passed; 3 failures in terminal cases above | PASS except baseline terminal failures |
| Static checks | N/A | Ruff F821/F822/F823 and `git diff --check` pass | PASS |

**Environment boundaries:** tests use temporary directories, ephemeral ports, no invocation of a live service restart. Live G6 port `9999` remains the old running process. No user drafts or local YAML were reset or cleaned.

## Performance — requires sign-off

First HTTP run (legacy then refactor): file-list p95 `227.552 -> 258.364 ms` (13.5% slower), Markdown Preview `98.828 -> 81.889 ms`, static asset `25.128 -> 25.088 ms`, info `16.058 -> 25.124 ms`.

In-process 35 alternating comparisons of exact same file-list response: median `348.314 -> 356.449 ms` (2.3% slower); p95 `483.984 -> 523.075 ms` (8.1% slower).

One reverse-order HTTP run overlaps with other tests and is **invalid as a non-degradation proof**. Repeat on a quiet host, agree a measurable performance budget and reject a statistically meaningful regression; avoid changing behavior for synthetic speed.

## Independent review

M365 FJP review packet prepared at `%LOCALAPPDATA%\Temp\lantern_foundation_g6_review.md`. Initial worker turn `61686840-m365-worker-20261017-103550-c06ae2da` was admitted but failed **before Send** (`recoverable=false`). No Sonnet judgment/consensus obtained and no duplicate Send was attempted.

## Outstanding gates

1. Measure performance at rest; compare repeated latency/memory samples and explain any reproducible slowdown.
2. Independent Sonnet 5.5 architectural debate; resolve confirmed blockers only, do not introduce unrelated feature changes.
3. Run final Windows smoke and Linux smoke where available; verify single CLI entrypoint and installer on an isolated checkout.
4. Reviewer sign-off; commit and checkpoint refactor on its own branch. Merge to `main` and push only when approved.
