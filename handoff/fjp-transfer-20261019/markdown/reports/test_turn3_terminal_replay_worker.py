from __future__ import annotations
import argparse, json, os, statistics, sys, tempfile, threading, time
from pathlib import Path
import psutil

parser=argparse.ArgumentParser()
parser.add_argument("--tree",required=True)
parser.add_argument("--iterations",type=int,default=400)
parser.add_argument("--warmup",type=int,default=20)
args=parser.parse_args()
tree=Path(args.tree).resolve()
sys.path.insert(0,str(tree))

from lantern.terminal import TerminalManager
from lantern.ws import WebSocketHub, dispatch, _frame

PAYLOAD_BYTES=200*1024
payload="R"*PAYLOAD_BYTES
assert len(payload.encode("utf-8"))==PAYLOAD_BYTES

class FakePty:
    def __init__(self,on_data,on_exit):
        self.on_data=on_data; self.on_exit=on_exit
    def emit(self,s): self.on_data(s)
    def close(self,graceful=True): pass
    def write(self,data): pass
    def resize(self,cols,rows): pass

class Peer:
    def __init__(self):
        self.subscriptions=set()
        self.protocol="v2"
        self.frames=[]
        self.last_payload=None
    def send(self,msg):
        raw=json.dumps(msg,ensure_ascii=False,separators=(",",":")).encode("utf-8")
        self.frames.append(_frame(0x1,raw))
        self.last_payload=msg
    def can_terminal(self): return True
    def close(self): pass

def pct(vals,p=.95):
    vals=sorted(vals)
    return vals[int((len(vals)-1)*p)]

proc=psutil.Process(os.getpid())
def tree_rss():
    total=0
    try:
        group=[proc]+proc.children(recursive=True)
    except psutil.Error:
        group=[proc]
    for item in group:
        try: total+=item.memory_info().rss
        except psutil.Error: pass
    return total

with tempfile.TemporaryDirectory(prefix="lantern-replay-bench-",ignore_cleanup_errors=True) as td:
    hub=WebSocketHub(); ptys={}
    def factory(tid,cwd,cols,rows,on_data,on_exit,command=None):
        p=FakePty(on_data,on_exit); ptys[tid]=p; return p
    manager=TerminalManager(Path(td),hub.broadcast,pty_factory=factory,max_output=PAYLOAD_BYTES)
    manager.create("bench",td)
    ptys["bench"].emit(payload)
    meta,retained,seq=manager.replay_one("bench")
    assert len(retained.encode("utf-8"))==PAYLOAD_BYTES
    assert seq==1
    peer=Peer(); hub.add(peer)
    for _ in range(args.warmup):
        peer.frames.clear(); peer.last_payload=None
        dispatch(peer,{"type":"terminal_subscribe","terminalId":"bench"},manager,None,hub)
        assert peer.last_payload["type"]=="terminal_replay"
        assert len(peer.last_payload["output"].encode("utf-8"))==PAYLOAD_BYTES
    cpu0=proc.cpu_times(); rss_peak=tree_rss(); stop=False
    def sample():
        global rss_peak
        while not stop:
            rss=tree_rss()
            if rss>rss_peak:rss_peak=rss
            time.sleep(.001)
    th=threading.Thread(target=sample,daemon=True); th.start()
    samples=[]; encoded_sizes=[]
    for _ in range(args.iterations):
        peer.frames.clear(); peer.last_payload=None
        t0=time.perf_counter_ns()
        dispatch(peer,{"type":"terminal_subscribe","terminalId":"bench"},manager,None,hub)
        samples.append((time.perf_counter_ns()-t0)/1_000_000)
        assert peer.last_payload["type"]=="terminal_replay"
        assert len(peer.last_payload["output"].encode("utf-8"))==PAYLOAD_BYTES
        assert peer.last_payload["seq"]==1
        encoded_sizes.append(len(peer.frames[-1]))
    stop=True; th.join(timeout=2)
    cpu1=proc.cpu_times()
    out={
      "tree":str(tree),
      "payload_bytes":PAYLOAD_BYTES,
      "iterations":args.iterations,
      "warmup":args.warmup,
      "median_ms":statistics.median(samples),
      "p95_ms":pct(samples,.95),
      "mean_ms":statistics.mean(samples),
      "min_ms":min(samples),
      "max_ms":max(samples),
      "cpu_s":(cpu1.user+cpu1.system)-(cpu0.user+cpu0.system),
      "peak_tree_rss_bytes":rss_peak,
      "encoded_frame_bytes_min":min(encoded_sizes),
      "encoded_frame_bytes_max":max(encoded_sizes),
      "retained_bytes":len(retained.encode("utf-8")),
      "seq":seq,
      "samples_ms":samples,
    }
    print(json.dumps(out))
