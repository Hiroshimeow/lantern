from pathlib import Path
import json
root = Path(r"E:\git-project\lantern\.wt\lantern-bot")
e = root / ".plan" / "lantern-pi-native-20261018" / "evidence-turn4"
raw = (e / "pi-t002-g6-winconpty-raw.txt").read_text(encoding="utf-8", errors="replace")
xterm = (root / "static" / "vendor" / "xterm.js").resolve().as_uri()
html = f"""<!doctype html><meta charset='utf-8'>
<div id='term'></div>
<script src={json.dumps(xterm)}></script>
<script>
window.done=false; window.snapshot=null;
const term=new Terminal({{cols:120,rows:40,scrollback:8000}});
term.open(document.getElementById('term'));
const raw={json.dumps(raw, ensure_ascii=False)};
term.write(raw,()=>{{
  const b=term.buffer.active, lines=[];
  for(let i=Math.max(0,b.length-60);i<b.length;i++){{
    const line=b.getLine(i); if(line) lines.push(line.translateToString(true));
  }}
  window.snapshot={{type:b.type,cursorX:b.cursorX,cursorY:b.cursorY,length:b.length,baseY:b.baseY,viewportY:b.viewportY,lines}};
  window.done=true;
}});
</script>"""
(e / "pi-t002-xterm-render.html").write_text(html, encoding="utf-8")
print(e / "pi-t002-xterm-render.html")
