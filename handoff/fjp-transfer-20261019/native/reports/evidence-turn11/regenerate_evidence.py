from __future__ import annotations
import json, sys, tempfile
from pathlib import Path

ROOT = Path(r"E:\\git-project\\lantern\\.wt\\lantern-bot")
sys.path.insert(0, str(ROOT))

from lantern.terminal import TerminalManager
from lantern.ws import WebSocketHub, dispatch
from tests.test_pi_reconnect_e2e import (
    _CapturePty,
    _real_pi_exact_client_results,
    _real_pi_headless_cross_stack_results,
)

ROOT = Path(r"E:\git-project\lantern\.wt\lantern-bot")
raw_path = ROOT / ".plan" / "lantern-pi-native-20261018" / "evidence-turn4" / "pi-t002-g6-winconpty-raw.txt"
raw = raw_path.read_bytes()

class Peer:
    def __init__(self):
        self.subscriptions=set()
        self.messages=[]
        self.protocol="v2"
    def send(self, msg):
        self.messages.append(msg)

spawned={}
hub=WebSocketHub()
def factory(term_id,cwd,cols,rows,on_data,on_exit,command=None):
    p=_CapturePty(on_data,on_exit)
    spawned[term_id]=p
    return p

with tempfile.TemporaryDirectory(prefix="lantern-gap-evidence-") as td:
    manager=TerminalManager(Path(td),hub.broadcast,pty_factory=factory,flush_ms=0,max_output=8)
    manager.create("pi-gap",td,80,24,"Gap proof")
    spawned["pi-gap"].emit("SNAP")
    spawned["pi-gap"].emit("ABCDEFGHIJK")
    peer=Peer()
    hub.add(peer)
    dispatch(peer,{"type":"terminal_subscribe","terminalId":"pi-gap"},manager,None,hub)
    replay=next(m for m in peer.messages if m["type"]=="terminal_replay")
    gap={
        "output":replay["output"],
        "seq":replay["seq"],
        "truncated":replay["truncated"],
        "metaHasOutputOffset":"outputOffset" in replay["meta"],
        "metaHasOldestSeq":"oldestSeq" in replay["meta"],
        "metaHasTruncated":"truncated" in replay["meta"],
    }
    manager.kill("pi-gap")

result={
    "capture":{
        "bytes":len(raw),
        "crlfPairs":raw.count(bytes((13,10))),
        "cr":raw.count(bytes((13,))),
        "lf":raw.count(bytes((10,))),
        "utf8RoundTrip":raw.decode("utf-8").encode("utf-8")==raw,
    },
    "headlessNegative":_real_pi_headless_cross_stack_results(),
    "exactClient":_real_pi_exact_client_results(),
    "publicWsGap":gap,
}
out=ROOT/".plan"/"lantern-pi-native-20261018"/"evidence-turn11"/"pi-t003-byte-faithful-and-ws-gap.json"
out.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
print(json.dumps(result,indent=2,ensure_ascii=False))
