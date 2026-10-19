from __future__ import annotations
import json, os, socket, statistics, subprocess, sys, tempfile, threading, time, urllib.request
from pathlib import Path
import psutil

REPO=Path(r"E:\git-project\lantern")
BASE=REPO/".wt"/"test-foundation-baseline-turn2"
OUT=REPO/".plan"/"lantern-markdown-main-20261018"/"test_turn2_perf.json"

def reserve():
    with socket.socket() as s:
        s.bind(("127.0.0.1",0)); return s.getsockname()[1]

def req(base, ep):
    t=time.perf_counter()
    with urllib.request.urlopen(base+ep, timeout=10) as r:
        body=r.read(); assert r.status==200
    return (time.perf_counter()-t)*1000, len(body)

def pct(v,p=.95):
    x=sorted(v); return x[int((len(x)-1)*p)]

def tree_metrics(pid):
    try:
        p=psutil.Process(pid); ps=[p]+p.children(recursive=True)
    except psutil.Error:
        return (0.0,0)
    cpu=0.0; rss=0
    for q in ps:
        try:
            ct=q.cpu_times(); cpu+=ct.user+ct.system; rss+=q.memory_info().rss
        except psutil.Error: pass
    return cpu,rss

with tempfile.TemporaryDirectory(prefix="lantern-turn2-perf-", ignore_cleanup_errors=True) as td:
    td=Path(td); data=td/"files"; data.mkdir()
    for i in range(1000):
        (data/f"fixture_{i:04}.txt").write_text(f"Line {i}\n",encoding="utf-8")
    text="# Benchmark\n\n"+"".join(f"## Section {i}\n\n"+("Hello **Markdown**. "*17)+"\n\n" for i in range(250))
    (data/"long.md").write_text(text,encoding="utf-8",newline="\n")
    servers={}
    try:
        for name,entry,cwd in [
            ("baseline",BASE/"lan_drive.py",BASE),
            ("head",REPO/"main.py",REPO),
        ]:
            port=reserve(); base=f"http://127.0.0.1:{port}"
            w=td/name; w.mkdir()
            proc=subprocess.Popen([sys.executable,str(entry),"--root",str(data),"--host","127.0.0.1","--port",str(port),"--config",str(w/"cfg.yaml"),"--cache-dir",str(w/"cache")],
                cwd=cwd,env=dict(os.environ,LANTERN_WORK_DIR=str(w/"work")),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            for _ in range(150):
                try:
                    req(base,"/api/info"); break
                except Exception:
                    if proc.poll() is not None: raise RuntimeError(f"{name} exited {proc.returncode}")
                    time.sleep(.08)
            else: raise RuntimeError(f"{name} not ready")
            servers[name]=(proc,base)

        result={"python":sys.version,"baseline_sha":"1b5939357bfd3748a1c56b5e491bc55026b0368b","head_sha":"ffe3decb4469cff36bb98f8afd6ba8e9e89af089","data":{"files":1000,"markdown_bytes":(data/"long.md").stat().st_size},"workloads":{}}
        for title,ep,n in [("list","/api/list?p=/",120),("preview","/api/plugin/preview?p=long.md",60),("info","/api/info",120)]:
            for _ in range(8):
                for name in ("baseline","head"): req(servers[name][1],ep)
            lat={"baseline":[],"head":[]}; lengths={"baseline":set(),"head":set()}
            cpu0={}; rss_peak={}
            for name,(proc,base) in servers.items():
                cpu0[name],rss_peak[name]=tree_metrics(proc.pid)
            stop=False
            def sample():
                while not stop:
                    for name,(proc,_) in servers.items():
                        _,rss=tree_metrics(proc.pid); rss_peak[name]=max(rss_peak[name],rss)
                    time.sleep(.02)
            th=threading.Thread(target=sample,daemon=True); th.start()
            for i in range(n):
                order=("baseline","head") if i%2==0 else ("head","baseline")
                for name in order:
                    ms,ln=req(servers[name][1],ep); lat[name].append(ms); lengths[name].add(ln)
            stop=True; th.join(timeout=2)
            cpu1={name:tree_metrics(proc.pid)[0] for name,(proc,_) in servers.items()}
            row={"n":n}
            for name in ("baseline","head"):
                row[name]={"median_ms":statistics.median(lat[name]),"p95_ms":pct(lat[name]),"mean_ms":statistics.mean(lat[name]),"cpu_s":cpu1[name]-cpu0[name],"peak_tree_rss_bytes":rss_peak[name],"body_lengths":sorted(lengths[name])}
            row["ratios"]={"median":row["head"]["median_ms"]/row["baseline"]["median_ms"],"p95":row["head"]["p95_ms"]/row["baseline"]["p95_ms"],"cpu":(row["head"]["cpu_s"]/row["baseline"]["cpu_s"] if row["baseline"]["cpu_s"] else None),"rss":(row["head"]["peak_tree_rss_bytes"]/row["baseline"]["peak_tree_rss_bytes"] if row["baseline"]["peak_tree_rss_bytes"] else None)}
            result["workloads"][title]=row
        OUT.write_text(json.dumps(result,indent=2),encoding="utf-8")
        print(json.dumps(result,indent=2))
    finally:
        for proc,_ in servers.values():
            proc.terminate()
        for proc,_ in servers.values():
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)
