# Lantern — LAN Drive

A one-file web file manager for your LAN or Tailscale network.

It lets you browse, preview, upload, edit, download, stream, and manage files from a browser — because emailing files to yourself in 2026 would be embarrassing.

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
- Open a responsive terminal drawer:
  - Linux: real PTY, with optional `tmux` sessions.
  - Windows: PowerShell or Command Prompt command mode.
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

Optional:

- [Pillow](https://python-pillow.org/) for better image thumbnails
- `ffmpeg` and `ffprobe` for video metadata and thumbnails
- `tmux` on Linux for persistent terminal sessions

Install Pillow:

```bash
python -m pip install pillow
```

Ubuntu/Debian optional packages:

```bash
sudo apt install ffmpeg tmux python3-pil
```

## Quick start

### Windows

```powershell
python lan_drive.py --root "E:\" --port 9999
```

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
terminal_backend_linux: "pty"
terminal_shell_linux: "/bin/bash"
terminal_backend_windows: "command"
terminal_shell_windows: "powershell"
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
| `Ctrl+V` | Paste into the active terminal or Windows command input |
| `Ctrl+L` | Clear the terminal |
| `Ctrl+D` | Send EOF on PTY terminals |
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
- Carriage-return line updates
- `Ctrl+C` copy-versus-interrupt behavior
- Windows command-mode clipboard insertion
- UTF-8 PowerShell output

## Project layout

```text
lan_drive.py              Main application, server, UI, and terminal implementation
lan_drive_config.yaml     Runtime configuration
test_terminal_ui.py       Terminal renderer and Windows command-mode tests
README.md                 You are here. Congratulations on finding documentation.
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
