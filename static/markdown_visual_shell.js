(() => {
  'use strict';
  // This small controller loads the 2.8 MB editor only when the user selects "Edit visually".
  // The existing read-only preview remains the fast default.
  const trigger = document.querySelector('[data-action="visual-edit"]');
  const sourceTrigger = document.querySelector('[data-action="mode-source"]');
  const previewTrigger = document.querySelector('[data-action="mode-preview"]');
  const preview = document.querySelector('article.md-preview');
  if (!trigger || !sourceTrigger || !previewTrigger || !preview) return;

  const path = trigger.getAttribute('data-path');
  const nonce = document.currentScript?.nonce || '';
  const root = document.querySelector('.content');
  // Exactly one authoritative mode. The legacy active getter remains for
  // browser tests and for the common save/draft path in either editor.
  const view = {
    mode: 'preview', get active() { return this.mode === 'visual' || this.mode === 'source'; },
    loading: false, instance: null, version: null,
    dirty: false, revision: 0, savedRevision: 0, saving: false, conflict: false,
    baseline: '', lastSaved: '', roundtripSafe: false, approvedReformat: false,
    saveTimer: 0, draftTimer: 0, checkTimer: 0, host: null, status: null,
    saveButton: null, closeButton: null, details: null, requestAgain: false,
    savedSincePreview: false, switchingFromPaged: false,
  };
  const key = location.origin + ':' + path;
  const escapeCss = s => s.replace(/[^A-Za-z0-9_-]/g, '-');
  const cleanLineEndings = text => String(text || '').replace(/\r\n/g, '\n').replace(/\n+$/, '');
  const status = (message, kind = 'info') => {
    if (view.status) {
      view.status.textContent = message;
      view.status.dataset.kind = kind;
    }
  };
  const api = async (url, options = {}) => {
    const res = await fetch(url, { cache: 'no-store', credentials: 'same-origin', ...options });
    let data;
    try { data = await res.json(); } catch { throw new Error('Invalid server response'); }
    if (!res.ok || data.error) {
      const error = new Error(data.error || ('HTTP ' + res.status));
      error.status = res.status;
      error.data = data;
      throw error;
    }
    return data;
  };

  // Browser-local crash recovery: retain the unsaved revision even if FJP/LAN disconnects.
  const drafts = {
    async store(mode, data) {
      if (!globalThis.indexedDB) return null;
      return new Promise((resolve, reject) => {
        const request = indexedDB.open('lantern-md-drafts', 1);
        request.onupgradeneeded = () => {
          if (!request.result.objectStoreNames.contains('drafts')) request.result.createObjectStore('drafts');
        };
        request.onerror = () => reject(request.error);
        request.onsuccess = () => {
          const db = request.result;
          const transaction = db.transaction('drafts', mode === 'get' ? 'readonly' : 'readwrite');
          const storage = transaction.objectStore('drafts');
          let op;
          if (mode === 'get') op = storage.get(key);
          else if (mode === 'delete') op = storage.delete(key);
          else op = storage.put(data, key);
          op.onsuccess = () => resolve(op.result);
          op.onerror = () => reject(op.error);
          transaction.oncomplete = () => db.close();
          transaction.onabort = () => db.close();
        };
      });
    },
    async read() { return this.store('get'); },
    async write(content) {
      return this.store('put', { content, version: view.version, at: Date.now() });
    },
    async clear() { return this.store('delete'); },
  };
  const getEditorText = () => view.instance?.getMarkdown() || '';
  const saveDraft = async () => {
    if (!view.active || !view.instance) return true;
    const text = getEditorText();
    if (text === view.lastSaved && !view.dirty) return true;
    try { await drafts.write(text); return true; }
    catch {
      status('Local draft storage unavailable. Keep this editor open or download the draft.', 'error');
      return false;
    }
  };
  const queueDraft = () => {
    clearTimeout(view.draftTimer);
    view.draftTimer = setTimeout(saveDraft, 900);
  };
  const queueSave = (delay = 2400) => {
    clearTimeout(view.saveTimer);
    if (view.conflict || !view.roundtripSafe && !view.approvedReformat) return;
    view.saveTimer = setTimeout(() => { void save(false); }, delay);
  };
  const changed = () => {
    if (!view.active) return;
    view.dirty = true;
    view.revision += 1;
    status(view.conflict ? 'Conflict: your draft is preserved; do not overwrite another client.' :
      !view.roundtripSafe && !view.approvedReformat
      ? 'Formatting differs from source. Review before saving.' : 'Unsaved changes…',
      view.conflict ? 'error' : 'info');
    // Milkdown features may issue internal document transactions after mount.
    // Compare the actual Markdown after a brief idle gap; only semantic source
    // changes should cause autosave or durable draft writes.
    clearTimeout(view.checkTimer);
    const observedRevision = view.revision;
    view.checkTimer = setTimeout(() => {
      if (!view.active || !view.instance || observedRevision !== view.revision) return;
      if (getEditorText() === view.lastSaved) {
        view.dirty = false;
        clearTimeout(view.draftTimer);
        clearTimeout(view.saveTimer);
        if (!view.conflict && !view.saving) status(view.roundtripSafe ?
          'Ready. Type directly in the document. Autosave enabled.' :
          'Visual editing ready. Formatting differs; review required before Save.');
        return;
      }
      queueDraft();
      queueSave();
    }, 260);
  };
  const restoreButtons = () => {
    const paged = !!window.__lanternMdPaged?.active;
    trigger.disabled = view.loading || view.saving || paged;
    trigger.textContent = paged ? 'Editing by section' : 'Edit visually';
    sourceTrigger.disabled = view.loading || view.saving;
    previewTrigger.disabled = view.loading || view.saving;
    for (const [control, mode] of [
      [previewTrigger, 'preview'], [trigger, 'visual'], [sourceTrigger, 'source'],
    ]) {
      control.setAttribute('aria-pressed', String(view.mode === mode || (mode === 'visual' && paged)));
    }
    if (view.saveButton) view.saveButton.disabled = view.saving;
  };

  const ensureShellStyle = () => {
    if (document.querySelector('link[href="/static/markdown_visual_shell.css"]')) return;
    const sheet = document.createElement('link');
    sheet.rel = 'stylesheet';
    sheet.href = '/static/markdown_visual_shell.css';
    document.head.appendChild(sheet);
  };

  // Third-party code runs only when explicitly requested, entirely from Lantern's own origin.
  const loadBundle = async () => {
    if (window.LanternCrepe) return window.LanternCrepe;
    if (window.__lanternCrepePromise) return window.__lanternCrepePromise;
    window.__lanternCrepePromise = new Promise((resolve, reject) => {
      const style = document.createElement('link');
      style.rel = 'stylesheet';
      style.href = '/static/vendor/lantern-crepe.min.css';
      document.head.appendChild(style);
      ensureShellStyle();
      const script = document.createElement('script');
      script.src = '/static/vendor/lantern-crepe.min.js';
      script.nonce = nonce;
      script.onload = () => window.LanternCrepe ? resolve(window.LanternCrepe) : reject(new Error('Editor not initialized'));
      script.onerror = () => reject(new Error('Offline editor asset unavailable'));
      document.head.appendChild(script);
    }).catch(err => { window.__lanternCrepePromise = null; throw err; });
    return window.__lanternCrepePromise;
  };
  const downloadDraft = () => {
    const content = getEditorText();
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = path.split('/').pop().replace(/\.(md|markdown)$/i, '') + '-lantern-unsaved.md';
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  };

  function renderToolbar(kind, sourceText = '') {
    ensureShellStyle();
    const shell = document.createElement('section');
    shell.className = 'md-visual-shell';
    const tools = document.createElement('div');
    tools.className = 'md-visual-tools';
    const heading = document.createElement('span');
    heading.textContent = kind === 'source' ? 'Markdown source · exact text' : 'Edit directly in document';
    heading.className = 'md-visual-label';
    const saveBtn = document.createElement('button');
    saveBtn.className = 'btn primary';
    saveBtn.textContent = 'Save';
    saveBtn.type = 'button';
    saveBtn.addEventListener('click', () => { void save(true); });
    const draftBtn = document.createElement('button');
    draftBtn.className = 'btn';
    draftBtn.textContent = 'Download draft';
    draftBtn.type = 'button';
    draftBtn.addEventListener('click', downloadDraft);
    const closeBtn = document.createElement('button');
    closeBtn.className = 'btn';
    closeBtn.textContent = 'Back to preview';
    closeBtn.type = 'button';
    closeBtn.addEventListener('click', () => { void close(); });
    const label = document.createElement('span');
    label.className = 'md-visual-status';
    label.setAttribute('role', 'status');
    label.setAttribute('aria-live', 'polite');
    tools.append(heading, saveBtn, draftBtn, closeBtn, label);
    const editorHost = document.createElement('div');
    editorHost.className = 'md-visual-host';
    editorHost.id = 'md-visual-edit-' + escapeCss(path);
    if (kind === 'source') {
      const area = document.createElement('textarea');
      area.className = 'md-source-area';
      area.setAttribute('aria-label', 'Markdown source');
      area.spellcheck = false;
      area.wrap = 'off';
      area.value = sourceText;
      area.addEventListener('input', changed);
      editorHost.append(area);
      view.instance = { getMarkdown: () => area.value, focus: () => area.focus(), destroy: () => {} };
    }
    shell.append(tools, editorHost);
    preview.insertAdjacentElement('afterend', shell);
    view.host = shell;
    view.status = label;
    view.saveButton = saveBtn;
    view.closeButton = closeBtn;
    return editorHost;
  }

  const showReformatReview = () => new Promise(resolve => {
    // Treat any source-to-editor rewrite as potentially lossy. Require an explicit
    // review before the first Save; never silently normalize Markdown.
    const original = view.baseline;
    const converted = getEditorText();
    const modal = document.createElement('dialog');
    modal.className = 'md-format-review';
    const title = document.createElement('h2');
    title.textContent = 'Review Markdown conversion before saving';
    const description = document.createElement('p');
    description.textContent = 'This editor serializes Markdown differently from the existing file. Review the source and proposed version; accepting will change the file format.';
    const contents = document.createElement('div');
    contents.className = 'md-format-diff';
    for (const [label, value] of [['Original', original], ['Editor serialization', converted]]) {
      const panel = document.createElement('div');
      const h = document.createElement('h3');
      h.textContent = label;
      const pre = document.createElement('pre');
      pre.textContent = value.length > 30000 ? value.slice(0, 30000) + '\n… (truncated comparison)' : value;
      panel.append(h, pre);
      contents.append(panel);
    }
    const actions = document.createElement('div');
    actions.className = 'md-format-actions';
    const cancel = document.createElement('button');
    cancel.className = 'btn';
    cancel.textContent = 'Keep original / Cancel save';
    const accept = document.createElement('button');
    accept.className = 'btn primary';
    accept.textContent = 'Accept conversion & Save';
    actions.append(cancel, accept);
    modal.append(title, description, contents, actions);
    document.body.appendChild(modal);
    const finish = decision => { modal.close(); modal.remove(); resolve(decision); };
    cancel.addEventListener('click', () => finish(false));
    accept.addEventListener('click', () => finish(true));
    modal.addEventListener('cancel', e => { e.preventDefault(); finish(false); });
    modal.showModal();
  });

  async function save(manual) {
    if (!view.active || !view.instance || view.conflict) {
      if (view.conflict) status('File changed externally. Your draft is retained; download it before reloading.', 'error');
      return;
    }
    if (view.saving) { view.requestAgain = true; return; }
    const text = getEditorText();
    if (text === view.lastSaved) {
      view.dirty = false;
      await drafts.clear().catch(() => {});
      if (manual) status('Already saved');
      return;
    }
    if (!view.roundtripSafe && !view.approvedReformat) {
      if (!manual) { status('Review conversion required before autosave.', 'warn'); return; }
      if (!await showReformatReview()) { status('Save cancelled; draft retained.', 'warn'); return; }
      view.approvedReformat = true;
    }
    const revision = view.revision;
    view.saving = true;
    restoreButtons();
    status('Saving…');
    try {
      const result = await api('/api/md/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, content: text, version: view.version }),
      });
      view.version = result.version;
      view.lastSaved = text;
      view.baseline = text;
      view.savedSincePreview = true;
      if (view.revision === revision) {
        view.dirty = false;
        await drafts.clear().catch(() => {});
        status('Saved ✓');
      } else {
        view.dirty = true;
        status('Saved; continuing with newer edits…');
        queueSave(500);
      }
    } catch (error) {
      if (error.status === 409 || error.status === 404) {
        view.conflict = true;
        status('Conflict: file changed or disappeared on disk. Draft preserved. Download your changes before reloading.', 'error');
      } else {
        status('Save failed: ' + error.message + '. Draft kept locally. Try Save again.', 'error');
      }
      await saveDraft();
    } finally {
      view.saving = false;
      restoreButtons();
      if (view.requestAgain) {
        view.requestAgain = false;
        if (!view.conflict) queueSave(100);
      }
    }
  }

  // Swap editing surfaces without changing documents or making a second
  // controller for Source. Both editors share draft, version and save state.
  async function switchEditor(kind) {
    if (!view.active || view.loading || view.saving || kind === view.mode) return;
    const contentNow = getEditorText();
    const wasDirty = view.dirty || contentNow !== view.lastSaved;
    // Milkdown can normalize raw Markdown, including HTML comments and tables.
    // Never reinterpret an unsaved exact Source draft without a versioned save.
    if (kind === 'visual' && view.mode === 'source' && wasDirty) {
      status('Save Source before entering Visual Edit; your unsaved text is unchanged.', 'warn');
      return;
    }
    // Never open a multi-megabyte document in the full Milkdown tree.
    // Source -> Visual goes through the existing section-indexed editor.
    if (kind === 'visual' && new Blob([contentNow]).size > 32 * 1024) {
      if (wasDirty) {
        status('Save Source before switching to section-based Visual Edit. Your draft is unchanged.', 'warn');
        return;
      }
      const y = scrollY;
      await view.instance?.destroy?.();
      view.instance = null;
      view.host?.remove();
      view.host = null;
      view.status = null;
      view.mode = 'preview';
      preview.hidden = false;
      restoreButtons();
      await start('visual');
      requestAnimationFrame(() => scrollTo(0, y));
      return;
    }
    if (wasDirty && !(await saveDraft())) return;
    const contents = wasDirty ? contentNow : view.baseline;
    const oldLastSaved = view.lastSaved;
    const oldSafe = view.roundtripSafe;
    const oldApproved = view.approvedReformat;
    let engine = null;
    try { if (kind === 'visual') engine = await loadBundle(); }
    catch (error) { status('Cannot load Visual editor: ' + error.message, 'error'); return; }
    const y = scrollY;
    view.loading = true;
    restoreButtons();
    clearTimeout(view.saveTimer);
    clearTimeout(view.draftTimer);
    clearTimeout(view.checkTimer);
    try {
      await view.instance?.destroy?.();
      view.instance = null;
      view.host?.remove();
      view.mode = kind;
      const editorHost = renderToolbar(kind, contents);
      if (kind === 'visual') {
        view.instance = await engine.createVisualMarkdown(editorHost, contents, changed, path, status);
      }
      const converted = getEditorText();
      const safeRoundtrip = cleanLineEndings(converted) === cleanLineEndings(contents);
      view.roundtripSafe = kind === 'source'
        ? (!wasDirty || oldSafe)
        : safeRoundtrip && (!wasDirty || oldSafe);
      view.approvedReformat = wasDirty && oldApproved;
      view.lastSaved = wasDirty ? oldLastSaved : (kind === 'visual' ? converted : contents);
      view.dirty = wasDirty;
      status(view.conflict ? 'Conflict: draft retained; another client changed the file.' :
        wasDirty ? 'Unsaved draft preserved across modes. Save before leaving.' :
        !view.roundtripSafe ? 'Formatting differs: review required before Save.' :
        kind === 'source' ? 'Source ready. Edits use versioned autosave.' :
        'Ready. Edit directly in the document.',
        view.conflict ? 'error' : view.dirty || !view.roundtripSafe ? 'warn' : 'info');
      view.instance.focus();
      requestAnimationFrame(() => scrollTo(0, y));
    } catch (error) {
      // Never discard the draft written above on a failed mode transition.
      view.instance?.destroy?.();
      view.instance = null;
      view.host?.remove();
      view.host = null;
      view.mode = 'preview';
      preview.hidden = false;
      alert('Unable to switch editor: ' + error.message + '. Saved file unchanged; local draft retained.');
    } finally {
      view.loading = false;
      restoreButtons();
    }
  }

  async function close() {
    if (!view.active || view.saving || view.loading) return;
    if (view.dirty && !confirm('Unsaved changes will remain as a local draft. Show the last saved Preview?')) return;
    if (view.dirty && !(await saveDraft())) return;
    clearTimeout(view.saveTimer);
    clearTimeout(view.draftTimer);
    clearTimeout(view.checkTimer);
    const y = scrollY;
    await view.instance?.destroy?.();
    view.instance = null;
    view.host?.remove();
    view.host = null;
    view.status = null;
    view.mode = 'preview';
    preview.hidden = false;
    restoreButtons();
    // Preview is server-rendered. Reload only when this tab saved new source;
    // clean toggles simply switch surfaces without a navigation or refetch.
    if (view.savedSincePreview) {
      sessionStorage.setItem('lantern-md-scroll:' + path, String(y));
      location.reload();
    } else {
      requestAnimationFrame(() => scrollTo(0, y));
    }
  }

  async function start(kind = 'visual') {
    if (view.active) return switchEditor(kind);
    if (view.loading) return;
    const pagedNow = window.__lanternMdPaged;
    if (pagedNow?.active) {
      view.switchingFromPaged = true;
      try { await pagedNow.close(kind); }
      finally { view.switchingFromPaged = false; }
      if (pagedNow.active) return; // Dirty section: user cancelled switch.
    }
    view.loading = true;
    restoreButtons();
    try {
      const start = performance.now();
      const doc = await api('/api/md/document?p=' + encodeURIComponent(path));
      if(kind === 'visual' && doc.bytes > 32 * 1024){
        const loadPaged = () => new Promise((resolve,reject)=>{
          if(window.LanternPagedEditor)return resolve(window.LanternPagedEditor);
          const script=document.createElement('script');
          script.src='/static/markdown_paged_editor.js';script.nonce=nonce;
          script.onload=()=>window.LanternPagedEditor ?
            resolve(window.LanternPagedEditor):reject(Error('Paged editor module not initialized'));
          script.onerror=()=>reject(Error('Paged editor module unavailable'));
          document.head.appendChild(script);
        });
        const paged=await loadPaged();
        await paged.open({doc,path,preview,trigger,nonce,loadBundle,
          onClosed: (changed) => {
            view.mode = 'preview';
            if (changed) view.savedSincePreview = true;
            restoreButtons();
            if (view.savedSincePreview && !view.switchingFromPaged) {
              sessionStorage.setItem('lantern-md-scroll:' + path, String(scrollY));
              location.reload();
            }
          },
        });
        view.mode = 'paged';
        restoreButtons();
        return;
      }
      const engine = kind === 'visual' ? await loadBundle() : null;
      let contents = doc.content;
      const recovered = await drafts.read().catch(() => null);
      view.version = doc.version;
      view.baseline = doc.content;
      view.conflict = false;
      view.dirty = false;
      view.approvedReformat = false;
      if (recovered?.mode !== 'paged' && typeof recovered?.content === 'string'
        && recovered.content !== doc.content && confirm('An unsaved Markdown draft was found in this browser. Restore it?')) {
        contents = recovered.content;
        if (recovered.version !== doc.version) view.conflict = true;
      }
      const editorHost = renderToolbar(kind, contents);
      // Source needs no Milkdown runtime; both modes use the same versioned save.
      preview.hidden = true;
      if (kind === 'visual') {
        view.instance = await engine.createVisualMarkdown(editorHost, contents, changed, path, status);
      }
      view.mode = kind;
      const restoredDraft = contents !== doc.content;
      const serialized = view.instance.getMarkdown();
      // A restored draft is not the remote baseline. Never accidentally treat it
      // as "already saved" and delete the only copy of unsaved edits.
      view.lastSaved = restoredDraft ? doc.content : serialized;
      view.roundtripSafe = kind === 'source' || (!restoredDraft &&
        cleanLineEndings(serialized) === cleanLineEndings(view.baseline));
      if (restoredDraft) {
        view.dirty = true;
        view.revision += 1;
        // Keep the exact original draft in IndexedDB until the user changes or
        // explicitly saves it. Initial parsing may normalize Markdown syntax.
      }
      status(view.conflict ? 'Draft restored but disk version differs. Do not overwrite; download draft first.' :
        restoredDraft ? 'Unsaved draft restored.' :
        kind === 'source' ? 'Source ready. Versioned autosave enabled.' :
        view.roundtripSafe ? 'Ready. Type directly in the document. Autosave enabled.' :
        'Visual editing ready. Formatting differs; review required before Save.',
        view.conflict ? 'error' : view.roundtripSafe ? 'info' : 'warn');
      restoreButtons();
      view.instance.focus();
      window.__lanternMdMetrics = { loadMs: Math.round(performance.now() - start), editorBytes: doc.bytes };
    } catch (error) {
      if (view.instance) view.instance.destroy();
      view.instance = null;
      view.host?.remove();
      view.host = null;
      view.status = null;
      view.mode = 'preview';
      preview.hidden = false;
      alert('Markdown editor unavailable: ' + error.message + '\nOriginal preview and file are unchanged.');
    } finally {
      view.loading = false;
      restoreButtons();
    }
  }

  trigger.addEventListener('click', () => { void start('visual'); });
  sourceTrigger.addEventListener('click', () => { void start('source'); });
  previewTrigger.addEventListener('click', () => {
    if (window.__lanternMdPaged?.active) { void window.__lanternMdPaged.close(); return; }
    if (view.active) void close();
  });
  document.addEventListener('keydown', e => {
    if (!view.active || !(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== 's') return;
    e.preventDefault();
    void save(true);
  });
  window.addEventListener('beforeunload', e => {
    if (!view.active || !view.dirty) return;
    e.preventDefault();
    e.returnValue = '';
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && view.dirty) void saveDraft();
  });
  const scrollKey = 'lantern-md-scroll:' + path;
  const priorScroll = sessionStorage.getItem(scrollKey);
  if (priorScroll) {
    sessionStorage.removeItem(scrollKey);
    requestAnimationFrame(() => scrollTo(0, Number(priorScroll) || 0));
  }
  window.__lanternMdVisual = { get state() { return view; }, open: start,
    show: start, save: () => save(true), preview: close };
})();
