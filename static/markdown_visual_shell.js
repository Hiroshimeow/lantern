(() => {
  'use strict';
  // This small controller loads the 2.8 MB editor only when the user selects "Edit visually".
  // The existing read-only preview remains the fast default.
  const trigger = document.querySelector('[data-action="visual-edit"]');
  const sourceTrigger = document.querySelector('[data-action="mode-source"]');
  const previewTrigger = document.querySelector('[data-action="mode-preview"]');
  const preview = document.querySelector('article.md-preview');
  const topActions = document.querySelector('[data-md-edit-actions]');
  const topStatus = document.querySelector('[data-md-status]');
  const saveHeader = document.querySelector('[data-action="md-save"]');
  const draftHeader = document.querySelector('[data-action="md-download-draft"]');
  const backHeader = document.querySelector('[data-action="md-back-preview"]');
  if (!trigger || !sourceTrigger || !previewTrigger || !preview) return;

  const path = trigger.getAttribute('data-path');
  const nonce = document.currentScript?.nonce || '';
  // Files near 41 KiB fit in one editor; retain paged editing for larger
  // documents to cap ProseMirror work and preserve byte-exact page boundaries.
  const FULL_VISUAL_LIMIT_BYTES = 64 * 1024;
  const root = document.querySelector('.content');
  const anchorBridge = globalThis.LanternAnchorBridge;
  const anchorKey = 'lantern-md-anchor:' + path;
  const capturePosition = () => anchorBridge?.capture(view.mode, preview) || null;
  let pointerBookmark = null;
  const takeBookmark = () => {
    const selected = pointerBookmark || capturePosition();
    pointerBookmark = null;
    return selected;
  };
  async function restorePosition(mode, bookmark, y = null) {
    // Position mapping is best effort. A stale or unresolvable bookmark must
    // never tear down an otherwise valid editor, especially with unsaved work.
    let matched = false;
    try { matched = !!(bookmark && await anchorBridge?.restore(mode, bookmark, preview)); }
    catch (error) { console.warn('Markdown location could not be restored:', error); }
    if (!matched && y !== null) requestAnimationFrame(() => scrollTo(0, y));
    return matched;
  }
  // Exactly one authoritative mode. The legacy active getter remains for
  // browser tests and for the common save/draft path in either editor.
  const view = {
    mode: 'preview', get active() { return this.mode === 'visual' || this.mode === 'source'; },
    loading: false, instance: null, version: null,
    dirty: false, revision: 0, savedRevision: 0, saving: false, conflict: false,
    baseline: '', lastSaved: '', roundtripSafe: false, approvedReformat: false,
    draftTimer: 0, diffTimer: 0, checkTimer: 0, host: null, status: null,
    saveButton: null, closeButton: null, details: null,
    sourceArea: null, sourceBackdrop: null, sourceDeletions: null, visualDiffFallback: null, hunks: [],
    workHash: null, workState: 'clean', ackedText: '', piTurn: null, applyingPi: false,
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
  const draftWrites = new Set();
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
          else if (mode === 'delete') {
            storage.delete('paged:' + key); // Old 32-KiB paged drafts for this same document.
            op = storage.delete(key);
          } else op = storage.put(data, key);
          let result;
          op.onsuccess = () => { result = op.result; };
          op.onerror = () => reject(op.error);
          transaction.oncomplete = () => { db.close(); resolve(result); };
          transaction.onabort = () => { db.close(); reject(transaction.error); };
        };
      });
    },
    async read() { return this.store('get'); },
    async write(content) {
      const pending = this.store('put', {
        content, version: view.version, workHash: view.workHash || null, at: Date.now(),
      });
      draftWrites.add(pending);
      try { return await pending; }
      finally { draftWrites.delete(pending); }
    },
    async clear() {
      // A pending visibility/idle write must not resurrect a discarded draft.
      await Promise.allSettled([...draftWrites]);
      return this.store('delete');
    },
  };
  const getEditorText = () => view.instance?.getMarkdown() || '';
  // HTML textareas normalize CRLF/CR to LF when read. This is not a user edit,
  // so compare against the normalized baseline without rewriting disk bytes.
  const matchesLastSaved = text => text === (view.mode === 'source'
    ? view.lastSaved.replace(/\r\n?/g, '\n') : view.lastSaved);
  const diffApi = () => globalThis.LanternMarkdownDiff;
  const diffBaseline = () => String(view.baseline || '');
  const syncSourceBackdrop = () => {
    if (!view.sourceArea || !view.sourceBackdrop) return;
    view.sourceBackdrop.style.transform =
      'translate(' + (-view.sourceArea.scrollLeft) + 'px,' + (-view.sourceArea.scrollTop) + 'px)';
  };
  const renderSourceDiff = (hunks, draftText) => {
    if (!view.sourceArea || !view.sourceBackdrop || !view.sourceDeletions) return;
    const lines = String(draftText || '').replace(/\r\n?/g, '\n').split('\n');
    const classes = Array.from({length: Math.max(1, lines.length)}, () => new Set());
    const deletions = [];
    for (const hunk of hunks) {
      if (hunk.kind === 'add' || hunk.kind === 'mod') {
        for (let i = hunk.draftStart; i < hunk.draftEnd; i++) {
          if (classes[i]) classes[i].add(hunk.kind === 'add' ? 'md-diff-add' : 'md-diff-mod');
        }
      }
      if (hunk.baseText?.length) {
        const at = Math.max(0, Math.min(classes.length - 1, hunk.draftStart));
        classes[at].add('md-diff-delete-anchor');
        deletions.push(hunk);
      }
    }
    view.sourceBackdrop.textContent = '';
    const fragment = document.createDocumentFragment();
    for (let i = 0; i < classes.length; i++) {
      const line = document.createElement('span');
      line.className = 'md-source-diff-line ' + [...classes[i]].join(' ');
      line.textContent = lines[i] || ' ';
      fragment.append(line);
    }
    view.sourceBackdrop.append(fragment);
    view.sourceDeletions.textContent = '';
    for (const hunk of deletions) {
      const row = document.createElement('div');
      row.className = 'md-source-deletion';
      const label = document.createElement('span');
      label.className = 'md-source-deletion-label';
      label.textContent = 'Removed near line ' + (hunk.draftStart + 1);
      const old = document.createElement('pre');
      old.textContent = hunk.baseText.join('\n');
      row.append(label, old);
      view.sourceDeletions.append(row);
    }
    view.sourceDeletions.hidden = !deletions.length;
    syncSourceBackdrop();
  };
  const clearPreviewDiff = () => {
    for (const node of preview.querySelectorAll('.md-preview-diff-add,.md-preview-diff-mod')) {
      node.classList.remove('md-preview-diff-add', 'md-preview-diff-mod');
    }
    for (const ghost of preview.querySelectorAll('.md-preview-deletion')) ghost.remove();
  };

  const renderPreviewDiff = (hunks, draftText) => {
    ensureShellStyle();
    clearPreviewDiff();
    const lineCount = String(draftText || '').replace(/\r\n?/g, '\n').split('\n').length;
    const blocks = [...preview.querySelectorAll('[data-l]')]
      .filter(node => !node.closest('.md-preview-deletion'))
      .map(node => ({node, line: Math.max(0, Number(node.getAttribute('data-l')) - 1)}))
      .filter(item => Number.isSafeInteger(item.line))
      .sort((a, b) => a.line - b.line);

    for (let i = 0; i < blocks.length; i++) {
      blocks[i].end = i + 1 < blocks.length ? blocks[i + 1].line : lineCount;
    }

    for (const hunk of hunks) {
      if ((hunk.kind === 'add' || hunk.kind === 'mod') && hunk.draftEnd > hunk.draftStart) {
        for (const block of blocks) {
          if (block.line < hunk.draftEnd && block.end > hunk.draftStart) {
            block.node.classList.add(
              hunk.kind === 'add' ? 'md-preview-diff-add' : 'md-preview-diff-mod'
            );
          }
        }
        // Blank-line-only hunks have no rendered block. Never paint a nearby
        // block just to make the diff visible: that would be a false mapping.
      }

      if (Array.isArray(hunk.baseText) && hunk.baseText.length) {
        const ghost = document.createElement('div');
        ghost.className = 'md-preview-deletion';
        ghost.setAttribute('data-md-diff-ghost', 'true');
        const old = document.createElement('div');
        old.className = 'md-preview-deletion-text';
        old.textContent = hunk.baseText.join('\n');
        ghost.append(old);
        const anchor = blocks.find(block => block.line >= hunk.draftStart)?.node || null;
        if (anchor) anchor.insertAdjacentElement('beforebegin', ghost);
        else preview.append(ghost);
      }
    }
  };

  const renderVisualDiffFallback = (hunks, reason = '') => {
    const panel = view.visualDiffFallback;
    if (!panel) return;
    panel.textContent = '';
    const changed = (Array.isArray(hunks) ? hunks : []).filter(h =>
      h.kind === 'add' || h.kind === 'mod' || h.kind === 'del');
    if (!changed.length) {
      panel.hidden = true;
      return;
    }
    panel.hidden = false;
    panel.dataset.reason = reason || 'unmapped';
    const note = document.createElement('div');
    note.className = 'md-visual-diff-fallback-note';
    note.textContent = changed.length +
      ' pending Markdown change(s). Exact Visual positions are unavailable; Preview/Source shows them precisely.';
    panel.append(note);
    for (const hunk of changed) {
      if (!Array.isArray(hunk.baseText) || !hunk.baseText.length) continue;
      const ghost = document.createElement('div');
      ghost.className = 'md-visual-fallback-deletion';
      ghost.dataset.mdDiffGhost = 'true';
      ghost.textContent = hunk.baseText.join('\n');
      panel.append(ghost);
    }
  };

  const renderVisualDiff = (hunks, draftText) => {
    if (!view.instance) return;
    if (!hunks.length) {
      view.instance.clearPendingDiff?.();
      if (view.visualDiffFallback) {
        view.visualDiffFallback.hidden = true;
        view.visualDiffFallback.textContent = '';
      }
      document.documentElement.dataset.mdVisualDiff = 'clean';
      return;
    }
    if (typeof view.instance.setPendingDiff !== 'function') {
      renderVisualDiffFallback(hunks, 'bundle-unavailable');
      document.documentElement.dataset.mdVisualDiff = 'unmapped';
      return;
    }
    const result = view.instance.setPendingDiff(draftText, hunks) || {};
    if (result.mapped) {
      if (view.visualDiffFallback) {
        view.visualDiffFallback.hidden = true;
        view.visualDiffFallback.textContent = '';
      }
      document.documentElement.dataset.mdVisualDiff =
        result.unanchored ? 'mapped-partial' : 'mapped';
      return;
    }
    renderVisualDiffFallback(hunks, String(result.reason || 'unmapped'));
    document.documentElement.dataset.mdVisualDiff = 'unmapped';
  };

  const renderDraftDiff = () => {
    const diff = diffApi();
    if (!diff || !view.instance) return [];
    const text = getEditorText();
    const hunks = diff.diffLines(diffBaseline(), text);
    view.hunks = hunks;
    if (view.mode === 'source') renderSourceDiff(hunks, text);
    else if (view.mode === 'visual') renderVisualDiff(hunks, text);
    document.documentElement.dataset.mdPendingHunks = String(hunks.length);
    return hunks;
  };
  const queueDiff = () => {
    clearTimeout(view.diffTimer);
    view.diffTimer = setTimeout(renderDraftDiff, 120);
  };
  const fetchWorkState = () => api('/api/work?p=' + encodeURIComponent(path));

  const beginBotTurn = async () => {
    if (globalThis.__lanternMdPaged?.active) {
      throw new Error('LanternBot editing is not enabled while the section editor is active. Save or return to Source first.');
    }
    if (view.piTurn) throw new Error('A LanternBot Markdown turn is already active');

    let base;
    if (view.active && view.instance) {
      if (!(await saveDraft())) throw new Error('Unable to flush the current Markdown working copy');
      base = getEditorText();
    } else {
      const state = await fetchWorkState();
      if (!state.saved) throw new Error('Saved Markdown file is unavailable');
      base = state.work?.content ?? state.saved.content;
      view.version = state.saved.version;
      view.baseline = state.saved.content;
      view.lastSaved = state.saved.content;
      view.workHash = state.work?.hash || null;
      view.workState = state.state || (view.workHash ? 'pending' : 'clean');
      view.ackedText = base;
      view.conflict = state.state === 'external' || state.state === 'missing';
      if (view.conflict) throw new Error('Markdown saved file changed outside this working copy');
    }
    clearTimeout(view.draftTimer);
    view.piTurn = {
      base: String(base ?? ''),
      expectedRevision: view.revision,
    };
    status('LanternBot is editing the working copy. You may keep typing; overlapping changes keep your text.', 'info');
    return view.workHash || null;
  };

  const cancelBotTurn = () => {
    view.piTurn = null;
  };

  const replaceTextareaText = (area, nextText) => {
    const current = area.value;
    if (current === nextText) return false;
    let startAt = 0;
    const common = Math.min(current.length, nextText.length);
    while (startAt < common && current.charCodeAt(startAt) === nextText.charCodeAt(startAt)) startAt++;
    let oldEnd = current.length;
    let newEnd = nextText.length;
    while (oldEnd > startAt && newEnd > startAt &&
           current.charCodeAt(oldEnd - 1) === nextText.charCodeAt(newEnd - 1)) {
      oldEnd--; newEnd--;
    }
    area.setRangeText(nextText.slice(startAt, newEnd), startAt, oldEnd, 'preserve');
    return true;
  };

  const applyWorkingText = async (text, hash, { backed = true } = {}) => {
    const next = String(text ?? '');
    const bookmark = capturePosition();
    const y = scrollY;
    if (!view.active || view.mode === 'preview') {
      await renderDraftPreview(next);
      preview.hidden = false;
    } else if (view.mode === 'source' && view.sourceArea) {
      if (replaceTextareaText(view.sourceArea, next)) view.revision += 1;
    } else if (view.mode === 'visual') {
      const engine = await loadBundle();
      const host = view.host?.querySelector('.md-visual-host');
      if (!host) throw new Error('Visual editor host is unavailable');
      view.applyingPi = true;
      try {
        await view.instance?.destroy?.();
        host.textContent = '';
        view.instance = await engine.createVisualMarkdown(host, next, changed, path, status);
      } finally {
        view.applyingPi = false;
      }
      view.revision += 1;
      await restorePosition('visual', bookmark, y);
    }
    view.workHash = hash || null;
    view.workState = view.workHash ? 'pending' : 'clean';
    if (backed) view.ackedText = next;
    view.dirty = cleanLineEndings(next) !== cleanLineEndings(view.baseline);
    renderDraftDiff();
  };

  const onWorkChanged = async (eventPath, eventHash, final = false) => {
    if (String(eventPath || '').replace(/\\/g, '/') !== String(path || '').replace(/\\/g, '/')) return;
    const turn = view.piTurn;
    if (!turn) return;
    const state = await fetchWorkState();
    if (!state.saved) throw new Error('Saved Markdown file is unavailable');
    const piText = state.work?.content ?? state.saved.content;
    const serverHash = state.work?.hash || null;
    const humanText = view.active && view.instance ? getEditorText() : turn.base;
    const humanChanged = view.active && view.revision !== turn.expectedRevision;

    if (!final) {
      view.workHash = serverHash;
      view.workState = state.state || (serverHash ? 'pending' : 'clean');
      if (!humanChanged && view.mode !== 'visual') {
        await applyWorkingText(piText, serverHash, { backed: true });
        turn.expectedRevision = view.revision;
      }
      return;
    }

    clearTimeout(view.draftTimer);
    view.piTurn = null;
    if (!humanChanged) {
      await applyWorkingText(piText, serverHash, { backed: true });
      status('LanternBot changes are pending review. Press Ctrl+S or Save to commit.', 'info');
      return;
    }

    view.workHash = serverHash;
    view.workState = state.state || (serverHash ? 'pending' : 'clean');
    view.ackedText = piText;
    const diff = diffApi();
    if (!diff) throw new Error('Markdown diff engine is unavailable');
    let merged = humanText;
    let conflicts = [];
    let appliedPiHunks = 0;
    if (piText !== turn.base) {
      const result = diff.merge3(turn.base, humanText, piText);
      merged = result.text;
      conflicts = result.conflicts || [];
      appliedPiHunks = Number(result.appliedPiHunks || 0);
    }
    if (merged !== humanText) await applyWorkingText(merged, serverHash, { backed: false });
    if (!(await flushWorkingCopy(merged))) {
      throw new Error('Unable to reconcile your typing with LanternBot working-copy changes');
    }
    if (conflicts.length) {
      status('LanternBot finished; ' + conflicts.length +
        ' overlapping hunk(s) were skipped because your newer text wins.', 'warn');
    } else if (appliedPiHunks) {
      status('LanternBot changes merged with your typing and remain pending Save.', 'info');
    } else {
      status('Your newer typing is preserved; LanternBot made no additional non-overlapping changes.', 'info');
    }
  };

  const flushWorkingCopy = async (text = getEditorText()) => {
    if (!view.version) return false;
    try {
      const result = await api('/api/work/write', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path,
          content: text,
          expectHash: view.workHash || null,
          baseVersion: view.version,
        }),
      });
      view.workHash = result.hash || null;
      view.workState = result.state || (view.workHash ? 'pending' : 'clean');
      view.ackedText = text;
      await drafts.clear().catch(() => {});
      return true;
    } catch (error) {
      await drafts.write(text).catch(() => {});
      if (error.status === 409) {
        if (error.data?.reason === 'pi_turn') {
          status('LanternBot is editing this draft. Your newer typing is held locally and will flush after it finishes.', 'warn');
        } else {
          view.conflict = true;
          status('Conflict: draft or saved file changed elsewhere. Your newer typing is kept locally; reconcile before Save.', 'error');
        }
      } else {
        status('Working-copy sync failed. Your newer typing is kept in this browser.', 'error');
      }
      return false;
    }
  };
  const saveDraft = async () => {
    if (!view.active || !view.instance) return true;
    const text = getEditorText();
    if (view.saving) {
      await drafts.write(text).catch(() => {});
      return true;
    }
    if (matchesLastSaved(text) && !view.workHash) {
      view.ackedText = text;
      await drafts.clear().catch(() => {});
      return true;
    }
    return flushWorkingCopy(text);
  };
  const queueDraft = () => {
    clearTimeout(view.draftTimer);
    view.draftTimer = setTimeout(saveDraft, 900);
  };
  const changed = () => {
    if (!view.active || view.applyingPi) return;
    view.dirty = true;
    view.revision += 1;
    status(view.conflict ? 'Conflict: your draft is preserved; do not overwrite another client.' :
      !view.roundtripSafe && !view.approvedReformat
      ? 'Formatting differs from source. Review before saving.' : 'Unsaved changes — press Ctrl+S or Save to commit.',
      view.conflict ? 'error' : 'info');
    // Milkdown features may issue internal document transactions after mount.
    // Compare the actual Markdown after a brief idle gap; only semantic source
    // changes should cause durable local draft writes only. The real file is Save-only.
    clearTimeout(view.checkTimer);
    const observedRevision = view.revision;
    view.checkTimer = setTimeout(() => {
      if (!view.active || !view.instance || observedRevision !== view.revision) return;
      if (matchesLastSaved(getEditorText())) {
        view.dirty = false;
        queueDraft();
        renderDraftDiff();
        if (!view.conflict && !view.saving) status(view.roundtripSafe ?
          'Ready. No pending changes.' :
          'Visual editing ready. Formatting differs; review required before Save.');
        return;
      }
      queueDraft();
      queueDiff();
    }, 260);
  };
  const restoreButtons = () => {
    const paged = !!window.__lanternMdPaged?.active;
    root?.classList.toggle('md-editing', view.active || paged);
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
    if (topActions) topActions.hidden = !view.active;
    if (topStatus) {
      topStatus.hidden = !view.active;
      // Paged documents own a separate status element; never shadow its selector.
      topStatus.classList.toggle('md-visual-status', view.active);
    }
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
    view.sourceArea = null;
    view.sourceBackdrop = null;
    view.sourceDeletions = null;
    view.visualDiffFallback = null;
    const shell = document.createElement('section');
    shell.className = 'md-visual-shell';
    // Editing actions and status belong to the fixed page header.
    const editorHost = document.createElement('div');
    editorHost.className = 'md-visual-host';
    editorHost.id = 'md-visual-edit-' + escapeCss(path);
    if (kind === 'source') {
      const wrap = document.createElement('div');
      wrap.className = 'md-source-diff-wrap';
      const backdrop = document.createElement('div');
      backdrop.className = 'md-source-diff-backdrop';
      const backdropContent = document.createElement('div');
      backdropContent.className = 'md-source-diff-backdrop-content';
      backdrop.append(backdropContent);
      const area = document.createElement('textarea');
      area.className = 'md-source-area';
      area.setAttribute('aria-label', 'Markdown source');
      area.spellcheck = false;
      area.wrap = 'off';
      area.value = sourceText;
      area.addEventListener('input', changed);
      area.addEventListener('scroll', syncSourceBackdrop, {passive: true});
      const deleted = document.createElement('div');
      deleted.className = 'md-source-deletions';
      deleted.hidden = true;
      wrap.append(backdrop, area);
      editorHost.append(wrap, deleted);
      view.sourceArea = area;
      view.sourceBackdrop = backdropContent;
      view.sourceDeletions = deleted;
      view.instance = { getMarkdown: () => area.value, focus: () => area.focus(), destroy: () => {} };
    }
    shell.append(editorHost);
    if (kind === 'visual') {
      const fallback = document.createElement('div');
      fallback.className = 'md-visual-diff-fallback';
      fallback.hidden = true;
      shell.append(fallback);
      view.visualDiffFallback = fallback;
    }
    preview.insertAdjacentElement('afterend', shell);
    view.host = shell;
    view.status = topStatus;
    view.saveButton = saveHeader;
    view.closeButton = backHeader;
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
      pre.textContent = value.length > FULL_VISUAL_LIMIT_BYTES ? value.slice(0, FULL_VISUAL_LIMIT_BYTES) + '\n… (truncated comparison)' : value;
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
      if (view.conflict) status('File changed externally. Your working copy is retained; reconcile before Save.', 'error');
      return;
    }
    if (view.saving) { status('Save already in progress.', 'info'); return; }
    const text = getEditorText();
    if (!view.roundtripSafe && !view.approvedReformat && !matchesLastSaved(text)) {
      if (!await showReformatReview()) { status('Save cancelled; working copy retained.', 'warn'); return; }
      view.approvedReformat = true;
    }
    const revision = view.revision;
    view.saving = true;
    restoreButtons();
    status('Saving…');
    try {
      if (!(await flushWorkingCopy(text))) return;
      const hashToSave = view.workHash;
      if (!hashToSave) {
        view.dirty = false;
        view.lastSaved = text;
        view.baseline = text;
        view.ackedText = text;
        renderDraftDiff();
        if (manual) status('Already saved');
        return;
      }
      const result = await api('/api/work/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path,
          expectHash: hashToSave,
          expectSavedVersion: view.version,
        }),
      });
      view.version = result.version;
      view.lastSaved = text;
      view.baseline = text;
      view.workHash = null;
      view.workState = 'clean';
      view.ackedText = text;
      view.savedSincePreview = true;
      if (view.revision === revision) {
        view.dirty = false;
        await drafts.clear().catch(() => {});
        renderDraftDiff();
        status('Saved ✓');
      } else {
        view.dirty = true;
        await flushWorkingCopy(getEditorText());
        renderDraftDiff();
        status('Saved the earlier revision; newer edits are still pending.', 'warn');
      }
    } catch (error) {
      if (error.status === 409 || error.status === 404) {
        view.conflict = true;
        status('Conflict: saved file or working copy changed elsewhere. Your editor text is retained.', 'error');
      } else {
        status('Save failed: ' + error.message + '. Working copy retained.', 'error');
      }
      await drafts.write(getEditorText()).catch(() => {});
    } finally {
      view.saving = false;
      restoreButtons();
    }
  }

  // Swap editing surfaces without changing documents or making a second
  // controller for Source. Both editors share draft, version and save state.
  async function switchEditor(kind, requestedBookmark = null) {
    if (!view.active || view.loading || view.saving || kind === view.mode) return;
    const bookmark = requestedBookmark || capturePosition();
    const contentNow = getEditorText();
    // Milkdown may emit a mount transaction without changing Markdown.
    // Compare content, not its transient dirty flag, before switching modes.
    const wasDirty = !matchesLastSaved(contentNow);
    // Pending Source text may move into the full Visual editor; the working copy
    // remains the durable backing and any Milkdown normalization stays visible as diff.
    // Never open a multi-megabyte document in the full Milkdown tree.
    // Source -> Visual goes through the existing section-indexed editor.
    if (kind === 'visual' && new Blob([contentNow]).size > FULL_VISUAL_LIMIT_BYTES) {
      if (wasDirty || view.workHash) {
        status('Pending changes — use Source, or Save/Discard before section-based Visual Edit.', 'warn');
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
      await start('visual', bookmark);
      return;
    }
    if ((wasDirty || view.workHash) && !(await saveDraft())) return;
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
    clearTimeout(view.draftTimer);
    clearTimeout(view.diffTimer);
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
        kind === 'source' ? 'Source ready. Changes stay pending until Ctrl+S or Save.' :
        'Ready. Changes stay pending until Ctrl+S or Save.',
        view.conflict ? 'error' : view.dirty || !view.roundtripSafe ? 'warn' : 'info');
      view.instance.focus();
      renderDraftDiff();
      await restorePosition(kind, bookmark, y);
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

  async function renderDraftPreview(text) {
    const result = await api('/api/md/render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, content: text }),
    });
    const holder = document.createElement('div');
    holder.innerHTML = String(result.html || '');
    const article = holder.querySelector('article.md-preview');
    if (!article) throw new Error('Draft preview response did not contain an article');
    preview.innerHTML = article.innerHTML;
    await globalThis.__lanternMarkdownPreview?.refresh?.(preview);
    const diff = diffApi();
    const hunks = diff ? diff.diffLines(String(view.baseline || ''), text) : [];
    view.hunks = hunks;
    renderPreviewDiff(hunks, text);
    document.documentElement.dataset.mdPendingHunks = String(hunks.length);
  }

  async function hydratePendingPreview() {
    if (view.active || view.loading) return;
    try {
      const state = await fetchWorkState();
      if (view.active || view.loading) return;
      if (!state.saved) return;
      view.version = state.saved.version;
      view.baseline = state.saved.content;
      view.lastSaved = state.saved.content;
      view.workHash = state.work?.hash || null;
      view.workState = state.state || (view.workHash ? 'pending' : 'clean');
      view.ackedText = state.work?.content ?? state.saved.content;
      view.conflict = state.state === 'external' || state.state === 'missing';
      view.dirty = !!state.work &&
        cleanLineEndings(state.work.content) !== cleanLineEndings(state.saved.content);
      if (state.work) {
        await renderDraftPreview(state.work.content);
      } else {
        clearPreviewDiff();
        view.hunks = [];
        document.documentElement.dataset.mdPendingHunks = '0';
      }
    } catch (error) {
      console.warn('Unable to hydrate Markdown working copy:', error);
    }
  }

  async function close(requestedBookmark = null) {
    if (!view.active || view.saving || view.loading) return;
    const bookmark = requestedBookmark || capturePosition();
    const text = getEditorText();
    if (!(await flushWorkingCopy(text))) return;
    clearTimeout(view.draftTimer);
    clearTimeout(view.diffTimer);
    clearTimeout(view.checkTimer);
    const y = scrollY;
    const previousMode = view.mode;
    view.mode = 'preview';
    view.loading = true;
    restoreButtons();
    try {
      await renderDraftPreview(text);
      await view.instance?.destroy?.();
      view.instance = null;
      view.host?.remove();
      view.host = null;
      view.status = null;
      view.dirty = cleanLineEndings(text) !== cleanLineEndings(view.baseline);
      view.loading = false;
      preview.hidden = false;
      restoreButtons();
      await restorePosition('preview', bookmark, y);
    } catch (error) {
      view.mode = previousMode;
      view.loading = false;
      restoreButtons();
      status('Cannot render pending Preview: ' + error.message, 'error');
    }
  }

  async function start(kind = 'visual', requestedBookmark = null) {
    if (view.active) return switchEditor(kind, requestedBookmark);
    if (view.loading) return;
    const bookmark = requestedBookmark || capturePosition();
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
      const workState = await api('/api/work?p=' + encodeURIComponent(path));
      const doc = workState.saved;
      if (!doc) throw new Error('Saved Markdown file is missing');
      const serverWork = workState.work;
      let contents = serverWork?.content ?? doc.content;
      view.version = doc.version;
      view.baseline = doc.content;
      view.workHash = serverWork?.hash || null;
      view.workState = workState.state || (view.workHash ? 'pending' : 'clean');
      view.ackedText = contents;
      view.conflict = workState.state === 'external' || workState.state === 'missing';
      view.dirty = contents !== doc.content;
      view.approvedReformat = false;

      if(kind === 'visual' && new Blob([contents]).size > FULL_VISUAL_LIMIT_BYTES){
        if (serverWork) {
          status('Pending changes — use Source, or Save/Discard before section-based Visual Edit.', 'warn');
          return;
        }
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
        await restorePosition('visual', bookmark);
        return;
      }
      const engine = kind === 'visual' ? await loadBundle() : null;
      const recovered = await drafts.read().catch(() => null);
      if (recovered?.mode !== 'paged' && typeof recovered?.content === 'string' &&
          recovered.content !== contents) {
        const sameBacking = recovered.version === view.version &&
          (recovered.workHash ?? null) === (view.workHash ?? null);
        if (sameBacking) {
          contents = recovered.content;
          view.dirty = contents !== doc.content;
        } else if (!recovered.workHash &&
                   confirm('A legacy unsent browser draft was found. Restore it into the new working copy?')) {
          contents = recovered.content;
          view.dirty = contents !== doc.content;
        }
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
      view.ackedText = serverWork?.content ?? doc.content;
      // A restored draft is not the remote baseline. Never accidentally treat it
      // as "already saved" and delete the only copy of unsaved edits.
      view.lastSaved = restoredDraft ? doc.content : serialized;
      view.roundtripSafe = kind === 'source' ||
        cleanLineEndings(serialized) === cleanLineEndings(contents);
      if (restoredDraft) {
        view.dirty = true;
        view.revision += 1;
      }
      if (contents !== view.ackedText) queueDraft();
      status(view.conflict ? 'Draft restored but disk version differs. Do not overwrite; download draft first.' :
        restoredDraft ? 'Unsaved draft restored.' :
        kind === 'source' ? 'Source ready. Changes stay pending until Ctrl+S or Save.' :
        view.roundtripSafe ? 'Ready. Changes stay pending until Ctrl+S or Save.' :
        'Visual editing ready. Formatting differs; review required before Save.',
        view.conflict ? 'error' : view.roundtripSafe ? 'info' : 'warn');
      restoreButtons();
      renderDraftDiff();
      view.instance.focus();
      await restorePosition(kind, bookmark);
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

  // The browser blurs contenteditable on pointerdown. Capture the ProseMirror
  // selection BEFORE the toolbar button takes focus, not in its click handler.
  saveHeader?.addEventListener('click', () => { void save(true); });
  draftHeader?.addEventListener('click', downloadDraft);
  backHeader?.addEventListener('click', () => { void close(); });
  for (const button of [trigger, sourceTrigger, previewTrigger])
    button.addEventListener('pointerdown', () => { pointerBookmark = capturePosition(); }, true);
  trigger.addEventListener('click', () => { void start('visual', takeBookmark()); });
  sourceTrigger.addEventListener('click', () => { void start('source', takeBookmark()); });
  previewTrigger.addEventListener('click', () => {
    const bookmark = takeBookmark();
    if (window.__lanternMdPaged?.active) {
      if (bookmark) sessionStorage.setItem(anchorKey, JSON.stringify(bookmark));
      void window.__lanternMdPaged.close().then(() => {
        if (!preview.hidden) {
          void restorePosition('preview', bookmark);
          sessionStorage.removeItem(anchorKey);
        }
      });
      return;
    }
    if (view.active) void close(bookmark);
  });
  document.addEventListener('keydown', e => {
    if (!view.active || !(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== 's') return;
    e.preventDefault();
    void save(true);
  });
  window.addEventListener('beforeunload', e => {
    if (!view.active || getEditorText() === view.ackedText) return;
    e.preventDefault();
    e.returnValue = '';
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && view.active && getEditorText() !== view.ackedText) void saveDraft();
  });
  const scrollKey = 'lantern-md-scroll:' + path;
  const priorScroll = sessionStorage.getItem(scrollKey);
  const priorAnchor = sessionStorage.getItem(anchorKey);
  let initialBookmark = null;
  if (priorAnchor || priorScroll) {
    sessionStorage.removeItem(scrollKey);
    sessionStorage.removeItem(anchorKey);
    try { if (priorAnchor) initialBookmark = JSON.parse(priorAnchor); } catch { /* obsolete entry */ }
  }
  void hydratePendingPreview().finally(() => {
    if (initialBookmark || priorScroll) {
      requestAnimationFrame(() => {
        void restorePosition('preview', initialBookmark, Number(priorScroll) || 0);
      });
    }
  });
  window.__lanternMdVisual = { get state() { return view; }, open: start,
    show: start, save: () => save(true), preview: close, flushNow: saveDraft,
    beginBotTurn, cancelBotTurn, onWorkChanged };
})();
