# Lantern — Development rules

These rules apply to every agent and contributor working in this repository.

## Git layout

- The canonical checkout is the repo root; `main` owns Markdown/Preview/Edit/Crop.
- **ALL linked Git worktrees must be inside `<repo>/.wt/<feature-name>/`.** Never create sibling directories in `E:\git-project` or another parent workspace for Lantern. `.wt/` is Git-ignored.
- Use `git worktree list`, `git worktree move`, and `git worktree remove`. Inspect branch/status first; never delete a dirty worktree or run destructive `reset`/`stash`/`clean` without explicit owner approval.
- Prefer a single long-lived feature worktree `.wt/lantern-bot` for Pi native harness; do not create disposable clones/worktrees for each small task.
- Fetch and rebase a clean feature branch on the latest `main` **before starting development** and **before merging**. Verify tests/review after rebase; integrate with `git merge --ff-only`. Never overwrite concurrent work.

## Engineering and quality

1. Correctness, acceptance and mature upstream parity first; reliability, UX, performance and maintainability next. Simplicity is valuable only when behavior is fully preserved. Delivery speed/token savings are last.
2. Modules must own distinct responsibilities and be independently testable. Do not split by line count or add wrappers, duplicate state, provisional compatibility entrypoints or shadow implementations.
3. Lock behavioral characterization before structural refactors; run real unit/contract/browser evidence, protect user drafts and live services. Do not rewrite tests to make degraded code appear correct.
4. The `.md` on disk is the live source of truth for edits from Lantern, Pi or other editors. `md_temp` is the accepted diff snapshot. Keep precise revision/CAS and source mapping; no guessed or approximate replacement locations.
5. LanternBot uses native interactive Pi TUI/PTY for full command, skill and extension parity; sessions are identified by opaque session ID, not file path/browser tab. No new security/LAN quota enforcement until separately approved.
6. Baseline/architecture/Markdown/Pi design: `specs/002-lantern-foundation/`, `specs/003-markdown-fidelity/`, `specs/004-pi-native-harness/`. The documents are **DRAFT**: implementation gates and user approval still apply.
7. Do not deploy, restart a user's live Lantern process, merge functional refactors, or claim completion without fresh verification and owner authorization.
