from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lantern import config as app_config
from lantern.bot_config import LanternBotConfig


class LanternBotConfigTests(unittest.TestCase):
    def test_empty_config_is_full_inventory_for_localhost_and_lan(self):
        cfg = LanternBotConfig.from_mapping({})
        self.assertEqual(cfg.provider, "")
        self.assertEqual(cfg.model, "")
        for scope in ("local", "lan"):
            self.assertTrue(cfg.allows_model("cliproxy-2080", "gpt-6.1-sol", scope=scope))
            self.assertTrue(cfg.allows_model("github-copilot", "gpt-5", scope=scope))

    def test_localhost_full_while_lan_uses_independent_white_black_lists(self):
        cfg = LanternBotConfig.from_mapping({
            "access": {
                "localhost": {
                    "provider_mode": "all",
                    "model_mode": "all",
                },
                "lan": {
                    "provider_mode": "whitelist",
                    "providers": ["cliproxy-*"],
                    "model_mode": "blacklist",
                    "models": ["cliproxy-2080/claude-*"],
                    "bypass_models": ["github-copilot/gpt-5"],
                },
            },
        })
        self.assertTrue(cfg.allows_model("github-copilot", "claude-sonnet", scope="local"))
        self.assertTrue(cfg.allows_model("cliproxy-2080", "gpt-6.1-sol", scope="lan"))
        self.assertFalse(cfg.allows_model("cliproxy-2080", "claude-opus-5-5", scope="lan"))
        self.assertFalse(cfg.allows_model("github-copilot", "claude-sonnet", scope="lan"))
        self.assertTrue(cfg.allows_model("github-copilot", "gpt-5", scope="lan"))

    def test_lan_model_lock_is_scope_local_and_requires_exact_provider_model(self):
        cfg = LanternBotConfig.from_mapping({
            "access": {
                "lan": {
                    "provider_mode": "all",
                    "model_mode": "all",
                    "selection": {
                        "provider": "cliproxy-2080",
                        "model": "gpt-6.1-sol",
                        "lock_provider": True,
                        "lock_model": True,
                    },
                },
            },
        })
        self.assertTrue(cfg.allows_model("github-copilot", "gpt-5", scope="local"))
        self.assertTrue(cfg.allows_model("cliproxy-2080", "gpt-6.1-sol", scope="lan"))
        self.assertFalse(cfg.allows_model("cliproxy-2080", "claude-opus-5-5", scope="lan"))
        self.assertFalse(cfg.allows_model("github-copilot", "gpt-6.1-sol", scope="lan"))
        public = cfg.public_policy("lan")
        self.assertEqual(public["scope"], "lan")
        self.assertTrue(public["lockModel"])

    def test_locked_values_must_be_unambiguous(self):
        with self.assertRaisesRegex(ValueError, "requires selection.provider"):
            LanternBotConfig.from_mapping({
                "access": {"lan": {"selection": {"lock_provider": True}}},
            })
        with self.assertRaisesRegex(ValueError, "requires both"):
            LanternBotConfig.from_mapping({
                "access": {"lan": {"selection": {"model": "gpt-5", "lock_model": True}}},
            })

    def test_bypass_can_cross_lists_but_never_crosses_hard_lock(self):
        cfg = LanternBotConfig.from_mapping({
            "access": {
                "lan": {
                    "provider_mode": "whitelist",
                    "providers": ["cliproxy-*"],
                    "model_mode": "whitelist",
                    "models": ["cliproxy-2080/gpt-*"],
                    "bypass_models": ["github-copilot/claude-*"],
                    "selection": {
                        "provider": "cliproxy-2080",
                        "model": "gpt-6.1-sol",
                        "lock_provider": True,
                        "lock_model": True,
                    },
                },
            },
        })
        self.assertTrue(cfg.allows_model("cliproxy-2080", "gpt-6.1-sol", scope="lan"))
        self.assertFalse(
            cfg.allows_model("github-copilot", "claude-sonnet", scope="lan"),
            "bypass_models must not bypass a hard LAN selection lock",
        )

    def test_bare_model_pattern_matches_any_provider(self):
        cfg = LanternBotConfig.from_mapping({
            "access": {
                "lan": {
                    "model_mode": "whitelist",
                    "models": ["gpt-*"],
                },
            },
        })
        self.assertTrue(cfg.allows_model("github-copilot", "gpt-5", scope="lan"))
        self.assertTrue(cfg.allows_model("cliproxy-2080", "gpt-6.1-sol", scope="lan"))
        self.assertFalse(cfg.allows_model("cliproxy-2080", "claude-opus-5-5", scope="lan"))

    def test_legacy_allowed_lists_apply_to_lan_but_not_localhost(self):
        cfg = LanternBotConfig.from_mapping({
            "policy": {
                "allowed_providers": ["github-*"],
                "allowed_models": ["github-copilot/gpt-*"],
                "bypass_models": ["cliproxy-2080/claude-opus-*"],
                "max_prompts_per_day": 25,
                "max_tokens_per_day": 500_000,
            },
        })
        self.assertTrue(cfg.allows_model("cliproxy-2080", "gpt-6.1-sol", scope="local"))
        self.assertTrue(cfg.allows_model("github-copilot", "gpt-5", scope="lan"))
        self.assertFalse(cfg.allows_model("github-copilot", "claude-sonnet", scope="lan"))
        self.assertTrue(cfg.allows_model("cliproxy-2080", "claude-opus-5-5", scope="lan"))
        self.assertEqual(cfg.max_prompts_per_day, 25)
        self.assertEqual(cfg.max_tokens_per_day, 500_000)

    def test_real_yaml_nested_access_policy_loads(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "lan_drive_config.yaml"
            path.write_text(
                """root: C:/root
port: 9999
lantern_bot:
  enabled: true
  access:
    localhost:
      provider_mode: all
      model_mode: all
    lan:
      provider_mode: whitelist
      providers:
        - cliproxy-2080
      model_mode: whitelist
      models:
        - cliproxy-2080/gpt-*
      bypass_models:
        - github-copilot/gpt-5
      selection:
        provider: cliproxy-2080
        model: gpt-6.1-sol
        lock_provider: false
        lock_model: false
  policy:
    max_prompts_per_day: 10
  greeting: Hello
  lantern_context: |
    You are LanternBot.
    Keep context.
""",
                encoding="utf-8",
            )
            loaded = app_config.load_simple_yaml(path)
            cfg = LanternBotConfig.from_mapping(loaded["lantern_bot"])
            self.assertEqual(cfg.lan_access.provider_mode, "whitelist")
            self.assertEqual(cfg.lan_access.model_mode, "whitelist")
            self.assertEqual(cfg.lan_access.provider, "cliproxy-2080")
            self.assertEqual(cfg.max_prompts_per_day, 10)
            self.assertIn("Keep context.", cfg.system_prompt)
            self.assertTrue(cfg.allows_model("github-copilot", "gpt-5", scope="lan"))

    def test_write_config_file_roundtrips_access_policy(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.yaml"
            bot = LanternBotConfig.from_mapping({
                "access": {
                    "localhost": {"provider_mode": "all", "model_mode": "all"},
                    "lan": {
                        "provider_mode": "whitelist",
                        "providers": ["cliproxy-*"],
                        "model_mode": "blacklist",
                        "models": ["cliproxy-2080/claude-*"],
                        "bypass_models": ["github-copilot/gpt-5"],
                        "selection": {
                            "provider": "cliproxy-2080",
                            "model": "gpt-6.1-sol",
                            "lock_provider": True,
                            "lock_model": True,
                        },
                    },
                },
                "policy": {"max_tokens_per_day": 12345},
                "greeting": "HELLO",
                "lantern_context": "SYSTEM\nLINE2",
            })
            cfg = app_config.AppConfig(
                root=Path(td),
                port=9999,
                host="127.0.0.1",
                title="Lantern",
                cache_dir=Path(td) / "cache",
                config_path=path,
                lantern_bot=bot,
            )
            app_config.write_config_file(cfg)
            loaded = app_config.load_simple_yaml(path)
            restored = LanternBotConfig.from_mapping(loaded["lantern_bot"])
            self.assertEqual(restored.lan_access.provider_mode, "whitelist")
            self.assertEqual(restored.lan_access.providers, ("cliproxy-*",))
            self.assertEqual(restored.lan_access.model_mode, "blacklist")
            self.assertEqual(restored.lan_access.models, ("cliproxy-2080/claude-*",))
            self.assertTrue(restored.lan_access.lock_model)
            self.assertEqual(restored.max_tokens_per_day, 12345)
            self.assertEqual(restored.greeting, "HELLO")
            self.assertEqual(restored.system_prompt, "SYSTEM\nLINE2")


if __name__ == "__main__":
    unittest.main()
