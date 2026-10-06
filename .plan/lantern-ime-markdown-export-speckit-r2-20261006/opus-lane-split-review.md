[Reading 56 lines from start (total: 56 lines, 0 remaining)]

Reasoning completed in 1 step

VERDICT: APPROVE_WITH_REQUIRED_EDITS

RATIONALE

Decoupling the Markdown lane is sound. The Markdown lane is owned by plugin.py, a new static/markdown_preview.js and a new Mermaid vendor asset. None of these touch the terminal input boundary (terminal_scm.js, xterm.js, lantern_ws.py, lantern_terminal.py, lan_drive.py). T6 is already gated only on T3/T4 green and T5 passed, with no terminal dependency.
sharepoint
sharepoint
The terminal safety gate is not weakened. No terminal product code changes before a physical keyboard measurement, the automation probe is not accepted as evidence, and T2 stays blocked. The probe correctly reports that SendInput in Vietnamese mode produced plain keyCodes 83/84/65/82/84 and the exact string "start". It records the result as NOT_MEASURED, and the original UniKey settings were restored.
sharepoint
The attached docs already decouple the lanes, but they don't match the proposal. The current spec, plan and tasks use T0-A PASS → T0-B PASS-as-falsification (the "as" trace) → T0-C physical gate. They also let T1 baseline guard tests start now. The proposal says "T0-A → physical T0-B → T1 → T2" instead. The only document still blocking all product work globally is the Opus confirmation, which predates the current revision. You need to pick one name for the physical gate, or the gate's meaning will drift between documents.
sharepoint
+2
sharepoint
The two T0-B records conflict. The spec records an accepted "as" trace (keyCode 231 plus Backspaces, payloads ['a','·','\u007f','\u007f','á']). The probe file says "T0-B: NOT_MEASURED" and never mentions that trace. Both records need to be reconciled under one label.
sharepoint
+1
Section C as worded broadens scope. It says release requires the "terminal manual matrix". The current docs require the full IME regression matrix only if a class-(ii) finding leads to a terminal code change. Release should require that the physical gate is closed, not the full matrix.
sharepoint
T5 research text has a leftover terminal dependency. It says the final decision happens "after T0-B" and leaves the KaTeX decision "pending". The spec already resolves KaTeX as documented residual risk, with no trust option and a re-audit trigger.
sharepoint
sharepoint

DOC_EDITS

Gate naming (spec, plan and tasks). Choose one option and apply it the same way everywhere:
(a) Keep the current names. The physical gate is T0-C, and T0-B stays "PASS as falsification (as-trace)". Then add a line to the probe record: "the SendInput automation probe is non-evidence for T0-C; it doesn't count toward the 50 attempts."
(b) Rename T0-C to "physical T0-B" everywhere. Then relabel the old as-trace as T0-B0 (falsification).
Status lines (spec, plan, tasks). Add: "The automation probe (SendInput, UniKey 4.6 RC2) cannot exercise UniKey. The physical gate remains NOT_MEASURED. The original UniKey registry settings were restored."
Terminal order (tasks, top rule). State this explicitly:
T1 = guard tests only, with no change to static/terminal_scm.js.
T1 may run before the physical gate if you keep the current docs, or only after it if you adopt the proposal's order. Pick one.
T2 stays blocked until the physical gate gives a class-(ii) result and a focused review approves a changed contract.
T8 (tasks and plan). Replace "full regression" gating with: "T8 runs per lane. The combined T8 runs only after both lanes reach their exit."
Release (spec acceptance). Add a release row: "Combined release requires (1) the physical gate closed as NOT_REPRODUCED, class (i), class (ii) or class (iii), with four-channel evidence; (2) the full IME matrix only if terminal code changed; (3) M-A1–M-A12. If the physical gate stays NOT_MEASURED, the combined increment is not done or releasable. The Markdown lane may be implemented and tested on a separate branch or worktree but not merged as a release."
T5 research record. Remove "after T0-B". Change "decision pending" to "resolved per spec: documented residual risk, no KaTeX trust option, re-audit when Mermaid ships KaTeX ≥0.18.2". Also add the lodash-es 4.18.1 and Chevrotain 11.1.2 reachability rows (INCOMPLETE until verified).
Opus confirmation. Mark it "superseded on implementation gating by the lane-split revision". Check that its E1–E3 fixes are still present: the auto-restore on/off matrix in T-A2, lan_drive.py in the unchanged lists, and the double-backtick [`x`](u).
Markdown branch rule (tasks, T3–T7). Add: "The Markdown branch's diff must show no changes to the terminal-owned files or requirements.txt. Check this at each Markdown commit, not only at T8."

IMPLEMENTATION_GATE

May begin now, once the edits above are applied:
T3 tests first, then T4 (bounded parser and nonce CSP for all preview kinds).
Finishing the T5 record.
T6 vendoring, but only after T5 passes and T3/T4 are green.
T7 browser acceptance with Lantern reachable and every non-Lantern origin blocked.
All of this goes on a separate Markdown branch or worktree.
T1 guard tests, only if you keep the current docs' ordering.
Still blocked:
Any change to terminal product code (terminal_scm.js, xterm.js, lantern_ws.py, lantern_terminal.py, lan_drive.py).
T2, until the physical gate gives class (ii) and a focused review approves it.
Mermaid vendoring before T5 passes.
Combined T8.
Release, which also needs the M-A12 sign-off and follow-up ticket.
Unchanged: no CDN, no new Python dependency, nonce-only script CSP, no terminal persistence.