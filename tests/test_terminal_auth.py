"""Terminal-only password authentication; no access to the live 9999 service."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from lantern_terminal_auth import TerminalAccess, hash_password, password_matches, update_password_yaml
from lantern_ws import WebSocketHub, dispatch, _terminal_error_reply
import lan_drive


class TerminalPasswordTests(unittest.TestCase):
    def test_hash_and_config_do_not_store_plaintext(self):
        secret = "a-local-only-long-password"
        encoded = hash_password(secret)
        self.assertTrue(encoded.startswith("pbkdf2_sha256$"))
        self.assertNotIn(secret, encoded)
        self.assertTrue(password_matches(secret, encoded))
        self.assertFalse(password_matches("incorrect-password", encoded))
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "lan_drive_config.yaml"
            config.write_text('root: "C:/somewhere"\nport: 9999\n# keep comment\n', encoding="utf-8")
            update_password_yaml(config, encoded)
            text = config.read_text(encoding="utf-8")
            self.assertIn("terminal_password_hash:", text)
            self.assertIn("keep comment", text)
            self.assertIn("root:", text)
            self.assertNotIn(secret, text)
            update_password_yaml(config, hash_password("replacement-password"))
            self.assertEqual(text.count("terminal_password_hash:"), 1)
            self.assertEqual(config.read_text(encoding="utf-8").count("terminal_password_hash:"), 1)

    def test_local_cli_setup_writes_yaml_without_starting_server(self):
        import sys
        with tempfile.TemporaryDirectory() as temp:
            config=Path(temp)/"lan_drive_config.yaml"
            config.write_text('root: "D:/Test"\nport: 9999\n',encoding="utf-8")
            with patch.object(sys,"argv",["lan_drive.py","--config",str(config),
                                          "--set-terminal-password"]):
                with patch("lan_drive.getpass.getpass",side_effect=[
                    "cli-generated-long-password","cli-generated-long-password"]):
                    lan_drive.main()
            data=lan_drive.load_simple_yaml(config)
            self.assertTrue(password_matches(
                "cli-generated-long-password",data["terminal_password_hash"]))
            self.assertEqual(data["port"],9999)

    def test_remote_denied_without_password_and_local_bypass_uses_peer_not_host(self):
        auth = TerminalAccess("", local_bypass=True)
        self.assertFalse(auth.required("::1"))
        self.assertFalse(auth.required("127.0.0.1"))
        self.assertTrue(auth.permitted("127.0.0.1", ""))
        self.assertTrue(auth.required("100.99.88.77"))
        self.assertFalse(auth.permitted("100.99.88.77", "lantern_terminal=attacker"))
        self.assertFalse(auth.permitted("192.168.1.33", ""))
        forced = TerminalAccess(hash_password("password-example"), local_bypass=False)
        self.assertTrue(forced.required("127.0.0.1"))
        self.assertFalse(forced.permitted("127.0.0.1", ""))

    def test_remote_login_cookie_expiry_logout_and_rate_limit(self):
        auth = TerminalAccess(hash_password("correct-password-long"), local_bypass=True)
        remote = "100.120.121.122"
        self.assertEqual(auth.login(remote, "wrong")[0], 401)
        code, token = auth.login(remote, "correct-password-long")
        self.assertEqual(code, 200)
        cookie = "lantern_terminal=" + token
        self.assertTrue(auth.permitted(remote, cookie))
        self.assertFalse(auth.permitted("100.120.121.123", cookie))
        self.assertFalse(auth.permitted(remote, cookie + "extra"))
        header = auth.cookie_header(token, secure=True)
        self.assertIn("HttpOnly", header)
        self.assertIn("SameSite=Strict", header)
        self.assertIn("Secure", header)
        auth.logout(token)
        self.assertFalse(auth.permitted(remote, cookie))
        for _ in range(5):
            auth.login(remote, "wrong")
        self.assertEqual(auth.login(remote, "correct-password-long")[0], 429)

    def test_expired_session_gets_distinct_reauthentication_response(self):
        reply = _terminal_error_reply(
            {"type": "terminal_run", "terminalId": "old"},
            PermissionError("Terminal locked: login required"))
        self.assertEqual(reply["code"], "terminal_auth_required")
        self.assertEqual(reply["terminalId"], "old")

    def test_dispatch_and_broadcast_never_expose_terminal_to_remote(self):
        class Peer:
            def __init__(self):
                self.messages = []
                self.can_terminal = lambda: False
                self.protocol = "legacy"
                self.subscriptions = set()
            def send(self, message):
                self.messages.append(message)
        class Terminal:
            def list(self):
                raise AssertionError("Terminal metadata must not be read")
            def create(self, *_args):
                raise AssertionError("PTY must not be created")
        peer = Peer()
        for typ in ("terminal_sync", "terminal_client_v2", "terminal_create", "terminal_run",
                    "terminal_input", "terminal_subscribe", "terminal_kill", "terminal_key"):
            with self.assertRaises(PermissionError, msg=typ):
                dispatch(peer, {"type": typ, "terminalId": "victim"}, Terminal(), None)
        hub = WebSocketHub()
        hub.add(peer)
        for typ in ("terminal_list", "terminal_snapshot", "terminal_output", "terminal_exit"):
            hub.broadcast({"type": typ, "terminalId": "victim", "data": "PRIVATE PTY OUTPUT"})
        self.assertEqual(peer.messages, [])
        self.assertEqual(peer.subscriptions, set())
        # Non-terminal SCM viewing stays available, no new Git write endpoints.
        class Scm:
            def query(self, *_args):
                return {"branch": "main"}
        dispatch(peer, {"type": "scm_status", "reqId": "1", "cwd": ""}, Terminal(), Scm())
        self.assertEqual(peer.messages[0]["type"], "scm_data")


class ConfigProtectionTests(unittest.TestCase):
    def test_web_config_does_not_expose_password_hash_and_paths_are_hidden(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            path = root / "lan_drive_config.yaml"
            path.write_text("terminal_password_hash: \"secret-hash\"\n", encoding="utf-8")
            config = SimpleNamespace(root=root, config_path=path, show_hidden=True)
            with patch.object(lan_drive, "CONFIG", config, create=True):
                with self.assertRaises(PermissionError):
                    lan_drive.safe_join("/lan_drive_config.yaml")
                with self.assertRaises(PermissionError):
                    lan_drive.ensure_under_root(path)
                self.assertTrue(lan_drive.should_hide_entry(root, "lan_drive_config.yaml"))

    def test_parent_folder_copy_and_recursive_overwrite_cannot_expose_config(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve()
            parent=root/"app"
            parent.mkdir()
            config_path=parent/"lan_drive_config.yaml"
            config_path.write_text("terminal_password_hash: secret\n",encoding="utf-8")
            destination=root/"copies"
            destination.mkdir()
            cfg=SimpleNamespace(root=root,config_path=config_path,show_hidden=True)
            with patch.object(lan_drive,"CONFIG",cfg,create=True):
                with self.assertRaises(PermissionError):
                    lan_drive.copy_item(parent,destination,conflict="rename")
                self.assertFalse((destination/"app").exists())
                with self.assertRaises(PermissionError):
                    lan_drive.remove_existing_target(parent)
                self.assertTrue(config_path.exists())


if __name__ == "__main__":
    unittest.main()
