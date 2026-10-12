// Page-sized rich editing for large Markdown files. The Markdown-it block parser
// runs in a Worker. Only one page creates a ProseMirror view at a time.
// Unmodified text is never parsed into / serialized out of Milkdown.
(() => {
  'use strict';
  const WORKER_URL = '/static/vendor/lantern-md-segment-worker.min.js';
  const LEAVE_WARNING = 'You have unsaved Markdown edits. Keep or export your draft before leaving.';
  const normalize = text => String(text ?? '').replace(/\r\n/g, '\n').replace(/\n+$/, '');
  const button = (label, fn, cls = 'btn') => {
    const el = document.createElement('button');
    el.type = 'button'; el.textContent = label; el.className = cls;
    el.addEventListener('click', fn);
    return el;
  };
  const api = async (url, options = {}) => {
    const response = await fetch(url, {cache:'no-store',credentials:'same-origin',...options});
    let result;
    try { result = await response.json(); } catch { throw Error('Invalid response from Lantern server'); }
    if (!response.ok || result.error) {
      const err = Error(result.error || 'HTTP ' + response.status);
      err.status = response.status; throw err;
    }
    return result;
  };
  const boundaries = (original, edited) => {
    // Keep exact delimiters of the surrounding, unedited Markdown blocks.
    // A heading, list or fenced block in the next page must never be glued to
    // the edited region just because Milkdown trimmed extra newlines.
    const leading = original.match(/^(?:\r\n|\n|\r)*/)[0];
    const trailing = original.match(/(?:\r\n|\n|\r)*$/)[0];
    const core = String(edited).replace(/^(?:\r\n|\n|\r)*/, '').replace(/(?:\r\n|\n|\r)*$/, '');
    return leading + core + trailing;
  };

  class PagedEditor {
    constructor({doc, path, trigger, preview, loadBundle, nonce}) {
      this.path=path; this.trigger=trigger; this.preview=preview;
      this.loadBundle=loadBundle; this.nonce=nonce;
      this.source=doc.content; this.version=doc.version; this.bytes=doc.bytes;
      this.index=null; this.worker=null; this.pending=new Map(); this.workerId=0;
      this.pageNumber=-1; this.page=null; this.pageOriginal='';
      this.engine=null; this.rich=null; this.largeEditor=null; this.blockWrap=null; this.generation=0;
      this.lastSaved=''; this.roundtripSafe=false; this.approved=false;
      this.dirty=false; this.saving=false; this.conflict=false; this.revision=0;
      this.saveTimer=0; this.draftTimer=0; this.changedTimer=0; this.reindex=null;
      this.active=false; this.loadingPage=false; this.savePromise=null;
      this.draftKey='paged:'+location.origin+':'+path;
      this.onLeave=this.onLeave.bind(this); this.onKey=this.onKey.bind(this);
      this.onVisibility=this.onVisibility.bind(this);
    }
    status(message,kind='info') {
      if(!this.statusEl)return;
      this.statusEl.textContent=message;
      this.statusEl.dataset.kind=kind;
    }
    currentText() {
      if(this.largeEditor)return (this.blockWrap?.prefix||'')+this.largeEditor.getContent()+(this.blockWrap?.suffix||'');
      return this.rich ? this.rich.getMarkdown() : '';
    }
    pageSource() { return this.source.slice(this.page.start,this.page.end); }
    workerIndex(source) {
      if (!this.worker) {
        this.worker=new Worker(WORKER_URL);
        this.worker.onmessage = event => {
          const {id,ok,result,error}=event.data || {};
          const pending=this.pending.get(id);
          if (!pending) return;
          clearTimeout(pending.timeout);
          this.pending.delete(id);
          ok ? pending.resolve(result) : pending.reject(Error(error || 'Markdown indexing failed'));
        };
        this.worker.onerror=event => {
          const err=Error(event.message || 'Markdown worker crashed');
          for (const pending of this.pending.values()) {
            clearTimeout(pending.timeout); pending.reject(err);
          }
          this.pending.clear();
        };
      }
      return new Promise((resolve,reject) => {
        const id=++this.workerId;
        const timeout=setTimeout(() => {this.pending.delete(id);reject(Error('Index worker timed out'));},30000);
        this.pending.set(id,{resolve,reject,timeout});
        this.worker.postMessage({id,source});
      });
    }
    async loadLargeBlockEditor(){
      if(window.LanternLargeBlockEditor)return window.LanternLargeBlockEditor;
      if(this.codePromise)return this.codePromise;
      this.codePromise=new Promise((resolve,reject)=>{
        const script=document.createElement('script');
        script.src='/static/vendor/lantern-large-block.min.js';
        script.nonce=this.nonce;
        script.onload=()=>window.LanternLargeBlockEditor ?
          resolve(window.LanternLargeBlockEditor):reject(Error('CodeMirror did not initialize'));
        script.onerror=()=>reject(Error('Large-block editor asset unavailable'));
        document.head.append(script);
      });
      return this.codePromise;
    }
    async storeDraft(mode, value) {
      if (!indexedDB) return null;
      return new Promise((resolve,reject) => {
        const request=indexedDB.open('lantern-md-drafts',1);
        request.onupgradeneeded=()=>{
          if(!request.result.objectStoreNames.contains('drafts'))
            request.result.createObjectStore('drafts');
        };
        request.onerror=()=>reject(request.error);
        request.onsuccess=()=>{
          const db=request.result;
          const txn=db.transaction('drafts',mode==='get'?'readonly':'readwrite');
          const store=txn.objectStore('drafts');
          const operation=mode==='get'?store.get(this.draftKey):
            mode==='delete'?store.delete(this.draftKey):store.put(value,this.draftKey);
          operation.onsuccess=()=>resolve(operation.result);
          operation.onerror=()=>reject(operation.error);
          txn.oncomplete=()=>db.close();
          txn.onabort=()=>db.close();
        };
      });
    }
    async draftWrite() {
      if(!this.active || !this.dirty || !this.page) return;
      const current=this.currentText();
      if(current===this.lastSaved)return;
      try {
        await this.storeDraft('put',{
          mode:'paged', content:current, version:this.version,
          original:this.pageOriginal, start:this.page.start,
          end:this.page.end, at:Date.now(),
        });
      } catch { this.status('Cannot store local draft; keep this tab open until saved.','error'); }
    }
    changed(generation) {
      if(generation!==this.generation||!this.active)return;
      this.dirty=true; this.revision++;
      this.status(this.conflict?'File changed on another client; draft preserved.' :
        !this.roundtripSafe&&!this.approved?'Review conversion before saving.' :
        'Unsaved changes…',this.conflict?'error':'info');
      clearTimeout(this.changedTimer);
      const revision=this.revision;
      this.changedTimer=setTimeout(()=>{
        if(revision!==this.revision || !this.active)return;
        if(this.currentText()===this.lastSaved) {
          this.dirty=false;clearTimeout(this.draftTimer);clearTimeout(this.saveTimer);
          if(!this.conflict&&!this.saving)this.status('Ready. Edit directly in the document.');
          return;
        }
        clearTimeout(this.draftTimer);
        this.draftTimer=setTimeout(()=>{void this.draftWrite();},700);
        this.queueSave();
      },260);
    }
    queueSave(delay=2400) {
      clearTimeout(this.saveTimer);
      if(this.conflict||!this.roundtripSafe&&!this.approved)return;
      this.saveTimer=setTimeout(()=>{void this.save(false);},delay);
    }
    initUI() {
      const shell=document.createElement('section');
      shell.className='md-visual-shell md-paged-shell';
      const toolbar=document.createElement('div');
      toolbar.className='md-visual-tools md-paged-tools';
      const title=document.createElement('strong');
      title.textContent='✎ Visual Markdown · section editor';
      const prev=button('← Previous',()=>{void this.go(this.pageNumber-1);});
      const next=button('Next →',()=>{void this.go(this.pageNumber+1);});
      const page=document.createElement('input');
      page.className='md-page-number';page.type='number';page.min='1';page.value='1';page.title='Go to page';
      page.addEventListener('change',()=>{void this.go(Number(page.value)-1);});
      const pageCount=document.createElement('span');pageCount.className='md-page-count';
      const sections=document.createElement('select');
      sections.className='md-page-heading';sections.title='Jump to heading';
      sections.append(new Option('Nearby headings…',''));
      sections.addEventListener('change',()=>{
        const which=Number(sections.value);
        if(Number.isInteger(which)&&sections.value!=='')void this.go(which);
      });
      const headingSearch=document.createElement('input');
      headingSearch.type='search';headingSearch.placeholder='Find heading…';
      headingSearch.className='md-page-heading-search';headingSearch.title='Filter any heading without rendering thousands of options';
      headingSearch.addEventListener('input',()=>{
        clearTimeout(this.headingSearchTimer);
        this.headingSearchTimer=setTimeout(()=>this.headingRefresh(),140);
      });
      headingSearch.addEventListener('keydown',event=>{
        if(event.key!=='Enter')return;
        event.preventDefault();this.headingRefresh();
        const option=sections.options[1];
        if(option)void this.go(Number(option.value));
      });
      const search=document.createElement('input');
      search.type='search';search.placeholder='Find anywhere in document…';
      search.className='md-page-search';search.title='Find text in any section';
      search.addEventListener('keydown',event=>{
        if(event.key==='Enter'){event.preventDefault();void this.find(search.value);}
      });
      const goSearch=button('Find',()=>{void this.find(search.value);});
      const save=button('Save',()=>{void this.save(true);},'btn primary');
      const draft=button('Download draft',()=>this.download());
      const close=button('Back to preview',()=>{void this.close();});
      const status=document.createElement('span');
      status.className='md-visual-status';status.setAttribute('role','status');
      status.setAttribute('aria-live','polite');
      const pageRow=document.createElement('div');
      pageRow.className='md-paged-navigation';
      pageRow.append(prev,page,pageCount,next,headingSearch,sections,search,goSearch);
      toolbar.append(title,pageRow,save,draft,close,status);
      const host=document.createElement('div');host.className='md-visual-host';
      host.id='md-paged-edit-host';
      shell.append(toolbar,host);
      this.preview.insertAdjacentElement('afterend',shell);
      this.shell=shell;this.host=host;this.statusEl=status;
      this.prev=prev;this.next=next;this.pageField=page;
      this.countEl=pageCount;this.sections=sections;this.headingSearch=headingSearch;
      this.saveButton=save;this.searchInput=search;
      this.headingRefresh();
      this.updateNav();
    }
    headingRefresh(){
      // HTML <select> with 80,000 options was dominating cold-start for huge
      // documents. Keep only relevant options in the DOM, search the full index.
      const query=this.headingSearch?.value.trim().toLocaleLowerCase()||'';
      const headings=this.index.headings;
      let relevant=[];
      if(query){
        for(const h of headings){
          if(h.title.toLocaleLowerCase().includes(query))relevant.push(h);
          if(relevant.length>=70)break;
        }
      } else {
        const here=Math.max(0,this.pageNumber);
        for(const h of headings){
          if(h.page>=here-2&&h.page<=here+3)relevant.push(h);
          if(relevant.length>=60)break;
        }
        if(relevant.length===0)relevant=headings.slice(0,40);
      }
      this.sections.replaceChildren();
      const placeholder=new Option(query?'Matching headings…':'Nearby headings…','');
      this.sections.add(placeholder);
      const options=document.createDocumentFragment();
      for(const h of relevant){
        const option=document.createElement('option');
        option.value=String(h.page);
        option.textContent='  '.repeat(Math.max(0,h.level-1))+h.title+' · '+(h.page+1);
        options.append(option);
      }
      this.sections.append(options);
    }
    updateNav() {
      const total=this.index.pages.length;
      this.pageField.max=String(total);
      this.pageField.value=String(this.pageNumber+1);
      this.countEl.textContent='/ '+total;
      this.prev.disabled=this.loadingPage||this.pageNumber<=0;
      this.next.disabled=this.loadingPage||this.pageNumber>=total-1;
      this.pageField.disabled=this.loadingPage;
      this.sections.disabled=this.loadingPage;
      this.headingSearch.disabled=this.loadingPage;
      this.saveButton.disabled=this.saving||this.loadingPage||this.conflict;
      this.trigger.disabled=true;
      this.trigger.textContent='Editing by section';
    }
    async review(before,after) {
      const dlg=document.createElement('dialog');dlg.className='md-format-review';
      const title=document.createElement('h2');
      title.textContent='Review changes to this section';
      const explanation=document.createElement('p');
      explanation.textContent='Milkdown would rewrite Markdown formatting in this section. Review before saving; all other sections remain byte-for-byte unchanged.';
      const comparison=document.createElement('div');comparison.className='md-format-diff';
      for (const [name,content] of [['Original section',before],['Editor result',after]]) {
        const panel=document.createElement('div');
        const h=document.createElement('h3');h.textContent=name;
        const pre=document.createElement('pre');
        pre.textContent=content.length>40000?content.slice(0,40000)+'\n… (comparison truncated)':content;
        panel.append(h,pre);comparison.append(panel);
      }
      const actions=document.createElement('div');actions.className='md-format-actions';
      const cancel=button('Cancel / retain draft',()=>end(false));
      const accept=button('Accept changes & Save',()=>end(true),'btn primary');
      actions.append(cancel,accept);
      dlg.append(title,explanation,comparison,actions);
      document.body.append(dlg);
      let done;
      const answer=new Promise(resolve=>{done=resolve;});
      const end=value=>{dlg.close();dlg.remove();done(value);};
      dlg.addEventListener('cancel',event=>{event.preventDefault();end(false);});
      dlg.showModal();
      return answer;
    }
    async save(manual) {
      if(!this.active||!this.page||this.conflict)return false;
      if(this.saving)return this.savePromise || false;
      const current=this.currentText();
      if(current===this.lastSaved) {
        this.dirty=false;
        if(manual)this.status('Already saved.');
        return true;
      }
      if(!this.roundtripSafe&&!this.approved){
        if(!manual){this.status('Review formatting before autosave.','warn');return false;}
        if(!await this.review(this.pageOriginal,current)){
          this.status('Save cancelled; local draft kept.','warn');
          await this.draftWrite();return false;
        }
        this.approved=true;
      }
      const revision=this.revision;
      this.saving=true;this.updateNav();this.status('Saving…');
      const task=(async()=>{
        try {
          const patch=boundaries(this.pageOriginal,current);
          const newSource=this.source.slice(0,this.page.start)+patch+
            this.source.slice(this.page.end);
          const result=await api('/api/md/save',{
            method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({path:this.path,version:this.version,content:newSource}),
          });
          const change=patch.length-(this.page.end-this.page.start);
          this.version=result.version;this.source=newSource;
          this.page.end+=change;
          for(let i=this.pageNumber+1;i<this.index.pages.length;i++){
            this.index.pages[i].start+=change;this.index.pages[i].end+=change;
          }
          this.pageOriginal=patch;this.lastSaved=current;
          this.roundtripSafe=true;this.approved=false;
          if(this.revision===revision) {
            this.dirty=false;
            await this.storeDraft('delete').catch(()=>{});
            this.status('Saved ✓');
          } else {
            this.dirty=true;
            this.status('Saved; continuing with newer edits…');
            this.queueSave(800);
          }
          // Reparse edited block boundaries off-thread before the next page jump.
          this.reindex=this.workerIndex(this.source).catch(err=>{
            this.status('Saved, but page index refresh failed: '+err.message,'warn');
            return null;
          });
          return true;
        } catch(error) {
          if(error.status===409||error.status===404){
            this.conflict=true;
            this.status('Conflict: another client changed this file. Download draft; reload to reconcile.','error');
          } else {
            this.status('Save failed: '+error.message+'. Draft retained.','error');
          }
          await this.draftWrite();return false;
        } finally {this.saving=false;this.updateNav();}
      })();
      this.savePromise=task;
      try{return await task;}finally{this.savePromise=null;}
    }
    async go(next, restore=null) {
      if(!this.active||this.loadingPage)return false;
      const num=Math.max(0,Math.min(this.index.pages.length-1,Math.trunc(next)));
      if(!Number.isFinite(num))return false;
      if(num===this.pageNumber&&!restore)return true;
      if(this.saving&&!await this.savePromise)return false;
      if(this.dirty&&!await this.save(true))return false;
      clearTimeout(this.saveTimer);clearTimeout(this.draftTimer);clearTimeout(this.changedTimer);
      this.loadingPage=true;this.updateNav();
      try {
        if(this.reindex) {
          const result=await this.reindex;this.reindex=null;
          if(result){this.index=result;this.headingRefresh();}
        }
        // Preserve position as page numbers can shift after headings were edited.
        const target=Math.max(0,Math.min(num,this.index.pages.length-1));
        const p=this.index.pages[target];
        this.generation+=1;
        if(this.rich)await this.rich.destroy();
        this.rich=null;this.largeEditor?.destroy();this.largeEditor=null;
        this.blockWrap=null;this.host.replaceChildren();
        this.pageNumber=target;this.page=p;
        this.headingRefresh();
        this.pageOriginal=this.pageSource();
        const content=restore?.content??this.pageOriginal;
        const generation=this.generation;
        if(p.oversized) {
          // CodeMirror 6 renders only its visible viewport. A single giant fence
          // cannot safely be mounted in ProseMirror; edit its code directly.
          const note=document.createElement('p');
          note.className='md-oversized-note';
          const match=content.match(/^((?:\r?\n)*[ \t]{0,3}(?:`{3,}|~{3,})[^\r\n]*\r?\n)([\s\S]*?)(\r?\n[ \t]{0,3}(?:`{3,}|~{3,})[ \t]*(?:\r?\n)*)$/);
          note.textContent=match ?
            'Large code block: edit the code directly. Markdown fence markers and other pages stay intact.' :
            'This single Markdown block is too large for WYSIWYG. The editor shows only this block with virtualized text; other sections remain visual.';
          const codeHost=document.createElement('div');codeHost.className='md-oversized-code';
          this.host.append(note,codeHost);
          this.blockWrap=match?{prefix:match[1],suffix:match[3]}:{prefix:'',suffix:''};
          const lib=await this.loadLargeBlockEditor();
          this.largeEditor=lib.createBlockEditor(codeHost,match?match[2]:content,()=>this.changed(generation));
          this.status('Large block: CodeMirror viewport rendering enabled.','warn');
        } else {
          this.rich=await this.engine.createVisualMarkdown(this.host,content,()=>this.changed(generation),this.path,(message,kind)=>this.status(message,kind));
        }
        this.lastSaved=restore?this.pageOriginal:this.currentText();
        this.roundtripSafe=!restore&&normalize(this.currentText())===normalize(this.pageOriginal);
        this.approved=false;this.dirty=!!restore;this.revision=restore?1:0;
        if(restore && restore.version!==this.version)this.conflict=true;
        if(restore && restore.version===this.version &&
            restore.original!==this.pageOriginal)this.conflict=true;
        this.status(this.conflict?'Draft restored but file version differs. Download your draft before reloading.' :
          restore?'Unsaved draft restored. Review before saving.' :
          this.roundtripSafe?'Ready. Edit directly in the document.' :
          'Formatting may change; review this section before Save.',
          this.conflict?'error':this.roundtripSafe?'info':'warn');
        if(this.rich)this.rich.focus();
        if(this.largeEditor)this.largeEditor.focus();
        this.shell.scrollIntoView({block:'start'});
        return true;
      } catch(error){
        this.status('Section unavailable: '+error.message,'error');
        return false;
      } finally {this.loadingPage=false;this.updateNav();}
    }
    async find(query) {
      const term=String(query||'').trim();
      if(!term){this.status('Enter a search phrase.');return;}
      const lowered=this.source.toLocaleLowerCase();
      const needle=term.toLocaleLowerCase();
      const start=this.page?.end||0;
      let at=lowered.indexOf(needle,start);
      if(at<0)at=lowered.indexOf(needle,0);
      if(at<0){this.status('No match found in this document.','warn');return;}
      let lo=0,hi=this.index.pages.length-1;
      while(lo<hi){
        const m=(lo+hi)>>>1;
        if(this.index.pages[m].end<=at)lo=m+1;else hi=m;
      }
      if(await this.go(lo))this.status('Match found on page '+(lo+1)+'.');
    }
    download(){
      const text=this.currentText();
      const blob=new Blob([text],{type:'text/markdown;charset=utf-8'});
      const url=URL.createObjectURL(blob);
      const a=document.createElement('a');a.href=url;
      a.download=this.path.split('/').pop()+'-page-'+(this.pageNumber+1)+'-unsaved.md';
      document.body.append(a);a.click();a.remove();
      setTimeout(()=>URL.revokeObjectURL(url),3000);
    }
    onLeave(event){
      if(this.active&&this.dirty){event.preventDefault();event.returnValue=LEAVE_WARNING;}
    }
    onKey(event){
      if(!this.active||!(event.ctrlKey||event.metaKey)||event.key.toLowerCase()!=='s')return;
      event.preventDefault();void this.save(true);
    }
    onVisibility(){
      if(document.hidden&&this.dirty)void this.draftWrite();
    }
    async close(){
      if(!this.active||this.saving)return;
      if(this.dirty&&!confirm(LEAVE_WARNING+' Return to preview?'))return;
      if(this.dirty)await this.draftWrite();
      this.active=false;
      clearTimeout(this.saveTimer);clearTimeout(this.draftTimer);
      clearTimeout(this.changedTimer);clearTimeout(this.headingSearchTimer);
      removeEventListener('beforeunload',this.onLeave);
      document.removeEventListener('keydown',this.onKey);
      document.removeEventListener('visibilitychange',this.onVisibility);
      this.generation++;
      if(this.rich)await this.rich.destroy();
      this.largeEditor?.destroy();this.largeEditor=null;
      this.worker?.terminate();
      this.shell.remove();this.preview.hidden=false;
      this.trigger.disabled=false;this.trigger.textContent='Edit visually';
      window.__lanternMdPaged=null;
    }
    async open() {
      const began=performance.now();
      this.trigger.disabled=true;this.trigger.textContent='Indexing Markdown…';
      try {
        // Indexing is separate from Milkdown and runs in a background worker.
        const indexed=this.workerIndex(this.source).then(result=>{
          this.indexMs=Math.round(performance.now()-began);return result;
        });
        const [index,engine,draft]=await Promise.all([
          indexed,this.loadBundle(),this.storeDraft('get').catch(()=>null),
        ]);
        this.index=index;this.engine=engine;
        this.initUI();this.preview.hidden=true;this.active=true;
        window.__lanternMdPaged=this;
        const restored=draft?.mode==='paged' && typeof draft.content==='string' ?
          (confirm('Unsaved Markdown draft found. Restore it?')?draft:null):null;
        let initial=0;
        if(restored){
          initial=index.pages.findIndex(p=>p.start===restored.start);
          if(initial<0)initial=0;
        }
        if(!await this.go(initial,restored))throw Error('Unable to show first Markdown section');
        window.__lanternMdMetrics={
          paged:true, loadMs:Math.round(performance.now()-began),indexMs:this.indexMs,
          editorBytes:this.bytes, pages:index.pages.length,
          maxPageChars:index.maxPageChars, oversized:index.oversized,
        };
        addEventListener('beforeunload',this.onLeave);
        document.addEventListener('keydown',this.onKey);
        document.addEventListener('visibilitychange',this.onVisibility);
      }catch(error){
        this.active=false;
        this.worker?.terminate();
        this.shell?.remove();this.preview.hidden=false;
        this.trigger.disabled=false;this.trigger.textContent='Edit visually';
        window.__lanternMdPaged=null;
        alert('Unable to open paged Markdown editor: '+error.message+'\nOriginal file unchanged.');
        throw error;
      }
    }
  }
  window.LanternPagedEditor={open:async args=>new PagedEditor(args).open()};
})();
