from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import os
import queue
import socket
import struct
import threading
import urllib.parse
from typing import Any, Dict

_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_MAX_FRAME = 2 * 1024 * 1024
_MAX_QUEUED_BYTES = 8 * 1024 * 1024
_MAX_ACTIVE_REPLAY_CHARS = 800_000  # worst-case JSON escapes stay below peer queue budget


class PiSessionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PiSessionPermissionError(PermissionError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _frame(opcode: int, payload: bytes = b"") -> bytes:
    head = bytearray([0x80 | opcode])
    n = len(payload)
    if n < 126:
        head.append(n)
    elif n <= 0xFFFF:
        head.append(126)
        head.extend(struct.pack("!H", n))
    else:
        head.append(127)
        head.extend(struct.pack("!Q", n))
    return bytes(head) + payload


class WebSocketPeer:
    def __init__(self, handler) -> None:
        self.rfile, self.wfile = handler.rfile, handler.wfile
        self.connection = getattr(handler, "connection", None)
        if self.connection is not None and os.name == "nt":
            try:
                # A dead/paused browser can leave SocketIO.send() blocked even
                # after shutdown() from another thread. Bound one outbound send
                # so the per-peer writer can always terminate and reconnect.
                self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDTIMEO, 1500)
            except Exception:
                pass
        self.closed = False
        self.subscriptions: set[str] = set()
        self.protocol = "pending"  # v2 opt-in; stale browser tabs get legacy fallback
        self._send_q: "queue.Queue[bytes | None]" = queue.Queue()
        self._queue_lock = threading.Lock()
        self._pi_notice_lock = threading.RLock()
        self._queued_bytes = 0
        self._writer = threading.Thread(target=self._writer_loop, name=f"ws-writer-{id(self)}", daemon=True)
        self._writer.start()

    def send(self, payload: Dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._enqueue(_frame(0x1, raw))

    def _enqueue(self, frame: bytes) -> None:
        overflow = False
        with self._queue_lock:
            if self.closed:
                raise ConnectionError("websocket closed")
            if self._queued_bytes + len(frame) > _MAX_QUEUED_BYTES:
                self.closed = True
                overflow = True
            else:
                self._queued_bytes += len(frame)
        if overflow:
            # A shutdown does not guarantee a writer that is between writes
            # will fail on its next write. Queue an explicit stop marker so it
            # cannot drain the backlog and then sleep forever on queue.get().
            self._send_q.put(None)
            self._abort_socket()
            raise ConnectionError("websocket send queue exceeded 8 MiB")
        self._send_q.put(frame)

    def _writer_loop(self) -> None:
        try:
            while True:
                first = self._send_q.get()
                if first is None:
                    return
                chunks = [first]
                total = len(first)
                stop_after_write = False
                while total < 256 * 1024:
                    try:
                        nxt = self._send_q.get_nowait()
                    except queue.Empty:
                        break
                    if nxt is None:
                        stop_after_write = True
                        break
                    chunks.append(nxt)
                    total += len(nxt)
                blob = b"".join(chunks)
                try:
                    self.wfile.write(blob)
                    self.wfile.flush()
                finally:
                    with self._queue_lock:
                        self._queued_bytes = max(0, self._queued_bytes - len(blob))
                if stop_after_write:
                    return
        except Exception:
            with self._queue_lock:
                self.closed = True
            self._abort_socket()

    def _abort_socket(self) -> None:
        if self.connection is None:
            return
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass

    def recv(self):
        while not self.closed:
            head = self.rfile.read(2)
            if len(head) != 2:
                return None
            b1, b2 = head
            opcode = b1 & 15
            length = b2 & 127
            if not (b1 & 128):
                raise ValueError("fragmented frames unsupported")
            if length == 126:
                length = struct.unpack("!H", self.rfile.read(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self.rfile.read(8))[0]
            if length > _MAX_FRAME:
                raise ValueError("frame too large")
            if not (b2 & 128):
                raise ValueError("client frames must be masked")
            mask = self.rfile.read(4)
            payload = self.rfile.read(length)
            if len(mask) != 4 or len(payload) != length:
                return None
            payload = bytes(value ^ mask[index & 3] for index, value in enumerate(payload))
            if opcode == 8:
                try:
                    self._enqueue(_frame(0x8, payload[:125]))
                except Exception:
                    pass
                return None
            if opcode == 9:
                self._enqueue(_frame(0xA, payload[:125]))
                continue
            if opcode == 1:
                return payload.decode("utf-8", "replace")
        return None

    def close(self) -> None:
        with self._queue_lock:
            if self.closed:
                return
            self.closed = True
        self._send_q.put(None)
        self._abort_socket()


class WebSocketHub:
    def __init__(self):
        self.peers = set()
        self.lock = threading.Lock()
        self.pi_routes: dict[str, dict[str, Any]] = {}
        self.pi_peer_session: dict[Any, str] = {}
        self.pi_peer_attach_token: dict[Any, object] = {}

    def add(self, peer):
        with self.lock:
            self.peers.add(peer)

    def remove(self, peer):
        notices = []
        with self.lock:
            send_lock = getattr(peer, "_pi_notice_lock", None)
            if send_lock is None:
                send_lock = threading.RLock()
                peer._pi_notice_lock = send_lock
        with send_lock:
            with self.lock:
                self.peers.discard(peer)
