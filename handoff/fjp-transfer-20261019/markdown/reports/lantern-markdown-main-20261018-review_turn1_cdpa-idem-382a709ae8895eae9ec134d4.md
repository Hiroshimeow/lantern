# REVIEW Turn 1 — independent CSP contract/design adjudication

**Team:** lantern-markdown-main-20261018 | **task:** cdpa-idem-382a709ae8895eae9ec134d4 | **role:** REVIEW | **date:** 2026-10-18 (JST)
**Device/repo:** owned MD G6 `desktop-b5e4iue-87cea2af`, `E:\git-project\lantern` | **branch/HEAD:** `main` / `b2ffd886795840f0db570b8c07a913b406e68e80`
**Incoming:** `.plan/lantern-markdown-main-20261018/lantern-markdown-main-20261018-plan_turn2_cdpa-idem-382a709ae8895eae9ec134d4.md`

## Decision and scope

**ACCEPT_A_FOR_SCOPED_IMPLEMENTATION; ROUTE DEV.** The proposed *content-kind-based* CSP profiles are technically justified as the smallest change to reconcile interactive Markdown Preview/Edit/Source with Spec 001. This is approval to **document and test a proposed contract**, not approval of the residual security risk or a claim that M-A5/M-A12/release gates pass. An explicit renewed security-owner decision is mandatory before release. Option B (a distinct strict-CSP Markdown read-only realm plus an editor realm) remains a fallback if the owner rejects that risk, not a speculative feature to build in this slice.

**No tracked implementation delta exists to accept:** independently observed `git status --short -uall` = only `?? .pi/subagents.json`, `git diff --stat` and `git diff --cached --stat` empty, `git diff --check` exit 0. No implementation commit, product-source mutation, test rewrite, new worktree, or service restart by REVIEW. No edits to Pi/terminal/CDPA or Lantern :9999. This is a *design/security gate review*, not an implementation PASS.

## Sources and fresh independent verification

- Read `AGENTS.md`; Spec 001 `spec.md`/`plan.md`/`tasks.md`; Spec 002 `README.md`/`constitution.md`/`spec.md`/`plan.md`/`tasks.md`/`analysis.md`/`research.md`/`decisions.md`/`upstream-verification.md`/`verification.md`; Spec 003 `spec.md`/`plan.md`/`tasks.md`/`research.md`/`SOURCE_UX_PERFORMANCE_AUDIT_2026-10-17.md`; PLAN turns 1/2, DEV turn 1, TEST turn 1, DEV probe source/JSON, existing containment decision `docs/architecture/LANTERN_FUNCTION_FLOWS.md:622-645`, actual renderer/HTTP/WS consumers.
- Relevant skills discovered and loaded from G6 MD skill catalog: `ponytail-review` and `verification-before-completion`. Their YAGNI and evidence-before-PASS constraints govern this review.
- Fresh REVIEW command: `C:\Users\admin\miniconda3\python.exe -m pytest -q tests/test_plugin.py` -> **26 passed, 5 subtests passed, 1.35 s, exit 0**. This proves existing unit assertions, **not** the contradictory universal M-A5 or browser isolation.
- Fresh REVIEW **independent renderer probe** (in-memory Python sent on stdin, temp files only, no persistent probe script or server): generated `x.md`, `x.txt` and `x.pdf` pages via `plugin.render_preview_page`, parsed meta CSP and every script nonce, asserted a fresh nonce on repeat `.md` response. **Exit 0, observed:** `.md` `connect-src 'self'; worker-src 'self'`; `.txt` `connect-src 'none'`; native `.pdf` `connect-src 'none'; frame-src 'self'` with one iframe. All inspected script tags matched their generated nonce. This is server-renderer proof, **not a new independent browser/functional PASS**.
- Rechecked `git blame`: nonce core `e7e8e081` (2026-10-07), Markdown exception `1fa87ae3` (2026-10-12), native PDF frame exception `4c0f4db8` (2026-10-12); both predate Foundation 002 integration. No evidence this CSP discrepancy is a Foundation regression.
- Inspected DEV Edge 155 probe (`dev_turn1_csp_contract_probe.py` / `.json`): read-only .txt WS/fetch blocked; interactive .md WS opened and same-origin fetch succeeded; forced `connect-src 'none'` on the interactive page blocked required work/info fetch/WS and generated Worker CSP violations. The probe's Worker `created` state only records constructor return followed by immediate termination; it does **not** prove Worker startup or successful message handling. This REVIEW did **not** independently rerun that browser probe; treat as examined supporting evidence, not a fresh REVIEW browser test.
- TEST turn 1 reported full native suite **208 passed / 108 skipped / 47 subtests**; selected Edge suites **33 passed / 4 skipped / 1 terminal-owned failure**; Mermaid SVG/PNG subset observed. Those results are inherited evidence, not rerun by REVIEW. No full independent Edge, PDF visual, nine-context Mermaid timing, CPU/RSS, Linux smoke, or manual UX/security sign-off was run this turn.

## Findings — contract, correctness, threats, required correction

### R1 — BLOCKING CONTRACT DEFECT: universal 001 CSP is incompatible with the current unified editor

**Locations:** `specs/001-terminal-ime-markdown-export/spec.md:148-164,255`, `plan.md:96-106`, `tasks.md:133-148` versus `plugin.py:1245-1277,1291-1309`; consumers `static/markdown_visual_shell.js`, `static/markdown_paged_editor.js:71`, `static/chatbot.js:355`.

**Evidence:** 001 mandates `connect-src 'none'` and blocked preview WS *for all preview kinds*. Actual interactive Markdown page always includes Preview/Edit/Source controls and same-origin work API fetch, chatbot WS, and segment Worker; renderer deliberately permits `connect-src 'self'; worker-src 'self'`. DEV Edge counterfactual demonstrated strict policy blocks these required operations; independent renderer check reproduced profile strings. The page's Preview mode is not a separate security realm. Turning off its network permission on a client-side mode toggle would break document source-of-truth/CAS/md_temp/interaction.

**Correction:** explicitly redefine 001 M-A5 and CSP text by **server-classified page kind**, with editor-capable Markdown (including its Preview mode) allowed same-origin connect/Worker and read-only types retaining zero connections. Do not claim old M-A5 PASS or merely change a permissive assertion to hide the discrepancy. No speculative change to `plugin.py` unless a separate product defect is reproduced.

### R2 — CONTRACT/TEST OMISSION: native PDF frame exception

**Locations:** `plugin.py:1249-1260,1274,1311-1319`, 001 universal CSP requirements, `tests/test_plugin.py:491-517`.

**Evidence:** actual native PDF preview contains `iframe src=<same-origin raw PDF>` and `frame-src 'self'` but `connect-src 'none'`; extracted-text PDF is a different strict unframed rendering. The universal 001 CSP would otherwise block native frame. The named all-kinds unit test covers only Markdown/.txt/.csv and does not enforce either PDF variant.

**Correction:** document the narrow read-only native PDF `frame-src 'self'` exception and add exact assertions plus an Edge frame-load check. Do not silently broaden `frame-src` to Markdown or all document types; do not infer browser PDF visual acceptance from string generation alone.

### R3 — TEST ORACLE TOO PERMISSIVE; asynchronous Worker proof missing

**Locations:** `tests/test_plugin.py:491-517` and DEV probe `dev_turn1_csp_contract_probe.py:47-69,148-159`.

**Evidence:** static test accepts regex `connect-src '(none|self)'` keyed to literal UI phrase `"Edit visually"`; it neither enforces a strict per-kind policy nor tests PDF. DEV probe treats `new Worker(); terminate()` as `created` even when the forced strict policy emits an asynchronous CSP violation. A green static test therefore cannot prove M-A5.

**Correction:** assert separate exact profiles against explicit file kinds, no unauthorized `script-src` extras, all script nonces and per-response refresh, `noopener`/Back behavior, and no privilege decision based on a button/string. In an isolated real Edge origin, test allowed same-origin API/WS and Worker **readiness/message**, read-only WS/fetch/Worker **blocked by CSP**, external-origin WS/fetch/Worker blocked, script injection/un-nonced uploaded same-origin JS refused, and expected versus unexpected CSP console violations. Use a test-only loopback server; never touch :9999. Do not equate a constructor return with a live Worker.

### R4 — SECURITY RELEASE BLOCKER: same-origin capability/risk is not separately signed

**Locations:** `lantern/http/server.py:170-188`, `lantern/http/routes/files.py:546-595`, `plugin.py:1267-1277`, `static/markdown_preview.js:3,37-55,77`, `docs/architecture/LANTERN_FUNCTION_FLOWS.md:622-645`.

**Evidence/impact:** current raw uploaded `.html`/`.svg` may be served from Lantern origin according to MIME; Markdown raw HTML is escaped and local Mermaid is configured strict, while nonce CSP provides protection *inside the rendered preview page*. However that meta CSP is not an origin-wide sandbox and does not confine a separately navigated raw uploaded document. If any untrusted content obtains same-origin script execution, authenticated/same-origin protections alone do not distinguish it from the editor page: work/write APIs, WS and possibly terminal capabilities are in the same origin subject to their own runtime guards. `connect-src 'self'` intentionally expands the Markdown page's potential same-origin call surface compared with the old universal spec. **No exploit or bypass is proven by this review.** The previously recorded `LANTERN-SEC-001` consent addresses broader containment; it does not explicitly sign off this M-A5 deviation.

**Correction/release condition:** obtain renewed *explicit owner/security risk disposition*, recorded as pending until it actually exists; maintain `LANTERN-SEC-001` for iframe sandbox and same-origin uploaded HTML/SVG containment. Do not add a new auth/CSP framework, origin proxy or file-serving rewrite in this 001 documentation/test slice; if owner rejects remaining risk, route back to PLAN to design isolated realms with no false security equivalence.

## A versus B — required review dimensions

| Criterion | A: typed CSP profiles, existing unified app | B: isolated read-only Markdown Preview + editor realm |
| --- | --- | --- |
| Correctness/001 | Requires explicit contract revision and owner security approval; preserves existing real functionality | Can satisfy original strict preview WS rule but requires genuinely separate browser realm |
| 003 source-of-truth/CAS/md_temp/UX | Preserves live edits, same-document Preview/Visual/Source, 500ms anchor goal and draft continuity | Risks navigation, selection/scroll reset, hand-off of unsaved edits and duplicate state; requires new proof |
| Security | Nonce/escape/Mermaid strict and `connect-src 'self'` within editor; residual same-origin XSS/write/WS exposure still needs sign-off | Stronger isolation if correctly sandboxed, but does not itself contain raw uploaded HTML/SVG on same origin |
| Maintainability, owner, scalability | One `plugin.py::render_preview_page` composition path, server-verified content kind; no new owners or shadow stores | Additional lifecycle/realm/messaging/navigation surface, potential dual-document ownership |
| Mature alternatives / YAGNI | Browser-native nonce CSP, existing worker/renderer; no new dependencies, abstraction or parser | Browser iframe sandbox/opaque origin are mature primitives, but integration/revision costs are material and exceed this slice |
| Regression/performance evidence | No mode-navigation regression *expected* from retaining current architecture; actual full Edge/latency not measured here | Neither E2E parity nor latency, focus, selection, clipboard, MIME/export behavior has been measured |
| Verification quality | Static and limited browser evidence justify design, not release | No executable POC or acceptance evidence |

**Technical decision:** A is proportionate **within the established trusted-network/local application model**, conditional on owner accepting its exact deviation and unconfined raw-upload risk. No net new implementation abstraction is warranted in this turn (ponytail review: **Lean already; no complexity addition approved**). This is not proof of general LAN/public exposure safety.

## Proposed owner risk acknowledgement — must remain pending

"Lantern's Markdown Preview is an editor-capable same-origin application view sharing a document with Edit visually and Source. I expressly approve `connect-src 'self'; worker-src 'self'` there so its own-origin work APIs, WebSocket and segmentation Worker can function, replacing Spec 001's blanket ban on preview WebSockets; other read-only preview kinds keep `connect-src 'none'`, except native PDF's narrowly scoped same-origin iframe. I understand the nonce policy/Markdown escaping/Mermaid strict mode are not a complete sandbox, and a same-origin script compromise may reach editable-file/WS capabilities according to server permissions. `LANTERN-SEC-001` remains open for preview iframe containment and untrusted same-origin HTML/SVG isolation. This acceptance covers trusted deployment only, not public-internet hardening."

Owner must personally confirm or reject; neither PLAN, DEV nor REVIEW can sign on their behalf.

## DEV handoff — at most TWO coherent items, then REVIEW/TEST

1. **Contract/docs only (one task):** narrowly amend `specs/001-terminal-ime-markdown-export/spec.md`, `plan.md` and `tasks.md` for all three server-side CSP profiles (strict generic read-only, interactive Markdown, native PDF iframe, plus strict PDF text); split M-A5 into correct blocked/allowed assertions, revise M-A12 to require renewed owner confirmation, record this exact review decision and pending risk. No security weakening disguised as completed approval. Do not edit 002 or 003 behavior, Pi/native terminal, `.pi/subagents.json`, service routing, or :9999.
2. **Regression evidence (one task):** replace permissive `tests/test_plugin.py:491-517` CSP predicate with explicit kind + PDF coverage and add the smallest maintained disposable Edge test to demonstrate nonce rotation; disallowed script/third-party/readonly connections; allowed *functional* same-origin Markdown fetch, WS and Worker; native PDF frame load. Reuse existing Edge test harness where possible, not a parallel testing framework. `plugin.py` modification is allowed only for a separately reproducible defect, not to force spec conformity.

DEV must stop after these two items and route back to independent REVIEW/TEST. Commit only the accepted tracked doc/test slice after exact stdout/exit evidence, `git diff --check`, and confirmation unrelated untracked work stayed unchanged.

## Unresolved gates (no release claim)

- **001:** M-A5 currently **FAIL against original contract / revised contract pending**, M-A12 refreshed sign-off **INCOMPLETE**; PDF legibility/arrowheads/clipping **INCOMPLETE**; nine fresh FJP Chromium Mermaid timing contexts **NOT_MEASURED**; full offline/network/CSP and manual UX **INCOMPLETE**.
- **002:** full integration/architecture sign-off, paired CPU/RSS/latency budget, Linux smoke/manual UX remain **INCOMPLETE**; original terminal-owned Edge failure has no paired causality proof. This team may report/route but not fix native terminal ownership.
- **003:** source-lag baseline already documented pre-002, but MD-T000/001/002/003 fidelity/performance proof, crop safety, 3-mode UX, large-fixture Edge acceptance and hashes are **NOT_MEASURED** here; preserve original `.md`, `md_temp` snapshot, exact mapping and CAS. No 003 implementation accepted in this turn.
- **Integration:** no code commit, no branch integration, no owner/security sign-off, no tracked-tree completeness claim. Continue later in bounded slices; `DONE` is PLAN-only.

**Required route: DEV** — actionable documentation/test contract work remains. No external-only PAUSE justified.

## Repeated REVIEW invocation verification (same turn/handoff)

On the repeated Turn 1 instruction, independently rechecked G6 branch `main`, HEAD `b2ffd886795840f0db570b8c07a913b406e68e80`, no tracked/staged diff, and sole untracked `?? .pi/subagents.json`. Re-ran `C:\Users\admin\miniconda3\python.exe -m pytest -q tests/test_plugin.py`: **26 passed, 5 subtests passed, 0.90 seconds, exit 0**; `git diff --check`: **exit 0**. The specified AGENTS, 001/002/003 spec/plan/tasks/research/verification/audit and incoming PLAN documents remain present (15 exact paths tested), consistent with previously read contents; no newer implementation slice or evidence appeared. Decision and route unchanged. The previous independent in-memory renderer probe is not represented as rerun. Browser/security owner gates remain INCOMPLETE or NOT_MEASURED.
