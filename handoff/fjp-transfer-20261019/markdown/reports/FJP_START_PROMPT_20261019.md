You are continuing the Lantern Markdown/app lane on FJP.

Workspace:
C:\Users\DuongNH66\Desktop\git\lantern

Branch / implementation checkpoint (handoff commits may be on top):
main
34276bdd8b35b65cd1b34947b3137c3497b552b9

Read FIRST, in order:
1. AGENTS.md
2. docs/architecture/FOUNDATION_CURRENT.md
3. docs/architecture/LANTERN_SYSTEM_ARCHITECTURE.md
4. docs/architecture/LANTERN_FUNCTION_FLOWS.md
5. specs/001-terminal-ime-markdown-export/spec.md
6. specs/001-terminal-ime-markdown-export/plan.md
7. specs/001-terminal-ime-markdown-export/tasks.md
8. specs/002-lantern-foundation/README.md
9. specs/002-lantern-foundation/spec.md
10. specs/002-lantern-foundation/plan.md
11. specs/002-lantern-foundation/tasks.md
12. specs/002-lantern-foundation/verification.md
13. specs/003-markdown-fidelity/spec.md
14. specs/003-markdown-fidelity/plan.md
15. specs/003-markdown-fidelity/tasks.md
16. specs/003-markdown-fidelity/SOURCE_UX_PERFORMANCE_AUDIT_2026-10-17.md
17. handoff/fjp-transfer-20261019/markdown/reports/FJP_TRANSFER_HANDOFF_20261019.md
18. handoff/fjp-transfer-20261019/markdown/reports/lantern-markdown-main-20261018-plan_turn9_cdpa-idem-382a709ae8895eae9ec134d4.md
19. handoff/fjp-transfer-20261019/markdown/reports/lantern-markdown-main-20261018-review_turn15_cdpa-idem-382a709ae8895eae9ec134d4.md
20. handoff/fjp-transfer-20261019/markdown/reports/lantern-markdown-main-20261018-dev_turn14_cdpa-idem-382a709ae8895eae9ec134d4.md

Mission:
Continue all legally actionable Markdown/app work remaining from Spec 001 Markdown lane, Spec 002 Foundation closure/verification gates, and Spec 003, in dependency order.

Ownership:
- Own Markdown/app/source/diff/fidelity/crop/shared app work explicitly assigned by specs/reports.
- Do NOT take over Pi/native Terminal implementation except an explicitly justified shared contract boundary.
- Spec 004 is primarily Native/Pi ownership.

Engineering rules:
- Use systematic root-cause debugging.
- Use TDD for behavior changes: RED -> minimal existing-owner fix -> GREEN.
- Prefer mature existing abstractions; do not create speculative frameworks.
- Preserve unrelated dirty/untracked work.
- Never reset, stash, clean, or rewrite history.
- Report only tests/evidence actually run.
- Missing evidence is INCOMPLETE/NOT_MEASURED, never PASS.
- Keep changes in small coherent slices and request independent review/test for material boundaries.

Historical CDPA note:
The G6 workflow was frozen at accepted DEV hop51, attempts=1, with a provider/UI stream stall. Do not replay or reconstruct that Send. That execution is historical provenance only; continue source work from the FJP git/report state.

First actions:
1. Verify git status/HEAD.
2. Summarize the still-open owned items from the governing specs + latest reports.
3. Pick the next dependency-ordered incomplete item.
4. Reproduce it before editing.
5. Implement/test the smallest correct slice.
