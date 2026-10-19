from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(r"E:\git-project\lantern\.plan\lantern-markdown-main-20261018\cm6-merge-poc-deps")
with sync_playwright() as pw:
    b=pw.chromium.launch(channel="msedge",headless=True)
    p=b.new_page()
    p.set_content("<div id='app'></div>")
    p.add_script_tag(path=str(root/"cm6-poc.js"))
    for text in ["a\r\nb\nEDIT","Head CRLF\r\n日本語 🏮 LF\nEDIT_TARGET\r\nTail"]:
        out=p.evaluate("""text=>{
          CMPoc.createUnified(document.getElementById('app'),text,text);
          const s=CMPoc.view.state;
          return {
            inputLength:text.length,
            inputIndex:text.indexOf(text.includes('EDIT_TARGET')?'EDIT_TARGET':'EDIT'),
            docLength:s.doc.length,
            docString:s.doc.toString(),
            slice:s.sliceDoc(),
            index:s.doc.toString().indexOf(text.includes('EDIT_TARGET')?'EDIT_TARGET':'EDIT'),
            line2from:s.doc.lines>=2?s.doc.line(2).from:null,
            line3from:s.doc.lines>=3?s.doc.line(3).from:null,
            sep:s.facet(CMPoc.view.state.facet??null)
          }
        }""",text)
        print(repr(text),out)
    b.close()
