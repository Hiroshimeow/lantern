from __future__ import annotations

import unittest

from lantern.bot_config import LanternBotConfig
import lan_drive


class LanternBotConfigTests(unittest.TestCase):
    def test_empty_config_inherits_native_selection_and_allows_inventory(self):
        cfg = LanternBotConfig.from_mapping({})
        self.assertEqual(cfg.provider, "")
        self.assertEqual(cfg.model, "")
        self.assertFalse(cfg.lock_provider)
        self.assertFalse(cfg.lock_model)
        self.assertTrue(cfg.allows_model("cliproxy_2080", "gpt-6.1-sol"))
        self.assertTrue(cfg.allows_model("github-copilot", "gpt-5"))

    def test_nested_policy_filters_models_and_bypass_wins(self):
        cfg = LanternBotConfig.from_mapping({
            "selection": {
                "provider": "github-copilot",
                "model": "gpt-5",
                "lock_provider": False,
                "lock_model": False,
            },
            "policy": {
                "allowed_providers": ["github-*"],
                "allowed_models": ["github-copilot/gpt-*"],
                "bypass_models": ["cliproxy_2080/claude-opus-*"],
                "max_prompts_per_day": 25,
                "max_tokens_per_day": 500_000,
            },
            "greeting": "LanternBot hello",
            "lantern_context": "SYSTEM",
        })
        self.assertTrue(cfg.allows_model("github-copilot", "gpt-5"))
        self.assertFalse(cfg.allows_model("github-copilot", "claude-sonnet"))
        self.assertTrue(cfg.allows_model("cliproxy_2080", "claude-opus-5-5"))
        self.assertFalse(cfg.allows_model("cliproxy_2080", "gpt-6.1-sol"))
        self.assertEqual(cfg.max_prompts_per_day, 25)
        self.assertEqual(cfg.max_tokens_per_day, 500_000)
        self.assertEqual(cfg.system_prompt, "SYSTEM")

    def test_locked_values_must_be_configured(self):
        with self.assertRaisesRegex(ValueError, "requires provider"):
            LanternBotConfig.from_mapping({"selection": {"lock_provider": True}})
        with self.assertRaisesRegex(ValueError, "requires model"):
            LanternBotConfig.from_mapping({"selection": {"lock_model": True}})

    def test_bare_model_pattern_matches_any_provider(self):
        cfg = LanternBotConfig.from_mapping({
            "policy": {"allowed_models": ["gpt-*"]}
        })
        self.assertTrue(cfg.allows_model("github-copilot", "gpt-5"))
        self.assertTrue(cfg.allows_model("cliproxy_2080", "gpt-6.1-sol"))
        self.assertFalse(cfg.allows_model("cliproxy_2080", "claude-opus-5-5"))


    def test_real_yaml_nested_config_roundtrips_without_flattening(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "lan_drive_config.yaml"
            path.write_text(
                """root: C:/root
port: 9999
lantern_bot:
  enabled: true
  selection:
    provider: github-copilot
    model: gpt-5
    lock_provider: false
    lock_model: false
  policy:
    allowed_models:
      - github-copilot/gpt-*
      - cliproxy_2080/claude-opus-*
    bypass_models:
      - cliproxy_2080/gpt-6.1-sol
    max_prompts_per_day: 10
  greeting: Hello
  lantern_context: |
    You are LanternBot.
    Keep context.
""",
                encoding="utf-8",
            )
            loaded = lan_drive.load_simple_yaml(path)
            cfg = LanternBotConfig.from_mapping(loaded["lantern_bot"])
            self.assertEqual(cfg.provider, "github-copilot")
            self.assertEqual(cfg.model, "gpt-5")
            self.assertEqual(cfg.max_prompts_per_day, 10)
            self.assertIn("Keep context.", cfg.system_prompt)
            self.assertTrue(cfg.allows_model("cliproxy_2080", "gpt-6.1-sol"))


    def test_write_config_file_preserves_nested_lanternbot_policy(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.yaml"
            bot = LanternBotConfig.from_mapping({
                "selection": {"provider": None, "model": None},
                "policy": {
                    "allowed_models": ["github-copilot/gpt-*"],
                    "bypass_models": ["cliproxy_2080/gpt-6.1-sol"],
                    "max_tokens_per_day": 12345,
                },
                "greeting": "HELLO",
                "lantern_context": "SYSTEM\nLINE2",
            })
            cfg = lan_drive.AppConfig(
                root=Path(td),
                port=9999,
                host="127.0.0.1",
                title="Lantern",
                cache_dir=Path(td) / "cache",
                config_path=path,
                lantern_bot=bot,
            )
            lan_drive.write_config_file(cfg)
            loaded = lan_drive.load_simple_yaml(path)
            restored = LanternBotConfig.from_mapping(loaded["lantern_bot"])
            self.assertEqual(restored.allowed_models, ("github-copilot/gpt-*",))
            self.assertEqual(restored.bypass_models, ("cliproxy_2080/gpt-6.1-sol",))
            self.assertEqual(restored.max_tokens_per_day, 12345)
            self.assertEqual(restored.greeting, "HELLO")
            self.assertEqual(restored.system_prompt, "SYSTEM\nLINE2")


if __name__ == "__main__":
    unittest.main()
