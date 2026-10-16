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

_MODE_ALIASES = {
    "": "all",
    "all": "all",
    "full": "all",
    "allow": "whitelist",
    "allowlist": "whitelist",
    "white": "whitelist",
    "whitelist": "whitelist",
    "deny": "blacklist",
    "denylist": "blacklist",
    "black": "blacklist",
    "blacklist": "blacklist",
}


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


def _mode(value: Any, name: str, *, default: str = "all") -> str:
    raw = str(value if value is not None else default).strip().lower()
    result = _MODE_ALIASES.get(raw)
    if result is None:
        raise ValueError(f"{name} must be all, whitelist, or blacklist")
    return result


def _matches_model(patterns: tuple[str, ...], provider: str, model_id: str) -> bool:
    key = f"{provider}/{model_id}"
    return any(
        fnmatch.fnmatchcase(key, pattern)
        or ("/" not in pattern and fnmatch.fnmatchcase(model_id, pattern))
        for pattern in patterns
    )


@dataclass(frozen=True)
class LanternBotAccessPolicy:
    provider_mode: str = "all"
    providers: tuple[str, ...] = field(default_factory=tuple)
    model_mode: str = "all"
    models: tuple[str, ...] = field(default_factory=tuple)
    bypass_models: tuple[str, ...] = field(default_factory=tuple)
    provider: str = ""
    model: str = ""
    lock_provider: bool = False
    lock_model: bool = False

    @classmethod
    def from_mapping(
        cls,
        raw_value: Any,
        *,
        fallback_selection: Any = None,
        fallback_provider_mode: str = "all",
        fallback_providers: Any = None,
        fallback_model_mode: str = "all",
        fallback_models: Any = None,
        fallback_bypass: Any = None,
    ) -> "LanternBotAccessPolicy":
        raw = raw_value if isinstance(raw_value, dict) else {}
        selection = raw.get("selection") if isinstance(raw.get("selection"), dict) else {}
        if not selection and isinstance(fallback_selection, dict):
            selection = fallback_selection

        provider = str(selection.get("provider") or "").strip()
        model = str(selection.get("model") or "").strip()
        lock_provider = bool(selection.get("lock_provider", False))
        lock_model = bool(selection.get("lock_model", False))
        if bool(selection.get("locked", False)):
            lock_provider = True
            lock_model = True

        if lock_provider and not provider:
            raise ValueError("LanternBot access lock_provider requires selection.provider")
        if lock_model and (not provider or not model):
            raise ValueError(
                "LanternBot access lock_model requires both selection.provider and selection.model"
            )

        provider_mode = _mode(
            raw.get("provider_mode"),
            "lantern_bot access provider_mode",
            default=fallback_provider_mode,
        )
        model_mode = _mode(
            raw.get("model_mode"),
            "lantern_bot access model_mode",
            default=fallback_model_mode,
        )
        providers = _as_list(
            raw["providers"] if "providers" in raw else fallback_providers
        )
        models = _as_list(raw["models"] if "models" in raw else fallback_models)
        bypass = _as_list(
            raw["bypass_models"] if "bypass_models" in raw else fallback_bypass
        )

        return cls(
            provider_mode=provider_mode,
            providers=providers,
            model_mode=model_mode,
            models=models,
            bypass_models=bypass,
            provider=provider,
            model=model,
            lock_provider=lock_provider,
            lock_model=lock_model,
        )

    def _provider_allowed(self, provider: str) -> bool:
        matched = any(fnmatch.fnmatchcase(provider, pattern) for pattern in self.providers)
        if self.provider_mode == "whitelist":
            return matched
        if self.provider_mode == "blacklist":
            return not matched
        return True

    def _model_allowed(self, provider: str, model_id: str) -> bool:
        matched = _matches_model(self.models, provider, model_id)
        if self.model_mode == "whitelist":
            return matched
        if self.model_mode == "blacklist":
            return not matched
        return True

    def allows_model(self, provider: str, model_id: str) -> bool:
        provider = str(provider or "").strip()
        model_id = str(model_id or "").strip()
        if not provider or not model_id:
            return False

        # bypass_models bypasses only the provider/model list filters. An
        # administrative lock is stronger and must always remain enforceable.
        bypassed = _matches_model(self.bypass_models, provider, model_id)
        if not bypassed:
            if not self._provider_allowed(provider):
                return False
            if not self._model_allowed(provider, model_id):
                return False

        if self.lock_provider and provider != self.provider:
            return False
        if self.lock_model and (provider != self.provider or model_id != self.model):
            return False
        return True

    def public(self) -> dict[str, Any]:
        return {
            "providerMode": self.provider_mode,
            "modelMode": self.model_mode,
            "lockProvider": self.lock_provider,
            "lockModel": self.lock_model,
            "configuredProvider": self.provider or None,
            "configuredModel": self.model or None,
        }


@dataclass(frozen=True)
class LanternBotConfig:
    enabled: bool = True
    local_access: LanternBotAccessPolicy = field(default_factory=LanternBotAccessPolicy)
    lan_access: LanternBotAccessPolicy = field(default_factory=LanternBotAccessPolicy)
    max_prompts_per_day: int | None = None
    max_tokens_per_day: int | None = None
    greeting: str = DEFAULT_GREETING
    system_prompt: str = DEFAULT_SYSTEM_PROMPT

    @classmethod
    def from_mapping(cls, value: Any) -> "LanternBotConfig":
        raw = value if isinstance(value, dict) else {}
        selection = raw.get("selection") if isinstance(raw.get("selection"), dict) else {}
        policy = raw.get("policy") if isinstance(raw.get("policy"), dict) else {}
        access = raw.get("access") if isinstance(raw.get("access"), dict) else {}

        # Legacy global allow-lists remain readable. They become the LAN fallback;
        # localhost is full inventory by default in the new access-scoped schema.
        legacy_providers = policy.get("allowed_providers", raw.get("allowed_providers"))
        legacy_models = policy.get("allowed_models", raw.get("allowed_models"))
        legacy_bypass = policy.get(
            "bypass_models",
            policy.get("always_allowed_models", raw.get("bypass_models")),
        )
        legacy_provider_mode = "whitelist" if _as_list(legacy_providers) else "all"
        legacy_model_mode = "whitelist" if _as_list(legacy_models) else "all"

        local_access = LanternBotAccessPolicy.from_mapping(
            access.get("localhost"),
            fallback_selection=selection,
            fallback_provider_mode="all",
            fallback_providers=(),
            fallback_model_mode="all",
            fallback_models=(),
            fallback_bypass=legacy_bypass,
        )
        lan_access = LanternBotAccessPolicy.from_mapping(
            access.get("lan"),
            fallback_selection=selection,
            fallback_provider_mode=legacy_provider_mode,
            fallback_providers=legacy_providers,
            fallback_model_mode=legacy_model_mode,
            fallback_models=legacy_models,
            fallback_bypass=legacy_bypass,
        )

        greeting = str(raw.get("greeting") or DEFAULT_GREETING).strip()
        system_prompt = str(
            raw.get("lantern_context")
            or raw.get("system_prompt")
            or DEFAULT_SYSTEM_PROMPT
        ).strip()

        return cls(
            enabled=bool(raw.get("enabled", True)),
            local_access=local_access,
            lan_access=lan_access,
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

    @property
    def provider(self) -> str:
        return self.local_access.provider

    @property
    def model(self) -> str:
        return self.local_access.model

    @property
    def lock_provider(self) -> bool:
        return self.local_access.lock_provider

    @property
    def lock_model(self) -> bool:
        return self.local_access.lock_model

    @property
    def allowed_providers(self) -> tuple[str, ...]:
        return self.lan_access.providers if self.lan_access.provider_mode == "whitelist" else ()

    @property
    def allowed_models(self) -> tuple[str, ...]:
        return self.lan_access.models if self.lan_access.model_mode == "whitelist" else ()

    @property
    def bypass_models(self) -> tuple[str, ...]:
        return self.lan_access.bypass_models

    def access_policy(self, scope: str = "local") -> LanternBotAccessPolicy:
        return self.local_access if scope == "local" else self.lan_access

    def allows_model(self, provider: str, model_id: str, *, scope: str = "local") -> bool:
        return self.access_policy(scope).allows_model(provider, model_id)

    def public_policy(self, scope: str = "local") -> dict[str, Any]:
        selected = self.access_policy(scope)
        return {
            "enabled": self.enabled,
            "scope": "localhost" if scope == "local" else "lan",
            **selected.public(),
            "maxPromptsPerDay": self.max_prompts_per_day,
            "maxTokensPerDay": self.max_tokens_per_day,
            "greeting": self.greeting,
        }
