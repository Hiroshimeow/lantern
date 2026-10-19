from __future__ import annotations
import json, os, socket, statistics, subprocess, sys, tempfile, time, urllib.parse, urllib.request
import psutil
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'.plan'/'dev_turn4_ma11_tiny.json'
OUT.parent.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='lantern-ma11-dev-') as td:
    td=Path(td); files=td/'files'; files.mkdir()
    (files/'plain.md').write_text('# Plain\n\nNo diagram.\n',encoding='utf-8')
    fence=chr(96)*3
    (files/'mermaid.md').write_text('# Diagram\n\n'+fence+'mermaid\nflowchart LR\n A[Begin] --> B[End]\n'+fence+'\n',encoding='utf-8')
    with socket.socket() as s:
        s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    env=dict(os.environ,LANTERN_WORK_DIR=str(td/'work'))
    proc=subprocess.Popen([sys.executable,str(ROOT/'main.py'),'--root',str(files),'--host','127.0.0.1','--port',str(port),
        '--config',str(td/'config.yaml'),'--cache-dir',str(td/'cache')],cwd=ROOT,env=env,
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                with urllib.request.urlopen(base+'/api/info',timeout=.5) as r:
                    if r.status==200: break
            except Exception: time.sleep(.1)
        else: raise RuntimeError('server not ready')
        samples=[]
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='chrome',headless=True)
            version=browser.version
            try:
                for idx in range(1,10):
                    idle_load = None
                    for _ in range(40):
                        idle_load = psutil.cpu_percent(interval=0.25)
                        if idle_load < 15:
                            break
                    ctx=browser.new_context(viewport={'width':1200,'height':800})
                    page=ctx.new_page(); requests=[]; errors=[]
                    page.on('request',lambda r,requests=requests: requests.append(r.url))
                    page.on('pageerror',lambda e,errors=errors: errors.append(str(e)))
                    page.add_init_script("""(() => {
                      const realSetTimeout = window.setTimeout.bind(window);
                      window.__maGate={held:false,item:null}; window.__maLong=[]; new PerformanceObserver(list=>{for(const e of list.getEntries()) window.__maLong.push({start:e.startTime,duration:e.duration});}).observe({entryTypes:['longtask']});
                      window.setTimeout=function(fn,delay,...args){
                        if(!window.__maGate.held && Number(delay||0)===0 && window.mermaid && typeof fn==='function'){
                          window.__maGate.held=true; window.__maGate.item={fn,args}; return 2147483000;
                        }
                        return realSetTimeout(fn,delay,...args);
                      };
                      window.__maRelease=()=>{
                        const item=window.__maGate.item; window.__maGate.item=null;
                        if(item) realSetTimeout(()=>item.fn(...item.args),0);
                      };
                    })()""")
                    cdp=ctx.new_cdp_session(page); cdp.send('Performance.enable')
                    page.goto(base+'/api/plugin/preview?p=plain.md',wait_until='networkidle',timeout=20000)
                    plain_metrics={m['name']:m['value'] for m in cdp.send('Performance.getMetrics')['metrics']}
                    plain_ms=plain_metrics.get('ScriptDuration',0)*1000
                    plain_bundle=sum('mermaid-11.17.2.min.js' in u for u in requests)
                    requests.clear()
                    page.goto(base+'/api/plugin/preview?p=mermaid.md',wait_until='domcontentloaded',timeout=30000)
                    page.wait_for_function("() => window.__maGate?.held===true",timeout=20000)
                    gated={m['name']:m['value'] for m in cdp.send('Performance.getMetrics')['metrics']}
                    gated_ms=gated.get('ScriptDuration',0)*1000
                    page.evaluate("""() => {
                      window.__maInit=[];
                      window.__maParse=[];
                      window.__maRender=[]; window.__maRenderWindows=[];
                      const origInit=window.mermaid.initialize.bind(window.mermaid);
                      window.mermaid.initialize=(...a)=>{const t=performance.now(); try{return origInit(...a)} finally{window.__maInit.push(performance.now()-t)}};
                      const origParse=window.mermaid.parse.bind(window.mermaid);
                      window.mermaid.parse=async(...a)=>{const t=performance.now(); try{return await origParse(...a)} finally{window.__maParse.push(performance.now()-t)}};
                      const origRender=window.mermaid.render.bind(window.mermaid);
                      window.mermaid.render=async(...a)=>{const t=performance.now(); try{return await origRender(...a)} finally{const end=performance.now(); window.__maRender.push(end-t); window.__maRenderWindows.push({start:t,end})}};
                      window.__maRelease();
                    }""")
                    page.locator('.mermaid-output svg').first.wait_for(timeout=20000)
                    vals=page.evaluate("() => ({init:window.__maInit,parse:window.__maParse,render:window.__maRender,renderWindows:window.__maRenderWindows,long:window.__maLong})")
                    origin=urllib.parse.urlsplit(base)
                    external=[]
                    for u in requests:
                        p=urllib.parse.urlsplit(u)
                        if p.scheme in ('http','https') and p.netloc!=origin.netloc: external.append(u)
                    samples.append({
                      'index':idx,'pre_context_cpu_percent':idle_load,'plain_script_ms':plain_ms,'plain_bundle_requests':plain_bundle,
                      'gated_script_total_ms':gated_ms,'bundle_attributed_script_ms':max(0,gated_ms-plain_ms),
                      'initialize_ms':max(vals['init'] or [0]),'parse_ms':max(vals['parse'] or [0]),'render_ms':max(vals['render'] or [0]),'render_longtask_ms':max(([e['duration'] for e in vals['long'] if any(e['start'] < w['end'] and e['start']+e['duration'] > w['start'] for w in vals['renderWindows'])] or [0])),
                      'mermaid_bundle_requests_total':sum('mermaid-11.17.2.min.js' in u for u in requests),
                      'external_requests':external,'page_errors':errors})
                    ctx.close()
            finally: browser.close()
        bundle=[x['bundle_attributed_script_ms'] for x in samples]
        result={'browser_channel':'chrome','browser_version':version,'samples':samples,'summary':{
          'bundle_median_ms':statistics.median(bundle),'bundle_max_ms':max(bundle),
          'initialize_max_ms':max(x['initialize_ms'] for x in samples),
          'parse_max_ms':max(x['parse_ms'] for x in samples),
          'render_max_ms':max(x['render_ms'] for x in samples),'render_longtask_max_ms':max(x['render_longtask_ms'] for x in samples),
          'all_plain_zero_bundle':all(x['plain_bundle_requests']==0 for x in samples),
          'all_mermaid_one_bundle':all(x['mermaid_bundle_requests_total']==1 for x in samples),
          'all_external_zero':all(not x['external_requests'] for x in samples),
          'all_errors_zero':all(not x['page_errors'] for x in samples)}}
        OUT.write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
    finally:
        proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)
