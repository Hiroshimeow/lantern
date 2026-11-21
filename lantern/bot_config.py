from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from typing import Any


DEFAULT_GREETING = (
    "Hi! I am Lanbot, your workspace assistant. "
    "Select text, paste or drag files and images into chat, or type / for commands."
)

DEFAULT_SYSTEM_PROMPT = """You are LanternBot, the assistant embedded in Lantern.
Each user turn carries its own <lantern_context> block showing the file that was open during that specific turn.
The newest <lantern_context> block shows the file currently open right now (use it when the user says "this file" or "here"), while earlier turns' <lantern_context> blocks record which file was open when those earlier requests were made.
For any active file (Markdown or non-Markdown code/text/data file), path, logicalPath, and workingPath identify the real project file the user is currently viewing or editing.
Lazy File Reading & Token Efficiency Rule: Do NOT automatically read the file in <lantern_context> on greetings or unrelated questions. Only read or edit workingPath/logicalPath when the user actually asks about, references, or requests changes to that file. When line or selectedText is provided, use read with offset and limit around that line (e.g. 30-50 lines) rather than reading the entire file.
When editing, edit the real file directly using native edit/write/bash tools. Lantern shows the difference against an accepted md_temp snapshot. Ctrl+S accepts the current project file as the new comparison baseline. Never edit Lantern's private md_temp snapshot.
Full Coding Harness Rule: On localhost you have full coding harness permissions (including bash/script execution, @tintinweb/pi-subagents, pi-mcp-adapter, and @juicesharp/rpiv-todo). Preserve unrelated formatting and content; do not claim tests passed unless you actually ran them.
Exact Edit & Target Continuity Rule: When calling edit, copy oldText byte-for-byte
from the latest read output (never add or remove backslashes like Ref.\\[3] vs Ref.\\[3\\]).
If the user previously asked to edit file A and temporarily opened sample file B just to show a pattern, continue editing file A unless explicitly told to edit file B.
Paths listed under attachments are user-selected context (including multi-file selection). Read or process all listed attachments when relevant."""

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

_TOOL_MODE_PRESETS: dict[str, tuple[str, ...]] = {
    "*": ("*",),
    "all": ("*",),
    "full": ("*",),
    "yolo": ("*",),
    "code": ("read", "edit", "write", "grep", "find", "ls"),
    "readonly": ("read", "grep", "find", "ls"),
    "read-only": ("read", "grep", "find", "ls"),
    "none": ("none",),
    "chat": ("none",),
}

ALL_THINKING_LEVELS: tuple[str, ...] = ("off", "minimal", "low", "medium", "high", "xhigh")


def _parse_thinking_levels(value: Any) -> tuple[str, ...]:
    if value is None or value == "" or value == "*":
        return ()
    if isinstance(value, str):
        cleaned = value.strip().strip("[]()")
        items = [part.strip().lower() for part in re.split(r"[,;\s]+", cleaned) if part.strip()]
    elif isinstance(value, (list, tuple)):
        items = [str(item or "").strip().lower() for item in value if str(item or "").strip()]
    else:
        return ()
    if any(x in {"*", "all", "full"} for x in items):
        return ()
    valid = [x for x in items if x in ALL_THINKING_LEVELS]
    return tuple(dict.fromkeys(valid))


def _parse_models_and_thinking(
    value: Any,
) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
    if value is None:
        return (), {}
    if isinstance(value, (str, dict)):
        value = [value]
    if not isinstance(value, (list, tuple)):
        raise ValueError("LanternBot model/provider policy must be a YAML list")
    patterns: list[str] = []
    thinking_map: dict[str, tuple[str, ...]] = {}
    inline_re = re.compile(
        r"^(?:model\s*:\s*)?([^\s]+?)(?:\s+thinking\s*:\s*(\[[^\]]*\]|[^\s]+))?$",
        re.IGNORECASE,
    )
    for item in value:
        if isinstance(item, dict):
            raw_model = str(
                item.get("model")
                or item.get("id")
                or item.get("pattern")
                or item.get("name")
                or ""
            ).strip()
            raw_prov = str(item.get("provider") or "").strip()
            if raw_prov and raw_model and "/" not in raw_model:
                raw_model = f"{raw_prov}/{raw_model}"
            if raw_model:
                patterns.append(raw_model)
                t_levels = _parse_thinking_levels(
                    item.get("thinking", item.get("thinking_levels", item.get("allowed_thinking")))
                )
                if t_levels:
                    thinking_map[raw_model] = t_levels
            continue
        text = str(item or "").strip()
        if not text:
            continue
        m = inline_re.match(text)
        if m:
            pat = m.group(1).strip()
            if pat.lower().startswith("model:"):
                pat = pat[6:].strip()
            if pat:
                patterns.append(pat)
                if m.group(2):
                    t_levels = _parse_thinking_levels(m.group(2))
                    if t_levels:
                        thinking_map[pat] = t_levels
        else:
            patterns.append(text)
    return tuple(patterns), thinking_map


def _as_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        raise ValueError("LanternBot model/provider policy must be a YAML list")
    result = []
    for item in value:
        if isinstance(item, dict):
            raw_m = str(item.get("model") or item.get("id") or item.get("name") or "").strip()
            if raw_m:
                result.append(raw_m)
            continue
        text = str(item or "").strip()
        if text:
            result.append(text)
    return tuple(result)


def _normalize_tools(raw_tools: Any, raw_tool_mode: Any, *, is_lan: bool) -> tuple[str, ...]:
    if raw_tools is not None:
        if isinstance(raw_tools, str):
            preset = _TOOL_MODE_PRESETS.get(raw_tools.strip().lower())
            if preset is not None:
                return preset
        parsed = _as_list(raw_tools)
        if not parsed:
            raise ValueError("lantern_bot.access tools must contain at least one allowed tool")
        if any(item.lower() in {"*", "all", "full", "yolo"} for item in parsed):
            return ("*",)
        if not is_lan and set(x.lower() for x in parsed) == {"read", "edit", "write", "grep", "find", "ls"}:
            return ("*",)
        return parsed
    if raw_tool_mode is not None:
        mode_key = str(raw_tool_mode or "").strip().lower()
        preset = _TOOL_MODE_PRESETS.get(mode_key)
        if preset is not None:
            return preset
        raise ValueError(f"Unsupported lantern_bot.access tool_mode: {raw_tool_mode}")
    return ("read", "grep", "find", "ls") if is_lan else ("*",)


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
    thinking_levels: tuple[str, ...] = field(default_factory=tuple)
    model_thinking_map: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # Tool names / globs are checked by the Pi tool-call guard per turn.
    # Default for localhost is Full / YOLO mode ("*") with extensions & MCP enabled.
    tools: tuple[str, ...] = ("*",)
    extensions: bool = True
    mcp: bool = True

    @property
    def is_full_tools(self) -> bool:
        return self.tools == ("*",) or "*" in self.tools

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
        is_lan = raw.get("_scope") == "lan"
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
        raw_model_mode = raw.get("model_mode")
        raw_models_source = raw["models"] if "models" in raw else fallback_models
        if raw.get("models_whitelist") is not None:
            raw_model_mode = "whitelist"
            raw_models_source = raw.get("models_whitelist")
        elif raw.get("models_blacklist") is not None:
            raw_model_mode = "blacklist"
            raw_models_source = raw.get("models_blacklist")

        model_mode = _mode(
            raw_model_mode,
            "lantern_bot access model_mode",
            default=fallback_model_mode,
        )
        providers = _as_list(
            raw["providers"] if "providers" in raw else fallback_providers
        )
        models, model_thinking_map = _parse_models_and_thinking(raw_models_source)
        bypass = _as_list(
            raw["bypass_models"] if "bypass_models" in raw else fallback_bypass
        )
        scope_thinking = _parse_thinking_levels(
            raw.get("thinking", raw.get("thinking_levels", selection.get("thinking")))
        )
        if model and selection.get("thinking") and model not in model_thinking_map:
            sel_thinking = _parse_thinking_levels(selection.get("thinking"))
            if sel_thinking:
                key_pat = f"{provider}/{model}" if provider else model
                model_thinking_map[key_pat] = sel_thinking

        tools = _normalize_tools(
            raw.get("tools") if "tools" in raw else None,
            raw.get("tool_mode", raw.get("toolMode")),
            is_lan=is_lan,
        )
        return cls(
            tools=tools,
            extensions=bool(raw.get("extensions", not is_lan)),
            mcp=bool(raw.get("mcp", not is_lan)),
            provider_mode=provider_mode,
            providers=providers,
            model_mode=model_mode,
            models=models,
            bypass_models=bypass,
            provider=provider,
            model=model,
            lock_provider=lock_provider,
            lock_model=lock_model,
            thinking_levels=scope_thinking,
            model_thinking_map=model_thinking_map,
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

    def allowed_thinking_levels(self, provider: str = "", model_id: str = "") -> tuple[str, ...]:
        provider = str(provider or "").strip()
        model_id = str(model_id or "").strip()
        if model_id and self.model_thinking_map:
            key = f"{provider}/{model_id}" if provider else model_id
            for pattern, levels in self.model_thinking_map.items():
                if (
                    fnmatch.fnmatchcase(key, pattern)
                    or ("/" not in pattern and fnmatch.fnmatchcase(model_id, pattern))
                ):
                    return levels
        if self.thinking_levels:
            return self.thinking_levels
        return ALL_THINKING_LEVELS

    def allows_thinking(self, level: str, provider: str = "", model_id: str = "") -> bool:
        clean = str(level or "").strip().lower()
        return clean in self.allowed_thinking_levels(provider, model_id)

    def public(self) -> dict[str, Any]:
        return {
            "providerMode": self.provider_mode,
            "modelMode": self.model_mode,
            "lockProvider": self.lock_provider,
            "lockModel": self.lock_model,
            "configuredProvider": self.provider or None,
            "configuredModel": self.model or None,
            "allowedThinking": list(self.thinking_levels) if self.thinking_levels else list(ALL_THINKING_LEVELS),
            "modelThinking": {k: list(v) for k, v in self.model_thinking_map.items()},
            "tools": list(self.tools),
            "extensions": self.extensions,
            "mcp": self.mcp,
        }


@dataclass(frozen=True)
class LanternBotConfig:
    enabled: bool = True
    local_access: LanternBotAccessPolicy = field(default_factory=LanternBotAccessPolicy)
    lan_access: LanternBotAccessPolicy = field(default_factory=lambda: LanternBotAccessPolicy(
        tools=("read", "grep", "find", "ls"), extensions=False, mcp=False))
    max_prompts_per_day: int | None = None
    max_tokens_per_day: int | None = None
    greeting: str = DEFAULT_GREETING
    system_prompt: str = DEFAULT_SYSTEM_PROMPT

    @property
    def localhost(self) -> LanternBotAccessPolicy:
        return self.local_access

    @property
    def lan(self) -> LanternBotAccessPolicy:
        return self.lan_access

    @property
    def access(self) -> "LanternBotConfig":
        return self

    @classmethod
    def from_mapping(cls, value: Any) -> "LanternBotConfig":
        raw = value if isinstance(value, dict) else {}
        selection = raw.get("selection") if isinstance(raw.get("selection"), dict) else {}
        policy = raw.get("policy") if isinstance(raw.get("policy"), dict) else {}
        access = raw.get("access") if isinstance(raw.get("access"), dict) else {}

        legacy_providers = policy.get("allowed_providers", raw.get("allowed_providers"))
        legacy_models = policy.get("allowed_models", raw.get("allowed_models"))
        legacy_bypass = policy.get(
            "bypass_models",
            policy.get("always_allowed_models", raw.get("bypass_models")),
        )
        legacy_provider_mode = "whitelist" if _as_list(legacy_providers) else "all"
        legacy_model_mode = "whitelist" if _as_list(legacy_models) else "all"

        local_access = LanternBotAccessPolicy.from_mapping(
            {**(access.get("localhost") if isinstance(access.get("localhost") , dict) else {}), "_scope": "local"},
            fallback_selection=selection,
            fallback_provider_mode="all",
            fallback_providers=(),
            fallback_model_mode="all",
            fallback_models=(),
            fallback_bypass=legacy_bypass,
        )
        lan_access = LanternBotAccessPolicy.from_mapping(
            {**(access.get("lan") if isinstance(access.get("lan"), dict) else {}), "_scope": "lan"},
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

    def allows_thinking(
        self, level: str, provider: str = "", model_id: str = "", *, scope: str = "local"
    ) -> bool:
        return self.access_policy(scope).allows_thinking(level, provider, model_id)

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
