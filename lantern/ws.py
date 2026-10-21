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
        if len(raw) > 4 * 1024 * 1024 and isinstance(payload, dict) and str(payload.get("type") or "").startswith("chat_"):
            safe_payload = dict(payload)
            if "messages" in safe_payload and isinstance(safe_payload["messages"], list):
                safe_payload["messages"] = safe_payload["messages"][-5:]
                safe_payload["historyTruncatedByFrameGuard"] = True
            raw = json.dumps(safe_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if len(raw) > 4 * 1024 * 1024:
                safe_payload.pop("messages", None)
                safe_payload["historyTruncatedByFrameGuard"] = True
                raw = json.dumps(safe_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
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
        self.pi_peer_delivery: dict[Any, dict[str, Any]] = {}
        self.chat: Any = None

    def add(self, peer):
        with self.lock:
            self.peers.add(peer)

    def remove(self, peer):
        notices = []
        with self._pi_order_lock(peer):
            with self.lock:
                self.peers.discard(peer)
                peer.subscriptions.clear()
                notices = self._pi_detach_locked(peer)
        self._send_pi_notices(notices)

    def close_token(self, token: str):
        if not token:
            return
        with self.lock:
            peers = [peer for peer in self.peers
                     if hmac.compare_digest(getattr(peer, "auth_token", ""), token)]
        for peer in peers:
            self.remove(peer)
            peer.close()

    def close_lan_peers(self, access) -> int:
        with self.lock:
            lan_peers = [
                peer for peer in self.peers
                if not (hasattr(access, "is_local") and access.is_local(getattr(peer, "client_ip", "")))
            ]
        lan_locked = bool(getattr(access, "lan_locked", True))
        configured = bool(getattr(access, "configured", True))
        for peer in lan_peers:
            ip = str(getattr(peer, "client_ip", "") or "")
            req = access.required(ip) if hasattr(access, "required") else lan_locked
            authed = bool(getattr(peer, "can_terminal", lambda: not req)())
            try:
                peer.send({
                    "type": "terminal_auth",
                    "required": req,
                    "authenticated": authed,
                    "configured": configured,
                    "isLocal": False,
                    "lanSessions": 0,
                    "lanLocked": lan_locked,
                })
            except Exception:
                pass
            if not authed:
                self.remove(peer)
                threading.Timer(0.06, peer.close).start()
        return len(lan_peers)

    def notify_local_auth_state(self, access) -> None:
        with self.lock:
            local_peers = [
                peer for peer in self.peers
                if hasattr(access, "is_local") and access.is_local(getattr(peer, "client_ip", ""))
            ]
        lan_sessions = access.active_lan_sessions() if hasattr(access, "active_lan_sessions") else 0
        lan_locked = bool(getattr(access, "lan_locked", False))
        for peer in local_peers:
            try:
                peer.send({
                    "type": "terminal_auth",
                    "required": False,
                    "authenticated": True,
                    "configured": bool(getattr(access, "configured", True)),
                    "isLocal": True,
                    "lanSessions": lan_sessions,
                    "lanLocked": lan_locked,
                })
            except Exception:
                pass

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


    @staticmethod
    def _pi_role(route, peer) -> str:
        return "writer" if route.get("writer") is peer else "viewer"

    def _pi_order_lock(self, peer):
        with self.lock:
            send_lock = getattr(peer, "_pi_notice_lock", None)
            if send_lock is None:
                send_lock = threading.RLock()
                peer._pi_notice_lock = send_lock
            return send_lock

    def _pi_notices_locked(self, route):
        return [
            (
                peer,
                {
                    "type": "pi_session_ownership",
                    "sessionId": route["sessionId"],
                    "generation": route["generation"],
                    "role": self._pi_role(route, peer),
                    "ownershipEpoch": route["epoch"],
                },
            )
            for peer in list(route["peers"])
        ]

    def _send_pi_notices(self, notices):
        for peer, payload in notices:
            with self._pi_order_lock(peer):
                if not getattr(peer, "can_terminal", lambda: True)():
                    continue
                with self.lock:
                    route = self.pi_routes.get(payload.get("sessionId"))
                    if (
                        route is None
                        or route.get("generation") != payload.get("generation")
                        or route.get("epoch") != payload.get("ownershipEpoch")
                        or peer not in route.get("peers", ())
                    ):
                        continue
                try:
                    peer.send(payload)
                except Exception:
                    self.remove(peer)
                    try:
                        peer.close()
                    except Exception:
                        pass

    def _send_pi_replay(self, peer, payload, terminal, terminal_id: str):
        with self._pi_order_lock(peer):
            if not getattr(peer, "can_terminal", lambda: True)():
                raise PiSessionPermissionError(
                    "pi_session_not_attached", "peer is not authorized"
                )
            with terminal.lock:
                meta, _output, _seq, _start, _end = terminal.replay_view(terminal_id)
                if (
                    meta.get("generation") != payload.get("generation")
                    or not meta.get("running")
                ):
                    raise PiSessionError(
                        "pi_session_stale", "stale session generation"
                    )
                with self.lock:
                    session_id = payload.get("sessionId")
                    route = self.pi_routes.get(session_id)
                    if (
                        route is None
                        or route.get("generation") != payload.get("generation")
                        or self.pi_peer_session.get(peer) != session_id
                        or peer not in route.get("peers", ())
                    ):
                        raise PiSessionPermissionError(
                            "pi_session_not_attached", "peer is not attached"
                        )
                    current = dict(payload)
                    current["role"] = self._pi_role(route, peer)
                    current["ownershipEpoch"] = route["epoch"]
                peer.send(current)
                with self.lock:
                    attach_token = self.pi_peer_attach_token.get(peer)
                    if (
                        self.pi_peer_session.get(peer) == session_id
                        and attach_token is not None
                    ):
                        self.pi_peer_delivery[peer] = {
                            "sessionId": session_id,
                            "generation": payload.get("generation"),
                            "attachToken": attach_token,
                            "lastSeq": payload.get("seq"),
                        }

    def _pi_detach_locked(self, peer):
        session_id = self.pi_peer_session.pop(peer, None)
        self.pi_peer_attach_token.pop(peer, None)
        self.pi_peer_delivery.pop(peer, None)
        if not session_id:
            return []
        route = self.pi_routes.get(session_id)
        if not route:
            return []
        route["peers"].discard(peer)
        if route.get("writer") is peer:
            route["writer"] = None
            route["epoch"] += 1
            return self._pi_notices_locked(route)
        return []

    def pi_attach(self, peer, session_id: str, terminal_id: str, generation: str):
        notices = []
        with self.lock:
            if peer not in self.peers:
                raise PiSessionPermissionError(
                    "pi_session_not_attached", "peer is not connected"
                )
            current = self.pi_peer_session.get(peer)
            if current == session_id:
                route = self.pi_routes[session_id]
                if route["generation"] != generation:
                    raise PiSessionError(
                        "pi_session_stale", "stale session generation"
                    )
                return (
                    self._pi_role(route, peer),
                    route["epoch"],
                    notices,
                    self.pi_peer_attach_token[peer],
                )
            if current:
                notices.extend(self._pi_detach_locked(peer))
            route = self.pi_routes.get(session_id)
            if route is None:
                route = {
                    "sessionId": session_id,
                    "terminalId": terminal_id,
                    "generation": generation,
                    "peers": set(),
                    "writer": None,
                    "epoch": 0,
                    "active": True,
                }
                self.pi_routes[session_id] = route
            elif route["terminalId"] != terminal_id or route["generation"] != generation:
                if route["peers"]:
                    raise PiSessionError(
                        "pi_session_stale", "stale session generation"
                    )
                route.update(
                    terminalId=terminal_id,
                    generation=generation,
                    writer=None,
                    epoch=route["epoch"] + 1,
                    active=True,
                )
            route["peers"].add(peer)
            self.pi_peer_session[peer] = session_id
            attach_token = object()
            self.pi_peer_attach_token[peer] = attach_token
            if route["writer"] is None:
                route["writer"] = peer
                route["epoch"] += 1
                if len(route["peers"]) > 1:
                    notices.extend(self._pi_notices_locked(route))
            return self._pi_role(route, peer), route["epoch"], notices, attach_token

    def pi_detach(self, peer, session_id: str):
        with self._pi_order_lock(peer):
            with self.lock:
                if self.pi_peer_session.get(peer) != session_id:
                    return []
                return self._pi_detach_locked(peer)

    def pi_rollback_attach(self, peer, session_id: str, generation: str, attach_token):
        with self.lock:
            if (
                self.pi_peer_session.get(peer) != session_id
                or self.pi_peer_attach_token.get(peer) is not attach_token
            ):
                return []
            route = self.pi_routes.get(session_id)
            if (
                route is None
                or route.get("generation") != generation
                or peer not in route.get("peers", ())
            ):
                return []
            return self._pi_detach_locked(peer)

    def _pi_takeover_locked(self, peer, session_id: str, generation: str):
        if self.pi_peer_session.get(peer) != session_id:
            raise PiSessionPermissionError(
                "pi_session_not_attached", "peer is not attached"
            )
        route = self.pi_routes.get(session_id)
        if route is None or route["generation"] != generation:
            raise PiSessionError("pi_session_stale", "stale session generation")
        if peer not in route["peers"]:
            raise PiSessionPermissionError(
                "pi_session_not_attached", "peer is not attached"
            )
        if route.get("writer") is peer:
            raise PiSessionPermissionError(
                "pi_session_not_viewer", "takeover requires a viewer"
            )
        route["writer"] = peer
        route["epoch"] += 1
        return route["epoch"], self._pi_notices_locked(route)

    def pi_takeover(self, peer, session_id: str, generation: str):
        with self.lock:
            return self._pi_takeover_locked(peer, session_id, generation)

    def _pi_writer_target_locked(
        self, peer, session_id: str, generation: str, epoch: int
    ) -> str:
        if self.pi_peer_session.get(peer) != session_id:
            raise PiSessionPermissionError(
                "pi_session_not_attached", "peer is not attached"
            )
        route = self.pi_routes.get(session_id)
        if route is None or route["generation"] != generation:
            raise PiSessionError("pi_session_stale", "stale session generation")
        if route["epoch"] != epoch:
            raise PiSessionPermissionError(
                "pi_session_stale_owner", "stale owner epoch"
            )
        if route.get("writer") is not peer:
            raise PiSessionPermissionError(
                "pi_session_not_writer", "peer is not writer"
            )
        return route["terminalId"]

    def pi_writer_target(
        self, peer, session_id: str, generation: str, epoch: int
    ) -> str:
        with self.lock:
            return self._pi_writer_target_locked(
                peer, session_id, generation, epoch
            )

    def broadcast(self, message):
        msg_type = str(message.get("type") or "")
        pi_payloads = {}
        pi_scoped_event = message.get("_controlOwner") == "pi"
        client_message = message
        if "_controlOwner" in message:
            client_message = dict(message)
            client_message.pop("_controlOwner", None)
        with self.lock:
            peers = list(self.peers)
            if msg_type == "terminal_list":
                generations = {
                    item.get("id"): item.get("generation")
                    for item in message.get("terminals", [])
                    if item.get("running")
                }
                for route in self.pi_routes.values():
                    route["active"] = (
                        generations.get(route["terminalId"]) == route["generation"]
                    )
            if msg_type in {"terminal_output", "terminal_exit"}:
                for session_id, route in self.pi_routes.items():
                    if route["terminalId"] != message.get("terminalId"):
                        continue
                    if route["generation"] != message.get("generation"):
                        continue
                    pi_scoped_event = True
                    for peer in route["peers"]:
                        if msg_type == "terminal_output":
                            pi_payloads[peer] = {
                                "type": "pi_session_output",
                                "sessionId": session_id,
                                "generation": route["generation"],
                                "seq": message.get("seq"),
                                "data": message.get("data"),
                            }
                        else:
                            pi_payloads[peer] = {
                                "type": "pi_session_exit",
                                "sessionId": session_id,
                                "generation": route["generation"],
                                "exitCode": message.get("exitCode"),
                            }
        for peer in peers:
            if (
                (msg_type.startswith("terminal_") or msg_type.startswith("chat_"))
                and not getattr(peer, "can_terminal", lambda: True)()
            ):
                continue
            pi_payload = pi_payloads.get(peer)
            if pi_payload is not None:
                with self._pi_order_lock(peer):
                    if not getattr(peer, "can_terminal", lambda: True)():
                        continue
                    with self.lock:
                        session_id = pi_payload.get("sessionId")
                        route = self.pi_routes.get(session_id)
                        if (
                            route is None
                            or route.get("generation") != pi_payload.get("generation")
                            or self.pi_peer_session.get(peer) != session_id
                            or peer not in route.get("peers", ())
                        ):
                            continue
                        delivery = self.pi_peer_delivery.get(peer)
                        output_seq = pi_payload.get("seq")
                        if pi_payload.get("type") == "pi_session_output":
                            if (
                                delivery is None
                                or delivery.get("sessionId") != session_id
                                or delivery.get("generation") != pi_payload.get("generation")
                                or delivery.get("attachToken")
                                is not self.pi_peer_attach_token.get(peer)
                            ):
                                continue
                            last_seq = delivery.get("lastSeq")
                            if (
                                isinstance(output_seq, int)
                                and isinstance(last_seq, int)
                                and output_seq <= last_seq
                            ):
                                continue
                    try:
                        peer.send(pi_payload)
                    except Exception:
                        self.remove(peer)
                        peer.close()
                    else:
                        if pi_payload.get("type") == "pi_session_output":
                            with self.lock:
                                delivery = self.pi_peer_delivery.get(peer)
                                if (
                                    delivery is not None
                                    and delivery.get("sessionId") == session_id
                                    and delivery.get("generation")
                                    == pi_payload.get("generation")
                                    and delivery.get("attachToken")
                                    is self.pi_peer_attach_token.get(peer)
                                    and isinstance(output_seq, int)
                                ):
                                    last_seq = delivery.get("lastSeq")
                                    if not isinstance(last_seq, int) or output_seq > last_seq:
                                        delivery["lastSeq"] = output_seq
                continue
            if pi_scoped_event and msg_type in {"terminal_output", "terminal_exit"}:
                continue
            if (
                msg_type == "terminal_output"
                and getattr(peer, "protocol", "v2") != "legacy"
                and message.get("terminalId") not in peer.subscriptions
            ):
                continue
            if msg_type in {"chat_sessions_changed", "chat_commands_changed", "chat_work_locked", "chat_work_changed", "chat_work_error", "chat_real_file_touched"}:
                out_changed = dict(client_message)
                out_changed.pop("clientSessionId", None)
                try:
                    peer.send(out_changed)
                except Exception:
                    self.remove(peer)
                    peer.close()
                continue
            if (
                msg_type.startswith("chat_")
                and msg_type not in {"chat_work_changed", "chat_work_locked", "chat_work_error", "chat_real_file_touched", "chat_prefs_changed", "chat_favorites_changed", "chat_sessions_changed", "chat_commands_changed"}
            ):
                msg_runtime_id = str(message.get("runtimeId") or "").strip()
                msg_shared_sid = str(message.get("sharedSessionId") or "").strip()
                msg_cid = str(message.get("clientSessionId") or "").strip()
                peer_cid = str(getattr(peer, "chat_session_id", "") or "").strip()
                peer_scope = _chat_scope(peer)
                root_chat = getattr(self, "chat", None)
                if root_chat is not None and hasattr(root_chat, "peek_session_bot") and (msg_runtime_id or msg_shared_sid):
                    peer_bot = root_chat.peek_session_bot(peer_cid, scope=peer_scope)
                    if peer_bot is not None:
                        if msg_runtime_id and getattr(peer_bot, "runtime_id", "") != msg_runtime_id:
                            continue
                        if not msg_runtime_id and msg_shared_sid and peer_bot.current_session_id() != msg_shared_sid:
                            continue
                        out_msg = dict(client_message)
                        if peer_cid:
                            out_msg["clientSessionId"] = peer_cid
                        else:
                            out_msg.pop("clientSessionId", None)
                        try:
                            peer.send(out_msg)
                        except Exception:
                            self.remove(peer)
                            peer.close()
                        continue
                    elif msg_shared_sid:
                        continue
                if msg_cid:
                    if peer_cid != msg_cid:
                        continue
                else:
                    if peer_cid and peer_cid != "default":
                        continue
            try:
                peer.send(client_message)
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
    replay_filtered = getattr(terminal, "replay_excluding_control_owner", None)
    output = dict(replay_filtered("pi") if callable(replay_filtered) else terminal.replay())
    truncated = any(len(s) > 20000 for s in output.values())
    return {"type": "terminal_snapshot", "terminals": terminal.list(),
            "output": {k: s[-20000:] for k, s in output.items()}}, truncated


def upgrade(handler, hub, terminal, scm, access=None, chat=None):
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
    peer.client_ip = str(handler.client_address[0] or "")
    # Cookie is captured at handshake; every command/broadcast checks the
    # current expiry/revocation with the same immutable request credentials.
    peer.auth_token = access.cookie_token(handler.headers.get("Cookie", "")) if access else ""
    peer.can_terminal = (lambda: access.permitted(
        handler.client_address[0], handler.headers.get("Cookie", ""))) if access else (lambda: True)
    # Explicit URL version avoids timer races when a LAN client is slow to send.
    if urllib.parse.parse_qs(urllib.parse.urlsplit(handler.path).query).get("v") == ["2"]:
        peer.protocol = "v2"
    def legacy_fallback() -> None:
        # Older LAN browser tabs reconnect without the v2 handshake. Preserve their
        # terminal view until those tabs reload the new JS. This path is temporary.
        if not peer.can_terminal():
            return
        with terminal.lock:
            if peer.closed or peer.protocol != "pending" or not peer.can_terminal():
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
        if access is not None:
            is_local = access.is_local(handler.client_address[0]) if hasattr(access, "is_local") else False
            lan_sessions = access.active_lan_sessions() if (is_local and hasattr(access, "active_lan_sessions")) else 0
            peer.send({
                "type": "terminal_auth",
                "required": access.required(handler.client_address[0]),
                "authenticated": peer.can_terminal(),
                "configured": access.configured,
                "isLocal": is_local,
                "lanSessions": lan_sessions,
                "lanLocked": bool(getattr(access, "lan_locked", False)),
            })
        with terminal.lock:
            # Never reveal terminal metadata to unauthenticated LAN clients.
            if peer.can_terminal():
                peer.send({"type": "terminal_list", "terminals": terminal.list()})
            hub.add(peer)
        legacy_timer.start()
        while True:
            raw = peer.recv()
            if raw is None:
                break
            received = None
            try:
                received = json.loads(raw)
                dispatch(peer, received, terminal, scm, hub, chat=chat)
            except Exception as exc:
                try:
                    peer.send(_terminal_error_reply(received, exc))
                    if isinstance(exc, KeyError) and isinstance(received, dict) and received.get("type") in {"terminal_input", "terminal_key"}:
                        # A browser can race an exited/restarted PTY. Reconcile
                        # this one client from authoritative server metadata.
                        peer.send({"type": "terminal_list", "terminals": terminal.list()})
                except Exception:
                    break
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
        pass
    finally:
        legacy_timer.cancel()
        hub.remove(peer)
        peer.close()


def _terminal_error_reply(message, error):
    operation = message.get("type") if isinstance(message, dict) else ""
    op_text = str(operation or "")
    is_chat = op_text.startswith("chat_")
    is_pi = op_text.startswith("pi_session_")
    reply_type = "chat_error" if is_chat else ("pi_session_error" if is_pi else "terminal_error")
    reply = {"type": reply_type, "error": str(error)}
    if not isinstance(message, dict):
        return reply
    if isinstance(error, PermissionError) and str(error).startswith("Terminal locked"):
        reply["code"] = "terminal_auth_required"
        reply["operation"] = op_text
        if not is_pi:
            reply["terminalId"] = str(message.get("terminalId") or "")
        return reply
    code = getattr(error, "code", None)
    if code:
        reply["code"] = str(code)
    if is_pi:
        reply["operation"] = op_text
        reply["sessionId"] = str(message.get("sessionId") or "")
        return reply
    if operation in {"terminal_create", "terminal_run", "terminal_input", "terminal_key", "terminal_resize", "terminal_subscribe"}:
        reply["operation"] = operation
        reply["terminalId"] = str(message.get("terminalId") or "")
        if operation in {"terminal_create", "terminal_run"}:
            reply["code"] = "terminal_start_failed"
        elif operation in {"terminal_input", "terminal_key"} and isinstance(error, KeyError):
            reply["code"] = "terminal_not_running"
    return reply


def _chat_scope(peer) -> str:
    raw = str(getattr(peer, "client_ip", "") or "").strip()
    if raw.lower() == "localhost":
        return "local"
    try:
        ip = ipaddress.ip_address(raw)
        if getattr(ip, "ipv4_mapped", None) is not None:
            ip = ip.ipv4_mapped
        return "local" if ip.is_loopback else "lan"
    except ValueError:
        return "lan"



class PiSessionError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class PiSessionPermissionError(PermissionError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _bounded_replay(output: str, replay_start_utf8: int):
    truncated = len(output) > _MAX_ACTIVE_REPLAY_CHARS
    if truncated:
        drop = len(output) - _MAX_ACTIVE_REPLAY_CHARS
        omitted = output[:drop]
        output = output[drop:]
        replay_start_utf8 += len(omitted.encode("utf-8"))
    return output, replay_start_utf8, truncated


def _pi_session_view(pi, session_id: str, generation: str):
    if pi is None:
        raise RuntimeError("Pi session registry is unavailable")
    try:
        session = pi.get(session_id)
    except KeyError:
        raise PiSessionError("pi_session_not_found", "Pi session not found") from None
    if session.get("generation") != generation or not session.get("running"):
        raise PiSessionError("pi_session_stale", "stale session generation")
    return session


def _guard_generic_terminal_control(terminal, terminal_id: str, *, include_history: bool = False):
    owner = (
        terminal.control_owner(terminal_id, include_history=True)
        if include_history
        else terminal.control_owner(terminal_id)
    )
    if owner == "pi":
        raise PiSessionPermissionError(
            "pi_session_control_required",
            "Pi terminal control requires Pi session writer ownership",
        )


def dispatch(peer, msg, terminal, scm, hub=None, chat=None, pi=None):
    if not isinstance(msg, dict):
        raise ValueError("message must be an object")
    typ = str(msg.get("type") or "")
    if (
        (
            typ.startswith("terminal_")
            or typ.startswith("chat_")
            or typ.startswith("pi_session_")
        )
        and not getattr(peer, "can_terminal", lambda: True)()
    ):
        raise PermissionError(
            "Terminal locked: enter the password on the host-issued sign-in form"
        )
    if typ.startswith("chat_") and chat is None:
        raise RuntimeError("LanternBot is not initialized")
    root_chat = chat
    active_cid = ""
    peer_scope = _chat_scope(peer)
    scope = peer_scope
    if typ.startswith("chat_"):
        if hub is not None and hasattr(root_chat, "peek_session_bot"):
            hub.chat = root_chat
        raw_cid = str(msg.get("clientSessionId") or "").strip()
        if raw_cid:
            setattr(peer, "chat_session_id", raw_cid)
        active_cid = str(getattr(peer, "chat_session_id", "") or "").strip()
        if hasattr(root_chat, "get_session_bot"):
            try:
                chat = root_chat.get_session_bot(active_cid, scope=peer_scope)
            except TypeError:
                chat = root_chat.get_session_bot(active_cid)
        scope = getattr(chat, "access_scope", None) or peer_scope

    def _viewer_sessions() -> list[dict[str, Any]]:
        if not hasattr(root_chat, "list_sessions"):
            return []
        try:
            return root_chat.list_sessions(peer_scope, current_bot=chat)
        except TypeError:
            try:
                return root_chat.list_sessions(peer_scope)
            except TypeError:
                return root_chat.list_sessions()
        except Exception:
            return []

    if typ == "chat_sync":
        state = chat.bootstrap_state(scope)
        separate_history = bool(msg.get("separateHistory"))
        payload: Dict[str, Any] = {
            "type": "chat_state",
            "state": state,
            "summary": chat.summary(scope),
            "models": chat.available_models(scope),
            "sessions": _viewer_sessions(),
        }
        peer_cid = str(getattr(peer, "chat_session_id", "") or "").strip()
        if peer_cid:
            payload["clientSessionId"] = peer_cid
        if separate_history:
            payload["historySeparate"] = True
            peer.send(payload)
            try:
                if hasattr(chat, "get_messages_page"):
                    page = chat.get_messages_page(limit_messages=int(msg.get("historyLimit") or 24), max_bytes=512_000, tool_preview_chars=1200)
                else:
                    msgs = chat.get_messages()
                    page = {"messages": msgs, "totalMessages": len(msgs), "startIndex": 0, "endIndex": len(msgs), "hasMoreOlder": False, "olderCount": 0}
                hist_pkt: Dict[str, Any] = {"type": "chat_history_page", "isInitial": True, **page}
                if peer_cid:
                    hist_pkt["clientSessionId"] = peer_cid
                peer.send(hist_pkt)
            except Exception as exc:
                err_pkt: Dict[str, Any] = {"type": "chat_history_error", "error": f"Không tải được lịch sử hội thoại: {exc}"}
                if peer_cid:
                    err_pkt["clientSessionId"] = peer_cid
                peer.send(err_pkt)
            return
        try:
            if hasattr(chat, "get_messages_page"):
                page = chat.get_messages_page(limit_messages=24, max_bytes=512_000, tool_preview_chars=1200)
                payload.update(page)
            else:
                payload["messages"] = chat.get_messages()
        except Exception as exc:
            payload["messages"] = []
            payload["historyError"] = str(exc)
        peer.send(payload)
        return
    if typ == "chat_share_session":
        if peer_scope != "local":
            raise PermissionError("Only localhost can share or unshare sessions")
        sid = str(msg.get("sessionId") or "").strip()
        spath = str(msg.get("sessionPath") or "").strip()
        shared_flag = bool(msg.get("shared", True))
        res = (
            root_chat.set_session_shared(sid, shared_flag, session_path=spath, scope=peer_scope)
            if hasattr(root_chat, "set_session_shared")
            else {"ok": False}
        )
        peer.send({
            "type": "chat_sessions_list",
            "sessions": _viewer_sessions(),
            "sharedSessionId": res.get("sessionId") or sid,
            "shared": bool(res.get("shared", shared_flag)),
        })
        return
    if typ == "chat_prompt":
        context = dict(msg.get("context")) if isinstance(msg.get("context"), dict) else {}
        work_hash = msg.get("workHash")
        if not work_hash and isinstance(context.get("workHash"), str):
            work_hash = context.pop("workHash", None)
        else:
            context.pop("workHash", None)
        is_shared_rt = bool(chat in getattr(root_chat, "_shared_bots", {}).values())
        if is_shared_rt and (getattr(chat, "streaming", False) or getattr(chat, "_turn_in_progress", False)):
            raise RuntimeError("Shared session is currently busy completing a turn")
        if msg.get("steer") and hasattr(chat, "steer"):
            res = chat.steer(
                str(msg.get("message") or ""),
                context,
                work_hash=str(work_hash) if isinstance(work_hash, str) and work_hash else None,
                scope=scope,
            )
            peer.send({"type": "chat_steer_accepted", "reqId": msg.get("reqId"), **res})
            return
        prompt_res = chat.prompt(
            str(msg.get("message") or ""),
            context,
            work_hash=str(work_hash) if isinstance(work_hash, str) and work_hash else None,
            scope=scope,
        )
        is_sync_slash = bool(isinstance(prompt_res, dict) and prompt_res.get("slashHandled"))
        peer.send({
            "type": "chat_prompt_accepted",
            "reqId": msg.get("reqId"),
            "slashHandled": is_sync_slash,
        })
        if is_shared_rt and hasattr(chat, "emit"):
            try:
                chat.emit({
                    "type": "chat_shared_refresh",
                    "sessionId": chat.current_session_id() if hasattr(chat, "current_session_id") else "",
                    "senderClientSessionId": active_cid,
                })
            except Exception:
                pass
        return
    if typ == "chat_steer":
        context = dict(msg.get("context")) if isinstance(msg.get("context"), dict) else {}
        work_hash = msg.get("workHash")
        if not work_hash and isinstance(context.get("workHash"), str):
            work_hash = context.pop("workHash", None)
        else:
            context.pop("workHash", None)
        is_shared_rt = bool(chat in getattr(root_chat, "_shared_bots", {}).values())
        if is_shared_rt and (getattr(chat, "streaming", False) or getattr(chat, "_turn_in_progress", False)):
            raise RuntimeError("Shared session is currently busy completing a turn")
        if hasattr(chat, "steer"):
            res = chat.steer(
                str(msg.get("message") or ""),
                context,
                work_hash=str(work_hash) if isinstance(work_hash, str) and work_hash else None,
                scope=scope,
            )
        else:
            chat.prompt(
                str(msg.get("message") or ""),
                context,
                work_hash=str(work_hash) if isinstance(work_hash, str) and work_hash else None,
                scope=scope,
            )
            res = {"ok": True, "steered": False}
        peer.send({"type": "chat_steer_accepted", "reqId": msg.get("reqId"), **res})
        return
    if typ == "chat_abort":
        chat.abort()
        peer.send({"type": "chat_aborted"})
        return
    if typ == "chat_new":
        if hasattr(root_chat, "select_shared_session"):
            root_chat.select_shared_session(active_cid, peer_scope, session_id="")
            if hasattr(root_chat, "detach_busy_bot_for_switch"):
                chat = root_chat.detach_busy_bot_for_switch(active_cid, scope=peer_scope, target_session_id="__new__")
                scope = getattr(chat, "access_scope", None) or peer_scope
            elif hasattr(root_chat, "get_session_bot"):
                chat = root_chat.get_session_bot(active_cid, scope=peer_scope)
                scope = getattr(chat, "access_scope", None) or peer_scope
        skip_empty = bool(msg.get("skipIfEmpty"))
        try:
            state = chat.new_session(scope, skip_if_empty=skip_empty) if skip_empty else chat.new_session(scope)
        except TypeError:
            state = chat.new_session(scope)
        peer.send({
            "type": "chat_state",
            "isNew": True,
            "state": state,
            "summary": chat.summary(scope),
            "models": chat.available_models(scope),
            "messages": [],
            "sessions": _viewer_sessions(),
        })
        return
    if typ == "chat_set_model":
        chat.set_model(
            str(msg.get("provider") or ""),
            str(msg.get("modelId") or ""),
            scope,
        )
        peer.send({
            "type": "chat_model_changed",
            "state": chat.get_state(),
            "summary": chat.summary(scope),
        })
        return
    if typ in ("chat_toggle_favorite", "chat_toggle_favorite_model"):
        provider = str(msg.get("provider") or "").strip()
        model_id = str(msg.get("modelId") or "").strip()
        model_key = str(msg.get("modelKey") or "").strip()
        if model_key and (not provider or not model_id):
            if "/" in model_key:
                provider, model_id = model_key.split("/", 1)
            else:
                model_id = model_key
        res = chat.toggle_favorite_model(provider, model_id) if hasattr(chat, "toggle_favorite_model") else {"ok": False}
        peer.send({
            "type": "chat_favorites_changed",
            **res,
            "models": chat.available_models(scope),
            "summary": chat.summary(scope),
        })
        return
    if typ == "chat_set_thinking":
        res = chat.set_thinking_level(str(msg.get("level") or "medium")) if hasattr(chat, "set_thinking_level") else {"ok": True}
        peer.send({"type": "chat_prefs_changed", **res, "summary": chat.summary(scope)})
        return
    if typ == "chat_set_tool_mode":
        res = chat.set_tool_preset(str(msg.get("mode") or "full")) if hasattr(chat, "set_tool_preset") else {"ok": True}
        peer.send({"type": "chat_prefs_changed", **res, "summary": chat.summary(scope)})
        return
    if typ == "chat_set_prefs":
        res = chat.update_custom_settings(
            custom_system_prompt=msg.get("customSystemPrompt"),
            use_global_skills=msg.get("useGlobalSkills"),
            custom_skill_paths=msg.get("customSkillPaths"),
        ) if hasattr(chat, "update_custom_settings") else {"ok": True}
        peer.send({"type": "chat_prefs_changed", **res, "summary": chat.summary(scope)})
        return
    if typ == "chat_fork":
        upto_idx = msg.get("uptoIndex")
        src_path = str(msg.get("sourceSessionPath") or "").strip() or None
        custom_name = str(msg.get("customName") or "").strip() or None
        if hasattr(chat, "fork_session"):
            try:
                state = chat.fork_session(
                    scope,
                    upto_index=int(upto_idx) if upto_idx is not None and str(upto_idx) != "" else None,
                    source_session_path=src_path,
                    custom_name=custom_name,
                )
            except TypeError:
                state = chat.fork_session(scope)
        else:
            state = chat.bootstrap_state(scope)
        page_data = (
            chat.get_messages_page(limit_messages=24, max_bytes=512_000, tool_preview_chars=1200)
            if hasattr(chat, "get_messages_page")
            else {"messages": chat.get_messages()}
        )
        peer.send({
            "type": "chat_state",
            "state": state,
            "summary": chat.summary(scope),
            "models": chat.available_models(scope),
            "sessions": _viewer_sessions(),
            "isSwitch": True,
            **page_data,
        })
        return
    if typ == "chat_rename_session":
        sid = str(msg.get("sessionId") or "").strip()
        new_title = str(msg.get("name") or msg.get("title") or "").strip()
        spath = str(msg.get("sessionPath") or "").strip()
        target_sc = str(msg.get("sessionScope") or "").strip().lower() or None
        if hasattr(root_chat, "rename_session"):
            try:
                res = root_chat.rename_session(
                    sid,
                    new_title,
                    session_path=spath,
                    scope=target_sc or scope,
                    viewer_scope=peer_scope,
                )
            except TypeError:
                res = chat.rename_session(sid, new_title, session_path=spath, scope=scope)
        else:
            res = {"ok": False}
        peer.send({
            "type": "chat_sessions_list",
            "sessions": _viewer_sessions(),
            "renamedSessionId": sid,
            "sessionName": new_title,
        })
        return
    if typ == "chat_delete_session":
        sid = str(msg.get("sessionId") or "").strip()
        spath = str(msg.get("sessionPath") or "").strip()
        target_sc = str(msg.get("sessionScope") or "").strip().lower() or None
        if hasattr(chat, "delete_session"):
            try:
                res = chat.delete_session(
                    sid,
                    session_path=spath,
                    scope=target_sc or scope,
                    viewer_scope=peer_scope,
                )
            except TypeError:
                res = chat.delete_session(sid, session_path=spath, scope=scope)
        else:
            res = {"ok": False}
        if res.get("wasCurrent"):
            peer.send({
                "type": "chat_state",
                "isNew": True,
                "state": res.get("state") or chat.bootstrap_state(scope),
                "summary": chat.summary(scope),
                "models": chat.available_models(scope),
                "messages": [],
                "sessions": _viewer_sessions(),
            })
        peer.send({
            "type": "chat_sessions_list",
            "sessions": _viewer_sessions(),
            "deletedSessionId": sid,
        })
        return
    if typ == "chat_switch_session":
        session_path = str(msg.get("sessionPath") or "").strip()
        session_id = str(msg.get("sessionId") or "").strip()
        target_session_scope = str(msg.get("sessionScope") or "").strip().lower()
        shared_mgr = None
        if hasattr(root_chat, "select_shared_session"):
            shared_mgr = root_chat.select_shared_session(
                active_cid,
                peer_scope,
                session_id=session_id,
                session_path=session_path,
                session_scope=target_session_scope,
            )
        if shared_mgr is not None:
            chat = shared_mgr
            scope = getattr(chat, "access_scope", None) or peer_scope
            state = chat.bootstrap_state(scope)
        else:
            if hasattr(root_chat, "detach_busy_bot_for_switch"):
                chat = root_chat.detach_busy_bot_for_switch(
                    active_cid,
                    scope=peer_scope,
                    target_session_id=session_id,
                    target_session_path=session_path,
                )
            elif hasattr(root_chat, "get_session_bot"):
                try:
                    chat = root_chat.get_session_bot(active_cid, scope=peer_scope)
                except TypeError:
                    chat = root_chat.get_session_bot(active_cid)
            scope = getattr(chat, "access_scope", None) or peer_scope
            target_arg = session_path or session_id
            if getattr(chat, "streaming", False) or getattr(chat, "_turn_in_progress", False):
                state = dict(getattr(chat, "last_state", {}) or {})
                if getattr(chat, "_switched_session_override", None):
                    state.update(chat._switched_session_override)
            else:
                state = chat.switch_session(target_arg, scope) if hasattr(chat, "switch_session") else chat.bootstrap_state(scope)
        switch_limit = max(1, min(50, int(msg.get("limit") or 8)))
        page_data = (
            chat.get_messages_page(limit_messages=switch_limit, max_bytes=128_000, tool_preview_chars=1200)
            if hasattr(chat, "get_messages_page")
            else {"messages": chat.get_messages()}
        )
        peer.send({
            "type": "chat_state",
            "state": state,
            "summary": chat.summary(scope),
            "models": chat.available_models(scope),
            "sessions": _viewer_sessions(),
            "isSwitch": True,
            **page_data,
        })
        return
    if typ == "chat_list_sessions":
        peer.send({
            "type": "chat_sessions_list",
            "sessions": _viewer_sessions(),
        })
        return
    if typ == "chat_load_history":
        before_idx = msg.get("beforeIndex")
        limit_n = int(msg.get("limit") or 24)
        if hasattr(chat, "get_messages_page"):
            page = chat.get_messages_page(
                before_index=int(before_idx) if before_idx is not None else None,
                limit_messages=limit_n,
                max_bytes=512_000,
                tool_preview_chars=1200,
            )
        else:
            msgs = chat.get_messages()
            page = {"messages": msgs, "totalMessages": len(msgs), "startIndex": 0, "endIndex": len(msgs), "hasMoreOlder": False, "olderCount": 0}
        peer.send({
            "type": "chat_history_page",
            "isOlderPage": before_idx is not None,
            "prepend": before_idx is not None,
            **page,
        })
        return
    if typ == "chat_get_tool_output":
        msg_idx = int(msg.get("msgIndex") or 0)
        tool_idx = int(msg.get("toolIndex") or 0)
        res = chat.get_tool_output_full(msg_idx, tool_idx) if hasattr(chat, "get_tool_output_full") else {"ok": False}
        peer.send({"type": "chat_tool_output_full", **res})
        return
    if typ == "chat_rerun":
        turn_idx = int(msg.get("turnIndex") or 0)
        context = dict(msg.get("context")) if isinstance(msg.get("context"), dict) else {}
        work_hash = msg.get("workHash")
        chat.rerun_from_turn(
            turn_idx,
            message=str(msg.get("message") or "") or None,
            context=context,
            work_hash=str(work_hash) if isinstance(work_hash, str) and work_hash else None,
            scope=scope,
        )
        peer.send({"type": "chat_prompt_accepted", "reqId": msg.get("reqId"), "isRerun": True, "rerun": True})
        return
    if typ == "chat_reset_bot":
        state = chat.reset_runtime(scope) if hasattr(chat, "reset_runtime") else chat.bootstrap_state(scope)
        # Send reset result and provider/model independently WITHOUT attaching history
        peer.send({
            "type": "chat_bot_reset",
            "ok": True,
            "state": state,
            "summary": chat.summary(scope),
            "models": chat.available_models(scope),
            "sessions": _viewer_sessions(),
        })
        try:
            if hasattr(chat, "get_messages_page"):
                page = chat.get_messages_page(limit_messages=24, max_bytes=512_000, tool_preview_chars=1200)
                peer.send({"type": "chat_history_page", "isInitial": True, **page})
        except Exception as exc:
            peer.send({"type": "chat_history_error", "error": str(exc)})
        return
    if typ == "chat_compact":
        res = chat.compact_session(str(msg.get("instructions") or "")) if hasattr(chat, "compact_session") else {"ok": True}
        payload = {"type": "chat_compacted", "result": res}
        try:
            payload["state"] = chat.get_state()
            payload["summary"] = chat.summary(scope)
            payload["messages"] = chat.get_messages()
        except Exception:
            pass
        peer.send(payload)
        return
    if typ == "chat_extension_ui_response":
        res = chat.respond_extension_ui(str(msg.get("requestId") or ""), msg.get("value")) if hasattr(chat, "respond_extension_ui") else {"ok": True}
        peer.send({"type": "chat_extension_ui_ack", **res})
        return

    if typ.startswith("pi_session_") and hub is None:
        raise RuntimeError("Pi session hub is unavailable")

    if typ == "pi_session_attach":
        session_id = str(msg.get("sessionId") or "")
        generation = str(msg.get("generation") or "")
        notices = []
        rollback_notices = []
        attach_error = None
        with terminal.lock:
            session = _pi_session_view(pi, session_id, generation)
            meta, output, seq, replay_start_utf8, replay_end_utf8 = terminal.replay_view(
                session["terminalId"]
            )
            if meta.get("generation") != generation or not meta.get("running"):
                raise PiSessionError("pi_session_stale", "stale session generation")
            role, epoch, notices, attach_token = hub.pi_attach(
                peer, session_id, session["terminalId"], generation
            )
            output, replay_start_utf8, truncated = _bounded_replay(
                output, replay_start_utf8
            )
            try:
                hub._send_pi_replay(
                    peer,
                    {
                        "type": "pi_session_replay",
                        "sessionId": session_id,
                        "generation": generation,
                        "output": output,
                        "seq": seq,
                        "replayStartUtf8": replay_start_utf8,
                        "replayEndUtf8": replay_end_utf8,
                        "truncated": truncated,
                        "role": role,
                        "ownershipEpoch": epoch,
                    },
                    terminal,
                    session["terminalId"],
                )
            except Exception as exc:
                rollback_notices = hub.pi_rollback_attach(
                    peer, session_id, generation, attach_token
                )
                attach_error = exc
        if attach_error is not None:
            hub._send_pi_notices([*notices, *rollback_notices])
            raise attach_error
        hub._send_pi_notices(notices)
        return

    if typ == "pi_session_detach":
        notices = hub.pi_detach(peer, str(msg.get("sessionId") or ""))
        hub._send_pi_notices(notices)
        return

    if typ == "pi_session_takeover":
        session_id = str(msg.get("sessionId") or "")
        generation = str(msg.get("generation") or "")
        with terminal.lock:
            session = _pi_session_view(pi, session_id, generation)
            meta, _output, _seq, _start, _end = terminal.replay_view(
                session["terminalId"]
            )
            if meta.get("generation") != generation or not meta.get("running"):
                raise PiSessionError("pi_session_stale", "stale session generation")
            with hub.lock:
                _epoch, notices = hub._pi_takeover_locked(
                    peer, session_id, generation
                )
        hub._send_pi_notices(notices)
        return

    if typ in {"pi_session_input", "pi_session_key", "pi_session_resize"}:
        session_id = str(msg.get("sessionId") or "")
        generation = str(msg.get("generation") or "")
        try:
            epoch = int(msg.get("ownershipEpoch"))
        except (TypeError, ValueError):
            raise PiSessionPermissionError(
                "pi_session_stale_owner", "stale owner epoch"
            ) from None
        with terminal.lock:
            session = _pi_session_view(pi, session_id, generation)
            with hub.lock:
                terminal_id = hub._pi_writer_target_locked(
                    peer, session_id, generation, epoch
                )
                if terminal_id != session["terminalId"]:
                    raise PiSessionError(
                        "pi_session_stale", "stale session generation"
                    )
                meta, _output, _seq, _start, _end = terminal.replay_view(terminal_id)
                if meta.get("generation") != generation or not meta.get("running"):
                    raise PiSessionError(
                        "pi_session_stale", "stale session generation"
                    )
                if typ == "pi_session_input":
                    terminal.input(terminal_id, str(msg.get("data") or ""))
                elif typ == "pi_session_key":
                    mods = (
                        msg.get("modifiers")
                        if isinstance(msg.get("modifiers"), dict)
                        else {}
                    )
                    terminal.key(terminal_id, str(msg.get("key") or ""), mods)
                else:
                    terminal.resize(
                        terminal_id,
                        int(msg.get("cols") or 80),
                        int(msg.get("rows") or 24),
                    )
        return

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
        with terminal.lock:
            _guard_generic_terminal_control(
                terminal, term_id, include_history=True
            )
            meta, output, seq, replay_start_utf8, replay_end_utf8 = terminal.replay_view(
                term_id
            )
            hub.subscribe(peer, term_id)
        output, replay_start_utf8, truncated = _bounded_replay(
            output, replay_start_utf8
        )
        peer.send({
            "type": "terminal_replay",
            "terminalId": term_id,
            "meta": meta,
            "output": output,
            "seq": seq,
            "truncated": truncated,
            "replayStartUtf8": replay_start_utf8,
            "replayEndUtf8": replay_end_utf8,
        })
        return

    if typ in {
        "terminal_create",
        "terminal_run",
        "terminal_input",
        "terminal_key",
        "terminal_resize",
        "terminal_kill",
    }:
        term_id = str(msg.get("terminalId") or "")
        response = None
        with terminal.lock:
            _guard_generic_terminal_control(terminal, term_id)
            if typ == "terminal_create":
                meta = terminal.create(
                    term_id,
                    str(msg.get("cwd") or ""),
                    int(msg.get("cols") or 80),
                    int(msg.get("rows") or 24),
                    str(msg.get("title") or "Terminal"),
                )
                response = {
                    "type": "terminal_created",
                    "terminalId": meta["id"],
                    "meta": meta,
                }
            elif typ == "terminal_run":
                meta = terminal.run_command(
                    term_id,
                    str(msg.get("cwd") or ""),
                    str(msg.get("command") or ""),
                    str(msg.get("title") or "Command"),
                    int(msg.get("cols") or 80),
                    int(msg.get("rows") or 24),
                )
                response = {
                    "type": "terminal_created",
                    "terminalId": meta["id"],
                    "meta": meta,
                }
            elif typ == "terminal_input":
                terminal.input(term_id, str(msg.get("data") or ""))
            elif typ == "terminal_key":
                mods = (
                    msg.get("modifiers")
                    if isinstance(msg.get("modifiers"), dict)
                    else {}
                )
                terminal.key(term_id, str(msg.get("key") or ""), mods)
            elif typ == "terminal_resize":
                terminal.resize(
                    term_id,
                    int(msg.get("cols") or 80),
                    int(msg.get("rows") or 24),
                )
            else:
                terminal.kill(term_id)
        if response is not None:
            peer.send(response)
        return

    if typ == "terminal_rename":
        terminal.rename(
            str(msg.get("terminalId") or ""),
            str(msg.get("title") or ""),
        )
        return

    kind = {
        "scm_status": "status",
        "scm_history": "history",
        "scm_filediff": "filediff",
        "scm_commit": "commit",
    }.get(typ)
    if kind:
        reply = {
            "type": "scm_data",
            "reqId": msg.get("reqId"),
            "kind": kind,
        }
        try:
            reply.update({
                "ok": True,
                "data": scm.query(kind, str(msg.get("cwd") or ""), msg),
            })
        except Exception as exc:
            reply.update({"ok": False, "error": str(exc)})
        peer.send(reply)
        return
    raise ValueError("Unknown WebSocket message: " + typ)
