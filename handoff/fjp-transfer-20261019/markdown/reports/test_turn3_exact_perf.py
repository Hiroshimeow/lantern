from __future__ import annotations
import json, os, socket, statistics, subprocess, sys, tempfile, threading, time, urllib.request
from pathlib import Path
import psutil

REPO=Path(r"E:\git-project\lantern")
BASE=REPO/".wt"/"test-foundation-baseline-turn3"
OUT=REPO/".plan"/"lantern-markdown-main-20261018"/"test_turn3_exact_perf.json"
WORKER=REPO/".plan"/"lantern-markdown-main-20261018"/"test_turn3_terminal_replay_worker.py"
BASE_SHA="1b5939357bfd3748a1c56b5e491bc55026b0368b"
HEAD_SHA="ffe3decb4469cff36bb98f8afd6ba8e9e89af089"
TARGET_MD_BYTES=100*1024

def pct(vals,p=.95):
    vals=sorted(vals)
    return vals[int((len(vals)-1)*p)]

def reserve():
    with socket.socket() as s:
        s.bind(("127.0.0.1",0)); return s.getsockname()[1]

def request(base,ep):
    t0=time.perf_counter_ns()
    with urllib.request.urlopen(base+ep,timeout=10) as r:
        body=r.read(); assert r.status==200
    return (time.perf_counter_ns()-t0)/1_000_000,len(body)

def tree_metrics(pid):
    cpu=0.0;rss=0
    try: items=[psutil.Process(pid)]+psutil.Process(pid).children(recursive=True)
    except psutil.Error: return cpu,rss
    for p in items:
        try:
            ct=p.cpu_times();cpu+=ct.user+ct.system;rss+=p.memory_info().rss
        except psutil.Error: pass
    return cpu,rss

def exact_markdown():
    chunks=[b"# Exact 100 KiB Markdown Preview\n\n"]
    i=0
    while sum(map(len,chunks)) < TARGET_MD_BYTES:
        block=(f"## Section {i}\n\nHello **Markdown** {i}. | alpha | beta | gamma |\n\n").encode("ascii")
        remaining=TARGET_MD_BYTES-sum(map(len,chunks))
        if len(block)<=remaining:
            chunks.append(block)
        else:
            chunks.append(b"x"*remaining)
        i+=1
    data=b"".join(chunks)
    assert len(data)==TARGET_MD_BYTES
    return data

result={
 "identity":{"python":sys.version,"baseline_sha":BASE_SHA,"head_sha":HEAD_SHA},
 "preview_100k":{},
 "terminal_replay_200k":{}
}

# Exact 100 KiB Preview paired benchmark.
with tempfile.TemporaryDirectory(prefix="lantern-turn3-preview-",ignore_cleanup_errors=True) as td:
    td=Path(td);root=td/"files";root.mkdir()
    md=exact_markdown(); (root/"exact100k.md").write_bytes(md)
    servers={}
    try:
        for name,entry,cwd in [
            ("baseline",BASE/"lan_drive.py",BASE),
            ("head",REPO/"main.py",REPO),
        ]:
            port=reserve();base=f"http://127.0.0.1:{port}"
            home=td/name;home.mkdir()
            proc=subprocess.Popen([sys.executable,str(entry),"--root",str(root),"--host","127.0.0.1","--port",str(port),"--config",str(home/"cfg.yaml"),"--cache-dir",str(home/"cache")],
                cwd=cwd,env=dict(os.environ,LANTERN_WORK_DIR=str(home/"work")),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            for _ in range(180):
                try:
                    request(base,"/api/info");break
                except Exception:
                    if proc.poll() is not None: raise RuntimeError(f"{name} exited {proc.returncode}")
                    time.sleep(.07)
            else: raise RuntimeError(f"{name} not ready")
            servers[name]=(proc,base)
        endpoint="/api/plugin/preview?p=exact100k.md"
        for _ in range(10):
            for name in ("baseline","head"):request(servers[name][1],endpoint)
        lat={"baseline":[],"head":[]};lengths={"baseline":set(),"head":set()}
        cpu0={};rss_peak={}
        for name,(proc,_) in servers.items():
            cpu0[name],rss_peak[name]=tree_metrics(proc.pid)
        stop=False
        def sample_rss():
            while not stop:
                for name,(proc,_) in servers.items():
                    _,rss=tree_metrics(proc.pid);rss_peak[name]=max(rss_peak[name],rss)
                time.sleep(.01)
        th=threading.Thread(target=sample_rss,daemon=True);th.start()
        n=80
        for i in range(n):
            order=("baseline","head") if i%2==0 else ("head","baseline")
            for name in order:
                ms,ln=request(servers[name][1],endpoint)
                lat[name].append(ms);lengths[name].add(ln)
        stop=True;th.join(timeout=2)
        cpu1={name:tree_metrics(proc.pid)[0] for name,(proc,_) in servers.items()}
        row={"fixture_bytes":len(md),"n_per_side":n}
        for name in ("baseline","head"):
            row[name]={
              "median_ms":statistics.median(lat[name]),
              "p95_ms":pct(lat[name]),
              "mean_ms":statistics.mean(lat[name]),
              "cpu_s":cpu1[name]-cpu0[name],
              "peak_tree_rss_bytes":rss_peak[name],
              "body_lengths":sorted(lengths[name]),
              "samples_ms":lat[name],
            }
        row["ratios"]={
          "median":row["head"]["median_ms"]/row["baseline"]["median_ms"],
          "p95":row["head"]["p95_ms"]/row["baseline"]["p95_ms"],
          "cpu":row["head"]["cpu_s"]/row["baseline"]["cpu_s"] if row["baseline"]["cpu_s"] else None,
          "rss":row["head"]["peak_tree_rss_bytes"]/row["baseline"]["peak_tree_rss_bytes"] if row["baseline"]["peak_tree_rss_bytes"] else None,
        }
        row["body_parity"]=row["baseline"]["body_lengths"]==row["head"]["body_lengths"]
        result["preview_100k"]=row
    finally:
        for proc,_ in servers.values():proc.terminate()
        for proc,_ in servers.values():
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)

# 200 KiB replay through TerminalManager + WS dispatch/serialization.
runs={"baseline":[],"head":[]}
order=["baseline","head","head","baseline"]
trees={"baseline":BASE,"head":REPO}
for name in order:
    cp=subprocess.run([sys.executable,str(WORKER),"--tree",str(trees[name]),"--iterations","400","--warmup","25"],
        cwd=REPO,text=True,capture_output=True,timeout=90)
    if cp.returncode!=0:
        raise RuntimeError(f"terminal worker {name} failed: {cp.stderr[-2000:]} {cp.stdout[-2000:]}")
    runs[name].append(json.loads(cp.stdout.strip().splitlines()[-1]))

agg={"payload_bytes":200*1024,"runs":runs}
for name in ("baseline","head"):
    samples=[x for run in runs[name] for x in run["samples_ms"]]
    agg[name]={
      "runs_count":len(runs[name]),
      "iterations_total":len(samples),
      "median_ms":statistics.median(samples),
      "p95_ms":pct(samples),
      "mean_ms":statistics.mean(samples),
      "cpu_s_total":sum(run["cpu_s"] for run in runs[name]),
      "cpu_s_per_400_mean":statistics.mean(run["cpu_s"] for run in runs[name]),
      "peak_tree_rss_bytes_max":max(run["peak_tree_rss_bytes"] for run in runs[name]),
      "encoded_frame_bytes":sorted({run["encoded_frame_bytes_min"] for run in runs[name]}|{run["encoded_frame_bytes_max"] for run in runs[name]}),
      "retained_bytes":sorted({run["retained_bytes"] for run in runs[name]}),
    }
agg["ratios"]={
 "median":agg["head"]["median_ms"]/agg["baseline"]["median_ms"],
 "p95":agg["head"]["p95_ms"]/agg["baseline"]["p95_ms"],
 "cpu":agg["head"]["cpu_s_total"]/agg["baseline"]["cpu_s_total"] if agg["baseline"]["cpu_s_total"] else None,
 "rss":agg["head"]["peak_tree_rss_bytes_max"]/agg["baseline"]["peak_tree_rss_bytes_max"] if agg["baseline"]["peak_tree_rss_bytes_max"] else None,
}
result["terminal_replay_200k"]=agg
OUT.write_text(json.dumps(result,indent=2),encoding="utf-8")
print(json.dumps(result,indent=2))
