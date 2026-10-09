from __future__ import annotations

import base64
import hashlib
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

    def add(self, peer):
        with self.lock:
            self.peers.add(peer)

    def remove(self, peer):
        with self.lock:
            self.peers.discard(peer)
            peer.subscriptions.clear()

    def subscribe(self, peer, term_id: str):
        with self.lock:
            if peer in self.peers:
                # One active terminal subscription per LAN browser connection.
                # Prevent idle/background terminals accumulating on the same peer.
                peer.subscriptions.clear()
                peer.subscriptions.add(term_id)

    def unsubscribe(self, peer, term_id: str):
        with self.lock:
            peer.subscriptions.discard(term_id)

    def broadcast(self, message):
        with self.lock:
            peers = list(self.peers)
        for peer in peers:
            if (message.get("type") == "terminal_output" and getattr(peer, "protocol", "v2") != "legacy"
                    and message.get("terminalId") not in peer.subscriptions):
                continue
            try:
                peer.send(message)
            except Exception:
                self.remove(peer)
                peer.close()


def same_origin(handler):
    host = (handler.headers.get("Host") or "").strip().lower()
    origin = (handler.headers.get("Origin") or "").strip()
    if not host or not origin:
        return False
    try:
        parsed = urllib.parse.urlsplit(origin)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() == host


def _legacy_snapshot_payload(terminal):
    """Cap legacy UI tails so an older LAN tab cannot overflow one WebSocket frame.

    This never shortens the retained PTY history on the server.
    """
    output = dict(terminal.replay())
    truncated = any(len(s) > 20000 for s in output.values())
    return {"type": "terminal_snapshot", "terminals": terminal.list(),
            "output": {k: s[-20000:] for k, s in output.items()}}, truncated


def upgrade(handler, hub, terminal, scm):
    if not same_origin(handler):
        handler.send_error(403, "WebSocket Origin must match Host")
        return
    if (handler.headers.get("Upgrade") or "").lower() != "websocket":
        handler.send_error(400)
        return
    key = (handler.headers.get("Sec-WebSocket-Key") or "").strip()
    if not key or handler.headers.get("Sec-WebSocket-Version") != "13":
        handler.send_error(400)
        return
    try:
        decoded = base64.b64decode(key, validate=True)
    except Exception:
        handler.send_error(400)
        return
    if len(decoded) != 16:
        handler.send_error(400)
        return
    accept = base64.b64encode(hashlib.sha1((key + _WS_GUID).encode("ascii")).digest()).decode("ascii")
    try:
        handler.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception:
        pass
    handler.send_response(101)
    handler.send_header("Upgrade", "websocket")
    handler.send_header("Connection", "Upgrade")
    handler.send_header("Sec-WebSocket-Accept", accept)
    handler.end_headers()

    peer = WebSocketPeer(handler)
    # Explicit URL version avoids timer races when a LAN client is slow to send.
    if urllib.parse.parse_qs(urllib.parse.urlsplit(handler.path).query).get("v") == ["2"]:
        peer.protocol = "v2"
    def legacy_fallback() -> None:
        # Older LAN browser tabs reconnect without the v2 handshake. Preserve their
        # terminal view until those tabs reload the new JS. This path is temporary.
        with terminal.lock:
            if peer.closed or peer.protocol != "pending":
                return
            peer.protocol = "legacy"
            try:
                payload, truncated = _legacy_snapshot_payload(terminal)
                peer.send(payload)
                if truncated:
                    peer.send({"type": "terminal_error", "error":
                               "Older Lantern browser tab: history tail limited during reconnect; reload page for full replay."})
            except ConnectionError:
                peer.close()

    legacy_timer = threading.Timer(0.7, legacy_fallback)
    legacy_timer.daemon = True
    try:
        with terminal.lock:
            # Metadata first. New browsers request output only for their active tab.
            peer.send({"type": "terminal_list", "terminals": terminal.list()})
            hub.add(peer)
        legacy_timer.start()
        while True:
            raw = peer.recv()
            if raw is None:
                break
            try:
                dispatch(peer, json.loads(raw), terminal, scm, hub)
            except Exception as exc:
                try:
                    peer.send({"type": "terminal_error", "error": str(exc)})
                except Exception:
                    break
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
        pass
    finally:
        legacy_timer.cancel()
        hub.remove(peer)
        peer.close()


def dispatch(peer, msg, terminal, scm, hub=None):
    if not isinstance(msg, dict):
        raise ValueError("message must be an object")
    typ = str(msg.get("type") or "")
    if typ == "terminal_client_v2":
        peer.protocol = "v2"
        return
    if typ == "terminal_sync":
        peer.send({"type": "terminal_list", "terminals": terminal.list()})
        return
    if typ == "terminal_unsubscribe":
        if hub is not None:
            hub.unsubscribe(peer, str(msg.get("terminalId") or ""))
        return
    if typ == "terminal_subscribe":
        if hub is None:
            raise ValueError("Subscription hub unavailable")
        term_id = str(msg.get("terminalId") or "")
        # Lock only metadata/tail capture and subscription registration. JSON encoding
        # and socket I/O run outside terminal.lock. Sequence numbers allow the
        # browser to merge any live output that races ahead of the snapshot.
        with terminal.lock:
            meta, output, seq = terminal.replay_one(term_id)
            hub.subscribe(peer, term_id)
        # Retained PTY history is untouched. A configured 5M-character tail can
        # exceed an 8 MiB WebSocket queue after ANSI escaping; bound display replay.
        truncated = len(output) > _MAX_ACTIVE_REPLAY_CHARS
        peer.send({"type": "terminal_replay", "terminalId": term_id,
                   "meta": meta, "output": output[-_MAX_ACTIVE_REPLAY_CHARS:],
                   "seq": seq, "truncated": truncated})
        return
    if typ == "terminal_create":
        terminal.create(str(msg.get("terminalId") or ""), str(msg.get("cwd") or ""), int(msg.get("cols") or 80), int(msg.get("rows") or 24), str(msg.get("title") or "Terminal"))
        return
    if typ == "terminal_run":
        terminal.run_command(str(msg.get("terminalId") or ""), str(msg.get("cwd") or ""), str(msg.get("command") or ""), str(msg.get("title") or "Command"), int(msg.get("cols") or 80), int(msg.get("rows") or 24))
        return
    if typ == "terminal_input":
        terminal.input(str(msg.get("terminalId") or ""), str(msg.get("data") or ""))
        return
    if typ == "terminal_key":
        mods = msg.get("modifiers") if isinstance(msg.get("modifiers"), dict) else {}
        terminal.key(str(msg.get("terminalId") or ""), str(msg.get("key") or ""), mods)
        return
    if typ == "terminal_resize":
        terminal.resize(str(msg.get("terminalId") or ""), int(msg.get("cols") or 80), int(msg.get("rows") or 24))
        return
    if typ == "terminal_rename":
        terminal.rename(str(msg.get("terminalId") or ""), str(msg.get("title") or ""))
        return
    if typ == "terminal_kill":
        terminal.kill(str(msg.get("terminalId") or ""))
        return
    kind = {"scm_status": "status", "scm_history": "history", "scm_filediff": "filediff", "scm_commit": "commit"}.get(typ)
    if kind:
        reply = {"type": "scm_data", "reqId": msg.get("reqId"), "kind": kind}
        try:
            reply.update({"ok": True, "data": scm.query(kind, str(msg.get("cwd") or ""), msg)})
        except Exception as exc:
            reply.update({"ok": False, "error": str(exc)})
        peer.send(reply)
        return
    raise ValueError("Unknown WebSocket message: " + typ)
