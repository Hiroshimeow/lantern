from __future__ import annotations
import os,socket,subprocess,sys,tempfile,time,json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(r"E:\git-project\lantern")
with tempfile.TemporaryDirectory(prefix="lantern-undo-probe-",ignore_cleanup_errors=True) as td:
    td=Path(td); root=td/"root"; root.mkdir(); target=root/"undo.md"
    original="# Accept undo\n\nBase.\n"; accepted="# Accept undo\n\nAccepted.\n"
    target.write_text(original,encoding="utf-8",newline="")
    with socket.socket() as s: s.bind(("127.0.0.1",0)); port=s.getsockname()[1]
    base=f"http://127.0.0.1:{port}"
    env=dict(os.environ,LANTERN_WORK_DIR=str(td/"work"))
    proc=subprocess.Popen([sys.executable,str(ROOT/"main.py"),"--root",str(root),"--host","127.0.0.1","--port",str(port)],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
      import urllib.request
      for _ in range(100):
        try: urllib.request.urlopen(base+"/api/info",timeout=.5).close(); break
        except OSError: time.sleep(.1)
      with sync_playwright() as pw:
        browser=pw.chromium.launch(channel="msedge",headless=True)
        page=browser.new_page()
        page.goto(base+"/api/plugin/preview?p=undo.md")
        page.get_by_role("button",name="Source",exact=True).click()
        area=page.get_by_role("textbox",name="Markdown source"); area.wait_for()
        area.fill(accepted)
        page.wait_for_function("() => window.__lanternMdVisual.state.lastSaved.includes('Accepted.')")
        page.keyboard.press("Control+s")
        page.wait_for_function("() => document.documentElement.dataset.mdPendingHunks === '0'")
        area.click(); page.keyboard.press("Control+End"); page.keyboard.press("ArrowLeft"); page.keyboard.type(" MORE")
        page.wait_for_function("() => window.__lanternMdVisual.state.lastSaved.includes('Accepted. MORE')")
        before={"area":area.input_value(),"file":target.read_text(encoding="utf-8"),"state":page.evaluate("() => ({lastSaved:__lanternMdVisual.state.lastSaved,acked:__lanternMdVisual.state.ackedText,baseline:__lanternMdVisual.state.baseline,dirty:__lanternMdVisual.state.dirty})")}
        page.keyboard.press("Control+z")
        page.wait_for_timeout(1800)
        after={"area":area.input_value(),"file":target.read_text(encoding="utf-8"),"state":page.evaluate("() => ({lastSaved:__lanternMdVisual.state.lastSaved,acked:__lanternMdVisual.state.ackedText,baseline:__lanternMdVisual.state.baseline,dirty:__lanternMdVisual.state.dirty,conflict:__lanternMdVisual.state.conflict})")}
        page.keyboard.press("Control+y")
        page.wait_for_timeout(1800)
        redo={"area":area.input_value(),"file":target.read_text(encoding="utf-8"),"state":page.evaluate("() => ({lastSaved:__lanternMdVisual.state.lastSaved,acked:__lanternMdVisual.state.ackedText,baseline:__lanternMdVisual.state.baseline,dirty:__lanternMdVisual.state.dirty})")}
        print(json.dumps({"before":before,"afterUndo":after,"afterRedo":redo},ensure_ascii=False,indent=2))
        browser.close()
    finally:
      proc.terminate()
      try: proc.wait(timeout=5)
      except: proc.kill()
