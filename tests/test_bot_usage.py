from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lantern.bot_usage import LanternBotUsage


class LanternBotUsageTests(unittest.TestCase):
    def test_prompt_and_token_limits_are_persistent(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "usage.json"
            usage = LanternBotUsage(path)
            usage.assert_prompt_allowed(max_prompts=2, max_tokens=100)
            usage.record_prompt()
            usage.record_tokens(60)

            reopened = LanternBotUsage(path)
            self.assertEqual(reopened.snapshot()["prompts"], 1)
            self.assertEqual(reopened.snapshot()["tokens"], 60)
            reopened.record_prompt()
            with self.assertRaisesRegex(RuntimeError, "prompt limit"):
                reopened.assert_prompt_allowed(max_prompts=2, max_tokens=100)

    def test_token_limit_blocks_following_prompt(self):
        with tempfile.TemporaryDirectory() as td:
            usage = LanternBotUsage(Path(td) / "usage.json")
            usage.record_tokens(101)
            with self.assertRaisesRegex(RuntimeError, "token limit"):
                usage.assert_prompt_allowed(max_prompts=None, max_tokens=100)


if __name__ == "__main__":
    unittest.main()
