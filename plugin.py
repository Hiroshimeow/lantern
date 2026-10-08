#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Optional document preview plugin for LAN Drive.

This file is intentionally dependency-light. lan_drive.py must keep working when
this plugin is absent or broken. The public surface is small:
  - can_preview(path, config_path=None)
  - render_preview_page(path, root, config_path=None, app_title='LAN Drive')
  - info(config_path=None)
  - add_extension(config_path, pattern) / remove_extension(...)

Custom extension/pattern examples:
  .foo
  *.env.*
  *secret*
"""
from __future__ import annotations

import csv
import fnmatch
import html
import io
import json
import os
import re
import secrets
import subprocess
import zipfile
import zlib
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

VERSION = "0.1.0"
MAX_PREVIEW_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARS = 600_000
MAX_TABLE_ROWS = 160
MAX_TABLE_COLS = 32
MARKDOWN_EXTS = {".md", ".markdown"}

BUILTIN_PATTERNS = [
    ".txt", ".text", ".md", ".markdown", ".rst", ".log",
    ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".env", "*.env", "*.env.*", "*.env-*", "env.*", "*env.local", "*env.production", "*env.development",
    ".py", ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",
    ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".css", ".scss", ".html", ".htm",
    ".xml", ".svg", ".sql", ".go", ".rs", ".c", ".h", ".cpp", ".hpp", ".java",
    ".kt", ".swift", ".php", ".rb", ".lua", ".r", ".dockerfile",
    "dockerfile", "makefile", "readme", "license", "authorized_keys", "known_hosts", "hosts", "config",
    ".pdf", ".docx", ".xlsx", ".xlsm",
]

TEXTISH_EXTS = {
    ".txt", ".text", ".md", ".markdown", ".rst", ".log",
    ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env",
    ".py", ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
    ".css", ".scss", ".html", ".htm", ".xml", ".svg", ".sql", ".go", ".rs", ".c", ".h", ".cpp", ".hpp",
    ".java", ".kt", ".swift", ".php", ".rb", ".lua", ".r", ".dockerfile",
}

TEXTISH_NAMES = {
    "dockerfile", "makefile", "readme", "license", "authorized_keys", "known_hosts", "hosts", "config",
    ".env", ".gitignore", ".dockerignore", ".npmrc", ".yarnrc", ".pnpmrc", ".bashrc", ".zshrc", ".profile",
}


def h(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _default_config_path() -> Path:
    return Path(os.environ.get("LAN_DRIVE_PLUGIN_CONFIG", "/tmp/lan-drive-plugin-config.json"))


def _config_path(config_path: Optional[Path | str]) -> Path:
    return Path(config_path).expanduser().resolve() if config_path else _default_config_path()


def _load_config(config_path: Optional[Path | str]) -> Dict[str, Any]:
    path = _config_path(config_path)
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {"custom_patterns": []}


def _save_config(config_path: Optional[Path | str], data: Dict[str, Any]) -> None:
    path = _config_path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _normalize_pattern(pattern: str) -> str:
    p = (pattern or "").strip().lower().replace("\\", "/")
    if not p:
        return ""
    if "/" in p:
        p = p.rsplit("/", 1)[-1]
    if not any(ch in p for ch in "*?[]") and not p.startswith("."):
        # `envx` should mean extension `.envx` rather than an exact filename.
        p = "." + p
    return p[:160]


def custom_patterns(config_path: Optional[Path | str] = None) -> List[str]:
    data = _load_config(config_path)
    out: List[str] = []
    for item in data.get("custom_patterns", []):
        p = _normalize_pattern(str(item))
        if p and p not in out:
            out.append(p)
    return out


def add_extension(config_path: Optional[Path | str], pattern: str) -> Dict[str, Any]:
    p = _normalize_pattern(pattern)
    if not p:
        raise ValueError("empty extension/pattern")
    data = _load_config(config_path)
    arr = custom_patterns(config_path)
    if p not in arr:
        arr.append(p)
    data["custom_patterns"] = arr
    _save_config(config_path, data)
    return info(config_path)


def remove_extension(config_path: Optional[Path | str], pattern: str) -> Dict[str, Any]:
    p = _normalize_pattern(pattern)
    data = _load_config(config_path)
    data["custom_patterns"] = [x for x in custom_patterns(config_path) if x != p]
    _save_config(config_path, data)
    return info(config_path)


def _suffix_chain(name: str) -> List[str]:
    # pathlib only returns the last suffix; for app.env.local we want .env.local and .local too.
    lname = name.lower()
    parts = lname.split(".")
    if len(parts) <= 1:
        return []
    return ["." + ".".join(parts[i:]) for i in range(1, len(parts))]


def _matches_any(path: Path, patterns: Iterable[str]) -> bool:
    name = path.name.lower()
    suffixes = set(_suffix_chain(name))
    suffixes.add(path.suffix.lower())
    for raw in patterns:
        p = _normalize_pattern(raw)
        if not p:
            continue
        if any(ch in p for ch in "*?[]"):
            if fnmatch.fnmatch(name, p):
                return True
        elif p.startswith("."):
            if p in suffixes or name.endswith(p):
                return True
        else:
            if name == p:
                return True
    return False


def can_preview(path: Path | str, config_path: Optional[Path | str] = None) -> bool:
    p = Path(path)
    if not p.is_file():
        return False
    return _matches_any(p, BUILTIN_PATTERNS) or _matches_any(p, custom_patterns(config_path))


def _kind(path: Path, config_path: Optional[Path | str] = None) -> str:
    name = path.name.lower()
    ext = path.suffix.lower()
    if ext in MARKDOWN_EXTS:
        return "markdown"
    if ext == ".pdf":
        return "pdf"
    if ext == ".docx":
        return "docx"
    if ext in {".xlsx", ".xlsm"}:
        return "xlsx"
    if ext in {".csv", ".tsv"}:
        return "csv"
    if ext in TEXTISH_EXTS or name in TEXTISH_NAMES or _matches_any(path, custom_patterns(config_path)) or _matches_any(path, ["*.env.*", "*.env-*"]):
        return "text"
    return "text"


def _read_limited_bytes(path: Path, limit: int = MAX_PREVIEW_BYTES) -> Tuple[bytes, bool]:
    # Slice-after-read defeats the memory cap for multi-gigabyte files.
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    return data[:limit], len(data) > limit


def _decode_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp932", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode("utf-8", "replace")


def _is_probably_binary(data: bytes) -> bool:
    if b"\x00" in data[:4096]:
        return True
    if not data:
        return False
    sample = data[:4096]
    bad = sum(1 for b in sample if b < 9 or (13 < b < 32))
    return bad / max(1, len(sample)) > 0.18


def _render_text(path: Path) -> Tuple[str, str]:
    data, truncated = _read_limited_bytes(path)
    if _is_probably_binary(data):
        return "Binary-ish file", "<p>File này có vẻ là binary. Không render dạng text để tránh rác màn hình.</p>"
    text = _decode_text(data)
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]
        truncated = True
    note = "<div class='note'>Đã cắt preview để giữ UI nhẹ.</div>" if truncated else ""
    return "Text preview", f"{note}<pre class='text-preview'>{h(text)}</pre>"


def _trim_c0(value: str) -> str:
    return value.strip("".join(chr(i) for i in range(33)))


def _safe_markdown_target(url: str, source_path: Path, root: Path, image: bool = False) -> Optional[str]:
    raw = re.sub(r"[\t\r\n]", "", url)
    raw = _trim_c0(html.unescape(raw)).replace("\\", "/")
    if not raw or raw.startswith("//"):
        return None
    if raw.startswith("#"):
        return raw

    split = urlsplit(raw)
    scheme = split.scheme.lower()
    if scheme:
        if image or scheme not in {"http", "https", "mailto"}:
            return None
        return urlunsplit((scheme, split.netloc, split.path, split.query, split.fragment))

    decoded_path = unquote(split.path)
    if re.search(r"%(?:2e%?2e|2f)", decoded_path, flags=re.I):
        return None

    root_resolved = root.resolve()
    parent = source_path.resolve().parent
    if decoded_path.startswith("/"):
        relative = decoded_path.lstrip("/")
    else:
        try:
            parent_rel = parent.relative_to(root_resolved).as_posix()
        except ValueError:
            return None
        relative = "/".join(x for x in (parent_rel, decoded_path) if x)

    target = (root_resolved / Path(*[x for x in relative.split("/") if x not in {"", "."}])).resolve()
    try:
        rel = target.relative_to(root_resolved).as_posix()
    except ValueError:
        return None

    encoded = "/" + "/".join(quote(segment, safe="") for segment in rel.split("/") if segment)
    if split.query:
        encoded += "?" + split.query
    if split.fragment:
        encoded += "#" + split.fragment
    return encoded or "/"


def _md_inline(text: str, source_path: Path, root: Path) -> str:
    stash: List[str] = []

    def keep(fragment: str) -> str:
        token = f"\u0000MD{len(stash)}\u0000"
        stash.append(fragment)
        return token

    work = re.sub(
        r"`([^`\n]+)`",
        lambda m: keep(f"<code>{h(m.group(1))}</code>"),
        text,
    )

    def image_repl(match: re.Match[str]) -> str:
        alt = match.group(1)
        target = _safe_markdown_target(match.group(2), source_path, root, image=True)
        if target is None:
            return alt
        return keep(f'<img src="{h(target)}" alt="{h(alt)}">')

    work = re.sub(r"!\[([^\]]*)\]\(([^)\r\n]*)\)", image_repl, work)

    def link_repl(match: re.Match[str]) -> str:
        label = match.group(1)
        target = _safe_markdown_target(match.group(2), source_path, root, image=False)
        if target is None:
            return label
        return keep(
            f'<a href="{h(target)}" target="_blank" rel="noopener noreferrer">{h(label)}</a>'
        )

    work = re.sub(r"\[([^\]]+)\]\(([^)\r\n]*)\)", link_repl, work)
    escaped = h(work)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", escaped)
    escaped = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"<em>\1</em>", escaped)

    changed = True
    while changed:
        changed = False
        for i in range(len(stash) - 1, -1, -1):
            token = f"\u0000MD{i}\u0000"
            if token in escaped:
                escaped = escaped.replace(token, stash[i])
                changed = True
    return escaped


def _flush_md_paragraph(out: List[str], lines: List[str], source_path: Path, root: Path) -> None:
    if not lines:
        return
    text = " ".join(x.strip() for x in lines).strip()
    if text:
        out.append(f"<p>{_md_inline(text, source_path, root)}</p>")
    lines.clear()


def _split_table_row(line: str) -> List[str]:
    cells = line.strip()
    if cells.startswith("|"):
        cells = cells[1:]
    if cells.endswith("|"):
        cells = cells[:-1]
    return [cell.strip() for cell in cells.split("|")][:MAX_TABLE_COLS]


def _is_table_separator(line: str) -> bool:
    cells = _split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _render_markdown(path: Path, root: Path) -> Tuple[str, str]:
    data, truncated = _read_limited_bytes(path)
    text = _decode_text(data).replace("\x00", "")
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]
        truncated = True

    lines = text.splitlines()
    out: List[str] = []
    para: List[str] = []
    list_type = ""
    in_quote = False
    mermaid_count = 0

    def flush() -> None:
        _flush_md_paragraph(out, para, path, root)

    def close_list() -> None:
        nonlocal list_type
        if list_type:
            out.append(f"</{list_type}>")
            list_type = ""

    def close_quote() -> None:
        nonlocal in_quote
        if in_quote:
            out.append("</blockquote>")
            in_quote = False

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        opener = re.match(r"^ {0,3}([`~])\1{2,}(.*)$", line)
        if opener:
            flush()
            close_list()
            close_quote()
            char = opener.group(1)
            run = len(line.lstrip()) - len(line.lstrip().lstrip(char))
            info = opener.group(2).strip()
            close_re = re.compile(rf"^ {{0,3}}{re.escape(char)}{{{run},}}\s*$")
            end = i + 1
            while end < len(lines) and not close_re.match(lines[end]):
                end += 1
            code_lines = lines[i + 1:end]
            language = info.split(None, 1)[0] if info else ""
            if end >= len(lines):
                body = "\n".join(code_lines)
                attr = f' data-language="{h(language)}"' if language else ""
                out.append(f'<pre class="md-code"{attr}><code>{h(body)}</code></pre>')
                break
            body = "\n".join(code_lines)
            if language.lower() == "mermaid" and mermaid_count < 24:
                mermaid_count += 1
                out.append(
                    f'<div class="mermaid-diagram" data-diagram-index="{mermaid_count}">'
                    f'<pre class="mermaid-source"><code>{h(body)}</code></pre>'
                    '<div class="mermaid-output"></div>'
                    f'<button class="btn" type="button" data-action="png" data-diagram-index="{mermaid_count}" hidden>PNG</button>'
                    "</div>"
                )
            else:
                attr = f' data-language="{h(language)}"' if language else ""
                out.append(f'<pre class="md-code"{attr}><code>{h(body)}</code></pre>')
            i = end + 1
            continue

        if i + 1 < len(lines) and "|" in line and _is_table_separator(lines[i + 1]):
            flush()
            close_list()
            close_quote()
            headers = _split_table_row(line)
            rows: List[List[str]] = []
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip() and len(rows) < MAX_TABLE_ROWS:
                rows.append(_split_table_row(lines[i]))
                i += 1
            head = "".join(f"<th>{_md_inline(cell, path, root)}</th>" for cell in headers)
            body_rows = []
            for row in rows:
                cells = row + [""] * max(0, len(headers) - len(row))
                body_rows.append(
                    "<tr>" + "".join(f"<td>{_md_inline(cell, path, root)}</td>" for cell in cells[:len(headers)]) + "</tr>"
                )
            out.append(
                '<div class="table-wrap"><table><thead><tr>'
                + head
                + "</tr></thead><tbody>"
                + "".join(body_rows)
                + "</tbody></table></div>"
            )
            continue

        if not stripped:
            flush()
            close_list()
            close_quote()
            i += 1
            continue

        heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", stripped)
        if heading:
            flush()
            close_list()
            close_quote()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_md_inline(heading.group(2), path, root)}</h{level}>")
            i += 1
            continue

        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
            flush()
            close_list()
            close_quote()
            out.append("<hr>")
            i += 1
            continue

        quote_match = re.match(r"^>\s?(.*)$", line)
        if quote_match:
            flush()
            close_list()
            if not in_quote:
                out.append("<blockquote>")
                in_quote = True
            out.append(f"<p>{_md_inline(quote_match.group(1), path, root)}</p>")
            i += 1
            continue

        close_quote()
        ul = re.match(r"^\s*[-+*]\s+(.+)$", line)
        ol = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        if ul or ol:
            flush()
            tag = "ul" if ul else "ol"
            if list_type != tag:
                close_list()
                out.append(f"<{tag}>")
                list_type = tag
            item = (ul or ol).group(1)
            task = re.match(r"^\[([ xX])\]\s+(.*)$", item)
            if task:
                checked = " checked" if task.group(1).lower() == "x" else ""
                out.append(
                    '<li class="task-item"><input type="checkbox" disabled aria-label="task"'
                    + checked
                    + ">"
                    + _md_inline(task.group(2), path, root)
                    + "</li>"
                )
            else:
                out.append(f"<li>{_md_inline(item, path, root)}</li>")
            i += 1
            continue

        close_list()
        para.append(line)
        i += 1

    flush()
    close_list()
    close_quote()
    note = "<div class='note'>Markdown preview uses a bounded parser; raw HTML is escaped.</div>"
    if truncated:
        note += "<div class='note'>Preview truncated to keep the UI bounded.</div>"
    return "Markdown preview", note + "<article class='md-preview'>" + "\n".join(out) + "</article>"


def _render_csv(path: Path) -> Tuple[str, str]:
    raw, truncated = _read_limited_bytes(path)
    text = _decode_text(raw)
    dialect = csv.excel_tab if path.suffix.lower() == ".tsv" else csv.excel
    reader = csv.reader(io.StringIO(text), dialect=dialect)
    rows: List[List[str]] = []
    for i, row in enumerate(reader):
        if i >= MAX_TABLE_ROWS:
            truncated = True
            break
        rows.append(row[:MAX_TABLE_COLS])
    if not rows:
        return "CSV preview", "<p>CSV/TSV rỗng.</p>"
    maxcols = max(len(r) for r in rows)
    html_rows = []
    for i, row in enumerate(rows):
        cells = "".join(("<th>" if i == 0 else "<td>") + h(row[j] if j < len(row) else "") + ("</th>" if i == 0 else "</td>") for j in range(maxcols))
        html_rows.append(f"<tr>{cells}</tr>")
    note = "<div class='note'>Đã cắt bảng preview.</div>" if truncated else ""
    return "CSV/TSV preview", note + "<div class='table-wrap'><table>" + "\n".join(html_rows) + "</table></div>"


def _xml_text(elem: ET.Element) -> str:
    return "".join(elem.itertext())


def _render_docx(path: Path) -> Tuple[str, str]:
    try:
        with zipfile.ZipFile(path) as z:
            names = ["word/document.xml"] + [n for n in z.namelist() if n.startswith("word/") and n.endswith(".xml") and any(k in n for k in ("header", "footer", "footnotes", "endnotes"))]
            parts: List[str] = []
            for name in names:
                try:
                    root = ET.fromstring(z.read(name))
                except Exception:
                    continue
                # WordprocessingML paragraphs/tables. itertext is crude but robust enough for fast preview.
                text = _xml_text(root)
                text = re.sub(r"[ \t\r\f\v]+", " ", text)
                text = re.sub(r"\n{3,}", "\n\n", text)
                if text.strip():
                    label = name.replace("word/", "")
                    parts.append(f"--- {label} ---\n{text.strip()}")
            body = "\n\n".join(parts).strip()
            if not body:
                body = "Không trích được text từ DOCX này."
            if len(body) > MAX_TEXT_CHARS:
                body = body[:MAX_TEXT_CHARS] + "\n\n[truncated]"
            return "DOCX preview", f"<pre class='text-preview'>{h(body)}</pre>"
    except zipfile.BadZipFile:
        return "DOCX preview", "<p>File DOCX không phải zip hợp lệ hoặc đã hỏng.</p>"


def _xlsx_shared_strings(z: zipfile.ZipFile) -> List[str]:
    try:
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    except Exception:
        return []
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    strings = []
    for si in root.findall(f".//{ns}si"):
        strings.append("".join(si.itertext()))
    return strings


def _xlsx_sheet_names(z: zipfile.ZipFile) -> List[Tuple[str, str]]:
    try:
        root = ET.fromstring(z.read("xl/workbook.xml"))
    except Exception:
        return []
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    rel_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    out = []
    for sheet in root.findall(f".//{ns}sheet"):
        out.append((sheet.attrib.get("name", "Sheet"), sheet.attrib.get(rel_ns + "id", "")))
    return out


def _xlsx_rels(z: zipfile.ZipFile) -> Dict[str, str]:
    try:
        root = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    except Exception:
        return {}
    rels: Dict[str, str] = {}
    for rel in root:
        rid = rel.attrib.get("Id", "")
        target = rel.attrib.get("Target", "")
        if rid and target:
            if not target.startswith("/"):
                target = "xl/" + target
            else:
                target = target.lstrip("/")
            rels[rid] = target
    return rels


def _cell_value(cell: ET.Element, shared: List[str]) -> str:
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    typ = cell.attrib.get("t", "")
    if typ == "inlineStr":
        return "".join(cell.itertext())
    v = cell.find(f"{ns}v")
    if v is None or v.text is None:
        return ""
    raw = v.text
    if typ == "s":
        try:
            return shared[int(raw)]
        except Exception:
            return raw
    return raw


def _render_xlsx(path: Path) -> Tuple[str, str]:
    try:
        with zipfile.ZipFile(path) as z:
            shared = _xlsx_shared_strings(z)
            sheets = _xlsx_sheet_names(z)
            rels = _xlsx_rels(z)
            blocks: List[str] = []
            for sheet_name, rid in sheets[:5]:
                target = rels.get(rid)
                if not target or target not in z.namelist():
                    continue
                root = ET.fromstring(z.read(target))
                ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
                rows_html = []
                for r_i, row in enumerate(root.findall(f".//{ns}sheetData/{ns}row")):
                    if r_i >= MAX_TABLE_ROWS:
                        break
                    vals = [_cell_value(c, shared) for c in list(row)[:MAX_TABLE_COLS]]
                    cells = "".join(f"<td>{h(v)}</td>" for v in vals)
                    rows_html.append(f"<tr>{cells}</tr>")
                if rows_html:
                    blocks.append(f"<h2>{h(sheet_name)}</h2><div class='table-wrap'><table>{''.join(rows_html)}</table></div>")
            if not blocks:
                return "Excel preview", "<p>Không thấy sheet/cell để preview.</p>"
            return "Excel preview", "<div class='note'>Preview tối đa vài sheet đầu, không tính công thức/style.</div>" + "".join(blocks)
    except zipfile.BadZipFile:
        return "Excel preview", "<p>File Excel không phải OOXML zip hợp lệ. .xls đời cũ chưa hỗ trợ bằng stdlib.</p>"


def _decode_pdf_string(s: str) -> str:
    # Minimal PDF literal string unescape.
    s = s.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
    s = re.sub(r"\\n", "\n", s)
    s = re.sub(r"\\r", "\n", s)
    s = re.sub(r"\\t", "\t", s)
    def repl_oct(m: re.Match[str]) -> str:
        try:
            return chr(int(m.group(1), 8))
        except Exception:
            return ""
    return re.sub(r"\\([0-7]{1,3})", repl_oct, s)


def _extract_pdf_text_naive(data: bytes) -> str:
    chunks: List[bytes] = []
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, flags=re.S):
        raw = m.group(1)
        header = data[max(0, m.start() - 300):m.start()]
        if b"FlateDecode" in header:
            try:
                raw = zlib.decompress(raw)
            except Exception:
                pass
        chunks.append(raw)
    if not chunks:
        chunks = [data]
    text_parts: List[str] = []
    for raw in chunks[:400]:
        s = raw.decode("latin-1", "ignore")
        for item in re.findall(r"\((?:\\.|[^\\)]){1,1000}\)\s*Tj", s):
            literal = item.rsplit(")", 1)[0][1:]
            text_parts.append(_decode_pdf_string(literal))
        for arr in re.findall(r"\[(.*?)\]\s*TJ", s, flags=re.S):
            vals = re.findall(r"\((?:\\.|[^\\)])*\)", arr)
            if vals:
                text_parts.append("".join(_decode_pdf_string(v[1:-1]) for v in vals))
    out = "\n".join(t.strip() for t in text_parts if t.strip())
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _render_pdf(path: Path) -> Tuple[str, str]:
    # Prefer system pdftotext when present. It is common on Linux boxes and much better than naive parsing.
    try:
        r = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"], capture_output=True, text=True, timeout=15, errors="replace")
        if r.returncode == 0 and r.stdout.strip():
            body = r.stdout[:MAX_TEXT_CHARS]
            note = "<div class='note'>Text lấy bằng pdftotext.</div>"
            return "PDF preview", note + f"<pre class='text-preview'>{h(body)}</pre>"
    except Exception:
        pass
    data, truncated = _read_limited_bytes(path, MAX_PREVIEW_BYTES)
    text = _extract_pdf_text_naive(data)
    if not text:
        msg = "Không trích được text PDF bằng parser nhẹ. Browser vẫn có thể mở PDF gốc bằng nút Open raw."
        return "PDF preview", f"<p>{h(msg)}</p>"
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + "\n\n[truncated]"
    note = "<div class='note'>PDF parser nhẹ, kết quả có thể thiếu font/Unicode phức tạp.</div>"
    if truncated:
        note += "<div class='note'>Chỉ đọc một phần đầu file.</div>"
    return "PDF preview", note + f"<pre class='text-preview'>{h(text)}</pre>"


def render_content(path: Path | str, config_path: Optional[Path | str] = None, root: Optional[Path | str] = None) -> Tuple[str, str]:
    p = Path(path)
    kind = _kind(p, config_path)
    if kind == "markdown":
        return _render_markdown(p, Path(root) if root is not None else p.parent)
    if kind == "pdf":
        return _render_pdf(p)
    if kind == "docx":
        return _render_docx(p)
    if kind == "xlsx":
        return _render_xlsx(p)
    if kind == "csv":
        return _render_csv(p)
    return _render_text(p)


def render_preview_page(path: Path | str, root: Path | str, config_path: Optional[Path | str] = None, app_title: str = "LAN Drive") -> bytes:
    p = Path(path)
    rootp = Path(root)
    try:
        rel = p.resolve().relative_to(rootp.resolve()).as_posix()
    except Exception:
        rel = p.name
    title, body = render_content(p, config_path, rootp)
    raw_url = "/" + "/".join([quote_component(x) for x in rel.split("/")])
    nonce = secrets.token_urlsafe(24)
    csp = (
        "default-src 'none'; "
        f"script-src 'nonce-{nonce}'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "connect-src 'none'; "
        "base-uri 'none'; "
        "object-src 'none'; "
        "form-action 'none'"
    )
    css = """
:root{color-scheme:dark;--bg:#080a0f;--panel:#10151e;--line:#283343;--text:#f8fafc;--muted:#b9c4d0;--accent:#68e37a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}.bar{position:sticky;top:0;z-index:5;display:flex;gap:10px;align-items:center;padding:10px 12px;background:rgba(16,21,30,.94);border-bottom:1px solid var(--line);backdrop-filter:blur(12px)}.title{font-weight:850;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.grow{flex:1}.btn{height:34px;padding:0 11px;border-radius:11px;border:1px solid rgba(255,255,255,.12);background:#151d29;color:var(--text);text-decoration:none;display:inline-flex;align-items:center;font-weight:750;cursor:pointer}.btn.primary{background:linear-gradient(135deg,#54ee69,#7eaaff);color:#061007;border:0}.content{padding:14px}.note{padding:8px 10px;margin:0 0 10px;border:1px solid rgba(255,255,255,.1);border-radius:12px;background:rgba(255,255,255,.04);color:var(--muted)}.text-preview{margin:0;padding:14px;border:1px solid var(--line);border-radius:14px;background:#05070b;color:#eef7ef;white-space:pre-wrap;word-break:break-word;font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}.md-preview{max-width:980px;margin:0 auto;padding:18px 22px;border:1px solid var(--line);border-radius:16px;background:#0b1018;color:#edf5ff;font-size:15px;line-height:1.72}.md-preview h1,.md-preview h2,.md-preview h3{line-height:1.25;border-bottom:1px solid rgba(255,255,255,.1);padding-bottom:.28em}.md-preview a{color:#8db4ff}.md-preview code{background:#18202c;border:1px solid rgba(255,255,255,.09);border-radius:6px;padding:.1em .35em}.md-code{padding:12px 14px;border:1px solid #263142;border-radius:13px;background:#05070b;overflow:auto}.md-preview blockquote{margin:10px 0;padding:4px 12px;border-left:4px solid var(--accent);background:rgba(104,227,122,.06);color:var(--muted)}.md-preview hr{border:0;border-top:1px solid var(--line);margin:18px 0}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:14px;background:#070a10;margin:10px 0}table{border-collapse:collapse;min-width:100%;font:13px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}td,th{border:1px solid #263142;padding:6px 8px;vertical-align:top;max-width:360px;white-space:pre-wrap}th{background:#111827;position:sticky;top:0}h2{margin:18px 0 8px;font-size:16px}.muted{color:var(--muted)}.task-item{list-style:none}.task-item input{margin-right:.5em}.mermaid-diagram{margin:14px 0;padding:12px;border:1px solid var(--line);border-radius:14px;background:#fff;color:#111}.mermaid-output svg{max-width:100%;height:auto}
@media print{:root{color-scheme:light}body,.md-preview{background:#fff!important;color:#111!important}.bar,.muted,.note,.mermaid-diagram>.btn{display:none!important}.content{padding:0}.md-preview{max-width:none;border:0;padding:0}.table-wrap,.md-code{overflow:visible!important}th{position:static!important}pre{white-space:pre-wrap!important;overflow:visible!important}.mermaid-output svg{max-width:100%!important;height:auto!important}.mermaid-diagram{border:0;padding:0}}
"""
    mermaid_script = (
        f'<script nonce="{h(nonce)}" src="/static/vendor/mermaid-11.17.2.min.js" defer></script>\n'
        if 'class="mermaid-diagram"' in body else ""
    )
    helper_script = f'<script nonce="{h(nonce)}" src="/static/markdown_preview.js" defer></script>'
    page = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="{h(csp)}"><title>{h(title)} - {h(rel)}</title><style>{css}</style>
{mermaid_script}{helper_script}</head>
<body>
<div class="bar"><button class="btn" type="button" data-action="back">↩ Back</button><div class="title">{h(title)} · {h(rel)}</div><div class="grow"></div><button class="btn" type="button" data-action="print">Print / Save as PDF</button><a class="btn" href="/api/plugin/preview?p={h(rel)}">Preview</a><a class="btn" href="{h(raw_url)}?edit=1">Edit</a><a class="btn" href="{h(raw_url)}" target="_blank" rel="noopener noreferrer">Open raw</a><a class="btn primary" href="{h(raw_url)}?download=1">Download</a></div>
<div class="content" data-doc-name="{h(p.stem)}"><div class="muted">{h(app_title)} plugin preview · {h(p.name)}</div>{body}</div>
</body></html>"""
    return page.encode("utf-8", "surrogateescape")


def quote_component(s: str) -> str:
    from urllib.parse import quote
    return quote(s)


def info(config_path: Optional[Path | str] = None) -> Dict[str, Any]:
    return {
        "ok": True,
        "version": VERSION,
        "builtin_patterns": BUILTIN_PATTERNS,
        "custom_patterns": custom_patterns(config_path),
        "formats": ["markdown", "text/env/code/log", "csv/tsv", "pdf", "docx", "xlsx/xlsm"],
        "notes": [
            "DOCX/XLSX preview uses stdlib OOXML parsing, no formatting/macros.",
            "PDF preview prefers pdftotext when installed, otherwise best-effort parser.",
            "Legacy .doc/.xls binary Office is not parsed by stdlib; use raw download or convert.",
        ],
    }
