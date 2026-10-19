from __future__ import annotations
import os,socket,subprocess,sys,tempfile,time,urllib.request,json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(r'E:\\git-project\\lantern')
fence=chr(96)*3
md='# Gantt inspect\n\n'+fence+'mermaid\ngantt\n title Release\n dateFormat YYYY-MM-DD\n section Demo\n Task A :a1, 2026-10-18, 2d\n'+fence+'\n'
with tempfile.TemporaryDirectory(prefix='lantern-gantt-inspect-') as td:
    td=Path(td); root=td/'files'; root.mkdir(); (root/'g.md').write_text(md,encoding='utf-8')
    with socket.socket() as s: s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    proc=subprocess.Popen([sys.executable,str(ROOT/'main.py'),'--root',str(root),'--host','127.0.0.1','--port',str(port),'--config',str(td/'config.yaml'),'--cache-dir',str(td/'cache')],cwd=ROOT,env={**os.environ,'LANTERN_WORK_DIR':str(td/'work')},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(base+'/api/info',timeout=.5): break
            except OSError: time.sleep(.1)
        with sync_playwright() as pw:
            b=pw.chromium.launch(channel='msedge',headless=True); p=b.new_page(viewport={'width':1200,'height':800})
            p.goto(base+'/api/plugin/preview?p=g.md',wait_until='domcontentloaded')
            p.locator('.mermaid-output svg').wait_for(timeout=20000)
            data=p.locator('.mermaid-output svg').evaluate("""svg => ({
              outer: svg.outerHTML.slice(0,30000),
              viewBox: svg.getAttribute('viewBox'),
              width: svg.getAttribute('width'),
              height: svg.getAttribute('height'),
              rect: svg.getBoundingClientRect().toJSON(),
              texts: [...svg.querySelectorAll('text')].map(t=>({text:t.textContent, cls:t.getAttribute('class'), style:t.getAttribute('style'), fs:getComputedStyle(t).fontSize, x:t.getAttribute('x'), y:t.getAttribute('y')}))
            })""")
            print(json.dumps(data,indent=2,ensure_ascii=False))
            b.close()
    finally:
        proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill()
