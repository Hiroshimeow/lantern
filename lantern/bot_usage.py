from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class LanternBotUsage:
    def __init__(self, path: Path):
        self.path = Path(path).expanduser().resolve()
        self.lock = threading.RLock()

    @staticmethod
    def _today() -> str:
        return datetime.now().astimezone().date().isoformat()

    def _fresh(self) -> dict[str, Any]:
        return {"date": self._today(), "prompts": 0, "tokens": 0}

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return self._fresh()
        if not isinstance(value, dict) or value.get("date") != self._today():
            return self._fresh()
        return {
            "date": self._today(),
            "prompts": max(0, int(value.get("prompts") or 0)),
            "tokens": max(0, int(value.get("tokens") or 0)),
        }

    def _save(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".lanternbot-usage-", suffix=".tmp",
                                    dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                try:
                    os.fsync(stream.fileno())
                except OSError:
                    pass
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return dict(self._load())

    def assert_prompt_allowed(
        self,
        *,
        max_prompts: int | None,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        with self.lock:
            value = self._load()
            if max_prompts is not None and value["prompts"] >= max_prompts:
                raise RuntimeError(
                    f"LanternBot daily prompt limit reached ({max_prompts})"
                )
            if max_tokens is not None and value["tokens"] >= max_tokens:
                raise RuntimeError(
                    f"LanternBot daily token limit reached ({max_tokens})"
                )
            return dict(value)

    def record_prompt(self) -> dict[str, Any]:
        with self.lock:
            value = self._load()
            value["prompts"] += 1
            self._save(value)
            return dict(value)

    def record_tokens(self, tokens: int) -> dict[str, Any]:
        amount = max(0, int(tokens or 0))
        with self.lock:
            value = self._load()
            value["tokens"] += amount
            self._save(value)
            return dict(value)
