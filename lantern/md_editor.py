"""Markdown-specific compatibility wrapper over Lantern's generic text CAS store."""
from __future__ import annotations

from pathlib import Path

from .text_file import (
    MAX_TEXT_FILE_BYTES,
    TextFileError,
    read_text_snapshot,
    save_text_cas,
)

MAX_MARKDOWN_EDITOR_BYTES = MAX_TEXT_FILE_BYTES
_MARKDOWN_SUFFIXES = frozenset((".md", ".markdown"))
MarkdownEditorError = TextFileError


def require_markdown(path: Path) -> None:
    if path.suffix.lower() not in _MARKDOWN_SUFFIXES:
        raise MarkdownEditorError(400, "Only .md and .markdown files are supported")
    if not path.is_file():
        raise MarkdownEditorError(404, "Markdown file not found")


def read_document(path: Path):
    require_markdown(path)
    return read_text_snapshot(path, MAX_MARKDOWN_EDITOR_BYTES)


def save_document(path: Path, content: str, expected_version: str):
    require_markdown(path)
    return save_text_cas(path, content, expected_version, MAX_MARKDOWN_EDITOR_BYTES)
