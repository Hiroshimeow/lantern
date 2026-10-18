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
  let pointerScrollY = null;
  const takePosition = () => {
    const snapshot = {
      bookmark: pointerBookmark || capturePosition(),
      y: pointerScrollY ?? scrollY,
    };
    pointerBookmark = null;
    pointerScrollY = null;
    return snapshot;
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
    loading: false, instance: null, version: null, currentVersion: null,
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
    const target = view.status || topStatus;
    if (target) {
      target.textContent = message;
      target.dataset.kind = kind;
    }
  };
  const syncStatusVisibility = () => {
    if (!topStatus) return;
    topStatus.hidden = !view.active && view.workState !== 'missing';
    // Paged documents own a separate status element; never shadow its selector.
    topStatus.classList.toggle('md-visual-status', view.active);
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
    if (view.sourceDeletions) {
      const area = view.sourceArea;
      const style = getComputedStyle(area);
      const lineHeight = parseFloat(style.lineHeight) || 21;
      const paddingTop = parseFloat(style.paddingTop) || 16;
      for (const row of view.sourceDeletions.children) {
        const at = Number(row.dataset.line) * lineHeight + paddingTop - area.scrollTop;
        row.hidden = at < 0 || at > area.clientHeight - 32;
        row.style.top = at + 'px';
      }
    }
  };
  const hunkButtons = index => {
    const group = document.createElement('span');
    group.className = 'md-hunk-actions';
    for (const [action, label] of [['accept', '✓ Accept'], ['undo', '↶ Undo']]) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'md-hunk-button';
      button.textContent = label;
      button.title = action === 'accept'
        ? 'Accept only this change into md_temp'
        : 'Restore only this change in the real project .md';
      button.addEventListener('click', event => {
        event.stopPropagation();
        void actionHunk(index, action);
      });
      group.append(button);
    }
    return group;
  };
  const actionHunk = async (index, action) => {
    if (view.saving || view.loading || view.piTurn) {
      status('Wait for the current operation before changing a diff hunk.', 'warn');
      return;
    }
    if (view.active && !(await saveDraft())) return;
    try {
      const state = await fetchWorkState();
      if (!state.saved || state.currentVersion !== view.currentVersion ||
          state.saved.version !== view.version) {
        await refreshDiskBaseline();
        status('File changed elsewhere; review refreshed diff before applying an action.', 'warn');
        return;
      }
      const before = state.saved.content;
      const real = state.work?.content ?? before;
      const h = diffApi()?.diffLines(before, real)[index];
      if (!h) return;
      const lines = text => String(text).replace(/\r\n?/g, '\n').split('\n');
      let next;
      if (action === 'accept') {
        const baseLines = lines(before);
        next = [...baseLines.slice(0, h.baseStart), ...h.draftText, ...baseLines.slice(h.baseEnd)].join('\n');
        await api('/api/work/accept-hunk', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({
            path, content:next, expectSavedVersion:state.saved.version,
            expectCurrentVersion:state.currentVersion,
          }),
        });
      } else {
        const realLines = lines(real);
        next = [...realLines.slice(0, h.draftStart), ...h.baseText, ...realLines.slice(h.draftEnd)].join('\n');
        await api('/api/work/write', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({
            path, content:next, expectHash:state.work?.hash || null,
            baseVersion:state.saved.version,
          }),
        });
      }
      const fresh = await fetchWorkState();
      adoptSavedBaseline(fresh);
      view.currentVersion = fresh.currentVersion;
      view.workHash = fresh.work?.hash || null;
      view.workState = fresh.state;
      const current = fresh.work?.content ?? fresh.saved.content;
      view.ackedText = current;
      view.lastSaved = current;
      if (view.active) await applyWorkingText(current, view.workHash, {backed:true});
      else await renderDraftPreview(current);
      status(action === 'accept'
        ? 'Accepted this hunk into md_temp; other diff hunks remain.'
        : 'Reverted this hunk in the real .md; other edits remain.', 'info');
    } catch (error) {
      status('Diff action refused: ' + error.message, 'error');
    }
  };

  const renderSourceDiff = (hunks, draftText) => {
    if (!view.sourceArea || !view.sourceBackdrop || !view.sourceDeletions) return;
    const lines = String(draftText || '').replace(/\r\n?/g, '\n').split('\n');
    const classes = Array.from({length: Math.max(1, lines.length)}, () => new Set());

    for (const hunk of hunks) {
      if (hunk.kind === 'add' || hunk.kind === 'mod') {
        for (let i = hunk.draftStart; i < hunk.draftEnd; i++) {
          if (classes[i]) classes[i].add(hunk.kind === 'add' ? 'md-diff-add' : 'md-diff-mod');
        }
      }
      if (hunk.baseText?.length) {
        const at = Math.max(0, Math.min(classes.length - 1, hunk.draftStart));
        classes[at].add('md-diff-delete-anchor');

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
    for (const [index, hunk] of hunks.entries()) {
      const row = document.createElement('div');
      row.className = 'md-source-deletion';
      row.dataset.line = String(hunk.draftStart);
      const old = document.createElement('span');
      old.className = 'md-source-deletion-text';
      old.textContent = hunk.baseText?.length
        ? '− ' + hunk.baseText.join(' ↵ ') : '+ ' + hunk.draftText.join(' ↵ ');
      old.title = old.textContent;
      row.append(old, hunkButtons(index));
      view.sourceDeletions.append(row);
    }
    view.sourceDeletions.hidden = !hunks.length;
    syncSourceBackdrop();
  };
  const clearPreviewDiff = () => {
    for (const node of preview.querySelectorAll('.md-preview-diff-add,.md-preview-diff-mod')) {
      node.classList.remove('md-preview-diff-add', 'md-preview-diff-mod');
    }
    for (const ghost of preview.querySelectorAll('.md-preview-deletion,.md-preview-hunk-actions')) ghost.remove();
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

    for (const [index, hunk] of hunks.entries()) {
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
        ghost.append(old, hunkButtons(index));
        const anchor = blocks.find(block => block.line >= hunk.draftStart)?.node || null;
        if (anchor) anchor.insertAdjacentElement('beforebegin', ghost);
        else preview.append(ghost);
      } else {
        const toolbar = document.createElement('div');
        toolbar.className = 'md-preview-hunk-actions';
        toolbar.append(hunkButtons(index));
        const anchor = blocks.find(block => block.line >= hunk.draftStart)?.node || null;
        if (anchor) anchor.insertAdjacentElement('beforebegin', toolbar);
        else preview.append(toolbar);
      }
    }
  };

  // Keep controls out of ProseMirror's editable DOM. An exact source-line
  // proof locates each toolbar; unproved blocks get actions in the fallback
  // panel, never an arbitrary nearby row.
  const clearVisualHunkTools = () => {
    view.host?.querySelectorAll('.md-visual-hunk-actions').forEach(node => node.remove());
    view.host?.querySelector('.md-visual-host')?.classList.remove('has-diff-actions');
  };
  const showVisualHunkTools = hunks => {
    clearVisualHunkTools();
    const host = view.host?.querySelector('.md-visual-host');
    if (!host || typeof view.instance?.sourceBlockAtLine !== 'function') return;
    host.classList.add('has-diff-actions');
    const rect = host.getBoundingClientRect();
    for (const [index, hunk] of hunks.entries()) {
      const block = view.instance.sourceBlockAtLine(hunk.draftStart + 1);
      if (!block || !host.contains(block)) continue;
      const blockRect = block.getBoundingClientRect();
      const toolbar = document.createElement('div');
      toolbar.className = 'md-visual-hunk-actions';
      toolbar.style.top = (blockRect.top - rect.top) + 'px';
      toolbar.append(hunkButtons(index));
      host.append(toolbar);
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
    for (const [index, hunk] of hunks.entries()) {
      const group = document.createElement('div');
      group.className = 'md-visual-fallback-deletion';
      group.dataset.mdDiffGhost = 'true';
      const original = document.createElement('span');
      original.textContent = Array.isArray(hunk.baseText) && hunk.baseText.length
        ? hunk.baseText.join('\n') : 'Added content';
      group.append(original, hunkButtons(index));
      panel.append(group);
    }
  };

  const renderVisualDiff = (hunks, draftText) => {
    if (!view.instance) return;
    clearVisualHunkTools();
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
      showVisualHunkTools(hunks);
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
    const editorText = getEditorText();
    // Visual serialization can reformat a complex Markdown table without a
    // human edit. Pending diff compares md_temp to the real project bytes.
    const text = matchesLastSaved(editorText) ? view.ackedText : editorText;
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

  const adoptSavedBaseline = state => {
    if (!state?.saved) return false;
    view.version = state.saved.version; // md_temp, not the project .md
    view.baseline = state.saved.content;
    view.workState = state.state || (state.work ? 'pending' : 'clean');
    view.conflict = false;
    if (view.active && view.instance)
      view.dirty = cleanLineEndings(getEditorText()) !== cleanLineEndings(view.baseline);
    renderDraftDiff();
    return true;
  };

  // A project .md may also be edited in VS Code. Poll its real version,
  // refreshing the preview/editor without silently overwriting local typing.
  let refreshingReal = false;
  const refreshDiskBaseline = async ({quiet = false} = {}) => {
    if (refreshingReal || view.loading || view.saving || view.piTurn || document.hidden) return false;
    refreshingReal = true;
    try {
      const state = await fetchWorkState();
      if (!state?.saved) return false;
      const currentVersion = state.currentVersion;
      const realText = state.work?.content ?? state.saved.content;
      const wasMissing = view.workState === 'missing';
      if (currentVersion === view.currentVersion && state.saved.version === view.version && !wasMissing)
        return false;
      const prevReal = view.ackedText;
      const local = view.active && view.instance ? getEditorText() : prevReal;
      const locallyEdited = view.active && view.instance && !matchesLastSaved(local);
      if (locallyEdited && currentVersion !== view.currentVersion) {
        // No blind overwrite. Conflicting human/bot/VS Code hunks remain in
        // the browser recovery copy until the user resolves them.
        const merge = diffApi()?.merge3(prevReal, local, realText);
        if (!merge || merge.conflicts?.length) {
          view.conflict = true;
          status('File changed in VS Code/LanternBot while you typed. Local text is retained; resolve overlapping edits in Source.', 'warn');
          await drafts.write(local).catch(() => {});
          return false;
        }
        adoptSavedBaseline(state);
        view.currentVersion = currentVersion;
        view.workHash = state.work?.hash || null;
        view.lastSaved = realText;
        view.ackedText = realText;
        await applyWorkingText(merge.text, view.workHash, {backed: false});
        return flushWorkingCopy(merge.text);
      }
      adoptSavedBaseline(state);
      syncStatusVisibility();
      view.currentVersion = currentVersion;
      view.workHash = state.work?.hash || null;
      view.lastSaved = realText;
      view.ackedText = realText;
      if (view.active && view.instance) {
        await applyWorkingText(realText, view.workHash, {backed: true});
      } else {
        await renderDraftPreview(realText);
      }
      if (wasMissing)
        status('Project .md is available again. Diff reflects the live file.', 'info');
      else if (!quiet)
        status('Project .md changed externally. Diff reflects the live file.', 'info');
      return true;
    } catch (error) {
      if (error.status === 404) {
        const firstMissing = view.workState !== 'missing';
        view.conflict = true;
        view.workState = 'missing';
        if (firstMissing && view.active && view.instance) {
          await drafts.write(getEditorText()).catch(() => {});
        }
        syncStatusVisibility();
        status('Project .md unavailable; local recovery text retained.', 'error');
      } else if (!quiet) {
        console.warn('Cannot refresh Markdown from disk:', error);
      }
      return false;
    } finally {
      refreshingReal = false;
    }
  };

  const beginBotTurn = async () => {
    if (view.piTurn) throw new Error('A LanternBot Markdown turn is already active');
    if (globalThis.__lanternMdPaged?.active)
      await globalThis.__lanternMdPaged.beginBotTurn();

    let base;
    if (view.active && view.instance) {
      if (!(await saveDraft())) throw new Error('Unable to flush the current Markdown working copy');
      base = getEditorText();
    } else {
      const state = await fetchWorkState();
      if (!state.saved) throw new Error('Saved Markdown file is unavailable');
      base = state.work?.content ?? state.saved.content;
      view.version = state.saved.version;
      view.currentVersion = state.currentVersion;
      view.baseline = state.saved.content;
      view.lastSaved = base;
      view.workHash = state.work?.hash || null;
      view.workState = state.state || (view.workHash ? 'pending' : 'clean');
      view.ackedText = base;
      view.conflict = state.state === 'missing';
      if (view.conflict) throw new Error('Saved Markdown file is unavailable');
    }
    clearTimeout(view.draftTimer);
    view.piTurn = {
      base: String(base ?? ''),
      expectedRevision: view.revision,
    };
    status('LanternBot edits the real .md. The md_temp baseline is unchanged until Ctrl+S.', 'info');
    return view.workHash || null;
  };

  const cancelBotTurn = () => {
    view.piTurn = null;
    globalThis.__lanternMdPaged?.cancelBotTurn?.();
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
    if (backed) {
      view.ackedText = next;
      view.lastSaved = view.mode === 'visual' ? getEditorText() : next;
    }
    view.dirty = cleanLineEndings(next) !== cleanLineEndings(view.baseline);
    renderDraftDiff();
  };

  const onWorkChanged = async (eventPath, eventHash, final = false) => {
    if (String(eventPath || '').replace(/\\/g, '/') !== String(path || '').replace(/\\/g, '/')) return;
    const turn = view.piTurn;
    if (!turn) return;
    if (globalThis.__lanternMdPaged?.active) {
      await globalThis.__lanternMdPaged.onBotWorkChanged(final);
      if (final) view.piTurn = null;
      return;
    }
    const state = await fetchWorkState();
    if (!state.saved) throw new Error('Saved Markdown file is unavailable');
    const piText = state.work?.content ?? state.saved.content;
    const serverHash = state.work?.hash || null;
    const humanText = view.active && view.instance ? getEditorText() : turn.base;
    const humanChanged = view.active && view.revision !== turn.expectedRevision;

    if (!final) {
      view.currentVersion = state.currentVersion;
      view.workHash = serverHash;
      view.workState = state.state || (serverHash ? 'pending' : 'clean');
      if (!humanChanged) {
        await applyWorkingText(piText, serverHash, { backed: true });
        turn.expectedRevision = view.revision;
      }
      return;
    }

    clearTimeout(view.draftTimer);
    view.piTurn = null;
    view.currentVersion = state.currentVersion;
    if (!humanChanged) {
      await applyWorkingText(piText, serverHash, { backed: true });
      status('LanternBot updated the real .md. Ctrl+S accepts it as the comparison baseline.', 'info');
      return;
    }

    view.workHash = serverHash;
    view.workState = state.state || (serverHash ? 'pending' : 'clean');
    view.ackedText = piText;
    view.lastSaved = piText;
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
      status('LanternBot changes merged into the real .md; diff remains visible.', 'info');
    } else {
      status('Your newer typing is preserved; LanternBot made no additional non-overlapping changes.', 'info');
    }
  };

  // Every edit goes to the project .md, not md_temp. A CAS rejects writes
  // based on stale file versions (VS Code, bot, or another browser).
  let writingReal = null;
  const flushWorkingCopy = async (text = getEditorText()) => {
    if (!view.version) return false;
    if (view.piTurn) {
      await drafts.write(text).catch(() => {});
      status('LanternBot is editing the real .md; your typing will merge when its turn ends.', 'warn');
      return false;
    }
    if (writingReal) {
      await writingReal;
      if (view.active && view.instance && matchesLastSaved(getEditorText())) return true;
      text = view.active && view.instance ? getEditorText() : text;
    }
    if (text === view.lastSaved) return true;
    if (view.mode === 'visual' && !view.roundtripSafe && !view.approvedReformat) {
      if (!await showReformatReview()) {
        status('Markdown conversion cancelled; local edit kept for recovery.', 'warn');
        await drafts.write(text).catch(() => {});
        return false;
      }
      view.approvedReformat = true;
    }

    const put = (bodyText, hash, version) => api('/api/work/write', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({path, content:bodyText, expectHash:hash, baseVersion:version}),
    });
    const task = (async () => {
      try {
        let persistedText = text;
        let result;
        try {
          result = await put(text, view.workHash || null, view.version);
        } catch (error) {
          if (error.status !== 409) throw error;
          const state = await fetchWorkState();
          if (!state.saved) throw error;
          const actual = state.work?.content ?? state.saved.content;
          const merge = diffApi()?.merge3(view.ackedText, text, actual);
          if (!merge || merge.conflicts?.length) {
            view.conflict = true;
            status('Real .md changed concurrently. Overlapping edits are kept locally; no overwrite.', 'error');
            await drafts.write(text).catch(() => {});
            return false;
          }
          adoptSavedBaseline(state);
          view.currentVersion = state.currentVersion;
          view.workHash = state.work?.hash || null;
          view.ackedText = actual;
          persistedText = merge.text;
          result = await put(persistedText, view.workHash, view.version);
          if (persistedText !== text) await applyWorkingText(persistedText, view.workHash, {backed:false});
        }
        view.workHash = result.hash || null;
        view.currentVersion = result.currentVersion;
        view.workState = result.state;
        view.ackedText = persistedText;
        view.lastSaved = persistedText;
        view.conflict = false;
        view.dirty = cleanLineEndings(persistedText) !== cleanLineEndings(view.baseline);
        await drafts.clear().catch(() => {});
        renderDraftDiff();
        return true;
      } catch (error) {
        await drafts.write(text).catch(() => {});
        status('Cannot update project .md: ' + error.message + '. Local edit retained.', 'error');
        return false;
      }
    })();
    writingReal = task;
    try { return await task; }
    finally { if (writingReal === task) writingReal = null; }
  };
  const saveDraft = async () => {
    if (!view.active || !view.instance) return true;
    const text = getEditorText();
    if (view.piTurn) {
      await drafts.write(text).catch(() => {});
      return false;
    }
    if (view.saving) {
      await drafts.write(text).catch(() => {});
      return false;
    }
    if (matchesLastSaved(text)) return true;
    return flushWorkingCopy(text);
  };
  const queueDraft = () => {
    clearTimeout(view.draftTimer);
    view.draftTimer = setTimeout(() => { void saveDraft(); }, 110);
  };
  const changed = () => {
    if (!view.active || view.applyingPi) return;
    view.dirty = true;
    view.revision += 1;
    status(view.conflict ? 'Concurrent file edit: reviewing changes before writing.' :
      !view.roundtripSafe && !view.approvedReformat
      ? 'Visual Markdown conversion requires review before writing the real .md.' :
      'Updating project .md automatically; Ctrl+S accepts the diff baseline.',
      view.conflict ? 'error' : 'info');
    // Milkdown features may issue internal document transactions after mount.
    // Compare the actual Markdown after a brief idle gap; only semantic source
    // changes should cause durable local draft writes only. The real file is Save-only.
    clearTimeout(view.checkTimer);
    const observedRevision = view.revision;
    view.checkTimer = setTimeout(() => {
      if (!view.active || !view.instance || observedRevision !== view.revision) return;
      if (matchesLastSaved(getEditorText())) {
        view.dirty = cleanLineEndings(getEditorText()) !== cleanLineEndings(view.baseline);
        queueDraft();
        renderDraftDiff();
        if (!view.conflict && !view.saving) status(view.roundtripSafe ?
          'Ready. No pending changes.' :
          'Visual editing ready. Formatting differs; review before writing the real .md.');
        return;
      }
      queueDraft();
      queueDiff();
    }, 90);
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
    if (topActions) topActions.hidden = paged;
    syncStatusVisibility();
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
      wrap.append(backdrop, area, deleted);
      editorHost.append(wrap);
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

  // Ctrl+S accepts a diff checkpoint; it never commits edits to the real
  // .md because every prior edit has already been written there.
  async function save(manual) {
    if (view.loading || view.saving || view.conflict || view.piTurn) {
      if (view.piTurn) status('Wait until LanternBot finishes before accepting diff.', 'warn');
      return;
    }
    if (view.active && view.instance && !(await saveDraft())) return;
    if (writingReal) await writingReal;
    view.saving = true;
    restoreButtons();
    try {
      const state = await fetchWorkState();
      if (!state.saved) throw new Error('Project Markdown file is unavailable');
      if (view.currentVersion && state.currentVersion !== view.currentVersion) {
        // Do not accept an external edit the user has not seen yet.
        view.saving = false;
        await refreshDiskBaseline();
        status('The project file changed. Review new diff before accepting.', 'warn');
        return;
      }
      const current = state.work?.content ?? state.saved.content;
      const result = await api('/api/work/save', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          path, expectHash:state.work?.hash || null,
          expectSavedVersion:state.saved.version,
        }),
      });
      view.version = result.version;
      view.currentVersion = result.version;
      view.baseline = current;
      view.workHash = null;
      view.workState = 'clean';
      view.ackedText = current;
      view.lastSaved = view.active ? getEditorText() : current;
      view.dirty = false;
      await drafts.clear().catch(() => {});
      if (view.active) renderDraftDiff();
      else await renderDraftPreview(current);
      if (manual) status('Saved diff baseline into md_temp. Real .md remains editable.', 'info');
    } catch (error) {
      status('Could not accept diff: ' + error.message, 'error');
    } finally {
      view.saving = false;
      restoreButtons();
    }
  }

  // Swap editing surfaces without changing documents or making a second
  // controller for Source. Both editors share draft, version and save state.
  async function switchEditor(kind, requestedBookmark = null, requestedY = null) {
    if (!view.active || view.loading || view.saving || kind === view.mode) return;
    const bookmark = requestedBookmark || capturePosition();
    const y = requestedY ?? scrollY;
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
    // An untouched Visual editor may normalize GFM tables on serialization.
    // When no real edit occurred, switch using the actual project Markdown,
    // not that normalized Visual serialization and never the md_temp baseline.
    const contents = wasDirty ? contentNow : view.ackedText;
    // The accepted md_temp snapshot must not replace the real document.
    const oldSafe = view.roundtripSafe;
    const oldApproved = view.approvedReformat;
    let engine = null;
    try { if (kind === 'visual') engine = await loadBundle(); }
    catch (error) { status('Cannot load Visual editor: ' + error.message, 'error'); return; }
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
      view.lastSaved = kind === 'visual' ? converted : contents;
      view.dirty = cleanLineEndings(contents) !== cleanLineEndings(view.baseline);
      status(view.conflict ? 'Conflict: draft retained; another client changed the file.' :
        wasDirty ? 'Real .md updated; continue editing or accept diff with Ctrl+S.' :
        !view.roundtripSafe ? 'Formatting differs: review required before Save.' :
        kind === 'source' ? 'Source edits update the project file automatically.' :
        'Edit updates the real .md. Ctrl+S accepts the diff baseline.',
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
      view.currentVersion = state.currentVersion;
      view.baseline = state.saved.content;
      view.lastSaved = state.work?.content ?? state.saved.content;
      view.workHash = state.work?.hash || null;
      view.workState = state.state || (view.workHash ? 'pending' : 'clean');
      view.ackedText = state.work?.content ?? state.saved.content;
      view.conflict = state.state === 'missing';
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

  async function close(requestedBookmark = null, requestedY = null) {
    if (!view.active || view.saving || view.loading) return;
    const bookmark = requestedBookmark || capturePosition();
    const y = requestedY ?? scrollY;
    const text = getEditorText();
    if (!(await flushWorkingCopy(text))) return;
    clearTimeout(view.draftTimer);
    clearTimeout(view.diffTimer);
    clearTimeout(view.checkTimer);
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

  async function start(kind = 'visual', requestedBookmark = null, requestedY = null) {
    if (view.active) return switchEditor(kind, requestedBookmark, requestedY);
    if (view.loading) return;
    const bookmark = requestedBookmark || capturePosition();
    const y = requestedY ?? scrollY;
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
      const baselineDoc = workState.saved;
      if (!baselineDoc) throw new Error('Markdown file is missing');
      const serverWork = workState.work;
      const doc = serverWork ? {...baselineDoc, content:serverWork.content, version:workState.currentVersion,
        bytes:new Blob([serverWork.content]).size} : baselineDoc;
      let contents = doc.content;
      view.version = baselineDoc.version;
      view.currentVersion = workState.currentVersion;
      view.baseline = baselineDoc.content;
      view.workHash = serverWork?.hash || null;
      view.workState = workState.state || (view.workHash ? 'pending' : 'clean');
      view.ackedText = contents;
      view.conflict = workState.state === 'missing';
      view.dirty = contents !== view.baseline;
      view.approvedReformat = false;

      if(kind === 'visual' && new Blob([contents]).size > FULL_VISUAL_LIMIT_BYTES){
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
        await restorePosition('visual', bookmark, y);
        return;
      }
      const engine = kind === 'visual' ? await loadBundle() : null;
      const recovered = await drafts.read().catch(() => null);
      if (recovered?.mode !== 'paged' && typeof recovered?.content === 'string' &&
          recovered.content !== contents) {
        const sameBacking = recovered.version === view.version &&
          (recovered.workHash ?? null) === (view.workHash ?? null);
        if (sameBacking || !recovered.workHash) {
          if (confirm('Recover a browser edit into the real project .md?')) {
            contents = recovered.content;
            view.dirty = contents !== view.baseline;
          } else {
            // Explicit rejection must not keep prompting on each mode switch.
            await drafts.clear().catch(() => {});
          }
        }
      }
      const editorHost = renderToolbar(kind, contents);
      // Source and Visual both edit the same project .md via versioned CAS.
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
      status(view.conflict ? 'Project .md unavailable; local recovery text retained.' :
        restoredDraft ? 'Browser recovery loaded; updating project .md automatically.' :
        kind === 'source' ? 'Source edits update the real .md automatically.' :
        view.roundtripSafe ? 'Real .md is live. Ctrl+S accepts the comparison baseline.' :
        'Visual serialization differs; review conversion before writing the real .md.',
        view.conflict ? 'error' : !view.roundtripSafe ? 'warn' : 'info');
      restoreButtons();
      renderDraftDiff();
      view.instance.focus();
      await restorePosition(kind, bookmark, y);
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
    button.addEventListener('pointerdown', () => {
      pointerBookmark = capturePosition();
      pointerScrollY = scrollY;
    }, true);
  trigger.addEventListener('click', () => {
    const pos = takePosition();
    void start('visual', pos.bookmark, pos.y);
  });
  sourceTrigger.addEventListener('click', () => {
    const pos = takePosition();
    void start('source', pos.bookmark, pos.y);
  });
  previewTrigger.addEventListener('click', () => {
    const pos = takePosition();
    const bookmark = pos.bookmark;
    if (window.__lanternMdPaged?.active) {
      if (bookmark) sessionStorage.setItem(anchorKey, JSON.stringify(bookmark));
      void window.__lanternMdPaged.close().then(() => {
        if (!preview.hidden) {
          void restorePosition('preview', bookmark, pos.y);
          sessionStorage.removeItem(anchorKey);
        }
      });
      return;
    }
    if (view.active) void close(bookmark, pos.y);
  });
  document.addEventListener('keydown', e => {
    if (globalThis.__lanternMdPaged?.active) return;
    if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== 's') return;
    e.preventDefault();
    void save(true);
  });
  window.addEventListener('beforeunload', e => {
    if (!view.active || matchesLastSaved(getEditorText())) return;
    e.preventDefault();
    e.returnValue = '';
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && view.active && getEditorText() !== view.ackedText) {
      void saveDraft();
      return;
    }
    if (!document.hidden) void refreshDiskBaseline();
  });
  window.addEventListener('focus', () => { void refreshDiskBaseline(); });
  setInterval(() => { if (!document.hidden) void refreshDiskBaseline({quiet:true}); }, 2500);
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
