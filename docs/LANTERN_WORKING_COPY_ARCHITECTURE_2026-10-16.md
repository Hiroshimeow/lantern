Lantern Working-Copy Architecture

Date: 2026-10-16 JST Status: review decision. This document is the implementation plan; no code has been written yet. Baseline reviewed: 03beaa4 + local ca80966, 7a16fc5, e00e623 + uncommitted WIP in lan_drive.py and plugin.py (/api/md/render).

Critical invariant: a real project file must never change until the user explicitly saves. Explicit save means Ctrl+S, the Save button, or the existing paged-section Save.

1. Final architecture decision

Build one generic, server-owned working copy per edited text file:

New module: lantern/working_copy.py, class WorkingCopyStore.
New HTTP API family: /api/work/*.
Wire only Markdown to it now.
Later, a generic text/code editor reuses the same store and API with no storage migration.
User sees: README.md  (● when pending)
  editor memory ──debounced/forced flush (hash CAS)──► WORKING COPY  ~/.lantern/work/<id>/README.md
                                                          ▲  Pi read/edit/write here only (guarded)
  DIFF = saved real bytes (decoded, LF) vs current editor text  → one hunk model → Source / Visual / Preview
  Save:    flush → CAS commit working → real file (existing lock/fsync/os.replace) → delete working dir
  Discard: delete working dir → editor reloads saved text
  Pi turn: forced flush → server turn-lock (Pi sole writer) → live apply if user idle / one diff3 at settle → flush

Who owns what
Thing	Owner	PersistenceSaved text and savedVersion (SHA-256 of real bytes)	Real file on disk	Project filesystem
Working content, workHash, baseVersion	WorkingCopyStore (server)	~/.lantern/work/<id>/
Pi-turn lock	WorkingCopyStore (in memory)	None. A restart clears it, and Pi restarts too
Editor text, localRev, ackedHash, turnBaseText	Browser editor	Memory, plus an IndexedDB outbox for unsent typing only
Answer to the operator's A/B/C question: B

Keep part of the current code. Use editor memory as the immediate source and a private working file as the durable backing.

Keep: the diff/merge engine, the merge policy, the guard extension, the render WIP and the CAS core.
Replace: the per-turn shadow transport, the browser-authoritative IndexedDB draft, and the forced Source-mode switch.

Dropping the current code entirely (C) would throw away tested pieces that already fit. Evolving it in place without a store (A) leaves the draft without a durable server-side home.

2. Review of current FJP commits and WIP
ca80966 — keep edits pending until explicit save

The direction is correct.

Correct:

Autosave is gone: no queueSave. save() is only called from Ctrl+S or the Save button.
save() reports "Saved the earlier revision; newer edits are still pending" instead of re-saving automatically.

Defects:

close() still destroys drafts. It shows confirm('Discard unsaved changes and return to Preview?') and calls drafts.clear(). Back to Preview must be a view switch, not a discard.
Preview shows the saved file, not the draft. close() reloads the server preview only when savedSincePreview is set. Otherwise it restores the original saved HTML. The WIP /api/md/render fixes this, but it isn't wired in yet.
switchEditor() still blocks Source→Visual while dirty, with "Save Source before entering Visual Edit". Under draft-first editing, the user's normal state is dirty, so this makes Visual unusable after any edit or Pi turn.
IndexedDB is still authoritative. start() asks confirm('An unsaved Markdown draft was found…'). In this design the draft lives in the working copy.
7a16fc5 — pending source diffs

This is a useful interim, but it isn't the target UX.

The textarea backdrop works for line bands (renderSourceDiff).
Deleted text is not an inline ghost. It appears in a separate .md-source-deletions list labelled "Removed near line N". The operator UX needs red ghosts at the position where the text was deleted.
Performance problem: renderSourceDiff rebuilds one <span> per line for the whole document on every diff tick. At 5 MB (~100k lines) that is a full DOM rebuild every ~400 ms of typing.
Fix: move Source to CodeMirror 6 with viewport-only decorations. Lantern already ships CM6 in /static/vendor/lantern-large-block.min.js, which the paged editor uses for oversized blocks. Reuse that bundle; it is not a new dependency class.
e00e623 — stage Pi Markdown edits in the browser draft (turn-1 design)

Keep:

LanternMarkdownDiff.diffLines and merge3 (file static/markdown_draft_diff.js; see the note on unseen files below).
The merge rule: non-overlapping Pi hunks apply, and where Pi and the human overlap, the human wins and Pi's hunk is skipped and reported.
Running Pi with --tools read,edit,write,grep,find,ls, which excludes shell tools.
--no-extensions --extension pi_markdown_guard.ts.
real_file_changed() detection at agent_settled.
The status messages about skipped hunks.

Replace:

MarkdownDraftShadow (lantern/pi_draft.py). It creates a per-prompt shadow from browser text sent over WebSocket. Replace it with WorkingCopyStore.working_path(rel).
Draft text in chat_prompt (draft.text, the 1 MiB cap in captureMarkdownDraft). The prompt should carry the path and the expected work hash only. Pi reads the file itself.
applyPiDraft() forcing Source. It calls start('source') / switchEditor('source') and yanks a Visual or Preview user into Source. Apply in the current mode instead.
area.value = result.text. This destroys the textarea's native undo stack. As an interim fix, select the minimal changed range (common prefix/suffix) and use execCommand('insertText'); the final fix is a CM6 transaction.
piTurns keyed by promptId, holding up to 6 entries. One active turn per document is enough: store a single turnBaseText.

Must remove — these cause data loss under the new model:

PiChatManager.new_session() → self.drafts.clear().
prompt() → self.drafts.clear() for non-Markdown context.
close() → self.drafts.clear().

Working copies are user data. Pi session lifecycle must never delete them.

Clean up the prompt context:

Rename draftPath/savedPath to workingPath/logicalPath.
Remove promptId, baseVersion and draftRevision. They are model-irrelevant noise.
Uncommitted WIP — /api/md/render + render_markdown_draft

Correct; commit it.

It uses the same parser and the same data-l anchors.
Relative links resolve against the real path, because render_markdown_draft(content, target, root) checks relative_to(root).
It enforces the size limit.
It refactors _render_markdown into _render_markdown_text cleanly.

Note: MAX_TEXT_CHARS (600k) truncates Preview for very large drafts. This matches existing Preview behaviour, so it's acceptable.

Existing code relevant to generalization
md_editor.save_document is already a generic UTF-8 text CAS: SHA-256 version, _SAVE_LOCK, fsync + os.replace, and it preserves CRLF and BOM. Only require_markdown() makes it Markdown-specific. Extract it.
lan_drive.api_save (the generic ?edit=1 text save) has no CAS and no fsync. A future generic editor must switch to the new path. It is out of scope now, but listed as a later migration.
CONFIG.cache_dir defaults to the system temp directory. Do not store working copies there; temp cleaners delete user drafts.
Not reviewed (not attached)

These files must be checked before commit 5:

lantern/pi_draft.py
lantern/pi_markdown_guard.ts
static/markdown_draft_diff.js (confirm it does prefix/suffix trimming and has an edit-distance cap)
static/markdown_anchor_bridge.js
the lantern-large-block bundle API
the test files
3. WorkingCopyStore state model
Per document (keyed by id)
WorkingCopy {
  id:            str   # sha256(normcase(root_abs) + "\0" + normcase(rel_posix))[:20]
  logical_rel:   str   # project-relative POSIX path, e.g. "docs/README.md"
  real_abs:      str   # resolved absolute real path (inside root)
  working_abs:   str   # ~/.lantern/work/<id>/<basename>
  base_version:  str   # sha256 of real bytes when this working copy was created / last rebased
  work_hash:     str   # sha256 of current working file bytes
  encoding:      {bom: bool, newline: "lf"|"crlf"|"mixed"|"none"}   # of real file at base
  kind:          str   # "markdown" now; "text" later
  updated_at:    float
}
In-memory only:
  turn_active:   bool
  doc_lock:      threading.Lock

Derived state (computed on each GET, never stored)
State	Conditionclean	No working dir
pending	A working dir exists and base_version == current real hash
external	A working dir exists and base_version != current real hash (the real file changed outside Lantern)
missing	The real file no longer exists
Invariants
Only the store's write, save and discard operations, plus Pi's tools during a turn the store has locked, may modify working_abs.
Only save (via the CAS core) and the existing paged-section Save may modify real_abs.
Every human write is a compare-and-set on the actual file hash. That makes any unexpected writer (terminal, second tab, Pi outside a turn) detectable.
While turn_active, human writes, save and discard are refused with 409 {reason:"pi_turn"}.
Working text is always stored LF-normalized and without a BOM. The real file's BOM and newline style are re-applied only at Save, by the CAS core.
4. Physical cache layout and metadata
~/.lantern/work/                         # configurable: work_dir; NOT CONFIG.cache_dir (temp)
  <id>/
    <basename>                           # e.g. README.md — keeps extension so Pi tools / syntax work
    meta.json
  guard.json                             # guard state for the Pi extension (see §7)


meta.json (written with tmp + fsync + os.replace):

{
  "v": 1,
  "id": "3f9c…",
  "root": "E:\\git-project\\lantern",
  "logicalPath": "docs/README.md",
  "realPath": "E:\\git-project\\lantern\\docs\\README.md",
  "baseVersion": "<sha256>",
  "workHash": "<sha256>",
  "encoding": {"bom": false, "newline": "crlf"},
  "kind": "markdown",
  "updatedAt": 1797400000.0
}


Why the file is named <basename> and not content: Pi sees README.md with a real extension. That helps the model and any language-aware tools, and costs nothing.

Cleanup rules
Save succeeds → delete <id>/ (only if work_hash is unchanged since the save started).
Discard → delete <id>/.
GET → if working content equals saved content, delete <id>/ and return clean.
Never delete on Pi new_session, chat close or Lantern shutdown.
If the real file is missing, keep the directory and report the document as orphaned. No automatic deletion and no time-based expiry in v1.
id includes the root, so two Lantern instances with different roots never collide. Two instances on the same root at the same time are unsupported; see §19.
5. API design

All mutation endpoints use POST, so the existing do_POST same-origin check applies. Paths are project-relative and resolved with safe_join. v1 enforces an allowlist, WORKING_COPY_SUFFIXES = {".md", ".markdown"}; later this widens to classify(path) == "text".

Endpoint	Request	Success	ErrorsGET /api/work?p=<rel>	—	{saved:{content,version,bom,newline}, work:null|{content,hash,baseVersion,updatedAt}, state, turnActive}	404, 413 (>5 MiB), 415 (non-UTF-8)
POST /api/work/write	{path, content, expectHash | null, baseVersion}	{hash, updatedAt}	409 {reason:"stale", currentHash} · 409 {reason:"pi_turn"} · 409 {reason:"base_changed", currentVersion} on create · 413
POST /api/work/save	{path, expectHash, expectSavedVersion}	{version, bytes}	409 {reason:"stale"|"pi_turn"|"external", currentVersion} · 404
POST /api/work/discard	{path, expectHash}	{ok:true}	409 {reason:"stale"|"pi_turn"}
POST /api/md/render (existing WIP)	{path, content}	{html}	as implemented
Endpoint semantics

write

With expectHash: null, it creates the working copy. The server requires baseVersion to equal the current real hash.
If the content equals the saved content, the server deletes the working copy instead and returns {hash:null}.

save

Take doc_lock, then the CAS core's _SAVE_LOCK.
Refuse if turn_active.
Read the working file and verify work_hash.
Call save_text_cas(real, content, expectSavedVersion).
Re-verify the working hash, then delete the working dir.

Overwrite after an external change is explicit: the client sends expectSavedVersion = currentVersion, the version it was just shown in the conflict banner. There is no force flag.

Why HTTP and not WebSocket for content
WebSocket frames are capped at 2 MiB inbound and the peer queue at 8 MiB outbound.
A JSON-escaped 5 MB document can exceed the outbound budget and get the peer disconnected.
So WebSocket events carry only {path, hash}. Content always travels over HTTP.
6. Browser memory ↔ working file synchronization
Editor memory is the immediate source of truth. The browser re-reads the working file only on open, reload, Pi-change events, settle and 409 recovery.
Flush trigger: after changed() goes idle — 600 ms for files under 1 MiB, 2 s above that.
Forced flush happens before a Pi prompt, before Save, on mode switch (non-blocking) and on pagehide.
One flush in flight at a time. Newer edits coalesce into the next flush. On success, ackedHash = hash.
On 409 stale: if a Pi turn just settled, run the settle reconciliation (§8). Otherwise show "This draft changed elsewhere" with Load current draft / Keep mine (retry with expectHash = currentHash) / Download.
On 409 pi_turn: hold the edits in memory and in the outbox, and flush after settle.
UI rules
The title stays the logical filename, with ● while pending.
Status text never mentions the cache path.
The beforeunload warning fires only if there is unflushed memory text (localRev not acknowledged). Text already in the working copy is safe.
7. Pi redirect and guard design
Prompt context (built server-side; the client never supplies workingPath)
kind: markdown
logicalPath: docs/README.md          # meaning: "this file", relative links, siblings
workingPath: C:\Users\…\.lantern\work\<id>\README.md   # the ONLY path to read/edit/write for this document
markdownMode, line, selectedText (unchanged)

System prompt line

Replace the draftPath text with:

For an active document with workingPath, read and edit only workingPath. logicalPath is its saved location; never read, edit or write it directly. Lantern saves it when the user chooses. Other project files may be edited normally.

Tool policy (Pi 1.2.0)
Keep --tools read,edit,write,grep,find,ls. No shell tools.
Keep --no-extensions --extension pi_markdown_guard.ts. Rename the guard to pi_working_copy_guard.ts when it is generalized.
Guard state (~/.lantern/work/guard.json)

The store writes it atomically whenever a working copy is created or deleted, or a turn starts or ends:

{"staged": [{"real": "<normcase abs>", "working": "<normcase abs>"}],
 "turnWritable": ["<normcase abs working path of the locked doc>"],
 "protectedDir": "<normcase abs ~/.lantern>"}

Guard rules in tool_call

Paths are normalized before comparison: resolve, follow symlinks, normcase.

Target	read	edit / writeA staged real path	Block, with the message "use workingPath <…>"	Block
A working path in turnWritable	Allow	Allow
Any other path under ~/.lantern/ (other working copies, meta.json, guard.json, pi-sessions)	Allow read of working files only	Block
Any other project file	Allow	Allow (direct, unstaged)

Other rules:

grep, find and ls stay allowed everywhere; they are read-only discovery.
If the guard handler fails, the call is blocked. This fail-safe behaviour is already verified.

Self-protection is mandatory. Without the ~/.lantern/ write block, Pi's own write tool could edit guard.json and unblock itself.

Other project files

They stay as normal direct Pi writes in v1. Staging every file would be a second version-control system. The one exception is Markdown that already has a working copy: its real path is blocked as above.

Detection backstop

At settle, the existing real_file_changed() check compares the real file's hash against the turn start. If it changed, emit chat_real_file_touched; the document state becomes external and Save requires an explicit choice. Nothing is ever reverted automatically.

8. Human/Pi concurrent-edit policy
Turn start (chat_prompt with Markdown context)
The browser force-flushes, then sends {context, workHash}. The hash is ackedHash, or null if the document is clean.
The server takes doc_lock. If no working copy exists, it creates one from the real file. It verifies work_hash == workHash; otherwise it rejects with "draft not flushed, retry". It sets turn_active, updates turnWritable, then sends the prompt.
The browser sets turnBaseText = editor text (exactly the flushed text) and turnLocalRev = localRev.
During the turn
On each tool_execution_end, the server re-hashes the working file. If it changed, it emits chat_work_changed {path, hash, final:false}.
If the user hasn't typed (localRev == turnLocalRev): the browser GETs the content and applies it now, in the current mode.
If the user has typed: the browser ignores intermediate updates. The editor stays fully editable, with the banner "Pi is editing — your edits will merge when it finishes." Flushes return pi_turn and are held.
Settle

Settle happens on agent_settled, abort, chat_process_exit, or a failed prompt request; the store releases the lock in a finally. The server emits {final:true}. The browser fetches Pi's result P and reconciles it against the turn base B and the human's current text H:

Case	ActionP == B	Flush H
H == B	Load P
Both changed	merge3(B, H, P): non-overlapping hunks merge, identical hunks dedupe, overlaps keep the human text. Skipped Pi hunks are listed in the chat

Then the browser flushes with expectHash = hash(P).

Why not something simpler
Locking the editor for the turn blocks typing for minutes, including turns that never touch the document.
Holding all Pi output as a proposal discards all of Pi's work if the user types a single character.
Asking the user puts a modal in front of a decision that is mechanical in almost every case.

merge3 already exists and is tested. No CRDT/OT is needed, because the working file has exactly one writer in each phase.

Reload during a turn with held edits

turnBaseText is lost. The outbox holds {text, baseHash}. On reopen, if baseHash != workHash, show Apply my unsent edits / Download / Drop. This case is rare and the fallback is accepted.

9. Shared diff model (Markdown now, any text later)

Rename static/markdown_draft_diff.js to static/text_diff.js. During the transition, keep globalThis.LanternMarkdownDiff as an alias.

type Hunk = {
  kind: 'add' | 'del' | 'mod',
  baseStart: number, baseEnd: number,     // saved lines, 0-based half-open
  draftStart: number, draftEnd: number,   // current lines, 0-based half-open
  baseText: string[],                     // red ghost lines (empty for 'add')
  inline?: { line: number, dFrom: number, dTo: number, bFrom: number, bTo: number }[] // 1:1 paired mod lines
};
diffLines(base: string, draft: string, opts?: { maxEdits?: number }): Hunk[]
merge3(base: string, ours: string, theirs: string): { text, conflicts: Hunk[], appliedPiHunks: number }


Algorithm:

LF-normalize both texts.
Trim the common prefix and suffix (linear).
Run line-level Myers on the remaining middle only, with an edit cap. Above the cap, the middle becomes one mod block.
For 1:1 paired modified lines, compute the intra-line range with a per-line prefix/suffix trim.

The baseline is saved real text, decoded and LF-normalized. In Visual mode it is view.lastSaved (Milkdown's serialization of the saved file), as now, so that normalization isn't shown as edits.

Decorations are always computed from the hunk array and never inserted into document content.

10. Markdown Preview / Visual / Source integration
Mode	Text shown	Diff rendering	Pi updateSource	Editor memory	CodeMirror 6 (reuse the lantern-large-block bundle). Line decorations: add = green, mod = yellow, intra-line spans. Block widgets for red, faded, struck-through ghosts at draftStart. Gutter markers. Viewport-only rendering	A CM6 transaction replacing the minimal changed range keeps the cursor and Ctrl+Z works. Interim (textarea): select the minimal range and execCommand('insertText')
Visual (≤64 KiB)	Editor memory	ProseMirror node decorations (block classes) plus widget decorations for deleted-block ghosts, exposed by a setDiffDecorations(hunks) hook in lantern-crepe. Block-level colours only. Tables: class on the table node; ghosts as a widget after the table	Recreate Milkdown with the new text and restore the bookmark (current switchEditor mechanics). Do not switch modes
Preview	Editor memory via POST /api/md/render (WIP)	Client-side: add md-diff-add/md-diff-mod classes to blocks whose data-l falls in draft hunks; insert ghost <div class="md-diff-del" data-diff-ghost> blocks without data-l	Re-render
Mode switching
Allow Source→Visual while dirty, and remove the current block. Any Milkdown reformatting now shows up as diff hunks, and the existing reformat review still runs at Save.
When converting to Visual will reformat lines, show the notice "Visual will reformat N lines (shown in diff)".
Back to Preview renders the draft and never discards. Add an explicit Discard changes button next to Save and Download draft.
Paged Visual (>64 KiB)

The paged editor (markdown_paged_editor.js) loads and section-saves the real file directly. That is an explicit user Save, so the invariant holds, but it bypasses any working copy. v1 rule: paged Visual and a pending working copy are mutually exclusive.

If a working copy exists, the Edit-visually button for large documents shows "Pending changes — use Source, or Save/Discard first".
While the paged editor has unsaved section edits, Pi prompts stay refused, as now.
Anchors

markdown_anchor_bridge.js must ignore [data-diff-ghost] and CM6/ProseMirror widgets when capturing or restoring. Verify before commit 8.

11. Save / Discard / external-change lifecycle
Save (Ctrl+S or button)
Refuse if a Pi turn is active ("Stop Pi first").
Run the reformat review if Visual reformatted the document.
Force-flush.
POST /api/work/save {expectHash: ackedHash, expectSavedVersion: savedVersion}.
On success: saved = text, the diff clears, ● clears, the outbox clears.
If the user typed during the save, the editor stays dirty. The next flush creates a new working copy against the new base. There is no automatic re-save.
Discard
Confirm.
POST /api/work/discard.
The editor loads the saved text and the outbox clears.
External change (state external on open, or 409 external on Save)

The banner reads: "README.md changed on disk outside Lantern." The diff is shown against the current disk text. Options:

Option	ActionKeep my draft	Next Save sends expectSavedVersion = currentVersion (explicit overwrite)
Discard my draft	Discard as above
Download draft	Save the draft locally

Three-way rebase onto the new disk version is not in v1; it would need a stored copy of the old base text.

Missing real file

Show "Original was moved or deleted". Download remains available. Save is disabled in v1.

12. Crash and reload recovery
Event	OutcomeBrowser tab crash or kill	The working copy holds everything up to the last flush. At most the debounce window is lost; pagehide writes the outbox
LAN or phone disconnect	Flush fails, the outbox holds {baseHash: ackedHash, text}, and it retries on reconnect
Reopen with outbox where baseHash == workHash	Restore silently (it is newer typing) and flush
Reopen with outbox where baseHash != workHash	Prompt: Apply mine / Download / Drop
Lantern restart	Working copies persist. The turn lock is in memory and clears; the Pi process restarts
Power loss during a working write	tmp + fsync + os.replace leaves either the old or the new working file, never a torn one
Pi crash mid-turn	The reader-loop finally emits chat_process_exit. The store releases the turn. The browser reconciles Pi's completed edits at settle
IndexedDB role

The lantern-md-drafts store becomes an outbox only:

Write it on pagehide, visibilitychange to hidden, and flush failure.
Clear it after the next acknowledged flush.
Remove the "Restore draft?" confirm and the drafts.read() authority in start().
The paged editor's paged: keys remain unchanged; the paged editor is out of scope.
13. Performance policy
Size	Diff trigger	Diff location	Source rendering	Flush debounce≤100 KB	~80 ms idle	Main thread	CM6	600 ms
~1 MB	~200 ms idle	Main thread (prefix/suffix trim keeps the middle small)	CM6 viewport	600 ms
~5 MB	~400 ms idle	Web Worker	CM6 viewport; decorations for visible ranges only	2 s

Rules:

Never diff on every keystroke. A newer edit cancels any diff still pending or running.
Use an edit cap with a block-hunk fallback, so the diff cost is bounded.
Server hashing is SHA-256 per write: about 10 ms at 5 MB, which is fine at the debounce rate.
On Windows, os.replace over a file Pi has open can raise PermissionError. Retry 3× with 50 ms backoff, then return 503 "busy, retry".
Visual is ≤64 KiB by design, so its cost is irrelevant.
Preview render already exists and is bounded by MAX_TEXT_CHARS.
14. File- and function-level patch plan against current FJP source
lantern/text_file.py (new; extracted from md_editor.py)
read_text_snapshot(path, max_bytes) — current _read_bytes + _snapshot_from_bytes, without the suffix check.
save_text_cas(path, content, expected_version, max_bytes) — the current save_document body, keeping _SAVE_LOCK, the BOM/CRLF restore, fsync and os.replace.
md_editor.py keeps require_markdown, read_document and save_document as thin wrappers, so existing callers and tests stay unchanged.
lantern/working_copy.py (new)

WorkingCopyStore(root, work_dir, allowed_suffixes) with:

doc_id
get(rel)
write(rel, content, expect_hash, base_version)
save(rel, expect_hash, expect_saved_version)
discard(rel, expect_hash)
working_path(rel)
begin_turn(rel, expect_hash) -> (working_abs, start_real_hash)
end_turn(rel) -> {hash, changed, real_touched}
_write_guard_state()
_atomic_write(path, bytes) — with the Windows retry

Use one threading.Lock per document id.

lan_drive.py
Construct WORK_STORE = WorkingCopyStore(CONFIG.root, Path.home()/".lantern"/"work", {".md", ".markdown"}) and pass it to PiChatManager.
Routes: GET /api/work → api_work_get; POST /api/work/write|save|discard → api_work_write|save|discard.
Keep the WIP api_md_render as is.
Keep /api/md/save for the paged editor and the legacy ?edit=1 Markdown editor.
plugin.py
Commit the WIP (_render_markdown_text, render_markdown_draft, markdown_draft_diff.js include).
Later, rename the include to text_diff.js.
lantern/pi_chat.py
Remove: from .pi_draft import MarkdownDraftShadow, self.drafts, _emit_draft_update, and every self.drafts.clear() (in new_session, prompt, close).
Constructor: take work_store. Set LANTERN_PI_GUARD_STATE to work_store.guard_path.
prompt(message, context, work_hash):
For Markdown: working_abs = store.begin_turn(rel, work_hash), then add logicalPath and workingPath.
On request failure: store.end_turn (in a finally).
Track self.turn_rel.
_reader_loop:
tool_execution_end → if turn_rel is set, call store.peek_hash and emit chat_work_changed {path, hash, final:false} on change.
agent_settled and the finally block → store.end_turn and emit {final:true} plus chat_real_file_touched if applicable.
build_prompt: fields kind, folder, path, logicalPath, workingPath, markdownMode, line. Remove promptId/draftPath/savedPath/baseVersion/draftRevision.
SYSTEM_PROMPT: the §7 wording.
abort(): no draft emission. Settle handles it.
lantern/pi_draft.py

Delete it.

lantern/pi_markdown_guard.ts

Rename to pi_working_copy_guard.ts and implement the §7 rules: read and edit blocks, the ~/.lantern write block, turnWritable, and normcase/realpath handling. Requires review because the current file was not attached.

lantern/ws.py
chat_prompt: pass msg.get("workHash"). Remove draft.
No new message types are received. chat_work_changed is a broadcast with the existing chat_ prefix, so the locked-peer filtering still applies.
static/chatbot.js
Replace captureMarkdownDraft() with prepareMarkdownTurn(context):
If the editor is active, await editor.flushNow(), call editor.beginPiTurn(), and return ackedHash.
If the editor is inactive, return null (the server creates the working copy from the real file).
Keep the paged-editor refusal.
Remove the 1 MiB draft cap and the /api/md/document fallback fetch.
onMessage:
chat_work_changed → editor.onWorkChanged(path, hash, final).
Replace the chat_draft_update branch.
Keep the chat_real_file_touched handling.
Exports: remove captureMarkdownDraft.
static/markdown_visual_shell.js
start():
Load via GET /api/work. Set view.baseline/version from saved.
Take editor contents from work?.content ?? saved.content.
Remove the IndexedDB restore confirm and apply the outbox per §12.
Add: flushNow(), queueFlush() (replaces queueDraft/saveDraft), beginPiTurn(), onWorkChanged() (live-apply when idle, merge3 at final; replaces applyPiDraft's forced Source and area.value assignment), discard().
save(): flush, then POST /api/work/save. Remove the direct /api/md/save call for the full editor.
close(): remove the confirm and drafts.clear(). Render the draft via /api/md/render into the article.md-preview container, then add the hunk annotations. No location.reload().
switchEditor(): remove the dirty Source→Visual block. Add the reformat notice.
renderSourceDiff(): keep it until commit 7, then replace it with the CM6 adapter.
Exports: {state, open, save, preview, discard, flushNow, beginPiTurn, onWorkChanged}. Remove getDraftSnapshot, beginPiDraft, applyPiDraft.
static/markdown_paged_editor.js

open() must check GET /api/work (or receive the state from the shell) and refuse if state != clean (§10).

static/markdown_draft_diff.js → static/text_diff.js

Rename and keep an alias. Ensure prefix/suffix trimming, an edit cap and an inline field. Add a worker entry point for large inputs.

15. Commit sequence (small, each one green)
feat(markdown): render unsaved draft preview — commit the WIP plugin.py + lan_drive.py as is.
refactor(text): extract generic text snapshot/CAS from md_editor — text_file.py; md_editor delegates; existing tests pass unchanged.
feat(work): WorkingCopyStore and /api/work endpoints (Markdown allowlist) — server only, with unit tests.
refactor(markdown): bind editor to working copy — load, flush, save, discard, outbox; non-destructive Preview of the draft; drop the dirty Source→Visual block.
fix(markdown): keep paged editor and pending working copy exclusive.
refactor(chat): Pi edits the working copy — delete pi_draft.py, add the turn lock, hash-only events, guard v2, remove draft clearing, new prompt fields.
fix(markdown): apply Pi changes in place — no mode switch, undo-preserving minimal replace, settle merge3, skipped-hunk report.
feat(markdown): CodeMirror Source with inline deletion ghosts — reuse the lantern-large-block CM6 bundle; diff in a worker for large files. This completes the core continuous-editable-diff UX.
feat(markdown): annotate Preview with pending hunks.
feat(markdown): Visual diff decorations — lantern-crepe hook.
16. Tests and acceptance
Invariant (automated; hash the real file before and after each step)
Typing in Source, then Visual, then Preview, then a reload, then a Lantern restart, then a browser kill: the real hash is unchanged.
A Pi turn that edits the document: the real hash is unchanged and the working hash changes.
Pi tries to edit / write / read the staged real path: blocked. Pi tries to write ~/.lantern/work/guard.json or another document's working copy: blocked.
Shell tools are unavailable.
Pi new_session, chat close and Lantern shutdown: the working copy still exists.
Only the following change the real hash: Save, paged-section Save, and save after an explicit external-overwrite choice.
Store unit tests
write with a stale expectHash → 409 stale. write during a turn → 409 pi_turn. Create with a stale baseVersion → 409.
Writing content equal to the saved content deletes the working copy.
save with the working copy modified by a third party → 409. Save during a turn → 409. External real change → 409 external. Retry with expectSavedVersion = current succeeds.
CRLF and BOM files: the working copy is LF without BOM; after save, the real file keeps CRLF and BOM.
Windows: os.replace while another handle has the file open → retried, or 503 without corruption.
Concurrency (adversarial)
User edits line 10 while Pi edits line 50: both survive.
Same line: the human's text wins and the skipped Pi hunk is listed.
Pi makes 3 sequential edits while the user is idle: each appears live, and Ctrl+Z undoes Pi's edit (after commit 7).
The user types during the turn, Pi makes no document edit: the held edits flush after settle.
Abort mid-turn, or kill the Pi process: completed edits reconcile and the turn lock is released.
Two tabs on the same document: the second tab's flush gets stale and offers Load / Keep mine / Download. Nothing is silently overwritten.
Prompt sent within 100 ms of typing: Pi reads the typed text (forced flush plus the hash check).
A terminal edits the working file: the next flush gets stale.
Continuous editable diff UX
Typing inside green or yellow text keeps the caret and focus, and colours update within the debounce.
Deleting a saved line shows an inline red ghost at that position (Source). Retyping the exact saved text removes the hunk. Undoing to the saved state clears all colours and ●.
getMarkdown(), CM6 doc.toString() and the working file never contain ghost or decoration text. Copying a selection across a ghost yields only real text.
Preview, Visual and Source with pending hunks: same colours on the same lines. Anchors round-trip to the same line. Wide-table suite passes.
After Save: no hunks, no working dir. After Discard: the saved text is shown.
Performance
100 KB: no perceptible lag.
1 MB: diff updates ≤250 ms after idle.
5 MB: typing never blocks the main thread for more than 50 ms; the diff runs in a worker; only visible lines are decorated.
Flushing 5 MB does not block typing.
Recovery
Kill the browser after typing and before the debounce: the outbox restores silently on reopen.
Outbox base differs from the working hash: Apply / Download / Drop prompt.
Restart Lantern mid-turn: the working copy keeps Pi's completed edits, and the next prompt works.
17. Current implementation to remove or replace (checklist)
Location	Item	Actionlantern/pi_draft.py	MarkdownDraftShadow	Delete
pi_chat.py	self.drafts, _emit_draft_update, drafts.clear() ×3, draft param, draftPath/savedPath/promptId/baseVersion/draftRevision fields	Replace with the store, logicalPath/workingPath
pi_chat.py	SYSTEM_PROMPT draftPath wording	Replace (§7)
ws.py	chat_prompt draft payload	Replace with workHash
chatbot.js	captureMarkdownDraft, the 1 MiB cap, the /api/md/document fallback, the chat_draft_update handler	Replace with prepareMarkdownTurn and chat_work_changed
markdown_visual_shell.js	getDraftSnapshot, beginPiDraft, applyPiDraft (forced Source, area.value), the piTurns map	Replace (§14)
markdown_visual_shell.js	The IndexedDB restore confirm in start(); drafts as authority	Outbox only
markdown_visual_shell.js	close() discard confirm, drafts.clear(), savedSincePreview reload	Non-destructive draft Preview
markdown_visual_shell.js	The dirty Source→Visual block in switchEditor()	Remove; add the reformat notice
markdown_visual_shell.js	Direct /api/md/save in save()	/api/work/save
markdown_visual_shell.js	renderSourceDiff full backdrop and separate deletions list	Interim; replaced by CM6 in commit 7
18. What NOT to build now
CRDT/OT, live merging of human typing into a running Pi turn, or per-keystroke server sync.
Per-hunk accept/reject.
Staging for non-Markdown files, or a generic text editor UI. The store is generic, and only the allowlist changes later.
Three-way rebase onto an externally changed real file, or a stored base-text snapshot.
Rename or move tracking for working copies, time-based expiry, or a multi-instance cross-process lock.
Character-level Myers diff, intra-line colours in Visual, or rendered Markdown inside ghosts (ghosts show raw source, struck through).
Pi edits in paged Visual, or a working copy combined with the paged editor.
A generic process-session abstraction, or Pi RPC routed through the PTY.
Parsing Pi's details.diff. The diff always comes from saved vs. current text.
Binary or image working copies.
19. Blockers that should stop implementation until resolved
Guard self-protection (stops commit 5). Verify that pi_markdown_guard.ts (not reviewed) blocks Pi write and edit under ~/.lantern/, including guard.json, and normalizes Windows case and symlinks. Without this, Pi can disable its own guard.
Paged editor bypass (stops commit 3 from shipping alone). Commit 4 must land with or before commit 3's release. Otherwise a 100 KB document can have a pending working copy while paged Visual edits and saves the real file from stale content.
Data-destroying session hooks (stops commit 5). All drafts.clear() calls tied to the Pi session lifecycle must be gone before working copies hold user data.
Content over WebSocket. No event may carry document text, because of the 8 MiB outbound queue disconnect. Enforce this in code review.
Unseen files to verify before their commits:
static/markdown_draft_diff.js: prefix/suffix trim and edit cap; otherwise 5 MB diffs freeze the UI.
markdown_anchor_bridge.js: ignores ghosts and widgets.
lantern-large-block bundle: exposes CM6 extension and decoration APIs, or can be rebuilt to.
lantern-crepe: exposes a ProseMirror plugin hook (commit 9 only; not a blocker for 1–8).
Mixed line endings. Saving a newline: "mixed" file writes LF throughout. The LF-normalized diff hides this. Either show a one-line warning before saving such files, or refuse Visual edits for them. Decide before commit 3; it is a correctness issue, not cosmetic.
Same root, two Lantern processes. Unsupported. Detect it at startup with a lock file in ~/.lantern/work/ and refuse to enable working copies in the second process.
Production-worthiness verdict

The design is production-worthy:

There are two copies of the document, each with a single owner and a single writer per phase.
Every write is checked with a hash CAS.
The real file is reachable only through the existing CAS save or an explicit paged save.
Crash recovery is a property of the storage layout, not extra code.
The store is generic now, and widening to other text files later is an allowlist change.