from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b=pw.chromium.launch(channel="msedge",headless=True)
    c=b.new_context(); p=c.new_page(); p.set_content("<p>x</p>")
    s=c.new_cdp_session(p)
    for method,args in [
        ("Emulation.setPageVisibilityOverride",{"visibilityState":"hidden"}),
        ("Page.setWebLifecycleState",{"state":"frozen"}),
    ]:
        try:
            print("try",method,s.send(method,args))
            print(p.evaluate("()=>({hidden:document.hidden,state:document.visibilityState})"))
        except Exception as e:
            print("err",method,e)
    b.close()
