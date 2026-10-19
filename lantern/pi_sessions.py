from __future__ import annotations

import os
import shutil
from copy import deepcopy
from pathlib import Path
from string import ascii_letters, digits
from typing import Any, Callable, Mapping, Optional, Sequence
from uuid import uuid4


def resolve_native_pi_argv() -> list[str]:
    """Resolve the installed Pi CLI without shell-string wrapping."""
    explicit = os.environ.get("LANTERN_PI_COMMAND", "").strip()
    pi = explicit
    if not pi:
        if os.name == "nt":
            pi = (
                shutil.which("pi.cmd")
                or shutil.which("pi.exe")
                or shutil.which("pi")
                or "pi.cmd"
            )
        else:
            pi = shutil.which("pi") or "pi"

    path = Path(pi)
    node = shutil.which("node.exe") or shutil.which("node")
    if os.name == "nt" and path.suffix.lower() in {".cmd", ".bat", ".ps1"}:
        try:
            cli = (
                path.resolve().parent
                / "node_modules"
                / "@earendil-works"
                / "pi-coding-agent"
                / "dist"
                / "bundle"
                / "cli.js"
            )
        except OSError:
            cli = Path()
        if node and cli.is_file():
            return [node, str(cli)]
    if path.suffix.lower() in {".js", ".mjs", ".cjs"} and node:
        return [node, str(path)]
    return [pi]


class PiSessionRegistry:
    """Server-internal ownership for native Pi sessions above TerminalManager."""

    def __init__(
        self,
        root: str | Path,
        state_dir: str | Path,
        terminal,
        pi_argv: Sequence[str],
        *,
        env: Optional[Mapping[str, str]] = None,
        id_factory: Optional[Callable[[], str]] = None,
        context_prompt_factory: Optional[Callable[[Mapping[str, Any]], str]] = None,
    ) -> None:
        if not pi_argv or isinstance(pi_argv, (str, bytes)):
            raise ValueError("pi_argv must be a non-empty sequence")
        self.root = Path(root).resolve()
        self.state_dir = Path(state_dir).resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.terminal = terminal
        self.pi_argv = tuple(pi_argv)
        self.env = dict(env or {})
        self.id_factory = id_factory or (lambda: uuid4().hex)
        self.context_prompt_factory = context_prompt_factory
        self._sessions: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _validate_session_id(session_id: str) -> None:
        allowed = set(ascii_letters + digits + "-_")
        if not isinstance(session_id, str) or not session_id or any(
            char not in allowed for char in session_id
        ):
            raise ValueError("Pi session id must be opaque ASCII letters/numbers/-/_")

    def context_cwd(self, context_ref: Mapping[str, Any]) -> Path:
        """Resolve immutable browser context to an existing cwd inside root."""
        if not isinstance(context_ref, Mapping):
            raise ValueError("Pi context must be an object")
        kind = str(context_ref.get("kind") or "folder").strip().lower()
        raw = context_ref.get("path") if kind in {"file", "markdown"} else context_ref.get("folder")
        if raw in (None, ""):
            raw = context_ref.get("folder") or ""
        rel = str(raw or "").replace("\\", "/").lstrip("/")
        candidate = (self.root / rel).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError:
            raise ValueError("Pi context cwd must stay inside the configured root") from None
        if kind in {"file", "markdown"}:
            candidate = candidate.parent
        if not candidate.exists() or not candidate.is_dir():
            raise ValueError("Pi context cwd must be an existing directory inside the configured root")
        return candidate

    def create_for_context(
        self,
        *,
        context_ref: Mapping[str, Any],
        cols: int = 80,
        rows: int = 24,
        title: str = "Pi",
    ) -> dict[str, Any]:
        return self.create(
            cwd=self.context_cwd(context_ref),
            context_ref=context_ref,
            cols=cols,
            rows=rows,
            title=title,
        )

    def _terminal_status(self, session: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        terminal_id = session["terminalId"]
        generation = session["generation"]
        for item in self.terminal.list():
            if item.get("id") == terminal_id and item.get("generation") == generation:
                return item
        return None

    def _view(self, session: Mapping[str, Any]) -> dict[str, Any]:
        terminal = self._terminal_status(session)
        return {
            "sessionId": session["sessionId"],
            "terminalId": session["terminalId"],
            "generation": session["generation"],
            "cwd": session["cwd"],
            "contextRef": deepcopy(session["contextRef"]),
            "running": bool(terminal and terminal.get("running")),
            "exitCode": terminal.get("exitCode") if terminal else None,
            "cols": int(terminal.get("cols", session["cols"])) if terminal else session["cols"],
            "rows": int(terminal.get("rows", session["rows"])) if terminal else session["rows"],
            "sessionDir": session["sessionDir"],
            "title": session["title"],
        }

    def create(
        self,
        *,
        cwd: str | Path,
        context_ref: Mapping[str, Any],
        cols: int = 80,
        rows: int = 24,
        title: str = "Pi",
    ) -> dict[str, Any]:
        context_snapshot = deepcopy(context_ref)
        session_id = self.id_factory()
        self._validate_session_id(session_id)
        terminal_id = f"pi:{session_id}"
        session_dir = self.state_dir / session_id

        if session_id in self._sessions or session_dir.exists():
            raise ValueError(f"Pi session id collision: {session_id}")
        if any(item.get("id") == terminal_id for item in self.terminal.list()):
            raise ValueError(f"Pi terminal id collision: {terminal_id}")

        session_dir.mkdir()
        argv = [*self.pi_argv]
        if self.context_prompt_factory is not None:
            prompt = str(self.context_prompt_factory(context_snapshot) or "").strip()
            if prompt:
                argv.extend(["--append-system-prompt", prompt])
        argv.extend([
            "--session-id",
            session_id,
            "--session-dir",
            str(session_dir),
            "--tui-mode",
            "regular",
        ])
        try:
            info = self.terminal.create_argv(
                terminal_id,
                cwd,
                argv,
                cols,
                rows,
                title,
                env=self.env,
                control_owner="pi",
            )
        except Exception:
            try:
                session_dir.rmdir()
            except OSError:
                pass
            raise

        session = {
            "sessionId": session_id,
            "terminalId": terminal_id,
            "generation": info["generation"],
            "cwd": info["cwd"],
            "contextRef": context_snapshot,
            "cols": int(info["cols"]),
            "rows": int(info["rows"]),
            "sessionDir": str(session_dir),
            "title": title,
        }
        self._sessions[session_id] = session
        return self._view(session)

    def get(self, session_id: str) -> dict[str, Any]:
        try:
            session = self._sessions[session_id]
        except KeyError:
            raise KeyError(f"Unknown Pi session: {session_id}") from None
        return self._view(session)

    def list(self) -> list[dict[str, Any]]:
        return [self._view(session) for session in self._sessions.values()]

    def stop(self, session_id: str) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Unknown Pi session: {session_id}")
        self.terminal.kill_if_generation(session["terminalId"], session["generation"])
        return self._view(session)

    def close(self) -> None:
        for session in list(self._sessions.values()):
            self.terminal.kill_if_generation(session["terminalId"], session["generation"])
