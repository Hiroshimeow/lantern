"""Password-only protection for remote Terminal WebSocket operations.

No auth database: one salted password hash in local YAML and expiring in-memory
browser sessions. The filesystem/Git browser remains under its existing rules.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import ipaddress
import os
import secrets
import tempfile
import threading
import time
from collections import deque
from http.cookies import SimpleCookie
from pathlib import Path

COOKIE = "lantern_terminal"
ITERATIONS = 400_000
SESSION_SECONDS = 8 * 60 * 60
FAIL_WINDOW = 5 * 60
MAX_FAILURES = 5


def hash_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 12 or len(password) > 1024:
        raise ValueError("Terminal password must contain 12-1024 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    b64 = lambda data: base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")
    return f"pbkdf2_sha256${ITERATIONS}${b64(salt)}${b64(digest)}"


def password_matches(password: str, encoded: str) -> bool:
    try:
        kind, count, salt, stored = encoded.split("$")
        if kind != "pbkdf2_sha256" or not (300_000 <= int(count) <= 2_000_000):
            return False
        decode = lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        salt_bytes, expected = decode(salt), decode(stored)
        if len(salt_bytes) != 16 or len(expected) != 32:
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                        salt_bytes, int(count))
        return hmac.compare_digest(candidate, expected)
    except (AttributeError, TypeError, ValueError, binascii.Error):
        return False


def update_password_yaml(config: Path, encoded: str) -> None:
    """Edit only the hash field; preserve machine config and comments."""
    if encoded.strip().casefold() not in {"", "no-password"} and not encoded.startswith("pbkdf2_sha256$"):
        raise ValueError("Invalid password hash")
    config = Path(config).resolve()
    config.parent.mkdir(parents=True, exist_ok=True)
    current = config.read_text(encoding="utf-8") if config.exists() else ""
    lines = [line for line in current.splitlines()
             if line.split(":", 1)[0].strip() != "terminal_password_hash"]
    lines.append(f'terminal_password_hash: "{encoded}"')
    contents = "\n".join(lines) + "\n"
    fd, name = tempfile.mkstemp(prefix=".lantern-password-", dir=str(config.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            os.chmod(name, 0o600)
        os.replace(name, config)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _token_from_cookie(header: str) -> str:
    if not header or len(header) > 4096:
        return ""
    try:
        cookie = SimpleCookie()
        cookie.load(header)
        item = cookie.get(COOKIE)
        token = item.value if item else ""
        return token if 40 <= len(token) <= 100 else ""
    except Exception:
        return ""


class TerminalAccess:
    def __init__(self, password_hash: str, *, local_bypass: bool = True):
        self._hash = password_hash if isinstance(password_hash, str) else ""
        self.local_bypass = local_bypass
        self.sessions: dict[str, tuple[float, str]] = {}
        self.attempts: dict[str, deque[float]] = {}
        self.lock = threading.RLock()

    @property
    def configured(self) -> bool:
        return self._hash.startswith("pbkdf2_sha256$") and self._hash.count("$") == 3

    @property
    def passwordless(self) -> bool:
        return self._hash.strip().casefold() in {"", "no-password"}

    def required(self, client_ip: str) -> bool:
        # Explicit opt-in: no configured password means no Terminal login,
        # including LAN/Tailscale; malformed hashes still fail closed.
        if self.passwordless:
            return False
        if not self.local_bypass:
            return True
        try:
            return not ipaddress.ip_address(client_ip).is_loopback
        except ValueError:
            return True

    def permitted(self, client_ip: str, cookie_header: str) -> bool:
        if not self.required(client_ip):
            return True
        token = _token_from_cookie(cookie_header)
        if not token:
            return False
        digest = hashlib.sha256(token.encode("ascii", "ignore")).hexdigest()
        with self.lock:
            entry = self.sessions.get(digest)
            if not entry:
                return False
            expiry, binding = entry
            if expiry <= time.time():
                self.sessions.pop(digest, None)
                return False
            return hmac.compare_digest(binding, client_ip)

    def login(self, client_ip: str, password: str) -> tuple[int, str]:
        if not self.configured:
            return 503, ""
        now = time.monotonic()
        with self.lock:
            failures = self.attempts.setdefault(client_ip, deque(maxlen=MAX_FAILURES))
            while failures and now - failures[0] > FAIL_WINDOW:
                failures.popleft()
            if len(failures) >= MAX_FAILURES:
                return 429, ""
            if not isinstance(password, str) or not password_matches(password, self._hash):
                failures.append(now)
                return 401, ""
            self.attempts.pop(client_ip, None)
            token = secrets.token_urlsafe(32)
            digest = hashlib.sha256(token.encode("ascii")).hexdigest()
            self.sessions[digest] = (time.time() + SESSION_SECONDS, client_ip)
            return 200, token

    def logout(self, token: str) -> None:
        if not token:
            return
        digest = hashlib.sha256(token.encode("ascii", "ignore")).hexdigest()
        with self.lock:
            self.sessions.pop(digest, None)

    @staticmethod
    def cookie_header(token: str, *, secure: bool) -> str:
        flags = "; Secure" if secure else ""
        return f"{COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_SECONDS}{flags}"

    @staticmethod
    def clear_cookie(*, secure: bool) -> str:
        flags = "; Secure" if secure else ""
        return f"{COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0{flags}"

    @staticmethod
    def cookie_token(header: str) -> str:
        return _token_from_cookie(header)
