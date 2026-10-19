import json, os, socket, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(r"E:\git-project\lantern")
cases={
"canonical":"# Heading\n\nParagraph text.\n",
"unicode":"# Unicode\n\nCJK 日本語 emoji 🏮 end\n",
"alias-em":"# Alias\n\n_emphasis_ and __strong__\n",
"alias-list":"# Alias\n\n+ one\n+ two\n",
"alias-link":"# Alias\n\n[OpenAI](https://openai.com/ \"T\")\n",
"crlf":"# CRLF\r\n\r\nParagraph.\r\n",
"mixed":"# Mixed\r\n\nParagraph.\r\n",
}
with tempfile.TemporaryDirectory(prefix="lantern-map-probe-") as td:
  td=Path(td); root=td/"root"; root.mkdir(); work=td/"work"; work.mkdir()
  for n,t in cases.items(): (root/f"{n}.md").write_bytes(t.encode("utf-8"))
  with socket.socket() as s: s.bind(("127.0.0.1",0)); port=s.getsockname()[1]
  base=f"http://127.0.0.1:{port}"
  p=subprocess.Popen([sys.executable,str(ROOT/"main.py"),"--root",str(root),"--host","127.0.0.1","--port",str(port),"--config",str(td/"c.yaml"),"--cache-dir",str(td/"cache")],cwd=ROOT,env={**os.environ,"LANTERN_WORK_DIR":str(work)},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  try:
    for _ in range(100):
      try:
        urllib.request.urlopen(base+"/api/info",timeout=.5).close(); break
      except OSError: time.sleep(.1)
    with sync_playwright() as pw:
      b=pw.chromium.launch(channel="msedge",headless=True)
      out={}
      for n,t in cases.items():
        page=b.new_page(); page.goto(base+f"/api/plugin/preview?p={n}.md",wait_until="domcontentloaded")
        page.get_by_role("button",name="Edit visually",exact=True).click()
        page.locator(".md-visual-host .ProseMirror[contenteditable='true']").wait_for(timeout=20000)
        got=page.evaluate("() => window.__lanternMdVisual.state.instance.getMarkdown()")
        out[n]={"same":got==t,"input":repr(t),"got":repr(got)}
        page.close()
      print(json.dumps(out,ensure_ascii=True,indent=2))
      b.close()
  finally:
    p.terminate(); p.wait(timeout=5)
