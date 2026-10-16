from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from typing import Any


DEFAULT_GREETING = (
    "🦸 Tôi là LanternBot — một thành viên của biệt đội Lantern. "
    "Ở đâu có Lantern, ở đó có ánh sáng; file nào tối nghĩa cứ đưa đây, tôi soi cho."
)

DEFAULT_SYSTEM_PROMPT = """You are LanternBot, the assistant embedded in Lantern.
The newest <lantern_context> block is authoritative for the user's current location.
When the user says this file, here, or this markdown, use that newest context.
For an active document with workingPath, read and edit only workingPath. logicalPath
is the saved project location and must not be read, edited, or written directly;
Lantern commits it only when the user explicitly chooses Save. Other project files
may be edited normally. Prefer native edit/write for mutations, preserve unrelated
content and formatting, and never claim tests passed unless you actually ran them.
Paths listed under attachments are user-selected context. Read them only when useful."""


def _as_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        raise ValueError("LanternBot model/provider policy must be a YAML list")
    result = []
    for item in value:
        text = str(item or "").strip()
        if text:
            result.append(text)
    return tuple(result)


def _optional_limit(value: Any, name: str) -> int | None:
    if value in (None, "", 0, "0"):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer or null") from exc
    if number < 1:
        raise ValueError(f"{name} must be a positive integer or null")
    return number


@dataclass(frozen=True)
class LanternBotConfig:
    enabled: bool = True
    provider: str = ""
    model: str = ""
    lock_provider: bool = False
    lock_model: bool = False
    allowed_providers: tuple[str, ...] = field(default_factory=tuple)
    allowed_models: tuple[str, ...] = field(default_factory=tuple)
    bypass_models: tuple[str, ...] = field(default_factory=tuple)
    max_prompts_per_day: int | None = None
    max_tokens_per_day: int | None = None
    greeting: str = DEFAULT_GREETING
    system_prompt: str = DEFAULT_SYSTEM_PROMPT

    @classmethod
    def from_mapping(cls, value: Any) -> "LanternBotConfig":
        raw = value if isinstance(value, dict) else {}
        selection = raw.get("selection") if isinstance(raw.get("selection"), dict) else {}
        policy = raw.get("policy") if isinstance(raw.get("policy"), dict) else {}

        provider = str(selection.get("provider") or raw.get("provider") or "").strip()
        model = str(selection.get("model") or raw.get("model") or "").strip()
        lock_provider = bool(selection.get("lock_provider", raw.get("lock_provider", False)))
        lock_model = bool(selection.get("lock_model", raw.get("lock_model", False)))
        if bool(selection.get("locked", False)):
            lock_provider = True
            lock_model = True
        if lock_provider and not provider:
            raise ValueError("lantern_bot.selection.lock_provider requires provider")
        if lock_model and not model:
            raise ValueError("lantern_bot.selection.lock_model requires model")

        greeting = str(raw.get("greeting") or DEFAULT_GREETING).strip()
        system_prompt = str(
            raw.get("lantern_context")
            or raw.get("system_prompt")
            or DEFAULT_SYSTEM_PROMPT
        ).strip()

        return cls(
            enabled=bool(raw.get("enabled", True)),
            provider=provider,
            model=model,
            lock_provider=lock_provider,
            lock_model=lock_model,
            allowed_providers=_as_list(policy.get("allowed_providers", raw.get("allowed_providers"))),
            allowed_models=_as_list(policy.get("allowed_models", raw.get("allowed_models"))),
            bypass_models=_as_list(
                policy.get("bypass_models", policy.get("always_allowed_models", raw.get("bypass_models")))
            ),
            max_prompts_per_day=_optional_limit(
                policy.get("max_prompts_per_day", raw.get("max_prompts_per_day")),
                "lantern_bot.policy.max_prompts_per_day",
            ),
            max_tokens_per_day=_optional_limit(
                policy.get("max_tokens_per_day", raw.get("max_tokens_per_day")),
                "lantern_bot.policy.max_tokens_per_day",
            ),
            greeting=greeting,
            system_prompt=system_prompt,
        )

    @staticmethod
    def _matches(patterns: tuple[str, ...], *, provider: str, model_id: str) -> bool:
        key = f"{provider}/{model_id}"
        return any(
            fnmatch.fnmatchcase(key, pattern)
            or ("/" not in pattern and fnmatch.fnmatchcase(model_id, pattern))
            for pattern in patterns
        )

    def allows_model(self, provider: str, model_id: str) -> bool:
        if self._matches(self.bypass_models, provider=provider, model_id=model_id):
            return True
        if self.allowed_providers and not any(
            fnmatch.fnmatchcase(provider, pattern) for pattern in self.allowed_providers
        ):
            return False
        if self.allowed_models and not self._matches(
            self.allowed_models, provider=provider, model_id=model_id
        ):
            return False
        return True

    def public_policy(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "lockProvider": self.lock_provider,
            "lockModel": self.lock_model,
            "configuredProvider": self.provider or None,
            "configuredModel": self.model or None,
            "maxPromptsPerDay": self.max_prompts_per_day,
            "maxTokensPerDay": self.max_tokens_per_day,
            "greeting": self.greeting,
        }
