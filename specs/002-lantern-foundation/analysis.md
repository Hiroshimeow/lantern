# Spec-Kit traceability / self-review (DRAFT)
**Ngày:** 2026-10-17
**Tình trạng:** docs-only, gate G0 CHƯA ĐƯỢC DUYỆT. Không thực thi task trong tài liệu này.

## Requirement → work package map
| Nhóm yêu cầu | Tài liệu đặc tả | Task phủ yêu cầu | Chứng cứ nghiệm thu |
|---|---|---|---|
| FND-001/002/003, one entrypoint/lifecycle/interfaces | 002/spec.md | F-T004–F-T005, F-T008–F-T010 | 2-instance no-global test, import graph, CLI/installer |
| FND-004/005, file/media/crop ownership/path | 002/spec.md | F-T006–F-T007 | root/UNC path, image/file CRUD, CAS |
| FND-006/007, behavioral parity and cutover | 002/spec.md | F-T002, F-T008–F-T011 | frozen HTTP/WS fixture, E2E, one main.py |
| FND-008/009/010, isolation/config/security deferral | 002/spec.md | F-T004–F-T005, F-T009, F-T011 | no side effects, config unchanged, no new LAN code |
| FND-011/012, workflow/WIP | 002/spec.md | F-T001, F-T013 | WIP disposition, independent review/rebase |
| MD-FR01–04, canonical .md/md_temp, CAS, watcher, diff | 003/spec.md | MD-T001, MD-T004–MD-T006 | original/snapshot/undo, external/2-tab collisions |
| MD-FR05–07, 3-mode decorations/source map/no byte loss | 003/spec.md | MD-T001–MD-T003, MD-T007–MD-T010 | strict byte corpus, exact mapping, visual/source E2E |
| MD-FR08/09, embedded Crop and asset CAS | 003/spec.md | MD-T012–MD-T014 | pixel/EXIF/GIF/reference/undo/asset E2E |
| MD-FR10/11, paged/anchor/layout | 003/spec.md | MD-T009–MD-T011, MD-T015 | 30col, CJK, 500ms flash, two viewports |
| MD-FR12, no new security | 003/spec.md | MD-T016 review gate | no new auth/policy changes |
| PI-FR01–03, Pi native/session/context | 004/spec.md | PI-T001–PI-T005, PI-T010–PI-T011 | real Pi parity; independent sessions same path |
| PI-FR04–06, scoped WS, multi-attach, replay | 004/spec.md | PI-T003, PI-T006–PI-T007 | attach/focus/resize owner/lossless snapshot |
| PI-FR07–09, native UI/Pi configuration | 004/spec.md | PI-T008–PI-T012 | actual slash/extension/model/IME/copy/paste |
| PI-FR10/11, future events and process lifecycle | 004/spec.md | PI-T007, PI-T013 | explicit restart semantics, contract docs |
| PI-FR12, ordinary terminal unchanged | 004/spec.md | PI-T014–PI-T015 | Terminal/SCM/Markdown regression |

## Cross-package source ownership
| Nơi sở hữu | Main base / 002 | Main Markdown / 003 | Pi worktree / 004 |
|---|---|---|---|
| CLI/composition/HTTP modules | Refactor once, freeze interfaces | Only call stable contract | Only call stable contract |
| `lantern/live_markdown.py`, byte diff, watcher | Preserve current behavior | Exclusive owner | Use ordinary files + file changes, no import |
| `plugin.py`, `tools/visual_markdown_entry.js`, `static/markdown*` | Preserve behavior | Exclusive owner | No modifications |
| `lantern/terminal.py`, `lantern/ws.py`, `static/terminal_scm.js` | Preserve & contract | No changes | May change with explicit terminal owner review/tests |
| `lantern/pi_chat.py`, Pi session modules, `static/chatbot*` | Preserve old behavior until 004 | No changes | Exclusive owner |
| `tools/image_crop_entry.js`, Crop service | Preserve functional API | Embedded consumer + adapter | No changes |
| Shared server route interfaces | Freeze at 002 | Narrow Markdown adapter | Narrow Pi/Terminal adapter |
| Tests | Characterization fixtures immutable | Feature suite 003 | Feature suite 004 |

## Quality / contradiction review
- Specs demand no feature degradation; therefore no automatic 'Visual becomes read-only' fallback in 003 without explicit owner choice. Source mode is a safe emergency operating mode, not accepted release substitute.
- 003 crop currently partially implemented in Milkdown Edit. Tasks call for reuse and Preview parity, not duplicate Crop UI.
- 004 sessions keyed opaque ID not file path or browser tab. Same file can have independent sessions; multiple tabs may attach one.
- 004 replay mechanism intentionally undecided until experimental lossless parity; raw ring buffer must not be assumed sufficient.
- No new security implementation anywhere. Local Pi parity prioritized; policy for LAN is a separate future spec.
- Mandatory WIP disposition before any refactor: dirty main and user drafts preserved.
- Spec/plan/tasks are approval documents; none claim tests passed unless observed in baseline history.

## Documentation gates before review
- [x] 002/003/004 each has `spec.md`, `plan.md`, `tasks.md`, `research.md`.
- [x] Constitution / open decisions / Mermaid architecture + workflows recorded.
- [x] Three rounds of actual Sonnet debate and third-round conditional consensus recorded.
- [ ] User approves baseline boundaries and decisions S1–S7.
- [ ] Characterization + proof tests executed (post-approval only).
- [ ] Each package implementation/review/benchmark/merge gate passed (post-approval only).

## No-op acceptance
Main source tree not changed by Spec-Kit work in this worktree. No installs, no product code edits, no resets/stashes of dirty main, no main/feature merges/pushes.
