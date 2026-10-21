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
    async renderSectionDiffPanel() {
      if (!this.shell) return;
      let panel = this.shell.querySelector('.md-paged-diff-panel');
      if (!panel) {
        panel = document.createElement('div');
        panel.className = 'md-paged-diff-panel';
        const top = this.shell.querySelector('.md-paged-top');
        if (top) top.insertAdjacentElement('afterend', panel);
        else this.shell.prepend(panel);
      }
      try {
        const state = await api('/api/work?p=' + encodeURIComponent(this.path));
        const baseText = state?.saved?.content ?? this.source;
        const currentText = this.currentFullMarkdown ? this.currentFullMarkdown() : this.source;
        const diff = globalThis.LanternMarkdownDiff;
        const hunks = diff?.diffLines ? diff.diffLines(baseText, currentText) : [];
        if (!hunks.length) {
          panel.hidden = true;
          panel.textContent = '';
          return;
        }
        panel.hidden = false;
        panel.textContent = '';
        const head = document.createElement('div');
        head.className = 'md-paged-diff-head';
        const title = document.createElement('span');
        title.style.color = '#68e37a';
        title.textContent = `🔀 Section Editing Live Diff: ${hunks.length} hunk(s) vs accepted baseline`;
        const btnWrap = document.createElement('div');
        btnWrap.style.display = 'inline-flex';
        btnWrap.style.gap = '6px';
        const acceptBtn = button('✓ Accept All Diff (Ctrl+S)', () => { void this.save(true); }, 'btn primary');
        btnWrap.append(acceptBtn);
        head.append(title, btnWrap);
        panel.append(head);
        hunks.slice(0, 12).forEach((h, i) => {
          const row = document.createElement('div');
          row.className = 'md-paged-hunk-item';
          const meta = document.createElement('div');
          meta.style.color = '#9fb1c5';
          meta.style.marginBottom = '3px';
          meta.textContent = `Hunk #${i + 1} (${h.kind.toUpperCase()} · Line ${(h.draftStart || 0) + 1})`;
          row.append(meta);
          if (Array.isArray(h.baseText) && h.baseText.length) {
            const del = document.createElement('div');
            del.className = 'md-paged-hunk-del';
            del.textContent = '- ' + h.baseText.slice(0, 6).join('\n- ');
            row.append(del);
          }
          if (Array.isArray(h.draftText) && h.draftText.length) {
            const add = document.createElement('div');
            add.className = 'md-paged-hunk-add';
            add.textContent = '+ ' + h.draftText.slice(0, 6).join('\n+ ');
            row.append(add);
          }
          panel.append(row);
        });
      } catch (_) {}
    }

    constructor({doc, path, trigger, preview, loadBundle, nonce, onClosed}) {
      this.path=path; this.trigger=trigger; this.preview=preview;
      this.loadBundle=loadBundle; this.nonce=nonce; this.onClosed=onClosed;
      this.savedSincePreview=false;
      this.source=doc.content; this.version=doc.version; this.bytes=doc.bytes;
      this.index=null; this.worker=null; this.pending=new Map(); this.workerId=0;
      this.pageNumber=-1; this.page=null; this.pageOriginal='';
      this.engine=null; this.rich=null; this.largeEditor=null; this.blockWrap=null; this.generation=0;
      this.lastSaved=''; this.roundtripSafe=false; this.approved=false;
      this.dirty=false; this.saving=false; this.conflict=false; this.revision=0;
      this.draftTimer=0; this.changedTimer=0; this.reindex=null;
      this.active=false; this.loadingPage=false; this.savePromise=null;
      this.botTurnActive=false;
      this.pendingDraftWrites=new Set();
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
      if(!this.rich)return '';
      if(typeof this.rich.isCleanFromMount==='function'&&this.rich.isCleanFromMount()&&this.pageOriginal)return this.pageOriginal;
      const raw=this.rich.getMarkdown();
      return typeof globalThis.LanternReconcileMarkdown==='function'
        ? globalThis.LanternReconcileMarkdown(raw, this.pageOriginal||'')
        : raw;
    }
    pageSource() { return this.source.slice(this.page.start,this.page.end); }
    hasUnsaved() { return !!this.page && this.currentText() !== this.lastSaved; }
    async clearDraft() {
      await Promise.allSettled([...this.pendingDraftWrites]);
      await this.storeDraft('delete');
    }
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
        this.pending.set(id,{
          resolve: rawRes => {
            try {
              const pages = Array.isArray(rawRes?.pages) ? rawRes.pages : [];
              if (pages.length > 1 && typeof source === 'string') {
                const merged = [ { ...pages[0] } ];
                for (let i = 1; i < pages.length; i++) {
                  const prev = merged[merged.length - 1];
                  const cur = pages[i];
                  const prevSlice = source.slice(prev.start, prev.end).trimEnd();
                  const curSlice = source.slice(cur.start, cur.end).trimStart();
                  const prevLastLine = (prevSlice.split(/\r?\n/).pop() || '').trim();
                  const curLines = curSlice.split(/\r?\n/);
                  const curFirstLine = (curLines[0] || '').trim();
                  const curSecondLine = (curLines[1] || '').trim();
                  const curStartsOrphanPipeRows = curFirstLine.startsWith('|') && !/^\|?[ \t:|-]+\|?$/.test(curSecondLine);
                  if (prevLastLine.startsWith('|') && curStartsOrphanPipeRows) {
                    prev.end = cur.end;
                    prev.oversized = (prev.end - prev.start) > 48 * 1024;
                  } else {
                    merged.push({ ...cur });
                  }
                }
                if (merged.length !== pages.length) {
                  rawRes.pages = merged;
                  if (Array.isArray(rawRes.headings)) {
                    for (const h of rawRes.headings) {
                      let lo = 0, hi = merged.length - 1;
                      while (lo < hi) {
                        const mid = (lo + hi) >>> 1;
                        if (merged[mid].end <= h.at) lo = mid + 1;
                        else hi = mid;
                      }
                      h.page = lo;
                    }
                  }
                }
              }
            } catch {}
            resolve(rawRes);
          },
          reject,
          timeout,
        });
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
          let operation;
          if (mode==='get') operation=store.get(this.draftKey);
          else if (mode==='delete') {
            store.delete(location.origin+':'+this.path); // Stale full-mode draft.
            operation=store.delete(this.draftKey);
          } else operation=store.put(value,this.draftKey);
          let result;
          operation.onsuccess=()=>{result=operation.result;};
          operation.onerror=()=>reject(operation.error);
          txn.oncomplete=()=>{db.close();resolve(result);};
          txn.onabort=()=>{db.close();reject(txn.error);};
        };
      });
    }
    async draftWrite() {
      if(!this.active || this.loadingPage || !this.hasUnsaved()) return;
      const current=this.currentText();
      const pending=this.storeDraft('put',{
        mode:'paged', content:current, version:this.version,
        original:this.pageOriginal, start:this.page.start,
        end:this.page.end, at:Date.now(),
      });
      this.pendingDraftWrites.add(pending);
      try { await pending; }
      catch { this.status('Cannot store local draft; keep this tab open until saved.','error'); }
      finally { this.pendingDraftWrites.delete(pending); }
    }
    changed(generation) {
      if(generation!==this.generation||!this.active)return;
      if(this.rich&&typeof this.rich.isCleanFromMount==='function'&&this.rich.isCleanFromMount())return;
      this.dirty=true; this.revision++;
      this.status(this.conflict?'File changed on another client; draft preserved.' :
        this.botTurnActive?'Lanbot is updating the real .md.' :
        'Updating the real .md automatically…',this.conflict?'error':'info');
      clearTimeout(this.changedTimer);
      const revision=this.revision;
      this.changedTimer=setTimeout(()=>{
        if(revision!==this.revision || !this.active)return;
        if(this.currentText()===this.lastSaved) {
          this.dirty=false;clearTimeout(this.draftTimer);
          if(!this.conflict&&!this.saving)this.status('Ready. Edit directly in the document.');
          return;
        }
        clearTimeout(this.draftTimer);
        this.draftTimer=setTimeout(()=>{
          void this.draftWrite();
          if(!this.botTurnActive)void this.flushReal(false);
          if(!this.botTurnActive)void this.renderSectionDiffPanel();
        },430);
      },260);
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
      const bottomNav=document.createElement('div');
      bottomNav.className='md-paged-bottom-nav';
      const prevBottom=button('← Previous',()=>{void this.go(this.pageNumber-1);});
      const countBottom=document.createElement('span');
      countBottom.className='md-page-count';
      const nextBottom=button('Next →',()=>{void this.go(this.pageNumber+1);});
      bottomNav.append(prevBottom,countBottom,nextBottom);
      shell.append(toolbar,host,bottomNav);
      this.preview.insertAdjacentElement('afterend',shell);
      this.shell=shell;this.host=host;this.statusEl=status;
      this.prev=prev;this.next=next;this.pageField=page;
      this.prevBottom=prevBottom;this.nextBottom=nextBottom;this.countBottomEl=countBottom;
      this.countEl=pageCount;this.sections=sections;this.headingSearch=headingSearch;
      this.saveButton=save;this.searchInput=search;
      this.headingRefresh();
      this.updateNav();
    }
    headingRefresh(){
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
      this.prev.disabled=this.loadingPage||this.botTurnActive||this.pageNumber<=0;
      this.next.disabled=this.loadingPage||this.botTurnActive||this.pageNumber>=total-1;
      if(this.prevBottom)this.prevBottom.disabled=this.prev.disabled;
      if(this.nextBottom)this.nextBottom.disabled=this.next.disabled;
      if(this.countBottomEl)this.countBottomEl.textContent='Page '+(this.pageNumber+1)+' / '+total;
      this.pageField.disabled=this.loadingPage||this.botTurnActive;
      this.sections.disabled=this.loadingPage||this.botTurnActive;
      this.headingSearch.disabled=this.loadingPage;
      this.saveButton.disabled=this.saving||this.loadingPage||this.conflict||this.botTurnActive;
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
    async flushReal() {
      if(!this.active||!this.page||this.conflict||this.botTurnActive)return false;
      if(this.saving)return this.savePromise || false;
      const current=this.currentText();
      if(current===this.lastSaved) {
        this.dirty=false;
        this.status('Project .md is up to date.');
        return true;
      }
      if(!this.roundtripSafe&&!this.approved){
        this.approved=true;
      }
      const revision=this.revision;
      this.saving=true;this.updateNav();this.status('Updating real .md…');
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
          this.savedSincePreview=true;
          this.page.end+=change;
          for(let i=this.pageNumber+1;i<this.index.pages.length;i++){
            this.index.pages[i].start+=change;this.index.pages[i].end+=change;
          }
          this.pageOriginal=patch;this.lastSaved=current;
          this.roundtripSafe=true;this.approved=false;
          if(this.revision===revision) {
            this.dirty=false;
            await this.clearDraft().catch(()=>{});
            this.status('Updated real .md. Ctrl+S accepts the diff baseline.');
          } else {
            this.dirty=true;
            await this.draftWrite();
            this.status('Updated real .md; newer typing still needs syncing.','warn');
          }
          this.reindex=this.workerIndex(this.source).catch(err=>{
            this.status('Real .md updated; page index refresh failed: '+err.message,'warn');
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
    async save(manual=true) {
      if(!this.active||this.conflict||this.botTurnActive)return false;
      if(this.saving&&!(await this.savePromise))return false;
      if(this.hasUnsaved()&&!(await this.flushReal()))return false;
      try{
        const state=await api('/api/work?p='+encodeURIComponent(this.path));
        if(!state.saved||state.currentVersion!==this.version){
          this.status('Project .md changed externally. Review before accepting diff.','warn');
          return false;
        }
        await api('/api/work/save',{
          method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({path:this.path,expectHash:state.work?.hash||null,
            expectSavedVersion:state.saved.version}),
        });
        if(manual)this.status('Saved diff baseline into md_temp. Real .md stays editable.');
        return true;
      }catch(error){
        this.status('Cannot accept diff: '+error.message,'error');return false;
      }
    }

    async beginBotTurn() {
      if(!this.active||this.conflict||this.loadingPage||this.botTurnActive)
        throw Error('Section editor is not ready for a Lanbot turn.');
      if(this.saving&&!(await this.savePromise))
        throw Error('Cannot finish the current Markdown write.');
      if(this.hasUnsaved()&&!(await this.flushReal()))
        throw Error('Cannot synchronize this section with the real .md.');
      const state=await api('/api/work?p='+encodeURIComponent(this.path));
      if(state.currentVersion!==this.version)
        throw Error('Project .md changed outside Lantern. Refresh this section before editing.');
      clearTimeout(this.changedTimer);clearTimeout(this.draftTimer);
      this.botTurnActive=true;
      this.host.inert=true;
      this.host.querySelector('.ProseMirror')?.blur();
      this.status('Lanbot edits the real .md; this section will refresh when it finishes.');
      this.updateNav();
      return state.work?.hash||null;
    }
    cancelBotTurn() {
      this.botTurnActive=false;
      if(this.host)this.host.inert=false;
      if(this.active)this.updateNav();
    }
    onBotWorkLocked(eventPath, locked) {
      const normEvent=String(eventPath||'').replace(/\\/g,'/').replace(/^\/+/, '');
      const normPath=String(this.path||'').replace(/\\/g,'/').replace(/^\/+/, '');
      if(normEvent&&normEvent!==normPath)return;
      if(locked){
        this.botTurnActive=true;
        if(this.host){this.host.inert=true;this.host.querySelector('.ProseMirror')?.blur();}
        this.status('🔒 Lanbot is editing the real .md; this section will refresh when it finishes.');
        if(this.active)this.updateNav();
      }else if(this.botTurnActive){
        this.cancelBotTurn();
      }
    }
    async onBotWorkChanged(final) {
      if(!this.botTurnActive||!final)return;
      try {
        const state=await api('/api/work?p='+encodeURIComponent(this.path));
        if(!state.saved)throw Error('Project Markdown is missing.');
        if(this.hasUnsaved()){
          this.conflict=true;
          await this.draftWrite();
          this.status('Another edit occurred during Lanbot. Local text retained; review before applying.','warn');
          return;
        }
        const next=state.work?.content??state.saved.content;
        if(next===this.source) {
          this.version=state.currentVersion;
          this.status('Lanbot completed; real .md is unchanged.');
          return;
        }
        const previous=this.source, oldPage=this.page;
        const oldBlock=previous.slice(oldPage.start,oldPage.end);
        const indexed=await this.workerIndex(next);
        const matching=indexed.pages.map((item,i)=>
          next.slice(item.start,item.end)===oldBlock?i:-1).filter(i=>i>=0);
        let target=matching.length===1?matching[0]:-1;
        if(target<0&&next.slice(0,oldPage.start)===previous.slice(0,oldPage.start))
          target=indexed.pages.findIndex(item=>item.start===oldPage.start);
        const unmapped=target<0;
        if(unmapped)target=0;
        this.source=next;this.version=state.currentVersion;
        this.index=indexed;this.reindex=null;
        this.botTurnActive=false;
        this.host.inert=false;
        this.savedSincePreview=true;
        if(!await this.go(target,null,true))
          throw Error('Could not reload the updated section.');
        if(unmapped)this.status(
          'Lanbot changed document structure. Showing section 1; old position could not be verified.','warn');
        else this.status('Lanbot updated the real .md. Continue editing; Ctrl+S accepts diff.');
      } catch(error) {
        this.conflict=true;
        this.status('Cannot synchronize Lanbot edit: '+error.message+
          '. Existing editor content retained; reopen Preview to inspect the real file.','error');
      } finally {
        this.cancelBotTurn();
      }
    }

    async go(next, restore=null, force=false) {
      if(!this.active||this.loadingPage)return false;
      const num=Math.max(0,Math.min(this.index.pages.length-1,Math.trunc(next)));
      if(!Number.isFinite(num))return false;
      if(num===this.pageNumber&&!restore&&!force)return true;
      if(this.saving&&!await this.savePromise)return false;
      if(this.botTurnActive){this.status('Wait for Lanbot to finish updating this section.','warn');return false;}
      if(this.hasUnsaved()&&!await this.flushReal())return false;
      clearTimeout(this.draftTimer);clearTimeout(this.changedTimer);
      this.loadingPage=true;this.updateNav();
      try {
        if(this.reindex) {
          const result=await this.reindex;this.reindex=null;
          if(result){this.index=result;this.headingRefresh();}
        }
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
        const fenceMatch=content.match(/^((?:\r?\n)*[ \t]{0,3}(?:`{3,}|~{3,})[^\r\n]*\r?\n)([\s\S]*?)(\r?\n[ \t]{0,3}(?:`{3,}|~{3,})[ \t]*(?:\r?\n)*)$/);
        const hasPipeTable=!fenceMatch && /^[ \t]*\|.+\|[ \t]*\r?\n[ \t]*\|[ \t:|-]+\|[ \t]*$/m.test(content);
        if(p.oversized && (fenceMatch || !hasPipeTable)) {
          const match=fenceMatch;
          const note=document.createElement('p');
          note.className='md-oversized-note';
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
          const visualContent=typeof globalThis.LanternPrepareVisualMarkdown==='function'
            ? globalThis.LanternPrepareVisualMarkdown(content)
            : content;
          this.rich=await this.engine.createVisualMarkdown(this.host,visualContent,()=>this.changed(generation),this.path,(message,kind)=>this.status(message,kind));
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
      if(this.active&&this.hasUnsaved()){event.preventDefault();event.returnValue=LEAVE_WARNING;}
    }
    onKey(event){
      if(!this.active||!(event.ctrlKey||event.metaKey)||event.key.toLowerCase()!=='s')return;
      event.preventDefault();void this.save(true);
    }
    onVisibility(){
      if(document.hidden&&this.hasUnsaved())void this.draftWrite();
    }
    async close(destination='preview'){
      if(!this.active||this.saving||this.loadingPage)return false;
      if(this.botTurnActive){this.status('Wait for Lanbot to finish first.','warn');return false;}
      if(this.hasUnsaved()&&!(await this.flushReal()))return false;
      clearTimeout(this.draftTimer);
      clearTimeout(this.changedTimer);clearTimeout(this.headingSearchTimer);
      this.loadingPage=true;this.updateNav();
      try { await this.clearDraft(); }
      catch {
        this.loadingPage=false;this.updateNav();
        this.status('Cannot clear local draft. Keep editing or download a copy before closing.','error');
        return false;
      }
      this.active=false;
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
      this.onClosed?.(this.savedSincePreview);
      return true;
    }
    async open() {
      const began=performance.now();
      this.trigger.disabled=true;this.trigger.textContent='Indexing Markdown…';
      try {
        const indexed=this.workerIndex(this.source).then(result=>{
          this.indexMs=Math.round(performance.now()-began);return result;
        });
        const [index,engine,draft]=await Promise.all([
          indexed,this.loadBundle(),this.storeDraft('get').catch(()=>null),
        ]);
        this.index=index;this.engine=engine;
        this.initUI();this.preview.hidden=true;this.active=true;
        window.__lanternMdPaged=this;
        let restored=null;
        if(draft?.mode==='paged' && typeof draft.content==='string') {
          if(confirm('Unsaved Markdown draft found. Restore it?')) restored=draft;
          else await this.clearDraft();
        }
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
