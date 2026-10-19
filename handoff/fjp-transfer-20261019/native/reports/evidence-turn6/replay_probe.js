const {JSDOM}=require('jsdom');
const dom=new JSDOM('<!doctype html><html><body></body></html>');
global.window=dom.window;
global.document=dom.window.document;
const { Terminal } = require('@xterm/headless');
const { SerializeAddon } = require('@xterm/addon-serialize');

function write(term, data){ return new Promise(r=>term.write(data,r)); }
function cellJson(cell){
  return {
    chars: cell.getChars(), width: cell.getWidth(),
    fg: cell.getFgColor(), bg: cell.getBgColor(),
    fgMode: cell.getFgColorMode(), bgMode: cell.getBgColorMode(),
    bold: cell.isBold(), italic: cell.isItalic(), underline: cell.isUnderline(),
    inverse: cell.isInverse(), dim: cell.isDim(), blink: cell.isBlink(), invisible: cell.isInvisible(), strike: cell.isStrikethrough()
  };
}
function snap(term){
  const b=term.buffer.active, rows=[];
  for(let y=0;y<term.rows;y++){
    const line=b.getLine(b.viewportY+y), cells=[];
    if(line) for(let x=0;x<term.cols;x++) cells.push(cellJson(line.getCell(x)));
    rows.push(cells);
  }
  return {
    cols:term.cols, rows:term.rows, type:b.type, cursorX:b.cursorX, cursorY:b.cursorY,
    viewportY:b.viewportY, baseY:b.baseY,
    modes:term.modes ? JSON.parse(JSON.stringify(term.modes)) : null,
    cells:rows
  };
}
function equal(a,b){return JSON.stringify(a)===JSON.stringify(b);}
async function rawReplay(chunks,{cols=20,rows=6,tailLimit=null,replayCols=cols,replayRows=rows,resizeTo=null}={}){
  const ref=new Terminal({cols,rows,scrollback:100,allowProposedApi:true});
  for(const c of chunks) await write(ref,c);
  if(resizeTo) ref.resize(...resizeTo);
  const reference=snap(ref);
  let raw=chunks.join('');
  if(tailLimit!==null) raw=raw.slice(-tailLimit);
  const replay=new Terminal({cols:replayCols,rows:replayRows,scrollback:100,allowProposedApi:true});
  await write(replay,raw);
  return {equal:equal(reference,snap(replay)),reference,reconstructed:snap(replay),raw};
}
async function serializedReplay(chunks,{cols=20,rows=6,resizeTo=null,replayCols=null,replayRows=null}={}){
  const ref=new Terminal({cols,rows,scrollback:100,allowProposedApi:true});
  const addon=new SerializeAddon(); ref.loadAddon(addon);
  for(const c of chunks) await write(ref,c);
  if(resizeTo) ref.resize(...resizeTo);
  const reference=snap(ref);
  const serialized=addon.serialize({scrollback:100});
  const rc=replayCols??ref.cols, rr=replayRows??ref.rows;
  const replay=new Terminal({cols:rc,rows:rr,scrollback:100,allowProposedApi:true});
  await write(replay,serialized);
  return {equal:equal(reference,snap(replay)),reference,reconstructed:snap(replay),serialized};
}
(async()=>{
  const cases={};
  cases.split=await rawReplay(['A\x1b[3','1mRED\x1b[0','mZ']);
  cases.alt=await rawReplay(['normal\x1b[?1049h','ALT\x1b[2;5H@']);
  cases.altExit=await rawReplay(['BASE\x1b[2;4H\x1b[1;32mN\x1b[0m','\x1b[?1049hALT\x1b[3;7H\x1b[4;35m@\x1b[0m','\x1b[?1049l']);
  cases.style=await rawReplay(['hello','\x1b[2;4H\x1b[1;34mX\x1b[0m\x1b[K']);
  cases.truncated=await rawReplay(['base line\r\n','\x1b[31mRED\x1b[0m\r\n','\x1b[2A\x1b[5G!'],{tailLimit:9});
  const resizeChunks=['0123456789ABCDEFGHIJ','\r\nTAIL'];
  cases.resizeRaw=await rawReplay(resizeChunks,{cols:10,rows:6,resizeTo:[16,6],replayCols:16,replayRows:6});
  cases.widthRaw=await rawReplay(['0123456789ABCDEFGHIJ\r\nEND'],{cols:12,rows:6,replayCols:20,replayRows:6});

  cases.serializeAlt=await serializedReplay(['normal\x1b[?1049h','ALT\x1b[2;5H@']);
  cases.serializeAltExit=await serializedReplay(['BASE\x1b[2;4H\x1b[1;32mN\x1b[0m','\x1b[?1049hALT\x1b[3;7H\x1b[4;35m@\x1b[0m','\x1b[?1049l']);
  cases.serializeStyle=await serializedReplay(['hello','\x1b[2;4H\x1b[1;34mX\x1b[0m\x1b[K']);
  cases.serializeModes=await serializedReplay(['\x1b[?2004h\x1b[?1h\x1b[?1004h','MODE']);
  cases.serializeResize=await serializedReplay(resizeChunks,{cols:10,rows:6,resizeTo:[16,6]});
  cases.serializeWidth=await serializedReplay(['0123456789ABCDEFGHIJ\r\nEND'],{cols:12,rows:6,replayCols:20,replayRows:6});
  const summary=Object.fromEntries(Object.entries(cases).map(([k,v])=>[k,{equal:v.equal,ref:{cols:v.reference.cols,rows:v.reference.rows,type:v.reference.type,cursorX:v.reference.cursorX,cursorY:v.reference.cursorY,modes:v.reference.modes},recon:{cols:v.reconstructed.cols,rows:v.reconstructed.rows,type:v.reconstructed.type,cursorX:v.reconstructed.cursorX,cursorY:v.reconstructed.cursorY,modes:v.reconstructed.modes},artifactBytes:(v.serialized||v.raw||'').length}]));
  summary.versions={headless:require('@xterm/headless/package.json').version,serialize:require('@xterm/addon-serialize/package.json').version};
  console.log(JSON.stringify(summary,null,2));
})().catch(e=>{console.error(e);process.exit(1)});
