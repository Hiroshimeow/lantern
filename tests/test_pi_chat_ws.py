from __future__ import annotations

import unittest

from lantern.ws import WebSocketHub, dispatch, _terminal_error_reply


class Peer:
    def __init__(self, allowed=True, client_ip="127.0.0.1"):
        self.messages = []
        self.can_terminal = lambda: allowed
        self.client_ip = client_ip
        self.protocol = "v2"
        self.subscriptions = set()

    def send(self, message):
        self.messages.append(message)


class FakeChat:
    def __init__(self):
        self.prompts = []
        self.models_set = []
        self.aborted = 0
        self.new_count = 0
        self.scope_calls = []

    def get_state(self):
        return {"sessionId": "session-1", "model": {"provider": "p", "id": "m"}}

    def bootstrap_state(self, scope="local"):
        self.scope_calls.append(("bootstrap", scope))
        return self.get_state()

    def summary(self, scope="local"):
        self.scope_calls.append(("summary", scope))
        return {"running": True, "streaming": False, "sessionId": "session-1",
                "model": {"provider": "p", "id": "m"}, "terminalId": "lantern_bot",
                "name": "LanternBot",
                "policy": {"enabled": True, "greeting": "hello"},
                "usage": {"date": "2026-10-16", "prompts": 0, "tokens": 0}}

    def available_models(self, scope="local"):
        self.scope_calls.append(("models", scope))
        return [{"provider": "p", "id": "m", "name": "m"}]

    def get_messages(self):
        return [{"role": "assistant", "content": "hello"}]

    def prompt(self, message, context, work_hash=None, scope="local"):
        self.scope_calls.append(("prompt", scope))
        self.prompts.append((message, context, work_hash))
        return {"success": True}

    def new_session(self, scope="local"):
        self.scope_calls.append(("new", scope))
        self.new_count += 1
        return {"sessionId": "session-new"}

    def abort(self):
        self.aborted += 1
        return {"success": True}

    def set_model(self, provider, model_id, scope="local"):
        self.scope_calls.append(("set_model", scope))
        self.models_set.append((provider, model_id))
        return {"success": True}


class PiChatWebSocketTests(unittest.TestCase):
    def test_chat_commands_use_terminal_access_gate(self):
        peer = Peer(allowed=False)
        chat = FakeChat()
        for typ in ("chat_sync", "chat_prompt", "chat_new", "chat_abort", "chat_set_model"):
            msg = {"type": typ, "message": "hi", "provider": "p", "modelId": "m"}
            with self.assertRaises(PermissionError, msg=typ):
                dispatch(peer, msg, object(), None, chat=chat)

        reply = _terminal_error_reply(
            {"type": "chat_prompt"},
            PermissionError("Terminal locked: login required"),
        )
        self.assertEqual(reply["type"], "chat_error")
        self.assertEqual(reply["code"], "terminal_auth_required")

    def test_chat_broadcast_is_hidden_from_locked_peers(self):
        hub = WebSocketHub()
        locked = Peer(allowed=False)
        allowed = Peer(allowed=True)
        hub.add(locked)
        hub.add(allowed)
        hub.broadcast({"type": "chat_bot_event", "event": {"type": "message_update"}})
        self.assertEqual(locked.messages, [])
        self.assertEqual(len(allowed.messages), 1)

    def test_chat_sync_returns_state_models_and_history(self):
        peer = Peer()
        chat = FakeChat()
        dispatch(peer, {"type": "chat_sync"}, object(), None, chat=chat)
        self.assertEqual(peer.messages[0]["type"], "chat_state")
        self.assertEqual(peer.messages[0]["state"]["sessionId"], "session-1")
        self.assertEqual(peer.messages[0]["models"][0]["id"], "m")
        self.assertEqual(peer.messages[0]["messages"][0]["content"], "hello")

    def test_chat_scope_comes_from_websocket_client_ip(self):
        local = Peer(client_ip="127.0.0.1")
        lan = Peer(client_ip="192.168.1.55")
        chat = FakeChat()

        dispatch(local, {"type": "chat_sync"}, object(), None, chat=chat)
        self.assertIn(("bootstrap", "local"), chat.scope_calls)
        self.assertIn(("models", "local"), chat.scope_calls)

        chat.scope_calls.clear()
        dispatch(lan, {"type": "chat_sync"}, object(), None, chat=chat)
        self.assertIn(("bootstrap", "lan"), chat.scope_calls)
        self.assertIn(("summary", "lan"), chat.scope_calls)
        self.assertIn(("models", "lan"), chat.scope_calls)

        chat.scope_calls.clear()
        dispatch(
            lan,
            {"type": "chat_prompt", "reqId": "lan-1", "message": "hello"},
            object(), None, chat=chat,
        )
        self.assertIn(("prompt", "lan"), chat.scope_calls)

    def test_chat_prompt_and_controls(self):
        peer = Peer()
        chat = FakeChat()
        dispatch(
            peer,
            {"type": "chat_prompt", "reqId": "r1", "message": "fix",
             "context": {"kind": "file", "path": "a.txt"}},
            object(), None, chat=chat,
        )
        self.assertEqual(chat.prompts, [("fix", {"kind": "file", "path": "a.txt"}, None)])
        self.assertEqual(peer.messages[-1], {"type": "chat_prompt_accepted", "reqId": "r1"})

        dispatch(peer, {"type": "chat_set_model", "provider": "p", "modelId": "x"},
                 object(), None, chat=chat)
        self.assertEqual(chat.models_set, [("p", "x")])

        dispatch(peer, {"type": "chat_abort"}, object(), None, chat=chat)
        self.assertEqual(chat.aborted, 1)

        dispatch(peer, {"type": "chat_new"}, object(), None, chat=chat)
        self.assertEqual(chat.new_count, 1)
        self.assertEqual(peer.messages[-1]["type"], "chat_state")
        self.assertEqual(peer.messages[-1]["state"]["sessionId"], "session-new")

    def test_chat_prompt_forwards_markdown_work_hash_only(self):
        peer = Peer()
        chat = FakeChat()
        work_hash = "a" * 64
        context = {"kind": "markdown", "path": "doc.md", "markdownMode": "source"}
        dispatch(
            peer,
            {"type": "chat_prompt", "reqId": "chat-1", "message": "edit",
             "context": context, "workHash": work_hash},
            object(), None, chat=chat,
        )
        self.assertEqual(chat.prompts, [("edit", context, work_hash)])
        self.assertEqual(peer.messages[-1],
                         {"type": "chat_prompt_accepted", "reqId": "chat-1"})

    def test_lan_direct_ws_model_override_is_rejected_by_real_manager(self):
        # The transport must derive scope from the peer IP. Supplying a
        # forged 'scope: local' in a crafted websocket message cannot bypass it.
        import sys
        import tempfile
        from pathlib import Path
        from lantern.bot_config import LanternBotConfig
        from lantern.pi_chat import LanternBotManager
        from lantern.working_copy import WorkingCopyStore

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "files"
            root.mkdir()
            fake = Path(__file__).with_name("fake_pi_rpc.py")
            policy = LanternBotConfig.from_mapping({
                "access": {
                    "localhost": {"provider_mode": "all", "model_mode": "all"},
                    "lan": {
                        "provider_mode": "whitelist",
                        "providers": ["fake"],
                        "model_mode": "whitelist",
                        "models": ["fake/gpt-6.1-sol"],
                        "selection": {
                            "provider": "fake", "model": "gpt-6.1-sol",
                            "lock_provider": True, "lock_model": True,
                        },
                    },
                },
            })
            manager = LanternBotManager(
                root, lambda _event: None,
                work_store=WorkingCopyStore(root, Path(tmp) / "work", {".md"}),
                session_dir=Path(tmp) / "sessions",
                argv_override=[sys.executable, "-u", str(fake)],
                request_timeout=3,
                usage_path=Path(tmp) / "usage.json",
                bot_config=policy,
            )
            local = Peer(client_ip="127.0.0.1")
            lan = Peer(client_ip="192.168.0.42")
            try:
                dispatch(local, {"type": "chat_sync"}, object(), None, chat=manager)
                self.assertEqual(len(local.messages[-1]["models"]), 6)
                dispatch(lan, {"type": "chat_sync"}, object(), None, chat=manager)
                self.assertEqual([m["id"] for m in lan.messages[-1]["models"]],
                                 ["gpt-6.1-sol"])
                with self.assertRaises(PermissionError):
                    dispatch(lan, {
                        "type": "chat_set_model",
                        "provider": "fake", "modelId": "claude-opus-5-5-high",
                        "scope": "local",
                    }, object(), None, chat=manager)
                self.assertEqual(manager.get_state()["model"]["id"], "gpt-6.1-sol")
                dispatch(local, {
                    "type": "chat_set_model",
                    "provider": "fake", "modelId": "claude-opus-5-5-high",
                }, object(), None, chat=manager)
                self.assertEqual(manager.get_state()["model"]["id"], "claude-opus-5-5-high")
                # LAN admission cannot inherit a model selected on localhost.
                dispatch(lan, {"type": "chat_sync"}, object(), None, chat=manager)
                self.assertEqual(lan.messages[-1]["state"]["model"]["id"], "gpt-6.1-sol")
            finally:
                manager.close()

    def test_missing_chat_manager_fails_closed(self):
        peer = Peer()
        with self.assertRaisesRegex(RuntimeError, "not initialized"):
            dispatch(peer, {"type": "chat_sync"}, object(), None, chat=None)


if __name__ == "__main__":
    unittest.main()
