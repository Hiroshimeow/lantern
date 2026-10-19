from __future__ import annotations
import json, os, socket, statistics, subprocess, sys, tempfile, threading, time, urllib.request
from pathlib import Path
import psutil
REPO=Path(r"E:\git-project\lantern"); BASE=REPO/".wt"/"test-foundation-baseline-turn3"
OUT=REPO/".plan"/"lantern-markdown-main-20261018"/"test_turn3_preview_repeats.json"
TARGET=100*1024

def pct(v,p=.95):
    v=sorted(v); return v[int((len(v)-1)*p)]
def reserve():
    with socket.socket() as s: s.bind(("127.0.0.1",0)); return s.getsockname()[1]
def req(base,ep):
    t=time.perf_counter_ns()
    with urllib.request.urlopen(base+ep,timeout=10) as r: b=r.read(); assert r.status==200
    return (time.perf_counter_ns()-t)/1_000_000,len(b)
def metrics(pid):
    cpu=0.0;rss=0
    try: ps=[psutil.Process(pid)]+psutil.Process(pid).children(recursive=True)
    except psutil.Error:return cpu,rss
    for p in ps:
        try:
            c=p.cpu_times();cpu+=c.user+c.system;rss+=p.memory_info().rss
        except psutil.Error:pass
    return cpu,rss
def md():
    x=b"# Exact 100 KiB\n\n"; i=0
    while len(x)<TARGET:
        block=(f"## S{i}\n\nText **bold** row {i} | a | b | c |\n\n").encode()
        x += block[:TARGET-len(x)]
        i+=1
    assert len(x)==TARGET; return x

rounds=[]
for round_no in range(3):
    with tempfile.TemporaryDirectory(prefix=f"lantern-turn3-r{round_no}-",ignore_cleanup_errors=True) as td:
        td=Path(td);root=td/"files";root.mkdir();raw=md();(root/"x.md").write_bytes(raw)
        order_launch=[("baseline",BASE/"lan_drive.py",BASE),("head",REPO/"main.py",REPO)]
        if round_no%2: order_launch=list(reversed(order_launch))
        servers={}
        try:
            for name,entry,cwd in order_launch:
                port=reserve();base=f"http://127.0.0.1:{port}";home=td/name;home.mkdir()
                p=subprocess.Popen([sys.executable,str(entry),"--root",str(root),"--host","127.0.0.1","--port",str(port),"--config",str(home/"cfg.yaml"),"--cache-dir",str(home/"cache")],cwd=cwd,env=dict(os.environ,LANTERN_WORK_DIR=str(home/"work")),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                for _ in range(180):
                    try:req(base,"/api/info");break
                    except Exception:
                        if p.poll() is not None:raise RuntimeError(f"{name} exit {p.returncode}")
                        time.sleep(.07)
                else:raise RuntimeError(f"{name} startup")
                servers[name]=(p,base)
            ep="/api/plugin/preview?p=x.md"
            for _ in range(10):
                for name in ("baseline","head"):req(servers[name][1],ep)
            vals={"baseline":[],"head":[]}; lens={"baseline":set(),"head":set()}
            c0={};peak={}
            for name,(p,_) in servers.items():c0[name],peak[name]=metrics(p.pid)
            stop=False
            def sample():
                while not stop:
                    for name,(p,_) in servers.items():
                        _,r=metrics(p.pid);peak[name]=max(peak[name],r)
                    time.sleep(.01)
            th=threading.Thread(target=sample,daemon=True);th.start()
            n=60
            for i in range(n):
                req_order=("baseline","head") if (i+round_no)%2==0 else ("head","baseline")
                for name in req_order:
                    ms,ln=req(servers[name][1],ep);vals[name].append(ms);lens[name].add(ln)
            stop=True;th.join(timeout=2)
            c1={name:metrics(p.pid)[0] for name,(p,_) in servers.items()}
            row={"round":round_no+1,"launch_order":[x[0] for x in order_launch],"fixture_bytes":len(raw),"n":n}
            for name in ("baseline","head"):
                row[name]={"median_ms":statistics.median(vals[name]),"p95_ms":pct(vals[name]),"mean_ms":statistics.mean(vals[name]),"cpu_s":c1[name]-c0[name],"peak_tree_rss_bytes":peak[name],"body_lengths":sorted(lens[name])}
            row["ratios"]={"median":row["head"]["median_ms"]/row["baseline"]["median_ms"],"p95":row["head"]["p95_ms"]/row["baseline"]["p95_ms"],"cpu":row["head"]["cpu_s"]/row["baseline"]["cpu_s"],"rss":row["head"]["peak_tree_rss_bytes"]/row["baseline"]["peak_tree_rss_bytes"]}
            rounds.append(row)
        finally:
            for p,_ in servers.values():p.terminate()
            for p,_ in servers.values():
                try:p.wait(timeout=5)
                except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
out={"rounds":rounds,"p95_ratios":[r["ratios"]["p95"] for r in rounds],"median_p95_ratio":statistics.median(r["ratios"]["p95"] for r in rounds),"all_body_parity":all(r["baseline"]["body_lengths"]==r["head"]["body_lengths"] for r in rounds)}
OUT.write_text(json.dumps(out,indent=2),encoding="utf-8");print(json.dumps(out,indent=2))
