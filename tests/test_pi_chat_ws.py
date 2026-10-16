from __future__ import annotations

import unittest

from lantern.ws import WebSocketHub, dispatch, _terminal_error_reply


class Peer:
    def __init__(self, allowed=True):
        self.messages = []
        self.can_terminal = lambda: allowed
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

    def get_state(self):
        return {"sessionId": "session-1", "model": {"provider": "p", "id": "m"}}

    def summary(self):
        return {"running": True, "streaming": False, "sessionId": "session-1",
                "model": {"provider": "p", "id": "m"}, "terminalId": "pi_chat"}

    def available_models(self):
        return [{"provider": "p", "id": "m", "name": "m"}]

    def get_messages(self):
        return [{"role": "assistant", "content": "hello"}]

    def prompt(self, message, context, draft=None):
        self.prompts.append((message, context, draft))
        return {"success": True}

    def new_session(self):
        self.new_count += 1
        return {"sessionId": "session-new"}

    def abort(self):
        self.aborted += 1
        return {"success": True}

    def set_model(self, provider, model_id):
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
        hub.broadcast({"type": "chat_pi_event", "event": {"type": "message_update"}})
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

    def test_chat_prompt_forwards_markdown_draft_payload(self):
        peer = Peer()
        chat = FakeChat()
        draft = {
            "promptId": "chat-1",
            "baseVersion": "a" * 64,
            "draftRevision": 4,
            "text": "# Draft\n",
        }
        context = {"kind": "markdown", "path": "doc.md", "markdownMode": "source"}
        dispatch(
            peer,
            {"type": "chat_prompt", "reqId": "chat-1", "message": "edit",
             "context": context, "draft": draft},
            object(), None, chat=chat,
        )
        self.assertEqual(chat.prompts, [("edit", context, draft)])
        self.assertEqual(peer.messages[-1],
                         {"type": "chat_prompt_accepted", "reqId": "chat-1"})

    def test_missing_chat_manager_fails_closed(self):
        peer = Peer()
        with self.assertRaisesRegex(RuntimeError, "not initialized"):
            dispatch(peer, {"type": "chat_sync"}, object(), None, chat=None)


if __name__ == "__main__":
    unittest.main()
