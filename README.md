# 🏮 Lantern

**Your computer has files. Your other computer would like to meet them.**

A local-first file manager for the browser: **files, Markdown visual editing, actual PDF pages, Git, a real terminal, media, and Mermaid** — all on your own machine or a trusted LAN.

**Windows · Linux · macOS · LAN / Tailscale · No accounts · No database · No cloud upload**

![Lantern file browser](docs/images/lantern-file-browser.png)

> Lantern began with a modest request: *“Can I just browse that folder from another computer?”*
>
> Naturally, it now has a Git panel, a Markdown editor, a PDF viewer and a terminal. Scope creep has excellent taste.

## 🚀 Three actions. One Lantern.

**Already cloned the repo on Windows?** You do **not** need to configure Python or YAML yourself.

1. **Double-click `run.bat`.**
2. **Choose your root folder.** Press Enter for your user folder.
3. **Choose how to run it:** `1` = **Nohup** (hidden server console), `2` = **Terminal** (visible server console).

That's it. Lantern prepares Python 3.12 in `.venv`, installs its dependencies through `uv`, generates a local `lan_drive_config.yaml` from the tracked template, starts the server and opens the browser.

| Run mode | What you get | What you *don't* get |
|---|---|---|
| **1 · Nohup** | Server runs in the background, logs in `%LOCALAPPDATA%\Lantern\logs` | A permanent Windows service — signing out or rebooting ends it |
| **2 · Terminal** | Visible server console and logs | Any obligation to stare at logs for fun |

**The browser terminal is a separate feature.** Choosing Nohup does *not* disable the terminal inside Lantern. And choosing Terminal does *not* enable browser terminal access if your YAML disables it.

On first launch, the bootstrap needs internet access to download missing tools. Later launches reuse the environment. The safe default is **`http://127.0.0.1:9999`**, accessible only from the server machine until you explicitly allow LAN access.

*Yes, it really is three actions after cloning. Your future self is welcome.*

---

## ✨ Pick a mode. Pretend you only came here for one feature.

| Mode | The useful part | The less official description |
|---|---|---|
| 📁 **Files** | Browse, search, upload, edit, rename, move, duplicate, archive and download | Explorer went for a walk and found a browser |
| 📝 **Markdown Preview** | Styled documents, tables, code, relative images and task lists | Read your Markdown without looking at asterisk soup |
| ✍️ **Edit Visually** | WYSIWYG Markdown with autosave and conflict protection | *“What if the preview were also the editor?”* |
| 📄 **PDF Preview** | Real pages in the browser's native PDF viewer | PDFs have layouts. Apparently that's important |
| 🧩 **Mermaid** | Offline diagrams, PNG export and Print / PDF | Your architecture diagram doesn't need to call a CDN |
| 🌿 **Git / SCM** | Status, branches, diff, history, stage, commit, pull, push | A little branch accountability never hurt anyone |
| 🖥️ **Terminal** | Real PTY / ConPTY sessions in browser tabs | An actual shell; no textarea dressed as one |
| 🎬 **Media** | Photos, audio, video streaming, thumbnails and subtitles | Yes, the NAS now has a personality |

## ✍️ Markdown that you can actually *edit*

![Lantern Edit Visually working with tables and linked images](docs/images/lantern-edit-visually.png)

**Preview** is the fast, read-only starting point. The Markdown toolbar switches between **Preview / Edit visually / Source** without navigating away when nothing needs refreshing. **Edit visually** lets you type into the rendered document; **Source** edits the exact Markdown text and does not load the large visual editor bundle. Both editors share versioned saves and local draft recovery. Save the resulting **Markdown file**, not a proprietary document.

In **Preview**, GFM pipe tables are rendered (including escaped pipes and pipes inside inline code), and HTML comments stay hidden. In **Edit visually** and **Source**, comments and Mermaid code remain available to edit. Mermaid is rendered as a diagram **only in Preview**. HTML content such as raw `<table>` tags is escaped, not executed.

A few things that matter outside a demo:

- **Tables:** add or remove rows and columns in the visual editor.
- **Images:** display existing relative Markdown images without changing source links. **Ctrl+V** a screenshot from Paint or paste/drop a supported image: Lantern uploads it to the document's nearby `assets/` folder and inserts a real relative link. No temporary `blob:` links in your saved Markdown.
- **Crop:** in **Edit visually**, click a PNG/JPEG/WebP/BMP image → **Crop image** → drag to select → **Apply crop**. A new PNG is saved in `assets/`, and the original remains untouched. **Delete image** (or the Delete key) removes only the Markdown reference, never the asset. Cropping animated GIF/SVG is not supported.
- **Autosave:** saves edits after idle without blocking the entire page.
- **Two people, one file:** content-hash checks reject stale writes (HTTP 409) rather than silently overwriting the other person's work.
- **Draft recovery:** local browser drafts and a downloadable emergency copy. Switching back to Preview with unsaved edits asks for confirmation and keeps the draft. Because Wi-Fi has opinions.
- **Formatting safety:** if opening a file would rewrite its Markdown syntax, Lantern requires a before/after review before saving.
- **Large documents:** full-document visual editing up to 32 KiB; larger UTF-8 documents up to **5 MiB** use lossless, section-based navigation. Source mode can edit the whole document up to the same 5 MiB limit. Switching from Source to Visual on a large file enters the paged editor (save pending Source edits first). Switching back from a paged section to Source also requires saving that section, so unsaved edits cannot silently disappear. Very large code fences use a localized CodeMirror pane.

The visual editor lazy-loads its offline Milkdown/ProseMirror bundle only when requested. A big document does not need to summon an entire editor just because you wanted to read a heading.

> Files named `final_final_REAL_final_v9.md` are fully supported. No questions asked.

### 🧩 Mermaid, still living entirely on your computer

![Lantern Markdown and Mermaid preview](docs/images/lantern-markdown-mermaid.png)

Write fenced `mermaid` blocks for flowcharts, sequence diagrams or state diagrams. Lantern loads the locally vendored Mermaid runtime **only when a document contains a diagram**.

You can export individual diagrams as **PNG** or use **Print / Save as PDF** for the Markdown preview via your browser's print workflow. Markdown editing and Mermaid rendering are separate features: you are not forced to use the editor to view a diagram.

If the diagram needs 14 boxes to explain one `if` statement, the renderer will cooperate. Your reviewer may not.

## 📄 PDF preview that shows the **PDF**, not just its text

![Real PDF rendered inside Lantern's browser-native viewer](docs/images/lantern-pdf-preview.png)

Opening a `.pdf` now displays **real pages**, including their visual layout, using the browser's PDF viewer. On a supported browser you get page navigation, zoom, scrolling and the browser's own PDF controls.

The existing file server supports **HTTP byte ranges**. Lantern opens the lightweight viewer shell without waiting for a server-side PDF text parser to finish.

Need plain text instead? Click **Extract text (slower)**. That uses `pdftotext` if available, or a bounded fallback, and only targets an initial portion of the file. It is optional — **not** the prerequisite for looking at page one.

If your browser lacks inline PDF support, use **Open raw** or **Download**.

> Old PDF workflow: “Please wait while I interpret your document's existential meaning.”
>
> New PDF workflow: “Here are the pages.”

Other document previews are deliberately different: **DOCX** and **XLSX/XLSM** use bounded, lightweight content previews, **not** a full-fidelity Microsoft Office renderer. They do not promise exact fonts, formula evaluation or print layout.

## 📁 Files, without the USB-stick diplomacy

Grid or list view, breadcrumbs, search, sorting, lazy loading, thumbnails, multi-file uploads, create/rename/copy/move/delete, ZIP/archive tools, file downloads and shared links.

Images open as images. Videos stream with seeking and HTTP Range support. Subtitles and thumbnails are supported, with richer media metadata available when `ffmpeg` / `ffprobe` are installed.

One server can serve multiple browser clients. You don't have to install Lantern on every PC just to browse the server from that PC.

## 🌿 Git and a real shell — together, but not mysteriously

![Lantern Git SCM panel](docs/images/lantern-git-panel.png)

Git reads happen in the SCM panel: working-tree changes, stage/unstage, diffs, branch tracking, untracked files and commit history.

Git writes — including **commit, checkout, pull and push** — use a **visible terminal session** so you can see the command and its result.

![Lantern terminal](docs/images/lantern-terminal.png)

The browser terminal uses **xterm.js + WebSocket + real PTY** on Linux/macOS, or **ConPTY via pywinpty** on Windows. It supports multiple sessions, resize, rename, bounded output history and reconnecting a browser tab.

Windows defaults to **PowerShell** (falling back to CMD). Git Bash is optional via `LANTERN_SHELL` or `PI_WEB_SHELL`, because MSYS2's “`fork: Resource temporarily unavailable`” is not a feature anyone requested.

Handy keys: **Ctrl + backtick** toggles the drawer; `Alt+Enter` toggles fullscreen; `Ctrl+C` copies a selection or sends interrupt; `Ctrl+V` pastes.

Closing a browser tab does not by itself kill a server-hosted terminal. **Stopping Lantern does.** It is persistent across browser reconnects, not immortal.

---

## 🌐 Using it from another computer

By default Lantern binds to `127.0.0.1` for safety. On a **trusted** LAN or Tailscale network, explicitly choose a reachable interface in your ignored YAML:

```yaml
root: "D:/Share"
host: "0.0.0.0"   # Only on a trusted network
port: 9999
terminal_enabled: false
```

Restart Lantern, then open `http://SERVER-LAN-IP:9999` from another device (or your machine's Tailscale IP). **Do not** enter `0.0.0.0` in the browser address bar.

*Clients need a browser. The server needs Python and its dependencies.* With several separate Lantern servers, each owns its own terminals, preview limits and cache; sharing a folder over the network does not turn them into a distributed transaction system.

### 🔐 Security: the joke ends here

Lantern has **no built-in login, permissions, or authorization**. If someone can reach the server, they can access the files exposed through it. When browser terminal access is enabled, they may be able to execute commands with **the server user's OS privileges**.

Use the smallest useful root, restrict firewall rules, avoid Administrator/root, prefer loopback or private Tailscale, and **never expose Lantern directly to the public internet** without an authenticated front end.

The Markdown preview applies HTML escaping, same-origin checks, nonce-based script CSP and path/URL confinement. Stronger isolation for uploaded HTML/SVG and iframe preview content remains a security hardening item. Do not treat an unpublished port number as authentication.

---

## 🛠️ Other ways to install and run

### Windows: installer instead of Git clone

If you don't want to manage a clone, `install.bat` (or `install.ps1`) can install an independent copy into `%LOCALAPPDATA%\Lantern`, prepare Python 3.12 and dependencies, and generate its own local config.

```powershell
.\install.bat -Root "D:\Share"
# To enable browser terminal explicitly:
.\install.bat -Root "D:\Share" -EnableTerminal
# Bind to every interface only on a trusted LAN:
.\install.bat -Root "D:\Share" -BindAll
```

The installer defaults to **127.0.0.1**, port **9999**, and **browser terminal disabled**. Its generated launcher lives at `%LOCALAPPDATA%\Lantern\Run-Lantern.bat`.

### Linux / macOS

```bash
python3 -m pip install -r requirements.txt
python3 lan_drive.py --root "$HOME" --host 127.0.0.1 --port 9999
```

Or manage the Python environment with `uv`. The browser-side editor, terminal UI and Mermaid resources are vendored — **Node and CDN access are not needed at runtime**.

### Configuration and existing clones

Git tracks **`lan_drive_config.yaml_copy`**, not your machine's real `lan_drive_config.yaml` or `lan_drive_config.local.yaml`. Those local config files are ignored, so new clones can use the template and existing users can keep their paths and settings.

Manual setup:

```powershell
Copy-Item lan_drive_config.yaml_copy lan_drive_config.yaml
uv run --with-requirements requirements.txt python lan_drive.py --config lan_drive_config.yaml
```

**Updating an old clone with a modified, previously tracked YAML?** A normal `git pull` can conflict during the one-time transition to `.yaml_copy`. Use the safe fast-forward updater **before** pulling. It backs up the original bytes privately and restores the local YAML:

```powershell
$helper = Join-Path $env:TEMP 'lantern-safe-pull.py'
Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/Hiroshimeow/lantern/main/tools/safe_pull.py' -OutFile $helper
uv run --no-project python $helper --repo (Get-Location).Path
```

Run it from your Lantern checkout root. It refuses staged config changes rather than discarding them. After migration, normal `git pull --ff-only` is sufficient.

CLI overrides: `--root`, `--host`, `--port`, `--config`, `--title`, `--cache-dir`, `--sort`, `--view`, `--page-limit` and `--save-config`. Use `python lan_drive.py --help` for the authoritative list. CLI overrides are runtime-only unless explicitly saved.

---

## 🧪 For people who read test output voluntarily

```powershell
uv run --with-requirements requirements.txt python -m unittest -q
node --test tests/test_md_segmentation.mjs
```

Browser E2E tests are opt-in, run against disposable loopback servers, and do not need to restart your live Lantern instance:

```powershell
$env:LANTERN_E2E = "1"
uv run --with-requirements requirements.txt --with playwright python -m unittest -v tests.test_md_visual_e2e tests.test_md_paged_e2e tests.test_pdf_browser_e2e
```

Tests cover preview/XSS/CSP boundaries, PDF streaming, Markdown round-trips, save conflicts, large-file paging, terminal lifecycle, Git parsing, and LAN list/refresh behavior.

Main source map:

```text
lan_drive.py                HTTP server, filesystem, media, config
plugin.py                   Document preview, Markdown, native PDF shell
lantern_md_editor.py        Markdown save/version/draft contracts
lantern_terminal.py         PTY / Windows ConPTY
lantern_ws.py               WebSocket transport
lantern_scm.py              Git/SCM service
static/                     Browser frontend + offline vendor bundles
tools/                      Build and safe migration scripts
tests/                      Unit / integration / Edge browser E2E
docs/images/                Actual Lantern UI screenshots
run.bat                     Three-action Windows launcher
lan_drive_config.yaml_copy  Git-tracked configuration template
```

Want diagrams? We have diagrams about our diagrams:
[System architecture](LANTERN_SYSTEM_ARCHITECTURE.md) and
[detailed function flows](LANTERN_FUNCTION_FLOWS.md), with **44 Mermaid diagrams** in total.

Only rebuild the vendored visual Markdown assets when changing frontend build dependencies: `npm ci && npm run build:markdown`. This is a developer step, not a user installation requirement.

## Boundaries worth knowing

- The visual editor has a deliberate **5 MiB** maximum; read-only previews remain available separately.
- In Visual Edit, paste/drop PNG, JPEG, WebP, GIF or BMP images (up to 20 MiB each). Lantern saves each file in an adjacent `assets/` folder before inserting a durable relative Markdown link; unsupported clipboard formats are not uploaded.
- DOCX/Excel previews are bounded content views, not Word/Excel clones.
- Browser PDF rendering depends on PDF support in the browser; direct-open/download fallbacks exist.
- Browser print-to-PDF for Markdown uses the browser's print engine.
- There is **no authentication**, no promise of surviving a server restart with terminal sessions, and no public-internet security guarantee.
- There is currently **no license file**; normal copyright restrictions apply until one is added.

---

> **Lantern** — because sometimes the best distributed filesystem architecture is *“the other computer is literally right there.”*
