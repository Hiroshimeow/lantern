from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b=pw.chromium.launch(channel="msedge",headless=True)
    c=b.new_context()
    a=c.new_page(); a.set_content("<p>a</p>")
    print("a after a",a.evaluate("()=>({hidden:document.hidden,state:document.visibilityState,focus:document.hasFocus()})"))
    d=c.new_page(); d.set_content("<p>b</p>")
    print("a after b",a.evaluate("()=>({hidden:document.hidden,state:document.visibilityState,focus:document.hasFocus()})"))
    print("b",d.evaluate("()=>({hidden:document.hidden,state:document.visibilityState,focus:document.hasFocus()})"))
    a.bring_to_front()
    print("a front",a.evaluate("()=>({hidden:document.hidden,state:document.visibilityState,focus:document.hasFocus()})"))
    print("b back",d.evaluate("()=>({hidden:document.hidden,state:document.visibilityState,focus:document.hasFocus()})"))
    b.close()
