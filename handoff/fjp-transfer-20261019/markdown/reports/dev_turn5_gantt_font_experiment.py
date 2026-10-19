from __future__ import annotations
import os,socket,subprocess,sys,tempfile,time,urllib.request,json
from pathlib import Path
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(r'E:\\git-project\\lantern')
types=[('flowchart','flowchart LR\n A[Begin] --> B[End]'),('sequence','sequenceDiagram\n Alice->>Bob: Hello\n Bob-->>Alice: Ack'),('class','classDiagram\n Animal <|-- Dog\n class Dog { +bark() }'),('state','stateDiagram-v2\n [*] --> Ready\n Ready --> [*]'),('er','erDiagram\n CUSTOMER ||--o{ ORDER : places'),('gantt','gantt\n title Release\n dateFormat YYYY-MM-DD\n section Demo\n Task A :a1, 2026-10-18, 2d'),('pie','pie title Shares\n "Alpha" : 40\n "Beta" : 60')]
fence=lambda code:'\n'+chr(96)*3+'mermaid\n'+code+'\n'+chr(96)*3+'\n'
with tempfile.TemporaryDirectory(prefix='lantern-print-exp-') as td:
    td=Path(td); root=td/'files'; root.mkdir()
    body='# Mermaid acceptance\n\nPrintable sentinel 001 TEST.\n'+''.join('\n## '+k+'\n'+fence(c) for k,c in types)
    (root/'m.md').write_text(body,encoding='utf-8')
    with socket.socket() as s: s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    proc=subprocess.Popen([sys.executable,str(ROOT/'main.py'),'--root',str(root),'--host','127.0.0.1','--port',str(port),'--config',str(td/'config.yaml'),'--cache-dir',str(td/'cache')],cwd=ROOT,env={**os.environ,'LANTERN_WORK_DIR':str(td/'work')},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(base+'/api/info',timeout=.5): break
            except OSError: time.sleep(.1)
        with sync_playwright() as pw:
            b=pw.chromium.launch(channel='msedge',headless=True); p=b.new_page(viewport={'width':1280,'height':900})
            p.goto(base+'/api/plugin/preview?p=m.md',wait_until='domcontentloaded')
            p.wait_for_function("() => document.querySelectorAll('.mermaid-diagram.mermaid-ok').length===7",timeout=30000)
            css="@media print{.mermaid-output svg[aria-roledescription='gantt'] text{font-size:20px!important}.mermaid-output svg[aria-roledescription='gantt'] .titleText{font-size:24px!important}}"
            p.add_style_tag(content=css)
            out=ROOT/'.plan'/'lantern-markdown-main-20261018'/'dev_turn5_gantt_font_experiment.pdf'
            p.pdf(path=str(out),format='A4',print_background=True)
            b.close()
        with fitz.open(out) as d:
            rows=[]
            for i,page in enumerate(d):
                for block in page.get_text('dict')['blocks']:
                    for line in block.get('lines',[]):
                        for span in line.get('spans',[]):
                            txt=span.get('text','').strip()
                            if txt in {'Task A','Demo','Release','2026-10-18','2026-10-19','2026-10-20'}:
                                rows.append({'page':i+1,'text':txt,'size':span['size'],'bbox':span['bbox']})
            print(json.dumps({'pages':len(d),'rows':rows},indent=2))
    finally:
        proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill()
