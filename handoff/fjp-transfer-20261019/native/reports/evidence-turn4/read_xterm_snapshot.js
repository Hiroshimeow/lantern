const fs=require('fs');
(async()=>{
  const port=Number(process.argv[2]), out=process.argv[3];
  let tabs;
  for(let i=0;i<30;i++){try{tabs=await (await fetch('http://127.0.0.1:'+port+'/json')).json();if(Array.isArray(tabs))break}catch{} await new Promise(r=>setTimeout(r,100))}
  const t=tabs.find(x=>x.type==='page'&&String(x.url).includes('pi-t002-xterm-render.html'));
  if(!t) throw Error('xterm page target not found');
  const ws=new WebSocket(t.webSocketDebuggerUrl);let id=0;const pending=new Map();
  ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id&&pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id)}};
  await new Promise((res,rej)=>{ws.onopen=res;ws.onerror=rej});
  const call=(method,params={})=>new Promise((res,rej)=>{const n=++id;pending.set(n,m=>m.error?rej(Error(JSON.stringify(m.error))):res(m.result));ws.send(JSON.stringify({id:n,method,params}))});
  for(let i=0;i<50;i++){const r=await call('Runtime.evaluate',{expression:'window.done===true',returnByValue:true});if(r.result.value)break;await new Promise(r=>setTimeout(r,100))}
  const snap=await call('Runtime.evaluate',{expression:'JSON.stringify(window.snapshot)',returnByValue:true});
  fs.writeFileSync(out,snap.result.value,'utf8');console.log(snap.result.value);ws.close();
})().catch(e=>{console.error(e);process.exit(1)});
