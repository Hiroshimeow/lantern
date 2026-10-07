# Lantern Detailed Function Flows

 continuation of [LANTERN_SYSTEM_ARCHITECTURE.md](LANTERN_SYSTEM_ARCHITECTURE.md).
 file starts at the media/security/function-level layers so both documents remain within Lantern's 24-Mermaid-per-page rendering cap.

---

# PART F — MEDIA / THUMBNAILS

## 27. Thumbnail pipeline

```mermaid
flowchart TD
    A["GET /api/thumb"] --> B["resolve source file"]
    B --> C["classify file"]
    C --> D{"image?"}
    D -- yes --> E{"Pillow available?"}
    E -- yes --> F["make_image_thumb()"]
    E -- no --> G["fallback/original behavior"]

    C --> H{"video?"}
    H -- yes --> I{"ffmpeg available?"}
    I -- yes --> J["make_video_thumb()"]
    I -- no --> K["no generated video thumb"]

    F --> L["thumb_cache_path()"]
    J --> L
    L --> M["serve cached thumbnail"]
```

---

## 28. Video metadata / subtitle flow

```mermaid
flowchart TD
    A["Video selected"] --> B["GET /api/video_info"]
    B --> C["ffprobe_video_info()"]
    C --> D["video_info()"]
    D --> E["duration / resolution / bitrate / streams"]
    E --> F["find sidecar subtitles"]
    F --> G["video_subtitle_sidecars()"]
    G --> H{"subtitle format"}
    H -- srt --> I["srt_to_vtt()"]
    H -- ass/ssa --> J["ass_to_vtt()"]
    H -- vtt --> K["serve directly"]
    I --> L["GET /api/subtitle"]
    J --> L
    K --> L
    L --> M["HTML5 video player"]
```

---

# PART G — SECURITY BOUNDARIES

## 29. Security control map

```mermaid
flowchart TB
    NET["Trusted LAN / Tailscale"] --> HTTP["Lantern HTTP"]
    HTTP --> ORIGIN["Same-origin POST check"]
    ORIGIN --> PATH["Root path confinement"]
    PATH --> MUT["Filesystem mutation"]

    HTTP --> PREVIEW["Preview endpoint"]
    PREVIEW --> ESC["Escape raw Markdown/HTML"]
    ESC --> URL["URL normalization + allowlist"]
    URL --> CSP["Nonce-only CSP"]
    CSP --> LOCAL["Local scripts only"]
    LOCAL --> MER["Mermaid strict mode"]

    HTTP --> WS["WebSocket /ws"]
    WS --> WSO["same_origin() upgrade check"]
    WSO --> TERM["Terminal privilege = Lantern OS user"]

    TERM --> WARN["No auth: network access is security boundary"]

    classDef risk fill:#7f1d1d,stroke:#fca5a5,color:#fff
    classDef guard fill:#14532d,stroke:#86efac,color:#fff

    class NET,WARN risk
    class ORIGIN,PATH,ESC,URL,CSP,LOCAL,MER,WSO guard
```

---

## 30. Preview containment model

```mermaid
flowchart TD
    A["Untrusted Markdown file"] --> B["_render_markdown()"]
    B --> C["raw HTML escaped"]
    C --> D["links/images classified"]
    D --> E["server-generated HTML"]
    E --> F["fresh nonce CSP"]
    F --> G["only nonce-owned scripts execute"]
    G --> H["Mermaid securityLevel = strict"]
    H --> I["Preview rendered same-origin"]

    I --> R["Residual risk tracked separately"]
    R --> T["LANTERN-SEC-001"]
    T --> S1["future iframe sandboxing"]
    T --> S2["same-origin uploaded HTML/SVG containment"]
```

---

# PART H — FUNCTION-LEVEL MAPS

## 31. `lan_drive.py` core function groups

| Function/group | Input | Output / side effect |
| --- | --- | --- |
| `parse_args()` | CLI argv | argparse namespace |
| `build_config(args)` | CLI + YAML | resolved `AppConfig` |
| `safe_join(rel_url_path)` | user URL path | root-confined `Path` |
| `resolve_existing(rel)` | relative path | validated existing `Path` |
| `copy_item()` | source, destination, conflict mode | copied path |
| `move_item()` | source, destination, conflict mode | moved path |
| `extract_archive()` | archive, destination | extraction result |
| `list_entries_page()` | folder/search/paging/sort | paged JSON-like entries |
| `classify()` | file path | file kind |
| `video_info()` | video path | media metadata |
| `page_shell()` | title/body/current path | complete HTML page |
| `Handler.do_GET()` | HTTP GET | routed GET response |
| `Handler.do_POST()` | HTTP POST | routed mutation response |
| `main()` | process entry | initialized Lantern server |

### Function relationship

```mermaid
flowchart LR
    main --> parse_args
    main --> build_config
    build_config --> load_simple_yaml
    build_config --> norm_root
    main --> ThreadingHTTPServer
    ThreadingHTTPServer --> Handler
    Handler --> safe_join
    Handler --> list_entries_page
    Handler --> copy_item
    Handler --> move_item
    Handler --> extract_archive
    Handler --> render_preview["plugin.render_preview_page"]
    Handler --> upgrade_ws["lantern_ws.upgrade"]
```

---

## 32. `plugin.py` function graph

```mermaid
flowchart TD
    A["render_preview_page"] --> B["render_content"]
    B --> C["_kind"]
    C --> D["_render_markdown"]
    C --> E["_render_text"]
    C --> F["_render_csv"]
    C --> G["_render_docx"]
    C --> H["_render_xlsx"]
    C --> I["_render_pdf"]

    D --> J["_md_inline"]
    D --> K["_flush_md_paragraph"]
    D --> L["_split_table_row"]
    D --> M["_is_table_separator"]

    J --> N["_safe_markdown_target"]
    N --> O["_trim_c0"]
    J --> P["h() HTML escaping"]

    A --> Q["nonce + CSP"]
    A --> R["conditional Mermaid script"]
    A --> S["markdown_preview.js"]
```

---

## 33. `TerminalManager` function graph

```mermaid
flowchart TD
    A["TerminalManager"] --> C["create()"]
    A --> R["run_command()"]
    A --> I["input()"]
    A --> K["key()"]
    A --> Z["resize()"]
    A --> N["rename()"]
    A --> X["kill()"]
    A --> XA["kill_all()"]
    A --> L["list()"]
    A --> RP["replay()"]

    C --> SC["_safe_cwd()"]
    C --> V["_validate_id()"]
    C --> SL["_ensure_slot()"]
    C --> SP["_spawn_native()"]

    R --> SC
    R --> V
    R --> SL
    R --> SP

    SP --> WP["WinConPty"]
    SP --> PP["PosixPty"]

    WP --> QO["_queue_output()"]
    PP --> QO
    QO --> AR["_append_retained()"]
    QO --> BC["broadcast terminal_output"]

    WP --> HE["_handle_exit()"]
    PP --> HE
```

---

## 34. `ScmService` function graph

```mermaid
flowchart TD
    A["ScmService.query(kind,cwd,payload)"] --> B{"kind"}
    B -- status --> C["status()"]
    B -- history --> D["history()"]
    B -- filediff --> E["file_diff()"]
    B -- commit --> F["commit_detail()"]

    C --> G["_safe_cwd()"]
    D --> G
    E --> G
    F --> G

    C --> H["_git()"]
    D --> H
    E --> H
    F --> H

    C --> I["_parse_status_header()"]
    C --> J["_parse_status_files()"]
    C --> K["_parse_branches()"]
    C --> L["_parse_numstat()"]
    C --> M["_merge_stats()"]

    A --> W["ensure_watch()"]
    W --> CH["_schedule_changed()"]
    CH --> EM["_emit_changed()"]
```

---

## 35. `static/terminal_scm.js` UI graph

```mermaid
flowchart TD
    INIT["init UI"] --> CON["connect()"]
    CON --> MSG["onMessage()"]

    INIT --> DRAW["initDrawer()"]
    DRAW --> VIEW["setView()"]
    VIEW --> TERM["Terminal view"]
    VIEW --> GIT["Git view"]

    TERM --> NEW["newTerminal()"]
    NEW --> MAKEX["makeX()"]
    MAKEX --> ACTIVE["activate()"]
    ACTIVE --> FIT["scheduleFit()"]
    TERM --> CLOSE["closeTerm()"]

    GIT --> REF["refreshScm()"]
    REF --> REQ["request()"]
    REQ --> RENDER["renderScm()"]
    RENDER --> FDIFF["selectFile()"]
    RENDER --> COMMITD["selectCommit()"]

    GIT --> WRITE["gitCmd()"]
    WRITE --> RUNGIT["runGit()"]
    RUNGIT --> TERM
```

---

# PART I — END-TO-END USE CASES

## 36. Use case: open a Markdown architecture document

```mermaid
sequenceDiagram
    participant U as Browser user
    participant H as Handler
    participant P as plugin.py
    participant JS as markdown_preview.js
    participant M as Mermaid runtime

    U->>H: GET /api/plugin/preview?p=LANTERN_SYSTEM_ARCHITECTURE.md
    H->>H: safe_join()
    H->>P: render_preview_page(path, root)
    P->>P: _render_markdown()
    P->>P: generate nonce + CSP
    P-->>H: complete preview HTML
    H-->>U: 200 text/html

    U->>U: parse HTML
    U->>M: load local Mermaid vendor from HEAD
    U->>JS: load deferred helper
    JS->>M: initialize(strict)
    loop each Mermaid block, max 24
        JS->>M: render(source)
        M-->>JS: SVG
        JS-->>U: show diagram
    end
```

---

## 37. Use case: edit a file

```mermaid
flowchart TD
    A["User opens ?edit=1"] --> B["Handler.serve_editor()"]
    B --> C["load current text"]
    C --> D["browser editor"]
    D --> E["POST /api/save"]
    E --> F["same-origin POST check"]
    F --> G["read_json() bounded body"]
    G --> H["resolve existing path under root"]
    H --> I["write file"]
    I --> J["JSON success"]
    J --> K["browser refresh"]
```

---

## 38. Use case: upload files

```mermaid
flowchart TD
    A["User selects files/folder"] --> B["browser upload queue"]
    B --> C["parallel uploads bounded by config"]
    C --> D["POST /api/upload"]
    D --> E["same-origin check"]
    E --> F["resolve destination directory"]
    F --> G["conflict strategy"]
    G --> H{"rename / overwrite / skip"}
    H --> I["write bytes"]
    I --> J["response metadata"]
    J --> K["progress update"]
    K --> L{"more files?"}
    L -- yes --> C
    L -- no --> M["refresh directory"]
```

---

## 39. Use case: run a Git commit

```mermaid
sequenceDiagram
    participant U as User
    participant JS as Git UI
    participant WS as WebSocket
    participant TM as TerminalManager
    participant PTY as PTY/ConPTY
    participant G as git

    U->>JS: enter commit message
    JS->>JS: gitCmd("commit")
    JS->>JS: runGit("git commit", command)
    JS->>WS: terminal_run
    WS->>TM: run_command()
    TM->>PTY: spawn shell + git command
    PTY->>G: git commit -m ...
    G-->>PTY: visible stdout/stderr
    PTY-->>TM: terminal output
    TM-->>WS: broadcast
    WS-->>JS: terminal_output
    JS-->>U: visible commit result
```

---

## 40. Use case: browser reconnect while terminal survives

```mermaid
sequenceDiagram
    participant B1 as Browser connection A
    participant WS as WebSocketHub
    participant TM as TerminalManager
    participant PTY as PTY process
    participant B2 as Browser connection B

    B1->>WS: connected
    B1->>TM: create terminal via WS
    TM->>PTY: spawn shell
    B1--xWS: network loss / refresh
    Note over TM,PTY: Lantern process remains alive
    PTY->>TM: output continues
    TM->>TM: retain bounded output
    B2->>WS: reconnect
    B2->>WS: terminal_sync
    WS->>TM: list() + replay()
    TM-->>B2: snapshot + retained output
    B2->>B2: rebuild xterm tabs
```

---

# PART J — DATA AND STATE OWNERSHIP

## 41. State ownership diagram

```mermaid
flowchart LR
    subgraph Browser
        B1["Directory UI state"]
        B2["xterm instances"]
        B3["SCM panel state"]
        B4["Markdown preview DOM"]
    end

    subgraph LanternProcess
        S1["CONFIG / AppConfig"]
        S2["TERM_MANAGER"]
        S3["SCM_SERVICE"]
        S4["WS_HUB"]
    end

    subgraph Persistent
        P1["Filesystem root"]
        P2["Config YAML"]
        P3["Git metadata"]
        P4["Thumbnail cache"]
    end

    B1 <--> P1
    B2 <--> S2
    B3 <--> S3
    B4 --> P1

    S1 <--> P2
    S2 --> P1
    S3 <--> P3
    S4 <--> B2
    S4 <--> B3
    P1 --> P4
```

---

# PART K — TEST ARCHITECTURE

## 42. Test coverage map

```mermaid
flowchart TD
    T["Lantern test suite"] --> P["test_plugin.py"]
    T --> S["test_security.py"]
    T --> TU["test_terminal_ui.py"]
    T --> TS["test_terminal_scm.py"]

    P --> P1["Markdown grammar"]
    P --> P2["URL normalization"]
    P --> P3["CSP nonce"]
    P --> P4["Mermaid preview contract"]

    S --> S1["same-origin mutation"]
    S --> S2["HTTP security boundaries"]

    TU --> U1["terminal JS behavior"]
    TU --> U2["reconnect/UI parity"]

    TS --> X1["TerminalManager"]
    TS --> X2["SCM service"]
    TS --> X3["WebSocket protocol"]
```

---

# PART L — OPERATIONAL MODEL

## 43. Deployment decision flow

```mermaid
flowchart TD
    A["Start Lantern"] --> B{"Who can reach host:port?"}
    B -- only localhost --> C["127.0.0.1 safe default"]
    B -- trusted LAN/Tailscale --> D["bind trusted interface / 0.0.0.0 with firewall"]
    B -- public internet --> E["Do not expose directly"]

    D --> F{"Need terminal?"}
    F -- no --> G["terminal_enabled: false"]
    F -- yes --> H["terminal_enabled: true"]
    H --> I["All reachable users can execute as Lantern OS user"]

    E --> J["Require auth + TLS + access control + reverse proxy"]
```

---

# PART M — FUNCTION INDEX

## 44. HTTP Handler API index

### GET

- `/ws` → WebSocket upgrade
- `/static/*` → static application assets
- `/api/info` → runtime/config information
- `/api/config` → current mutable UI config
- `/api/list` → directory listing/search/paging
- `/api/thumb` → image/video thumbnail
- `/api/folder_preview` → folder preview metadata
- `/api/video_info` → video metadata
- `/api/subtitle` → subtitle conversion/serving
- `/api/plugin/info` → plugin capability metadata
- `/api/plugin/preview` and `/api/preview` → rich document preview
- arbitrary directory → file browser page
- arbitrary file → file/media serving
- arbitrary file with `?edit=1` → editor
- arbitrary file with `?download=1` → attachment download

### POST

- `/api/upload`
- `/api/save`
- `/api/mkdir`
- `/api/newfile`
- `/api/rename`
- `/api/copy`
- `/api/move`
- `/api/duplicate`
- `/api/batch_rename`
- `/api/extract`
- `/api/delete`
- `/api/archive`
- `/api/zip`
- `/api/config`
- `/api/plugin/extensions`

---

## 45. WebSocket message index

| Type | Server action | Typical result |
| --- | --- | --- |
| `terminal_sync` | `terminal.list() + terminal.replay()` | `terminal_snapshot` |
| `terminal_create` | `TerminalManager.create()` | terminal created/broadcast |
| `terminal_run` | `TerminalManager.run_command()` | command PTY |
| `terminal_input` | `TerminalManager.input()` | bytes to PTY |
| `terminal_key` | `TerminalManager.key()` | encoded special key |
| `terminal_resize` | `TerminalManager.resize()` | PTY resize |
| `terminal_rename` | `TerminalManager.rename()` | title update |
| `terminal_kill` | `TerminalManager.kill()` | terminal exit |
| `scm_status` | `ScmService.query("status")` | `scm_data` |
| `scm_history` | `ScmService.query("history")` | `scm_data` |
| `scm_filediff` | `ScmService.query("filediff")` | `scm_data` |
| `scm_commit` | `ScmService.query("commit")` | `scm_data` |

---

# PART N — HIGH-LEVEL DEPENDENCY GRAPH

## 46. Python/JS dependency graph

```mermaid
flowchart TB
    LD["lan_drive.py"]
    PL["plugin.py"]
    LW["lantern_ws.py"]
    LT["lantern_terminal.py"]
    LS["lantern_scm.py"]

    TS["static/terminal_scm.js"]
    MP["static/markdown_preview.js"]
    XT["static/vendor/xterm.js"]
    MR["static/vendor/mermaid-11.17.2.min.js"]

    FS["Filesystem"]
    GIT["git"]
    PTY["pywinpty / POSIX pty"]
    BR["Browser"]

    LD --> PL
    LD --> LW
    LD --> LT
    LD --> LS
    LD --> FS

    LW --> LT
    LW --> LS

    LT --> PTY
    LS --> GIT

    BR --> TS
    BR --> MP
    TS --> XT
    MP --> MR

    TS <--> LW
    MP --> PL
```

---

# PART O — WHAT LANTERN IS NOT

Lantern intentionally does **not** currently provide:

- built-in authentication;
- public-internet hardening by itself;
- terminal survival across Lantern process restart;
- a hidden server-side Git mutation engine;
- a server-side PDF rendering service;
- a Mermaid CDN dependency;
- unrestricted Markdown raw HTML execution.

---

# PART P — CURRENT KNOWN FOLLOW-UP

## 47. Preview containment follow-up

The current Markdown/Mermaid lane is released with an explicit owner-approved residual-risk sign-off.

Tracked follow-up:

- `LANTERN-SEC-001`
  - preview iframe sandboxing;
  - containment of same-origin uploaded HTML/SVG serving.

```mermaid
flowchart LR
    NOW["Current release\nnonce CSP + escaped Markdown\nstrict local Mermaid"]
    RISK["Residual same-origin preview risk"]
    TICKET["LANTERN-SEC-001"]
    F1["iframe sandboxing"]
    F2["uploaded HTML/SVG containment"]

    NOW --> RISK --> TICKET
    TICKET --> F1
    TICKET --> F2
```

---

# PART Q — QUICK TRACE GUIDE

When debugging a feature, follow this owner map:

```mermaid
flowchart TD
    BUG["Observed bug"] --> Q{"Area?"}

    Q -- file browsing / upload / media --> LD["lan_drive.py"]
    Q -- document preview / Markdown parse --> PL["plugin.py"]
    Q -- Mermaid / PNG / Print-PDF --> MP["static/markdown_preview.js"]
    Q -- terminal browser UI --> TS["static/terminal_scm.js"]
    Q -- WebSocket protocol --> WS["lantern_ws.py"]
    Q -- PTY lifecycle / shell IO --> TM["lantern_terminal.py"]
    Q -- Git status/history/diff --> SCM["lantern_scm.py"]

    LD --> TL["test_security.py / endpoint tests"]
    PL --> TP["test_plugin.py"]
    MP --> TP
    TS --> TT["test_terminal_ui.py"]
    WS --> TW["test_terminal_scm.py"]
    TM --> TW
    SCM --> TW
```

---

## 48. Architectural summary

Lantern is deliberately structured around a small set of owners:

1. **`lan_drive.py` owns HTTP and filesystem behavior.**
2. **`plugin.py` owns safe document-to-preview HTML generation.**
3. **`markdown_preview.js` owns browser-only Mermaid/export behavior.**
4. **`lantern_ws.py` owns the browser/server realtime protocol.**
5. **`lantern_terminal.py` owns native terminal process lifetime and replay.**
6. **`lantern_scm.py` owns read-side Git state; Git mutations stay visible in terminal tabs.**
7. **Security relies on trusted-network deployment, root confinement, same-origin checks, preview escaping/CSP, and explicit terminal enablement.**

That separation is the main reason Lantern can remain small while still providing file manager + preview + terminal + SCM functionality in one application.
