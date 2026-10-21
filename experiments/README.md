# Option B: Milkdown-first read-only preview performance spike

This is a **read-only benchmark**, not a product preview replacement. It loads the
existing bundled Milkdown in an isolated browser page, blocks POST requests,
then marks the ProseMirror DOM non-editable. That last step is a diagnostic
approximation, **not** proof that Milkdown supports fully safe read-only mode.

Run `python experiments/renderer_benchmark.py` on an environment with a
functioning Chromium/Edge that can visit `127.0.0.1`. The benchmark reports 20
repetitions per size (5KiB, 41KiB, 70KiB, 500KiB, 4.9MiB) and explicitly flags
Preview's 600k-character truncation. For a real GO, add Mermaid / comment /
print / round-trip / security and cross-page selection checks. Never compare
full 4.9 MiB Milkdown to truncated baseline without acknowledging the limit.

If the browser reports `net::ERR_BLOCKED_BY_ADMINISTRATOR`, result is
**UNAVAILABLE**, not a performance result. Do not alter managed browser policy
or assert success from Node/server timings alone.

## Windows Edge pilot (2026-10-15)

Measured in a separate ephemeral FJP checkout on a real Edge, 3 samples per
size (not enough to claim a stable p95; preliminary median only):

| Markdown | Python Preview | Milkdown mount | Note |
|---|---:|---:|---|
| 5 KiB | 181.5 ms | 688 ms | Full-editor prototype |
| 41 KiB | 357.6 ms | 3344 ms | Full-editor prototype, ~9.4x slower |
| 70 KiB | 455.5 ms | 625 ms | Milkdown measurement is the **paged** editor, not full-document read-only |

**Decision:** keep the Python Preview as the default (option A) and park
Milkdown-first Preview (option B). These numbers do not prove correctness or
performance parity at 500 KiB / 4.9 MiB; the built-in Preview truncates source
at 600k characters. No code path switches the production Preview to Milkdown.

Use `LANTERN_BENCH_RUNS` (default 20) and `LANTERN_BENCH_SIZES`
(comma-separated bytes, default 5KiB/41KiB/70KiB/500KiB/4.9MiB) to reproduce.
