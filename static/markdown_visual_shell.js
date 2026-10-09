(() => {
  'use strict';
  // This small controller loads the 2.8 MB editor only when the user selects "Edit visually".
  // The existing read-only preview remains the fast default.
  const trigger = document.querySelector('[data-action="visual-edit"]');
  const preview = document.querySelector('article.md-preview');
  if (!trigger || !preview) return;

  const path = trigger.getAttribute('data-path');
  const nonce = document.currentScript?.nonce || '';
  const root = document.querySelector('.content');
  const view = {
    active: false, loading: false, instance: null, version: null,
    dirty: false, revision: 0, savedRevision: 0, saving: false, conflict: false,
    baseline: '', lastSaved: '', roundtripSafe: false, approvedReformat: false,
    saveTimer: 0, draftTimer: 0, checkTimer: 0, host: null, status: null,
    saveButton: null, closeButton: null, details: null, requestAgain: false,
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
    if (!view.active || !view.dirty || !view.instance) return;
    const text = getEditorText();
    if (text === view.lastSaved) return;
    try { await drafts.write(text); }
    catch { status('Local draft storage unavailable. Do not close this tab until saved.', 'warn'); }
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
    trigger.disabled = false;
    trigger.textContent = view.active ? 'Editing visually' : 'Edit visually';
    if (view.saveButton) view.saveButton.disabled = view.saving;
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
      const shellStyle = document.createElement('link');
      shellStyle.rel = 'stylesheet';
      shellStyle.href = '/static/markdown_visual_shell.css';
      document.head.appendChild(shellStyle);
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

  function renderToolbar() {
    const shell = document.createElement('section');
    shell.className = 'md-visual-shell';
    const tools = document.createElement('div');
    tools.className = 'md-visual-tools';
    const heading = document.createElement('span');
    heading.textContent = '✎ Edit directly in document';
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

  async function close() {
    if (!view.active || view.saving) return;
    if (view.dirty && !confirm('Unsaved changes remain in this browser. Return to preview?')) return;
    clearTimeout(view.saveTimer);
    clearTimeout(view.draftTimer);
    clearTimeout(view.checkTimer);
    if (view.dirty) await saveDraft();
    view.active = false;
    view.instance?.destroy();
    view.instance = null;
    const y = scrollY;
    // Source of truth for the preview stays the server's existing renderer.
    sessionStorage.setItem('lantern-md-scroll:' + path, String(y));
    location.reload();
  }

  async function start() {
    if (view.active || view.loading) return;
    view.loading = true;
    trigger.disabled = true;
    trigger.textContent = 'Loading editor…';
    try {
      const start = performance.now();
      const doc = await api('/api/md/document?p=' + encodeURIComponent(path));
      const engine = await loadBundle();
      let contents = doc.content;
      const recovered = await drafts.read().catch(() => null);
      view.version = doc.version;
      view.baseline = doc.content;
      if (recovered?.content && recovered.content !== doc.content && confirm('An unsaved Markdown draft was found in this browser. Restore it?')) {
        contents = recovered.content;
        if (recovered.version !== doc.version) view.conflict = true;
      }
      const editorHost = renderToolbar();
      // Preserve the same screen and scroll position; only replace the content surface.
      preview.hidden = true;
      view.host.scrollIntoView({ block: 'nearest' });
      view.instance = await engine.createVisualMarkdown(editorHost, contents, changed);
      view.active = true;
      const restoredDraft = contents !== doc.content;
      const serialized = view.instance.getMarkdown();
      // A restored draft is not the remote baseline. Never accidentally treat it
      // as "already saved" and delete the only copy of unsaved edits.
      view.lastSaved = restoredDraft ? doc.content : serialized;
      view.roundtripSafe = !restoredDraft &&
        cleanLineEndings(serialized) === cleanLineEndings(view.baseline);
      if (restoredDraft) {
        view.dirty = true;
        view.revision += 1;
        // Keep the exact original draft in IndexedDB until the user changes or
        // explicitly saves it. Initial parsing may normalize Markdown syntax.
      }
      status(view.conflict ? 'Draft restored but disk version differs. Do not overwrite; download draft first.' :
        restoredDraft ? 'Unsaved draft restored. Review changes before the first Save.' :
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
      view.active = false;
      preview.hidden = false;
      alert('Visual editor unavailable: ' + error.message + '\nOriginal preview and file are unchanged.');
    } finally {
      view.loading = false;
      restoreButtons();
    }
  }

  trigger.addEventListener('click', () => { void start(); });
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
  window.__lanternMdVisual = { get state() { return view; }, open: start, save: () => save(true) };
})();
