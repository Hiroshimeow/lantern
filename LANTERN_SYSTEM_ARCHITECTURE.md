# Lantern System Architecture & Function Flows

> Source-grounded architecture document for the current Lantern repository.
>
> Scope: file manager, HTTP routing, plugin preview, Markdown/Mermaid rendering, terminal/PTY, WebSocket transport, Git/SCM, media preview, configuration, security boundaries, and lifecycle.
>
> This file is intentionally Mermaid-heavy. It doubles as a real system document and a complex Markdown/Mermaid regression fixture for Lantern itself.

---

## 1. System purpose

Lantern is a lightweight LAN/Tailscale web file manager with integrated terminal and Git tooling.

Main capabilities:

- browse, search, preview, upload, edit, download, copy, move, rename, duplicate, delete, archive, and extract files;
- stream media and generate thumbnails;
- preview Markdown, text/code, CSV/TSV, DOCX, XLSX/XLSM, and PDF;
- render local/offline Mermaid diagrams inside Markdown preview;
- export each Mermaid diagram to PNG;
- print/save Markdown preview to PDF;
- provide multiple browser terminals backed by real PTY/ConPTY;
- preserve terminal processes across browser reconnect while Lantern itself remains running;
- expose Git status, history, diff, stage/unstage, checkout, commit, pull, and push;
- remain dependency-light and framework-light.

---

## 2. Top-level system context

```mermaid
flowchart LR
    U["User Browser"]
    LAN["Trusted LAN / Tailscale"]
    HTTP["ThreadingHTTPServer\nlan_drive.py"]
    H["Handler"]
    FS["Configured Root Filesystem"]
    CACHE["Thumbnail / Preview Cache"]
    PLUGIN["plugin.py\nPreview Engine"]
    WS["lantern_ws.py\nWebSocket Hub"]
    TERM["lantern_terminal.py\nTerminalManager"]
    PTY["WinConPty / PosixPty"]
    SCM["lantern_scm.py\nScmService"]
    GIT["git CLI"]
    MEDIA["Pillow / ffmpeg / ffprobe\noptional"]
    STATIC["static/*\nxterm.js / Mermaid / JS"]

    U --> LAN --> HTTP --> H
    H --> FS
    H --> CACHE
    H --> PLUGIN
    H --> STATIC
    H --> WS
    H --> MEDIA
    WS --> TERM --> PTY
    WS --> SCM --> GIT
    TERM --> FS
    SCM --> FS
    PLUGIN --> FS

    classDef core fill:#1f2937,stroke:#7dd3fc,color:#fff
    classDef io fill:#172554,stroke:#60a5fa,color:#fff
    classDef ext fill:#3f3f46,stroke:#a1a1aa,color:#fff

    class HTTP,H,PLUGIN,WS,TERM,SCM core
    class U,FS,CACHE,STATIC io
    class PTY,GIT,MEDIA ext
```

### Primary trust assumption

Lantern has no built-in authentication. The intended trust boundary is the private LAN/Tailscale network plus host firewall/reverse-proxy controls.

---

## 3. Repository module map

| Module | Primary responsibility | Important owners |
| --- | --- | --- |
| `lan_drive.py` | HTTP server, file manager UI/API, media serving, configuration | `AppConfig`, `Handler`, `main` |
| `plugin.py` | document/Markdown preview and preview-page CSP | `render_content`, `_render_markdown`, `render_preview_page` |
| `static/markdown_preview.js` | Mermaid render, PNG export, Print/PDF UI | `loadMermaid`, `initializeMermaid`, `renderOne`, `exportPng` |
| `lantern_ws.py` | WebSocket framing, connection hub, command dispatch | `WebSocketPeer`, `WebSocketHub`, `upgrade`, `dispatch` |
| `lantern_terminal.py` | PTY/ConPTY session ownership and retained output | `NativePty`, `WinConPty`, `PosixPty`, `TerminalManager` |
| `static/terminal_scm.js` | xterm UI, reconnect, terminal tabs, Git panel | `connect`, `makeX`, `newTerminal`, `refreshScm`, `runGit` |
| `lantern_scm.py` | read-side Git queries and metadata watching | `ScmService` |
| `test_plugin.py` | preview/CSP/Markdown security contracts | `MarkdownPreviewTests`, `HtmlAudit` |
| `test_terminal_ui.py` | browser terminal behavior contracts | `TerminalUiParityTests` |
| `test_terminal_scm.py` | terminal manager, SCM, WebSocket protocol | parity test classes |
| `test_security.py` | HTTP mutation security | `HttpMutationSecurityTests` |

---

# PART A — APPLICATION LIFECYCLE

## 4. Startup lifecycle — `main()`

```mermaid
flowchart TD
    A["python lan_drive.py"] --> B["parse_args()"]
    B --> C["build_config(args)"]
    C --> D{"root exists?"}
    D -- no --> E["print error + exit(2)"]
    D -- yes --> F["TerminalManager(root, WS_HUB.broadcast)"]
    F --> G["ScmService(root, WS_HUB.broadcast)"]
    G --> H["ensure_cache_dir(cache_dir)"]
    H --> I{"save config?\n--save-config or first run"}
    I -- yes --> J["write_config_file(CONFIG)"]
    I -- no --> K["continue"]
    J --> K
    K --> L["os.chdir(CONFIG.root)"]
    L --> M["print local + LAN URLs"]
    M --> N["ThreadingHTTPServer((host, port), Handler)"]
    N --> O["serve_forever()"]
    O --> P{"shutdown path"}
    P -- Ctrl+C --> Q["httpd.shutdown()"]
    Q --> R["SCM_SERVICE.close()"]
    R --> S["TERM_MANAGER.kill_all()"]
    P -- process exit --> R
```

### Startup invariants

- the configured root must exist;
- terminal and SCM managers are created once per Lantern process;
- terminal persistence is process-lifetime persistence, not process-restart persistence;
- HTTP requests are handled by a threaded server;
- shutdown closes SCM watchers and all terminal processes.

---

## 5. Configuration resolution flow

```mermaid
flowchart TD
    A["CLI args"] --> B["config_file_default_path() / --config"]
    B --> C["load_simple_yaml()"]
    C --> D["AppConfig defaults"]
    D --> E["apply file config"]
    E --> F["apply CLI overrides"]
    F --> G["normalize_* helpers"]
    G --> H["norm_root()"]
    H --> I["resolved AppConfig"]
    I --> J{"--save-config?"}
    J -- yes --> K["write_config_file()"]
    J -- no --> L["runtime-only overrides"]
```

Important normalization functions:

- `normalize_sort`
- `normalize_view`
- `normalize_page_limit`
- `normalize_fit`
- `normalize_animation`
- `normalize_conflict`
- `normalize_recursive_depth`

---

# PART B — HTTP AND FILE MANAGER

## 6. GET request router — `Handler.do_GET()`

```mermaid
flowchart TD
    A["HTTP GET"] --> B["urlsplit(self.path)"]
    B --> C{path}
    C -- "/favicon.ico" --> FAV["204"]
    C -- "/ws" --> WSINIT{"TERM_MANAGER + SCM_SERVICE ready?"}
    WSINIT -- no --> WS503["503 runtime not initialized"]
    WSINIT -- yes --> WSU["upgrade_websocket()"]

    C -- "/static/*" --> STATIC["serve_app_asset()"]
    C -- "/api/info" --> INFO["api_info()"]
    C -- "/api/config" --> CFG["api_config_get()"]
    C -- "/api/list" --> LIST["api_list()"]
    C -- "/api/thumb" --> TH["api_thumb()"]
    C -- "/api/folder_preview" --> FP["api_folder_preview()"]
    C -- "/api/video_info" --> VI["api_video_info()"]
    C -- "/api/subtitle" --> SUB["api_subtitle()"]
    C -- "/api/plugin/info" --> PI["api_plugin_info()"]
    C -- "/api/plugin/preview\n/api/preview" --> PP["api_plugin_preview()"]

    C -- other --> SAFE["safe_join(parsed.path)"]
    SAFE --> Q{"query contains edit?"}
    Q -- yes --> EDIT["serve_editor(target)"]
    Q -- no --> TYPE{"target type"}
    TYPE -- directory --> DIR["serve_directory(target)"]
    TYPE -- file + download --> DL["serve_static_file(download=True)"]
    TYPE -- file --> FILE["serve_file(target)"]
    TYPE -- missing --> N404["404 Not found"]

    B -. PermissionError .-> E403["403"]
    B -. unexpected exception .-> E500["500"]
```

---

## 7. POST mutation router — `Handler.do_POST()`

```mermaid
flowchart TD
    A["HTTP POST"] --> B{"Origin header present?"}
    B -- yes --> C{"same_origin(self)?"}
    C -- no --> E403["403 POST Origin must match Host"]
    C -- yes --> R["route by path"]
    B -- no --> R

    R --> U["/api/upload → api_upload()"]
    R --> S["/api/save → api_save()"]
    R --> MK["/api/mkdir → api_mkdir()"]
    R --> NF["/api/newfile → api_newfile()"]
    R --> RN["/api/rename → api_rename()"]
    R --> CP["/api/copy → api_copy()"]
    R --> MV["/api/move → api_move()"]
    R --> DP["/api/duplicate → api_duplicate()"]
    R --> BR["/api/batch_rename → api_batch_rename()"]
    R --> EX["/api/extract → api_extract()"]
    R --> DEL["/api/delete → api_delete()"]
    R --> AR["/api/archive → api_archive()"]
    R --> ZIP["/api/zip → api_zip()"]
    R --> CFG["/api/config → api_config_post()"]
    R --> EXT["/api/plugin/extensions → api_plugin_extensions()"]
    R --> N404["404 API not found"]

    R -. BadRequest .-> E400["400 JSON error"]
    R -. PermissionError .-> P403["403 JSON error"]
    R -. unexpected exception .-> E500["500 JSON error"]
```

---

## 8. Path confinement and mutation safety

```mermaid
flowchart TD
    A["User-provided relative path"] --> B["safe_join() / resolve_existing()"]
    B --> C["decode + normalize"]
    C --> D["resolve absolute candidate"]
    D --> E{"inside CONFIG.root?"}
    E -- no --> F["PermissionError / reject"]
    E -- yes --> G["operation-specific validation"]

    G --> H{"copy / move?"}
    H -- yes --> I["reject_self_nesting()"]
    I --> J["conflict_target()"]
    J --> K["rename / overwrite / skip"]
    H -- no --> L["continue"]

    K --> M["filesystem mutation"]
    L --> M

    M --> N["JSON result / refreshed UI"]
```

Core helpers:

- `safe_join`
- `ensure_under_root`
- `resolve_existing`
- `resolve_destination_dir`
- `reject_self_nesting`
- `conflict_target`
- `unique_path`

---

## 9. Directory listing and search pipeline

```mermaid
flowchart TD
    A["GET /api/list"] --> B["parse query: path, offset, limit, sort, query"]
    B --> C["safe_join / resolve directory"]
    C --> D["list_entries_page()"]
    D --> E{"recursive_depth > 0?"}
    E -- no --> F["scan direct children"]
    E -- yes --> G["walk bounded subtree"]
    F --> H["should_hide_entry()"]
    G --> H
    H --> I["stat + classify()"]
    I --> J["entry_to_json()"]
    J --> K["sort_key_for()"]
    K --> L["paginate"]
    L --> M["entries + total + paging metadata"]
    M --> N["browser grid/list"]
```

---

## 10. File operation family

```mermaid
flowchart LR
    UI["Browser selection"] --> API["POST API"]

    API --> CP["copy_item()"]
    API --> MV["move_item()"]
    API --> DUP["duplicate_name() + copy_item()"]
    API --> REN["rename"]
    API --> DEL["delete"]
    API --> ARC["iter_archive_entries()"]
    API --> EXT["extract_archive()"]

    CP --> CON["conflict_target()"]
    MV --> CON
    DUP --> CON
    CON --> FS["Filesystem"]

    ARC --> ZIP["ZIP/TAR response"]
    EXT --> SAFE["safe_extract_member_path()"]
    SAFE --> WRITE["write_extracted_file()"]
    WRITE --> FS
```

Archive extraction specifically confines every extracted member beneath the selected destination.

---

# PART C — PREVIEW AND MARKDOWN

## 11. Generic preview dispatch — `render_content()`

```mermaid
flowchart TD
    A["Preview request"] --> B["can_preview(path)"]
    B --> C["_kind(path)"]
    C --> D{kind}

    D -- markdown --> MD["_render_markdown()"]
    D -- text/code/log/env --> TXT["_render_text()"]
    D -- csv/tsv --> CSV["_render_csv()"]
    D -- docx --> DOCX["_render_docx()"]
    D -- xlsx/xlsm --> XLSX["_render_xlsx()"]
    D -- pdf --> PDF["_render_pdf()"]
    D -- unsupported --> RAW["raw/download fallback"]

    MD --> OUT["title + HTML body"]
    TXT --> OUT
    CSV --> OUT
    DOCX --> OUT
    XLSX --> OUT
    PDF --> OUT
```

---

## 12. Markdown parser flow — `_render_markdown()`

```mermaid
flowchart TD
    A["Read Markdown text"] --> B["remove NUL / normalize lines"]
    B --> C["one-pass line parser"]
    C --> D{current construct}

    D -- fenced code --> FENCE["track opener char + length + info"]
    D -- Mermaid fence --> MERM["emit .mermaid-diagram\n+ source + output + PNG button"]
    D -- table --> TABLE["_split_table_row()\n_is_table_separator()"]
    D -- task/list --> LIST["render list/task item"]
    D -- heading --> HEAD["render h1/h2/h3..."]
    D -- quote --> QUOTE["render blockquote"]
    D -- paragraph --> PARA["_flush_md_paragraph()"]

    FENCE --> INLINE["_md_inline() where applicable"]
    TABLE --> INLINE
    LIST --> INLINE
    HEAD --> INLINE
    QUOTE --> INLINE
    PARA --> INLINE

    INLINE --> LINK{"link/image?"}
    LINK -- link --> SAFE["_safe_markdown_target(image=False)"]
    LINK -- image --> SAFEIMG["_safe_markdown_target(image=True)"]
    SAFE --> ESC["escaped + quoted HTML"]
    SAFEIMG --> ESC
    MERM --> ESC

    ESC --> BODY["safe preview HTML body"]
```

---

## 13. Markdown link/image security path — `_safe_markdown_target()`

```mermaid
flowchart TD
    A["Raw Markdown URL"] --> B["remove parser whitespace"]
    B --> C["trim C0 controls / spaces"]
    C --> D["html.unescape once"]
    D --> E["backslash → slash"]
    E --> F["split path/query/fragment"]
    F --> G["URL-unquote path once"]
    G --> H{"encoded traversal residue?\n%2e%2e / %2f"}
    H -- yes --> REJ["reject"]
    H -- no --> I{"protocol-relative //host?"}
    I -- yes --> REJ
    I -- no --> J{"scheme"}
    J -- javascript/data/vbscript --> REJ
    J -- http/https/mailto --> K{"image?"}
    K -- yes --> REJ
    K -- no --> ALLOW["allow external link"]
    J -- relative/root/fragment --> RES["resolve against Markdown parent"]
    RES --> ROOT{"inside Lantern root?"}
    ROOT -- no --> REJ
    ROOT -- yes --> ENC["encode path segments once"]
    ENC --> LOCAL["emit confined local URL"]
```

---

## 14. Preview page + CSP construction — `render_preview_page()`

```mermaid
flowchart TD
    A["api_plugin_preview()"] --> B["safe_join('/' + p)"]
    B --> C{"target is file?"}
    C -- no --> D["404"]
    C -- yes --> E["render_preview_page()"]

    E --> F["render_content()"]
    F --> G["fresh secrets.token_urlsafe nonce"]
    G --> H["build nonce-only CSP"]

    H --> I{"body contains Mermaid diagram?"}
    I -- yes --> J["HEAD: Mermaid vendor script + defer + nonce"]
    I -- no --> K["no Mermaid vendor load"]

    J --> L["HEAD: markdown_preview.js + defer + nonce"]
    K --> L
    L --> M["toolbar: Back / Print-PDF / Preview / Edit / Raw / Download"]
    M --> N["HTTP 200 text/html"]
```

Current CSP:

```text
default-src 'none';
script-src 'nonce-{random}';
style-src 'self' 'unsafe-inline';
img-src 'self' data: blob:;
connect-src 'none';
base-uri 'none';
object-src 'none';
form-action 'none'
```

---

## 15. Mermaid render lifecycle — `static/markdown_preview.js`

```mermaid
flowchart TD
    A["DOMContent loaded via deferred helper"] --> B["collect .mermaid-diagram\nmax 24"]
    B --> C{"any diagrams?"}
    C -- no --> DONE["No Mermaid runtime work"]
    C -- yes --> D["loadMermaid()"]
    D --> E{"window.mermaid already available?"}
    E -- yes --> F["initializeMermaid(runtime)"]
    E -- no --> G["wait for nonce-authorized local vendor"]
    G --> F

    F --> H["strict securityLevel\nstartOnLoad:false\nhtmlLabels:false"]
    H --> I["renderAll() sequentially"]
    I --> J["yieldUi() between diagrams"]
    J --> K["renderOne(runtime, wrapper, index)"]
    K --> L{"render success?"}
    L -- yes --> M["inject sanitized Mermaid SVG output"]
    M --> N["enable PNG button"]
    L -- no --> O["show isolated render failure"]
    N --> P{"more diagrams?"}
    O --> P
    P -- yes --> J
    P -- no --> Q["pendingRenders resolved"]
```

Mermaid is fully local/offline; no CDN is required.

---

## 16. Mermaid PNG export — `exportPng()`

```mermaid
flowchart TD
    A["Click PNG"] --> B["find rendered SVG"]
    B --> C["svgDimensions()"]
    C --> D["derive viewBox / rendered dimensions"]
    D --> E["scale target ≈2x"]
    E --> F["cap <=8192 px per side\nand ≈32 MP"]
    F --> G["clone SVG + explicit width/height/xmlns"]
    G --> H["serialize → SVG Blob"]
    H --> I["Object URL → Image.decode()"]
    I --> J["Canvas white background"]
    J --> K["drawImage()"]
    K --> L["canvas.toBlob(image/png)"]
    L --> M["temporary download anchor"]
    M --> N["<doc>-diagram-N.png"]
    N --> O["revoke object URLs"]
```

---

## 17. Whole Markdown → PDF

```mermaid
flowchart TD
    A["Click Print / Save as PDF"] --> B["await pendingRenders"]
    B --> C["window.print()"]
    C --> D["print CSS switches to light mode"]
    D --> E["hide toolbar / UI controls"]
    E --> F["remove table/code overflow clipping"]
    F --> G["pre wraps for print"]
    G --> H["Mermaid SVG remains vector in page"]
    H --> I["Browser print dialog"]
    I --> J["Save as PDF"]
```

This uses the browser's print/PDF path rather than introducing a server-side PDF engine.

---

# PART D — TERMINAL

## 18. Terminal end-to-end data path

```mermaid
sequenceDiagram
    participant U as User
    participant XT as xterm.js
    participant JS as terminal_scm.js
    participant WS as lantern_ws.py
    participant TM as TerminalManager
    participant PTY as WinConPty/PosixPty
    participant SH as Shell

    U->>XT: keyboard input
    XT->>JS: term.onData(data)
    JS->>WS: terminal_input over WebSocket
    WS->>TM: input(term_id, data)
    TM->>PTY: write(data)
    PTY->>SH: native PTY stdin

    SH-->>PTY: stdout/stderr
    PTY-->>TM: on_data()
    TM->>TM: append retained scrollback
    TM-->>WS: broadcast terminal_output
    WS-->>JS: JSON WebSocket message
    JS-->>XT: term.write(output)
    XT-->>U: rendered terminal
```

---

## 19. Browser terminal creation — `newTerminal()`

```mermaid
flowchart TD
    A["Open Terminal drawer"] --> B{"active live terminal?"}
    B -- yes --> C["activate existing terminal"]
    B -- no --> D["newTerminal()"]
    D --> E["generate terminalId"]
    E --> F["ensure(meta, pending=True)"]
    F --> G["makeX(meta)"]
    G --> H["new Terminal() + FitAddon"]
    H --> I["term.open(host)"]
    I --> J["attach custom key handler"]
    J --> K["term.onData → WebSocket terminal_input"]
    K --> L["fit terminal"]
    L --> M["send terminal_create\nid,cwd,cols,rows,title"]
    M --> N["TerminalManager.create()"]
    N --> O["spawn native PTY"]
```

---

## 20. Native PTY selection — `TerminalManager._spawn_native()`

```mermaid
flowchart TD
    A["TerminalManager.create/run_command"] --> B["_safe_cwd()"]
    B --> C["_validate_id()"]
    C --> D["_ensure_slot()"]
    D --> E{"OS"}
    E -- Windows --> W["WinConPty\npywinpty / ConPTY"]
    E -- POSIX --> P["PosixPty\npty/fork process"]
    W --> F["reader loop"]
    P --> F
    F --> G["on_data(text)"]
    G --> H["_append_retained()"]
    H --> I["_queue_output()"]
    I --> J["WS_HUB.broadcast(terminal_output)"]
    F --> K["on_exit(code)"]
    K --> L["_handle_exit()"]
    L --> M["broadcast terminal list/exit state"]
```

---

## 21. Terminal lifecycle state machine

```mermaid
stateDiagram-v2
    [*] --> Pending: browser creates local xterm tab
    Pending --> Running: terminal_create accepted
    Running --> Running: terminal_input / terminal_key
    Running --> Running: terminal_resize
    Running --> Running: terminal_rename
    Running --> DisconnectedBrowser: WebSocket disconnect
    DisconnectedBrowser --> Running: browser reconnect + terminal_sync
    Running --> Exited: shell exits
    Running --> Killed: terminal_kill
    Exited --> Closed: UI disposes tab
    Killed --> Closed
    Closed --> [*]
```

Key property: browser reconnect does not kill the PTY. Lantern process shutdown does.

---

## 22. Browser reconnect and replay

```mermaid
flowchart TD
    A["WebSocket closes"] --> B["status = Reconnecting"]
    B --> C["schedule retry\ndelay starts 300 ms"]
    C --> D["connect()"]
    D --> E{"open?"}
    E -- no --> F["delay *= 1.6\ncap 5000 ms"]
    F --> C
    E -- yes --> G["status = Connected"]
    G --> H["terminal_sync"]
    H --> I["TerminalManager.list()"]
    H --> J["TerminalManager.replay()"]
    I --> K["terminal_snapshot"]
    J --> K
    K --> L["ensure tabs"]
    L --> M["replayWrite()"]
    M --> N["bounded scrollback restored"]
```

---

## 23. WebSocket dispatch — `dispatch()`

```mermaid
flowchart TD
    A["decoded JSON message"] --> B["type"]
    B --> TS["terminal_sync"]
    TS --> SNAP["terminal_snapshot(list + replay)"]

    B --> TC["terminal_create"]
    TC --> CREATE["TerminalManager.create()"]

    B --> TR["terminal_run"]
    TR --> RUN["TerminalManager.run_command()"]

    B --> TI["terminal_input"]
    TI --> INPUT["TerminalManager.input()"]

    B --> TK["terminal_key"]
    TK --> KEY["TerminalManager.key()"]

    B --> TZ["terminal_resize"]
    TZ --> RESIZE["TerminalManager.resize()"]

    B --> TN["terminal_rename"]
    TN --> RENAME["TerminalManager.rename()"]

    B --> TKL["terminal_kill"]
    TKL --> KILL["TerminalManager.kill()"]

    B --> SS["scm_status"]
    B --> SH["scm_history"]
    B --> SD["scm_filediff"]
    B --> SC["scm_commit"]

    SS --> Q["ScmService.query()"]
    SH --> Q
    SD --> Q
    SC --> Q
    Q --> REPLY["scm_data(reqId, kind, ok/data or error)"]

    B --> UNKNOWN["ValueError Unknown WebSocket message"]
```

---

# PART E — GIT / SCM

## 24. SCM read path

```mermaid
sequenceDiagram
    participant UI as Git panel
    participant JS as terminal_scm.js
    participant WS as lantern_ws.py
    participant SCM as ScmService
    participant GIT as git CLI

    UI->>JS: open Git / select tab
    JS->>WS: scm_status(reqId,cwd)
    WS->>SCM: query("status", cwd)
    SCM->>GIT: git status / branch / numstat
    GIT-->>SCM: text output
    SCM-->>WS: structured status
    WS-->>JS: scm_data(reqId)
    JS-->>UI: renderScm()

    UI->>JS: select commit
    JS->>WS: scm_commit(reqId, hash)
    WS->>SCM: commit_detail()
    SCM->>GIT: git show ...
    GIT-->>SCM: diff/details
    SCM-->>UI: via WS + render
```

---

## 25. Git write path — visible terminal by design

```mermaid
flowchart TD
    A["User Git action"] --> B{read or write?}
    B -- read --> C["request() via WebSocket"]
    C --> D["ScmService.query()"]
    D --> E["git CLI read"]
    E --> F["render SCM panel"]

    B -- write --> G["gitCmd()"]
    G --> H["build visible shell command"]
    H --> I["runGit(title, command)"]
    I --> J["terminal_run WebSocket"]
    J --> K["TerminalManager.run_command()"]
    K --> L["real PTY/ConPTY"]
    L --> M["git add/reset/commit/checkout/pull/push"]
    M --> N["visible output in terminal tab"]
    N --> O["SCM watcher detects metadata change"]
    O --> P["refresh Git panel"]
```

This design keeps Git mutations visible and auditable in a terminal rather than hiding them inside a silent API.

---

## 26. SCM watcher / refresh path

```mermaid
flowchart TD
    A["ScmService.ensure_watch(cwd)"] --> B["resolve .git directory"]
    B --> C{"watchdog available?"}
    C -- yes --> D["filesystem metadata watcher"]
    C -- no --> E["_start_poll_fallback()"]
    D --> F["_schedule_changed()"]
    E --> G["_git_signature() changed?"]
    G -- yes --> F
    G -- no --> E
    F --> H["_emit_changed()"]
    H --> I["WS_HUB.broadcast(scm_changed)"]
    I --> J["browser refreshScm()"]
```

---

---

## Detailed function-flow appendix

For media, security, module-level function graphs, end-to-end use cases, tests, deployment, and debug ownership, continue with [LANTERN_FUNCTION_FLOWS.md](LANTERN_FUNCTION_FLOWS.md).
