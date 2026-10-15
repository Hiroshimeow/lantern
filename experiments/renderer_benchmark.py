"""Browser comparison: fast Python Preview vs Milkdown mounted as read-only.

No files are changed. Run when Chromium/Edge policy permits loopback browsing.
Outputs JSON; UNAVAILABLE is a result, NOT a performance PASS or FAIL.
"""
import json
import os
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SIZES=[5*1024,41*1024,70*1024,500*1024,int(4.9*1024*1024)]

def make_document(size):
    text='# Benchmark: Markdown Preview\n\n'
    block=('## Section & headings\n\n'+'This paragraph has **bold**, _italic_, escapes \\_ and [links](#section).\n\n'
           +'| Name | Description | Value |\n|---|---|---|\n'
           +'| Cell1 | Cell2 | Cell3 |\n\n'+'```python\nprint("hello")\n```\n\n')
    while len(text.encode('utf8')) + len(block.encode('utf8')) < size:
        text+=block
    text+=('x'*(max(0,size-len(text.encode('utf8')))))
    return text

def percentile(values,q):
    if not values:return None
    values=sorted(values)
    return round(values[min(len(values)-1,int((len(values)-1)*q))],2)

def main():
    from playwright.sync_api import sync_playwright
    runs=max(1,min(20,int(os.environ.get('LANTERN_BENCH_RUNS','20'))))
    sizes=[int(x) for x in os.environ.get('LANTERN_BENCH_SIZES',','.join(map(str,SIZES))).split(',')]
    with tempfile.TemporaryDirectory(prefix='lantern-render-bench-') as root:
        root=Path(root)
        for size in sizes:
            (root/f'doc-{size}.md').write_text(make_document(size),encoding='utf-8')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        proc=subprocess.Popen([sys.executable,str(ROOT/'lan_drive.py'),'--host','127.0.0.1',
             '--root',str(root),'--port',str(port)],cwd=ROOT,
             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            with sync_playwright() as play:
                browser_options={'headless':True}
                if os.environ.get('LANTERN_CHROMIUM'):
                    browser_options['executable_path']=os.environ['LANTERN_CHROMIUM']
                elif os.name=='nt':
                    browser_options['channel']='msedge'
                else:
                    browser_options.update(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
                b=play.chromium.launch(**browser_options)
                try:
                    page=b.new_page()
                    try:page.goto('http://127.0.0.1:'+str(port)+'/api/info',timeout=6000)
                    except Exception as e:
                        print(json.dumps({'status':'UNAVAILABLE','reason':str(e)[:230],
                            'note':'No browser benchmark measurements can be inferred from this run.'}))
                        return 2
                    results=[]
                    for size in sizes:
                        values=[];fails=[]
                        for repeat in range(runs):
                            page=b.new_page()
                            url=f'http://127.0.0.1:{port}/api/plugin/preview?p=doc-{size}.md'
                            try:
                                page.goto(url,wait_until='domcontentloaded',timeout=30000)
                                # Time excludes server startup. This is DOM-ready elapsed
                                # navigation + first visible heading; not equivalent to FCP.
                                baseline=page.evaluate("() => {const p=performance.getEntriesByType('navigation')[0];return p?.domContentLoadedEventEnd || -1}")
                                if size>600000:
                                    # plugin.py deliberately truncates text; parity requires full text.
                                    truncated=True
                                else:truncated=False
                                page.evaluate("""() => {
                                    const original=window.fetch.bind(window);
                                    window.fetch=(url,options={})=>{
                                        if(String(options.method||'GET').toUpperCase()!=='GET')
                                            throw Error('Benchmark read-only: POST prohibited');
                                        return original(url,options);
                                    };
                                }""")
                                performance_start=time.monotonic()
                                page.evaluate("""async () => {
                                    await window.__lanternMdVisual.open('visual');
                                    const pm=document.querySelector('.md-visual-host .ProseMirror');
                                    if(!pm) throw Error('ProseMirror failed to mount');
                                    pm.setAttribute('contenteditable','false');
                                }""")
                                pm_elapsed=(time.monotonic()-performance_start)*1000
                                metrics=page.evaluate("""() => ({
                                  nodes:document.querySelectorAll('*').length,
                                  heap:performance.memory?.usedJSHeapSize ?? null,
                                  markdownLength:window.__lanternMdVisual.state.instance?.getMarkdown()?.length ?? -1,
                                  mount:window.__lanternMdMetrics?.loadMs ?? null,
                                })""")
                                values.append({'previewDomMs':baseline,'pmMountMs':pm_elapsed,
                                               'truncatedBaseline':truncated,**metrics})
                            except Exception as err:fails.append(str(err)[:250])
                            finally:page.close()
                        valid=[v for v in values if v['previewDomMs']>=0]
                        results.append({'sizeBytes':size,'runs':len(valid),'fails':fails[:2],
                           'baselineP50':percentile([v['previewDomMs'] for v in valid],.5),
                           'baselineP95':percentile([v['previewDomMs'] for v in valid],.95),
                           'pmP50':percentile([v['pmMountMs'] for v in valid],.5),
                           'pmP95':percentile([v['pmMountMs'] for v in valid],.95),
                           'previewTruncated':size>600000,'samples':valid[:1]})
                    print(json.dumps({'status':'MEASURED','results':results},indent=2))
                finally:b.close()
        finally:
            proc.terminate()
            try:proc.wait(timeout=6)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
    return 0

if __name__=='__main__':raise SystemExit(main())
