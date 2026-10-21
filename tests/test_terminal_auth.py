"""Terminal-only password authentication; no access to the live 9999 service."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from lantern.terminal_auth import TerminalAccess, hash_password, password_matches, update_password_yaml
from lantern.ws import WebSocketHub, dispatch, _terminal_error_reply
from lantern import config as app_config
from lantern import application
from lantern.filesystem import FileService


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

    def test_passwordless_config_values_do_not_require_remote_terminal_login(self):
        for value in ("", "no-password", " NO-PASSWORD "):
            for bypass in (True, False):
                with self.subTest(value=value, local_bypass=bypass):
                    access = TerminalAccess(value, local_bypass=bypass)
                    self.assertFalse(access.configured)
                    self.assertFalse(access.required("100.99.88.77"))
                    self.assertTrue(access.permitted("100.99.88.77", ""))

    def test_invalid_hash_does_not_silently_disable_auth(self):
        access = TerminalAccess("invalid-hash", local_bypass=True)
        self.assertTrue(access.required("100.99.88.77"))
        self.assertFalse(access.permitted("100.99.88.77", ""))
        self.assertFalse(access.configured)

    def test_cli_empty_password_disables_auth_and_preserves_yaml(self):
        import sys
        with tempfile.TemporaryDirectory() as temp:
            config=Path(temp)/"lan_drive_config.yaml"
            config.write_text(
                'root: "D:/Test"\nport: 9999\n# preserve comment\n'
                'terminal_password_hash: "' + hash_password("old-long-password") + '"\n',
                encoding="utf-8")
            with patch.object(sys, "argv", ["main.py", "--config", str(config),
                                             "--set-terminal-password"]):
                with patch("lantern.application.getpass.getpass", side_effect=["", ""]):
                    application.main()
            data=app_config.load_simple_yaml(config)
            self.assertEqual(data["terminal_password_hash"], "")
            self.assertIn("# preserve comment", config.read_text(encoding="utf-8"))
            self.assertFalse(TerminalAccess(data["terminal_password_hash"]).required("100.99.88.77"))

    def test_yaml_explicit_no_password_value_is_supported(self):
        with tempfile.TemporaryDirectory() as temp:
            config=Path(temp)/"lan_drive_config.yaml"
            update_password_yaml(config, "no-password")
            self.assertIn('terminal_password_hash: "no-password"',
                          config.read_text(encoding="utf-8"))
            self.assertFalse(TerminalAccess(app_config.load_simple_yaml(config)["terminal_password_hash"])
                             .required("192.168.0.50"))

    def test_local_cli_setup_writes_yaml_without_starting_server(self):
        import sys
        with tempfile.TemporaryDirectory() as temp:
            config=Path(temp)/"lan_drive_config.yaml"
            config.write_text('root: "D:/Test"\nport: 9999\n',encoding="utf-8")
            with patch.object(sys,"argv",["main.py","--config",str(config),
                                          "--set-terminal-password"]):
                with patch("lantern.application.getpass.getpass",side_effect=[
                    "cli-generated-long-password","cli-generated-long-password"]):
                    application.main()
            data=app_config.load_simple_yaml(config)
            self.assertTrue(password_matches(
                "cli-generated-long-password",data["terminal_password_hash"]))
            self.assertEqual(data["port"],9999)

    def test_password_enabled_still_gates_remote_and_uses_peer_address(self):
        auth = TerminalAccess(hash_password("local-remote-long-password"), local_bypass=True)
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


    def test_lock_unlock_lan_password_requirement_and_passwordless_lock(self):
        """Verify v7.8 Lock/Unlock LAN behavior:
        1. Unlock LAN -> removes password requirement even when YAML has password.
        2. Lock LAN -> revokes old sessions and requires password.
        3. Valid login after Lock -> permitted to use Terminal/bot.
        4. Locking again revokes the previous login cookie.
        5. Lock when no password is configured -> does NOT allow anonymous access.
        """
        pw_hash = hash_password("correct-horse-battery-staple")
        auth = TerminalAccess(pw_hash, local_bypass=True)
        lan_ip = "192.168.1.50"

        # Initially locked because password is configured
        self.assertTrue(auth.required(lan_ip))
        self.assertFalse(auth.permitted(lan_ip, ""))

        # 1. Unlock LAN (hard_lock=False) -> LAN can access immediately without password
        auth.revoke_all_lan(hard_lock=False)
        self.assertFalse(auth.lan_locked)
        self.assertFalse(auth.required(lan_ip))
        self.assertTrue(auth.permitted(lan_ip, ""))

        # 2. Lock LAN (hard_lock=True) -> requires password
        auth.revoke_all_lan(hard_lock=True)
        self.assertTrue(auth.lan_locked)
        self.assertTrue(auth.required(lan_ip))
        self.assertFalse(auth.permitted(lan_ip, ""))

        # 3. Valid login after Lock succeeds and cookie is permitted
        code, tok = auth.login(lan_ip, "correct-horse-battery-staple")
        self.assertEqual(code, 200)
        cookie = f"lantern_terminal={tok}"
        self.assertTrue(auth.permitted(lan_ip, cookie))

        # 4. Locking again revokes the previous cookie
        revoked = auth.revoke_all_lan(hard_lock=True)
        self.assertEqual(revoked, 1)
        self.assertFalse(auth.permitted(lan_ip, cookie))

        # 5. Lock when no password is configured -> must NOT allow anonymous access
        no_pwd_auth = TerminalAccess("", local_bypass=True)
        self.assertFalse(no_pwd_auth.required(lan_ip))
        self.assertTrue(no_pwd_auth.permitted(lan_ip, ""))
        no_pwd_auth.revoke_all_lan(hard_lock=True)
        self.assertTrue(no_pwd_auth.lan_locked)
        self.assertTrue(no_pwd_auth.required(lan_ip))
        self.assertFalse(no_pwd_auth.permitted(lan_ip, ""))
        self.assertEqual(no_pwd_auth.login(lan_ip, "anything")[0], 503)


class ConfigProtectionTests(unittest.TestCase):
    def test_web_config_does_not_expose_password_hash_and_paths_are_hidden(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            path = root / "lan_drive_config.yaml"
            path.write_text("terminal_password_hash: \"secret-hash\"\n", encoding="utf-8")
            config = SimpleNamespace(root=root, config_path=path, show_hidden=True)
            files=FileService(config, None)
            with self.assertRaises(PermissionError):
                files.safe_join("/lan_drive_config.yaml")
            with self.assertRaises(PermissionError):
                files.ensure_under_root(path)
            self.assertTrue(files.should_hide_entry(root, "lan_drive_config.yaml"))

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
            files=FileService(cfg, None)
            with self.assertRaises(PermissionError):
                files.copy_item(parent,destination,conflict="rename")
            self.assertFalse((destination/"app").exists())
            with self.assertRaises(PermissionError):
                files.remove_existing_target(parent)
            self.assertTrue(config_path.exists())


if __name__ == "__main__":
    unittest.main()
