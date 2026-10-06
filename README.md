# Lantern — LAN Drive

A one-file web file manager for your LAN or Tailscale network.

It lets you browse, preview, upload, edit, download, stream, and manage files from a browser — because emailing files to yourself in 2026 would be embarrassing.

<img width="2535" height="1450" alt="{FE52BE8D-0285-4C21-8380-FC5BD22036B2}" src="https://github.com/user-attachments/assets/22a7fee0-93c2-4e62-9301-ca210cfc2ae9" />

## What it does

- Browse folders in grid or list view with breadcrumbs, sorting, quick search, and recursive search.
- Preview images, text, code, documents, audio, and video.
- Stream video with HTTP Range support, seeking, and automatic next-video playback.
- Upload multiple files or entire folders with progress tracking and conflict handling.
- Create folders and text files; edit text, code, config, and log files in the browser.
- Rename, copy, move, duplicate, delete, archive, extract, and download files.
- Download multiple files or folders as a streamed ZIP archive.
- Copy direct share links for files and folders.
- Generate image and video thumbnails when optional tools are available.
- Open a responsive multi-terminal drawer powered by local xterm.js + FitAddon.
  - Linux/macOS: real PTY sessions.
  - Windows: real ConPTY sessions via `pywinpty`.
  - WebSocket transport keeps terminal processes alive across browser reconnects and replays bounded scrollback.
- Use the integrated Git/SCM panel for status, diffs, history, branch switching, stage/unstage, commit, pull, and push. Git reads run directly; writes run in visible terminal tabs.
- Work on desktop and mobile without requiring a database, Docker, or a ceremonial JavaScript framework sacrifice.

## Important security warning

Lantern has **no authentication** and can expose file-management operations and a terminal.

Use it only on a trusted LAN or private Tailscale network. Do **not** expose it directly to the public internet unless you place proper authentication, TLS, access controls, and a reverse proxy in front of it.

For a safer deployment:

- Set `root` to the smallest directory users actually need.
- Set `terminal_enabled: false` when remote command execution is unnecessary.
- Restrict host firewall rules to trusted devices or subnets.
- Do not run the process as an administrator or root unless you enjoy incident-response paperwork.

## Requirements

Required:

- Python 3
- A browser
- A network containing at least two devices, unless you enjoy sharing files with yourself

Runtime dependencies for Terminal/Git parity:

```bash
python -m pip install -r requirements.txt
```

`pywinpty` is installed only on Windows; `watchdog` provides low-latency Git metadata change notifications with a polling fallback.

Optional:

- [Pillow](https://python-pillow.org/) for better image thumbnails
- `ffmpeg` and `ffprobe` for video metadata and thumbnails

Install Pillow:

```bash
python -m pip install pillow
```

Ubuntu/Debian optional packages:

```bash
sudo apt install ffmpeg python3-pil
```

## Quick start

### Windows

```powershell
python lan_drive.py --root "$env:USERPROFILE" --host 127.0.0.1 --port 9999
```

### One-command Windows install

On a clean Windows machine, run this one command in PowerShell:

```powershell
$p=Join-Path $env:TEMP 'lantern-install.ps1'; Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/Hiroshimeow/lantern/main/install.ps1' -OutFile $p; & $p
```

It installs Lantern into `%LOCALAPPDATA%\Lantern`, prepares an isolated Python 3.12 environment with `uv`, creates a machine-local config, and starts Lantern.

Safe defaults:

- Bind only to `127.0.0.1`.
- Share `%USERPROFILE%`.
- Terminal disabled.
- Port `9999`.
- Machine-specific settings live in `%LOCALAPPDATA%\Lantern\lan_drive_config.local.yaml`.

After installation:

```text
%LOCALAPPDATA%\Lantern\Run-Lantern.bat
```

Open `http://127.0.0.1:9999` in a browser.

Common install variants:

```powershell
# Share only one folder
.\install.bat -Root "D:\Share"

# Listen on a specific trusted LAN or Tailscale IP
.\install.bat -Root "D:\Share" -HostAddress "100.x.y.z"

# Listen on every interface. Use only on a trusted network.
.\install.bat -Root "D:\Share" -BindAll

# Enable the browser terminal. Anyone who can reach Lantern can execute
# commands as the Windows user running Lantern.
.\install.bat -Root "D:\Share" -HostAddress "100.x.y.z" -EnableTerminal

# Install/update files without starting Lantern
.\install.bat -NoStart
```

When you already have a clone of this repository, run the examples above from the repository root. Running the installer again refreshes the installed application from the requested branch and rebuilds its managed virtual environment. Re-pass any non-default `-Root`, bind address, port, or terminal option because the installer regenerates the machine-local config.

To uninstall, stop Lantern and remove `%LOCALAPPDATA%\Lantern`.

> Lantern has no authentication. Do not expose `-BindAll` or `-EnableTerminal` to an untrusted network or the public internet.

### Linux

```bash
python3 lan_drive.py --root /srv/share --port 9999
```

### Use the configuration file

```bash
python lan_drive.py --config lan_drive_config.yaml
```

Then open:

```text
http://127.0.0.1:9999
```

From another device on the same LAN or Tailscale network:

```text
http://SERVER_IP:9999
```

The server prints its local and LAN addresses at startup, so nobody has to perform interpretive dance with `ipconfig`.

## Command-line options

```text
--config PATH       Configuration file path
--root PATH         Root directory exposed by the file manager
--host HOST         Bind address; default is 0.0.0.0
--port PORT         HTTP port; default is 9999
--title TITLE       Title displayed in the UI
--cache-dir PATH    Thumbnail and preview cache directory
--show-hidden       Show hidden files
--show-system       Show /proc, /sys, /run, and /dev under Linux root
--sort MODE         Initial sort order
--view MODE         Initial grid or list view
--page-limit N      Items loaded per page
--save-config       Persist CLI overrides to the configuration file
```

Run the authoritative version instead of trusting documentation written by a carbon-based life form:

```bash
python lan_drive.py --help
```

CLI overrides are runtime-only unless `--save-config` is supplied.

## Configuration

The default configuration file is `lan_drive_config.yaml` next to the script.

Common settings:

```yaml
root: "/srv/share"
port: 9999
host: "0.0.0.0"
title: "LAN Drive"
cache_dir: "/tmp/lan-drive-cache"

show_hidden: false
show_system: false
default_sort: "name-asc"
default_view: "grid"
page_limit: 100
folders_first: true

terminal_enabled: true
terminal_max_sessions: 16
terminal_max_buffer_chars: 204800
terminal_start_height_px: 380

thumb_fit: "cover"
folder_preview_enabled: true
upload_parallel: 3
upload_conflict: "ask"
```

Valid sort modes:

```text
name-asc, name-desc
mtime-asc, mtime-desc
size-asc, size-desc
type-asc, type-desc
ext-asc, ext-desc
```

Upload conflict policies:

```text
ask, overwrite, skip, rename
```

Several UI preferences are saved in the browser and selected server preferences are persisted to the YAML file.

## Terminal controls

Open or close the terminal with the toolbar button or:

```text
Ctrl + `
```

Useful shortcuts:

| Shortcut | Action |
|---|---|
| `Ctrl+C` | Copy selected terminal text; send interrupt when nothing is selected |
| `Ctrl+V` | Browser-native paste into xterm |
| `Ctrl+L` | Clear via the active shell/readline binding |
| `Ctrl+D` | Send EOF through xterm to the PTY |
| `Alt+Enter` | Toggle terminal fullscreen mode |
| `Esc` | Leave terminal fullscreen mode |

The renderer handles ANSI cursor movement, carriage-return progress updates, wide CJK characters, combining marks, and joined emoji. In other words, columns should remain columns instead of becoming modern art.

## Running tests

```bash
python -m py_compile lan_drive.py test_terminal_ui.py
python -m unittest discover -v
```

The terminal tests cover:

- CJK and Unicode cell widths
- Combining characters and joined emoji
- PTY lifecycle, replay, bounded history/output, live-session limits, resize, rename, and byte-exact key encoding
- xterm/WebSocket client wiring and absence of the retired custom ANSI/polling path
- Git status/history/diff parsing, path validation, request correlation, watcher notifications, and visible-terminal write commands
- Real Windows ConPTY and disposable Git repository runtime smoke

## Project layout

```text
lan_drive.py              Main file-manager application and HTTP integration
lantern_terminal.py       Persistent PTY/ConPTY terminal manager
lantern_scm.py            Direct Git query/parser/watcher service
lantern_ws.py             Same-origin WebSocket protocol bridge
static/terminal_scm.js    xterm multi-terminal + Git/SCM browser UI
lan_drive_config.yaml     Runtime configuration
test_terminal_ui.py       Browser client/static migration contracts
test_terminal_scm.py      Terminal + SCM deterministic tests
README.md                 Project documentation
```

## Design philosophy

The deployment process is intentionally complicated:

1. Copy the Python file.
2. Run the Python file.
3. Open a browser.
4. Spend the time you saved arguing about whether this should have been a Kubernetes cluster.

## Known boundaries

- Windows terminal support is command-oriented, not a full ConPTY terminal emulator.
- Advanced document preview depends on optional local integrations.
- Thumbnail quality depends on Pillow and `ffmpeg` availability.
- This project assumes a trusted private network and does not provide built-in user accounts or authorization.

## License

No license file is currently included. Until one is added, normal copyright restrictions apply.
