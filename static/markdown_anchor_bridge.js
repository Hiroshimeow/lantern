/* Experimental Preview <-> Source/Visual bookmark helper. Never edits a file. */
(() => {
  'use strict';
  function offsetForLine(source, line) {
    const wanted = Math.max(1, Math.trunc(Number(line) || 1));
    if (wanted === 1) return 0;
    let pos = 0;
    for (let current = 1; current < wanted; current++) {
      const found = source.indexOf('\n', pos);
      if (found < 0) return source.length;
      pos = found + 1;
    }
    return pos;
  }
  function lineForOffset(source, offset) {
    let result = 1;
    const end = Math.max(0, Math.min(source.length, Math.trunc(offset)));
    for (let i = 0; i < end; i++) if (source[i] === '\n') result++;
    return result;
  }
  function selectLine(sourceArea, line, select = false) {
    const offset = offsetForLine(sourceArea.value, line);
    if (select) sourceArea.setSelectionRange(offset, offset);
    else sourceArea.selectionStart = sourceArea.selectionEnd = offset;
    const style = getComputedStyle(sourceArea);
    const step = Number.parseFloat(style.lineHeight) || 21;
    sourceArea.scrollTop = Math.max(0, (line - 2) * step);
    sourceArea.focus({preventScroll:true});
    return offset;
  }
  function anchorFromElement(element) {
    if (!element?.closest) return null;
    const block=element.closest('[data-l]');
    const line = Number(block?.getAttribute('data-l'));
    if (!Number.isSafeInteger(line) || line <= 0) return null;
    const parent=block?.closest('article.md-preview');
    if (!parent) return null;
    const text=(block.textContent || '').trim();
    let ordinal=0;
    // Distinguish repeated words/paragraphs without guessing global offsets.
    for (const other of parent.querySelectorAll('[data-l]')) {
      if (other===block) break;
      if (other.tagName===block.tagName && other.textContent?.trim()===text) ordinal++;
    }
    return {line, blockTag:block.tagName, text:text.slice(0,512), ordinal};
  }
  function captureViewport(preview) {
    if (!preview || preview.hidden) return null;
    // Prefer the first visible source-anchored block, not global scrollY pixels.
    const blocks=preview.querySelectorAll('[data-l]');
    for(const block of blocks) {
      const box=block.getBoundingClientRect();
      if(box.bottom > 72 && box.top < innerHeight) return anchorFromElement(block);
    }
    return blocks.length ? anchorFromElement(blocks[0]):null;
  }
  function restorePreview(preview, bookmark) {
    if (!preview || !bookmark) return false;
    let best=null, distance=Infinity;
    for(const node of preview.querySelectorAll('[data-l]')) {
      const line=Number(node.getAttribute('data-l'));
      const delta=Math.abs(line-bookmark.line);
      if (delta<distance) {distance=delta;best=node;}
      if (delta===0 && (node.tagName===bookmark.blockTag)) {best=node;break;}
    }
    if (!best) return false;
    best.scrollIntoView({block:'start',behavior:'instant'});
    return true;
  }
  function sourceOffsetToPage(source, line, index) {
    const pos=offsetForLine(source,line);
    const pages=index?.pages || [];
    let lo=0,hi=pages.length-1;
    while(lo<hi){const mid=(lo+hi)>>>1;if(pages[mid].end<=pos)lo=mid+1;else hi=mid;}
    return pages.length ? lo : -1;
  }
  // Experimental wiring for the anchored Preview only. This script is NOT
  // included in the default Preview and never writes Markdown to disk.
  function installPrototype() {
    const preview=document.querySelector('article.md-preview');
    if (!preview || !preview.querySelector('[data-l]')) return;
    const buttons={
      visual:document.querySelector('[data-action="visual-edit"]'),
      source:document.querySelector('[data-action="mode-source"]'),
      preview:document.querySelector('[data-action="mode-preview"]'),
    };
    let pending=null, timer=0, contextButton=null;
    function cleanupMenu(){contextButton?.remove();contextButton=null;}
    function captureCurrent() {
      const source=document.querySelector('textarea.md-source-area');
      if(source && document.contains(source))return {line:lineForOffset(source.value,source.selectionStart)};
      if(!preview.hidden)return captureViewport(preview);
      // Visual ProseMirror text has no exact source offset. If mapping is
      // uncertain, do not guess or change selection. Preview can keep the
      // previous known source anchor as a fallback instead.
      return pending;
    }
    function revealText(root,bookmark) {
      if(!root||!bookmark?.text)return false;
      const texts=[...root.querySelectorAll('h1,h2,h3,h4,h5,h6,p,li,td,th,blockquote')]
        .filter(x=>x.textContent?.trim()===bookmark.text);
      // Without a PM source map, duplicate blocks cannot be resolved.
      // Fail closed rather than scrolling to the wrong occurrence.
      if(texts.length!==1)return false;
      const match=texts[0];
      match.scrollIntoView({block:'center',behavior:'instant'});
      return true;
    }
    async function restore(mode) {
      if(!pending)return;
      const anchor=pending;
      if(mode==='preview' && !preview.hidden && restorePreview(preview,anchor))return;
      if(mode==='source'){
        const source=document.querySelector('textarea.md-source-area');
        if(source){selectLine(source,anchor.line);return;}
      }
      if(mode==='visual'){
        const paged=globalThis.__lanternMdPaged;
        if(paged?.active && paged.index?.pages?.length){
          const index=sourceOffsetToPage(paged.source,anchor.line,paged.index);
          if(index!==paged.pageNumber)await paged.go(index);
        }
        const host=document.querySelector('.md-visual-host .ProseMirror');
        if(revealText(host,anchor))return;
        // Never select an unrelated duplicate text node silently.
      }
    }
    function waitFor(mode){
      let attempts=0;clearTimeout(timer);
      const check=()=>{
        if(mode==='preview'&&!preview.hidden||
          mode==='source'&&!!document.querySelector('textarea.md-source-area')||
          mode==='visual'&&!!document.querySelector('.md-visual-host .ProseMirror')){
          Promise.resolve(restore(mode)).catch(()=>{});return;
        }
        if(attempts++<100)timer=setTimeout(check,80);
      };check();
    }
    for(const [mode,button] of Object.entries(buttons))button?.addEventListener('click',()=>{
      pending=captureCurrent();cleanupMenu();if(pending)waitFor(mode);
    },true);
    preview.addEventListener('contextmenu',event=>{
      const selection=getSelection();
      if(!selection||selection.isCollapsed||!selection.toString().trim())return;
      const node=selection.anchorNode;
      const block=node?.nodeType===1 ? node : (node?.parentElement||event.target);
      const anchor=anchorFromElement(block);
      if(!anchor)return;
      event.preventDefault();cleanupMenu();
      const button=document.createElement('button');button.type='button';
      button.textContent='Go to block in Visual (experimental)';button.className='btn';
      button.style.cssText='position:fixed;z-index:99';
      button.style.left=Math.max(4,Math.min(innerWidth-230,event.clientX))+'px';
      button.style.top=Math.max(4,Math.min(innerHeight-40,event.clientY))+'px';
      button.addEventListener('click',()=>{
        pending=anchor;cleanupMenu();
        globalThis.__lanternMdVisual?.open('visual');waitFor('visual');
      });
      document.body.append(button);contextButton=button;
    });
    document.addEventListener('click',event=>{
      if(contextButton&&!contextButton.contains(event.target))cleanupMenu();
    },true);
    globalThis.__lanternAnchorSpike={captureCurrent,restore};
  }
  if(typeof document!=='undefined'){
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',installPrototype);
    else installPrototype();
  }
  const api={offsetForLine,lineForOffset,selectLine,anchorFromElement,captureViewport,restorePreview,sourceOffsetToPage};
  globalThis.LanternAnchorBridge=api;
  if(typeof module!=='undefined' && module.exports) module.exports=api;
})();
