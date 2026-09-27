from __future__ import annotations
import base64, hashlib, json, struct, threading, urllib.parse
from typing import Any, Dict

_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_MAX_FRAME = 2 * 1024 * 1024

class WebSocketPeer:
    def __init__(self, handler) -> None:
        self.rfile, self.wfile = handler.rfile, handler.wfile
        self.lock, self.closed = threading.Lock(), False
    def send(self, payload: Dict[str, Any]) -> None:
        self._send_frame(0x1, json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    def _send_frame(self, opcode: int, payload: bytes = b"") -> None:
        if self.closed: raise ConnectionError("websocket closed")
        head=bytearray([0x80|opcode]); n=len(payload)
        if n<126: head.append(n)
        elif n<=0xFFFF: head.extend([126]); head.extend(struct.pack("!H",n))
        else: head.extend([127]); head.extend(struct.pack("!Q",n))
        with self.lock: self.wfile.write(bytes(head)+payload); self.wfile.flush()
    def recv(self):
        while not self.closed:
            head=self.rfile.read(2)
            if len(head)!=2:return None
            b1,b2=head;opcode=b1&15;length=b2&127
            if not (b1&128):raise ValueError("fragmented frames unsupported")
            if length==126:length=struct.unpack("!H",self.rfile.read(2))[0]
            elif length==127:length=struct.unpack("!Q",self.rfile.read(8))[0]
            if length>_MAX_FRAME:raise ValueError("frame too large")
            if not (b2&128):raise ValueError("client frames must be masked")
            mask=self.rfile.read(4);payload=self.rfile.read(length)
            if len(mask)!=4 or len(payload)!=length:return None
            payload=bytes(v^mask[i%4] for i,v in enumerate(payload))
            if opcode==8:self.closed=True;return None
            if opcode==9:self._send_frame(10,payload[:125]);continue
            if opcode==1:return payload.decode("utf-8","replace")
        return None

class WebSocketHub:
    def __init__(self):
        self.peers=set();self.lock=threading.Lock()
    def add(self,p):
        with self.lock:self.peers.add(p)
    def remove(self,p):
        with self.lock:self.peers.discard(p)
    def broadcast(self,message):
        with self.lock:peers=list(self.peers)
        for p in peers:
            try:p.send(message)
            except Exception:self.remove(p)
def same_origin(handler):
    host=(handler.headers.get("Host") or "").strip().lower()
    origin=(handler.headers.get("Origin") or "").strip()
    if not host or not origin:return False
    try:p=urllib.parse.urlsplit(origin)
    except Exception:return False
    return p.scheme in {"http","https"} and p.netloc.lower()==host

def upgrade(handler,hub,terminal,scm):
    if not same_origin(handler):handler.send_error(403,"WebSocket Origin must match Host");return
    if (handler.headers.get("Upgrade") or "").lower()!="websocket":handler.send_error(400);return
    key=(handler.headers.get("Sec-WebSocket-Key") or "").strip()
    if not key or handler.headers.get("Sec-WebSocket-Version")!="13":handler.send_error(400);return
    try:decoded=base64.b64decode(key,validate=True)
    except Exception:handler.send_error(400);return
    if len(decoded)!=16:handler.send_error(400);return
    accept=base64.b64encode(hashlib.sha1((key+_WS_GUID).encode("ascii")).digest()).decode("ascii")
    handler.send_response(101);handler.send_header("Upgrade","websocket");handler.send_header("Connection","Upgrade");handler.send_header("Sec-WebSocket-Accept",accept);handler.end_headers()
    peer=WebSocketPeer(handler);hub.add(peer)
    try:
        peer.send({"type":"terminal_snapshot","terminals":terminal.list(),"output":dict(terminal.replay())})
        while True:
            raw=peer.recv()
            if raw is None:break
            try:dispatch(peer,json.loads(raw),terminal,scm)
            except Exception as exc:
                try:peer.send({"type":"terminal_error","error":str(exc)})
                except Exception:break
    except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError,OSError):pass
    finally:peer.closed=True;hub.remove(peer)
def dispatch(peer,msg,terminal,scm):
    if not isinstance(msg,dict):raise ValueError("message must be an object")
    typ=str(msg.get("type") or "")
    if typ=="terminal_sync":
        peer.send({"type":"terminal_snapshot","terminals":terminal.list(),"output":dict(terminal.replay())});return
    if typ=="terminal_create":
        terminal.create(str(msg.get("terminalId") or ""),str(msg.get("cwd") or ""),int(msg.get("cols") or 80),int(msg.get("rows") or 24),str(msg.get("title") or "Terminal"));return
    if typ=="terminal_run":
        terminal.run_command(str(msg.get("terminalId") or ""),str(msg.get("cwd") or ""),str(msg.get("command") or ""),str(msg.get("title") or "Command"),int(msg.get("cols") or 80),int(msg.get("rows") or 24));return
    if typ=="terminal_input":
        terminal.input(str(msg.get("terminalId") or ""),str(msg.get("data") or ""));return
    if typ=="terminal_key":
        mods=msg.get("modifiers") if isinstance(msg.get("modifiers"),dict) else {}
        terminal.key(str(msg.get("terminalId") or ""),str(msg.get("key") or ""),mods);return
    if typ=="terminal_resize":
        terminal.resize(str(msg.get("terminalId") or ""),int(msg.get("cols") or 80),int(msg.get("rows") or 24));return
    if typ=="terminal_rename":
        terminal.rename(str(msg.get("terminalId") or ""),str(msg.get("title") or ""));return
    if typ=="terminal_kill":
        terminal.kill(str(msg.get("terminalId") or ""));return
    kind={"scm_status":"status","scm_history":"history","scm_filediff":"filediff","scm_commit":"commit"}.get(typ)
    if kind:
        reply={"type":"scm_data","reqId":msg.get("reqId"),"kind":kind}
        try:reply.update({"ok":True,"data":scm.query(kind,str(msg.get("cwd") or ""),msg)})
        except Exception as exc:reply.update({"ok":False,"error":str(exc)})
        peer.send(reply);return
    raise ValueError("Unknown WebSocket message: "+typ)
