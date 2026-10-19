import json, os, re, socket, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
from PIL import Image
import fitz
from playwright.sync_api import sync_playwright
REPO=Path(__file__).resolve().parents[2]
OUT=Path(__file__).with_name("test_turn1_markdown_artifacts"); OUT.mkdir(exist_ok=True)
evidence={"identity":{"repo":str(REPO),"python":sys.version,"time":time.strftime("%Y-%m-%dT%H:%M:%S%z"),"browser":"msedge headless"},"checks":{},"errors":[]}
types=[
 ("flowchart","flowchart LR\n A[Begin] --> B[End]"),
 ("sequence","sequenceDiagram\n Alice->>Bob: Hello\n Bob-->>Alice: Ack"),
 ("class","classDiagram\n Animal <|-- Dog\n class Dog { +bark() }"),
 ("state","stateDiagram-v2\n [*] --> Ready\n Ready --> [*]"),
 ("er","erDiagram\n CUSTOMER ||--o{ ORDER : places"),
 ("gantt","gantt\n title Release\n dateFormat YYYY-MM-DD\n section Demo\n Task A :a1, 2026-10-18, 2d"),
 ("pie","pie title Shares\n \"Alpha\" : 40\n \"Beta\" : 60")]
def fence(code):return "\n"+chr(96)*3+"mermaid\n"+code+"\n"+chr(96)*3+"\n"
with tempfile.TemporaryDirectory(prefix="lantern-test-markdown-") as td:
 root=Path(td)/"files";root.mkdir()
 body="# Mermaid acceptance\n\nPrintable sentinel 001 TEST.\n"
 for key,code in types:body+="\n## "+key+"\n"+fence(code)
 (root/"mermaid-7.md").write_text(body,encoding="utf-8")
 (root/"plain.md").write_text("# Plain\n\nNo diagram.",encoding="utf-8")
 (root/"probe-evil.js").write_text("window.__lanternEvilExecuted=true;",encoding="utf-8")
 invalid="# Limits\n"+fence("flowchart ZZ\n A--->")+fence("flowchart LR\n X-->Y")
 invalid+=fence("flowchart LR\n X["+"x"*60050+"]")
 invalid+="".join(fence("flowchart LR\n X-->Y") for _ in range(23))
 (root/"limits.md").write_text(invalid,encoding="utf-8")
 with socket.socket() as s:
  s.bind(("127.0.0.1",0));port=s.getsockname()[1]
 base=f"http://127.0.0.1:{port}"
 cmd=[sys.executable,str(REPO/"main.py"),"--root",str(root),"--host","127.0.0.1","--port",str(port),"--config",str(Path(td)/"config.yaml"),"--cache-dir",str(Path(td)/"cache")]
 proc=subprocess.Popen(cmd,cwd=REPO,env=dict(os.environ,LANTERN_WORK_DIR=str(Path(td)/"work")),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:
  for attempt in range(120):
   try:
    with urllib.request.urlopen(base+"/api/info",timeout=1) as r:
     if r.status==200:break
   except Exception:
    if proc.poll() is not None:raise RuntimeError("isolated server exited")
    time.sleep(.1)
  else:raise RuntimeError("isolated server unavailable")
  with sync_playwright() as p:
   browser=p.chromium.launch(channel="msedge",headless=True)
   contexts=[]
   try:
    def new_page():
     ctx=browser.new_context(accept_downloads=True,viewport={"width":1280,"height":900});contexts.append(ctx)
     requests=[];external=[]
     ctx.on("request",lambda r:requests.append(r.url))
     def route(r):
      if r.request.url.startswith(base+"/"):r.continue_()
      else:external.append(r.request.url);r.abort()
     ctx.route("**/*",route)
     return ctx.new_page(),requests,external
    page,requests,external=new_page()
    res=page.goto(base+"/api/plugin/preview?p=plain.md",wait_until="networkidle")
    evidence["checks"]["plain"]={"http":res.status,"mermaid_requests":sum("mermaid-11.17.2.min.js" in x for x in requests),"external":external}
    page.close()
    page,requests,external=new_page();js_errors=[];console=[]
    page.on("pageerror",lambda e:js_errors.append(str(e)))
    page.on("console",lambda m:console.append({"type":m.type,"message":m.text}))
    res=page.goto(base+"/api/plugin/preview?p=mermaid-7.md",wait_until="domcontentloaded")
    page.wait_for_function("""() => document.querySelectorAll('.mermaid-diagram').length===7 && [...document.querySelectorAll('.mermaid-diagram')].every(e=>e.classList.contains('mermaid-ok')||/render failed|unavailable/i.test(e.querySelector('.mermaid-output')?.textContent||''))""",timeout=45000)
    state=page.locator(".mermaid-diagram").evaluate_all("""els=>els.map(e=>({ok:e.classList.contains('mermaid-ok'),svg:!!e.querySelector('.mermaid-output svg'),error:e.classList.contains('mermaid-ok')?'':e.querySelector('.mermaid-output')?.textContent?.slice(0,200)}))""")
    page.screenshot(path=str(OUT/"mermaid-seven.png"),full_page=True)
    evidence["checks"]["seven"]={"status":res.status,"types":[k for k,c in types],"rendered":state,"mermaid_requests":sum("mermaid-11.17.2.min.js" in x for x in requests),"external":external,"js_errors":js_errors,"console_errors":[x for x in console if x["type"]=="error"],"screenshot":str(OUT/"mermaid-seven.png")}
    csp=res.headers.get("content-security-policy","")
    scripts=re.findall(r"<script\b[^>]*>",page.content(),re.I)
    nonces=re.findall(r'\bnonce="([^"]+)"',"\n".join(scripts))
    match=re.search(r"script-src 'nonce-([^']+)'",csp)
    evidence["checks"]["csp"]={"value":csp,"script_count":len(scripts),"all_nonces_match":bool(match and nonces and all(x==match.group(1) for x in nonces))}
    page.evaluate("""() => {const s=document.createElement('script');s.src='/probe-evil.js';document.body.appendChild(s)}""")
    page.wait_for_timeout(300)
    evidence["checks"]["unnonced_js"]={"executed":page.evaluate("Boolean(window.__lanternEvilExecuted)")}
    evidence["checks"]["websocket"]={"result":page.evaluate("""() => new Promise(ok=>{try{let w=new WebSocket('ws://'+location.host+'/ws');w.onerror=()=>ok('blocked');w.onopen=()=>{w.close();ok('opened')};setTimeout(()=>ok('timeout'),1500)}catch(e){ok('exception:'+String(e))}})""")}
    pngs=[]
    for i in range(1,8):
     try:
      with page.expect_download(timeout=18000) as item:page.locator(f'.mermaid-diagram [data-action="png"][data-diagram-index="{i}"]').click()
      dl=item.value;file=OUT/dl.suggested_filename;dl.save_as(file)
      with Image.open(file) as im:dim=im.size;mins=im.convert("RGB").getextrema()
      pngs.append({"name":file.name,"bytes":file.stat().st_size,"dimensions":dim,"has_nonwhite":any(v[0]<248 for v in mins)})
     except Exception as ex:pngs.append({"index":i,"error":repr(ex)[:450]})
    evidence["checks"]["png"]=pngs
    page.evaluate("window.__printCalls=0;window.print=()=>{window.__printCalls++}")
    page.locator('[data-action="print"]').first.click();page.wait_for_function("window.__printCalls>0",timeout=12000)
    pdf=OUT/"mermaid-seven-print.pdf";page.pdf(path=str(pdf),format="A4",print_background=True)
    with fitz.open(pdf) as d:
     full_text="\n".join(z.get_text() for z in d)
     count=len(d);d[0].get_pixmap(matrix=fitz.Matrix(1.2,1.2)).save(str(OUT/"mermaid-seven-pdf-first.png"))
    evidence["checks"]["pdf"]={"print_button":page.evaluate("window.__printCalls"),"pages":count,"bytes":pdf.stat().st_size,"selectable_sentinel":"Printable sentinel 001 TEST." in full_text,"section_title_present":"flowchart" in full_text.lower(),"path":str(pdf)}
    page.close()
    page,requests,external=new_page()
    res=page.goto(base+"/api/plugin/preview?p=limits.md",wait_until="domcontentloaded")
    page.wait_for_timeout(7000)
    states=page.locator(".mermaid-diagram").evaluate_all("""els=>els.map(e=>({ok:e.classList.contains('mermaid-ok'),error:e.querySelector('.mermaid-output')?.textContent?.slice(0,150),source_len:e.querySelector('.mermaid-source')?.textContent?.length||0}))""")
    evidence["checks"]["limits"]={"status":res.status,"wrapper_count":len(states),"first_four":states[:4],"last":states[-1] if states else None,"mermaid_requests":sum("mermaid-11.17.2.min.js" in x for x in requests),"external":external}
   finally:
    for ctx in contexts:ctx.close()
    browser.close()
 except Exception as ex:
  evidence["errors"].append(type(ex).__name__+": "+str(ex))
  raise
 finally:
  proc.terminate()
  try:proc.wait(timeout=6)
  except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=6)
  (OUT/"results.json").write_text(json.dumps(evidence,indent=2,ensure_ascii=False),encoding="utf-8")
  print(json.dumps(evidence,indent=2,ensure_ascii=False))
