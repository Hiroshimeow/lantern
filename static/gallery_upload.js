/* Lantern v9.25 — Resilient Concurrent Upload Manager (Non-blocking Queue, Pause/Retry, Speed/ETA) */
(() => {
  'use strict';

  const uploadState = {
    queue: [],
    running: false,
    paused: false,
    activeCount: 0,
    startedAt: 0,
    sessionLoadedBytes: 0,
    conflictApplyAll: null, // null | 'overwrite' | 'rename' | 'skip'
    nextId: 1,
    rafId: 0,
  };

  function qSel(s) { return document.querySelector(s); }

  function humanBytes(n) {
    n = Number(n || 0);
    for (const u of ['B', 'KB', 'MB', 'GB', 'TB']) {
      if (n < 1024 || u === 'TB') return (u === 'B' ? Math.round(n) : n.toFixed(1)) + ' ' + u;
      n /= 1024;
    }
    return '0 B';
  }

  function formatEta(sec) {
    if (!Number.isFinite(sec) || sec <= 0 || sec > 86400) return '';
    const s = Math.round(sec);
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    const rem = s % 60;
    return `${m}m${rem < 10 ? '0' : ''}${rem}s`;
  }

  function currentDir() {
    return typeof window.currentPath === 'function' ? window.currentPath() : (window.APP?.currentPath || '');
  }

  function getConflictSetting() {
    const sel = qSel('#uploadConflict');
    return (sel && sel.value) || window.APP?.defaults?.upload_conflict || 'ask';
  }

  function getParallelLimit() {
    const n = Number(window.APP?.defaults?.upload_parallel || 3);
    return Math.max(1, Math.min(8, Number.isFinite(n) ? n : 3));
  }

  function uploadQuery(item, relDir) {
    const file = item.file || item;
    const relName = String(item.relPath || file.webkitRelativePath || file.name).replace(/^\/+/, '');
    const target = String(relDir || '').replace(/^\/+|\/+$/g, '');
    return `path=${encodeURIComponent(target)}&name=${encodeURIComponent(relName)}`;
  }

  async function preflightUpload(item, relDir) {
    const r = await fetch('/api/upload/check?' + uploadQuery(item, relDir), { cache: 'no-store' });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || 'Upload preflight failed');
    return !!data.exists;
  }


  const CHUNK_THRESHOLD_BYTES = 32 * 1024 * 1024; // 32 MiB
  const CHUNK_PART_BYTES = 16 * 1024 * 1024;      // 16 MiB per chunk

  async function abortServerChunks(uploadId) {
    if (!uploadId) return { ok: true, state: 'aborted-before-publication', aborted: true, published: false };
    try {
      const r = await fetch('/api/upload/abort', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: uploadId }),
        cache: 'no-store',
      });
      const data = await r.json().catch(() => ({}));
      return data && typeof data === 'object' ? data : { ok: r.ok };
    } catch (_) {
      return { ok: false, state: 'unknown' };
    }
  }

  async function queryUploadStatus(uploadId) {
    if (!uploadId) return { ok: true, state: 'not-published', published: false, aborted: false };
    try {
      const r = await fetch('/api/upload/status?id=' + encodeURIComponent(uploadId), { cache: 'no-store' });
      const data = await r.json().catch(() => ({}));
      return data && typeof data === 'object' ? data : { ok: r.ok };
    } catch (_) {
      return { ok: false, state: 'unknown' };
    }
  }

  async function reconcileServerOutcome(it, requestAbort = true) {
    if (!it || !it._uploadId) return { canceled: true, state: 'aborted-before-publication' };
    const res = requestAbort ? await abortServerChunks(it._uploadId) : await queryUploadStatus(it._uploadId);
    if (res && (res.published || res.state === 'published')) {
      return { ...res, state: 'published', published: true, publishedAfterCancel: Boolean(it._cancelRequested) };
    }
    if (res && (res.aborted || res.state === 'aborted-before-publication')) {
      return { canceled: true, state: 'aborted-before-publication', published: false, aborted: true };
    }
    return { canceled: Boolean(it._cancelRequested), state: res?.state || 'unknown' };
  }

  function cancelUploadItem(it) {
    if (!it) return;
    if (it.state === 'done' || it.state === 'skipped') {
      uploadState.queue = uploadState.queue.filter(x => x.id !== it.id);
      renderUploadQueue();
      return;
    }
    it._cancelRequested = true;
    if (it._xhr) {
      try { it._xhr.abort(); } catch (_) {}
      it._xhr = null;
    }
    if (it.state === 'ready' || it.state === 'error') {
      it.state = 'canceled';
      if (it._uploadId) void abortServerChunks(it._uploadId);
      uploadState.queue = uploadState.queue.filter(x => x.id !== it.id);
      renderUploadQueue();
      return;
    }
    if (it._completing) {
      it.state = 'canceling';
      if (it._abortCtrl) {
        try { it._abortCtrl.abort(); } catch (_) {}
        it._abortCtrl = null;
      }
      scheduleProgressUi();
      return;
    }
    it.state = 'canceling';
    scheduleProgressUi();
    if (it._uploadId) {
      void abortServerChunks(it._uploadId).then((res) => {
        if (res && (res.published || res.state === 'published')) {
          it.loaded = it.size;
          it.publishedAfterCancel = true;
          it.state = 'done';
        } else {
          it.state = 'canceled';
        }
        scheduleProgressUi();
      });
    } else {
      it.state = 'canceled';
      scheduleProgressUi();
    }
  }

  function uploadChunkXhr(it, uploadId, index, totalChunks, blob, onProgress) {
    const url = `/api/upload/chunk?id=${encodeURIComponent(uploadId)}&index=${index}&total=${totalChunks}`;
    return new Promise((resolve, reject) => {
      if (it._cancelRequested || it.state === 'canceled') {
        const err = new Error('aborted');
        err.aborted = true;
        reject(err);
        return;
      }
      const xhr = new XMLHttpRequest();
      it._xhr = xhr;
      xhr.open('POST', url);
      xhr.setRequestHeader('Content-Type', 'application/octet-stream');
      xhr.upload.onprogress = (e) => { if (e.lengthComputable && onProgress) onProgress(e.loaded); };
      xhr.onload = () => {
        if (it._xhr === xhr) it._xhr = null;
        let data = {};
        try { data = JSON.parse(xhr.responseText || '{}'); } catch (_) {}
        if (xhr.status >= 200 && xhr.status < 300) resolve(data);
        else { const err = new Error(data.error || `HTTP ${xhr.status}`); err.status = xhr.status; reject(err); }
      };
      xhr.onerror = () => {
        if (it._xhr === xhr) it._xhr = null;
        reject(new Error('network error'));
      };
      xhr.onabort = () => {
        if (it._xhr === xhr) it._xhr = null;
        const err = new Error('aborted');
        err.aborted = true;
        reject(err);
      };
      xhr.send(blob);
    });
  }

  async function uploadFileChunked(it, relDir, conflictMode) {
    const file = it.file;
    const totalChunks = Math.max(1, Math.ceil(file.size / CHUNK_PART_BYTES));
    if (!it._uploadId) {
      it._uploadId = 'up-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
      it._nextChunk = 0;
    }
    const relName = String(it.relPath || file.webkitRelativePath || file.name).replace(/^\/+/, '');
    const target = String(relDir || '').replace(/^\/+|\/+$/g, '');

    for (let idx = it._nextChunk || 0; idx < totalChunks; idx++) {
      if (it._cancelRequested || it.state === 'canceled') {
        return await reconcileServerOutcome(it, true);
      }
      while (uploadState.paused && !it._cancelRequested && it.state !== 'canceled') {
        await new Promise(r => setTimeout(r, 200));
      }
      if (it._cancelRequested || it.state === 'canceled') {
        return await reconcileServerOutcome(it, true);
      }
      const start = idx * CHUNK_PART_BYTES;
      const end = Math.min(file.size, start + CHUNK_PART_BYTES);
      const slice = file.slice(start, end);
      let chunkOk = false;
      let lastErr = null;
      for (let attempt = 1; attempt <= 3; attempt++) {
        if (it._cancelRequested || it.state === 'canceled') {
          return await reconcileServerOutcome(it, true);
        }
        try {
          await uploadChunkXhr(it, it._uploadId, idx, totalChunks, slice, (loadedInChunk) => {
            it.loaded = start + loadedInChunk;
            scheduleProgressUi();
          });
          chunkOk = true;
          break;
        } catch (err) {
          if (err?.aborted || it._cancelRequested || it.state === 'canceled') {
            return await reconcileServerOutcome(it, true);
          }
          lastErr = err;
          if (attempt < 3) await new Promise(r => setTimeout(r, 500 * attempt));
        }
      }
      if (it._cancelRequested || it.state === 'canceled') {
        return await reconcileServerOutcome(it, true);
      }
      if (!chunkOk) throw lastErr || new Error(`Chunk ${idx + 1}/${totalChunks} failed`);
      it._nextChunk = idx + 1;
      it.loaded = end;
      scheduleProgressUi();
    }

    if (it._cancelRequested || it.state === 'canceled') {
      return await reconcileServerOutcome(it, true);
    }

    it._completing = true;
    const ctrl = new AbortController();
    it._abortCtrl = ctrl;
    try {
      const r = await fetch('/api/upload/complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: it._uploadId, path: target, name: relName, total: totalChunks, conflict: conflictMode }),
        signal: ctrl.signal,
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        if (data && data.state === 'aborted-before-publication') {
          return { canceled: true, state: 'aborted-before-publication' };
        }
        if (it._cancelRequested) {
          return await reconcileServerOutcome(it, true);
        }
        const err = new Error(data.error || `HTTP ${r.status}`);
        err.status = r.status;
        throw err;
      }
      if (it._cancelRequested) {
        return { ...data, state: 'published', published: true, publishedAfterCancel: true };
      }
      return data;
    } catch (err) {
      if (err && (err.name === 'AbortError' || it._cancelRequested)) {
        return await reconcileServerOutcome(it, true);
      }
      const status = await queryUploadStatus(it._uploadId);
      if (status && (status.published || status.state === 'published')) {
        return status;
      }
      throw err;
    } finally {
      it._completing = false;
      if (it._abortCtrl === ctrl) it._abortCtrl = null;
    }
  }

  function uploadFileXhr(item, relDir, progressCb, conflictMode) {
    const file = item.file || item;
    const relName = String(item.relPath || file.webkitRelativePath || file.name).replace(/^\/+/, '');
    const url = `/api/upload?${uploadQuery(item, relDir)}&conflict=${encodeURIComponent(conflictMode || getConflictSetting())}`;
    return new Promise((resolve, reject) => {
      if (item._cancelRequested || item.state === 'canceled') {
        const err = new Error('aborted');
        err.aborted = true;
        reject(err);
        return;
      }
      const xhr = new XMLHttpRequest();
      item._xhr = xhr;
      xhr.open('POST', url);
      xhr.setRequestHeader('Content-Type', 'application/octet-stream');
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && progressCb) progressCb(e.loaded, e.total, relName);
      };
      xhr.onload = () => {
        if (item._xhr === xhr) item._xhr = null;
        let data = {};
        try { data = JSON.parse(xhr.responseText || '{}'); } catch (_) {}
        if (xhr.status >= 200 && xhr.status < 300) {
          if (item._cancelRequested) resolve({ ...data, publishedAfterCancel: true });
          else resolve(data);
        } else {
          const err = new Error(data.error || xhr.responseText || xhr.statusText || `HTTP ${xhr.status}`);
          err.status = xhr.status;
          reject(err);
        }
      };
      xhr.onerror = () => { if (item._xhr === xhr) item._xhr = null; reject(new Error('network error')); };
      xhr.onabort = () => { if (item._xhr === xhr) item._xhr = null; const err = new Error('aborted'); err.aborted = true; reject(err); };
      xhr.send(file);
    });
  }

  function askConflictChoice(relPath) {
    if (uploadState.conflictApplyAll) return uploadState.conflictApplyAll;
    const ans = prompt(
      `File already exists: ${relPath}\nEnter:\n- o = Overwrite (oa = Overwrite all)\n- r = Rename (ra = Rename all)\n- s = Skip (sa = Skip all)`,
      'r'
    );
    const v = String(ans || 's').trim().toLowerCase();
    if (v === 'oa') { uploadState.conflictApplyAll = 'overwrite'; return 'overwrite'; }
    if (v === 'ra') { uploadState.conflictApplyAll = 'rename'; return 'rename'; }
    if (v === 'sa') { uploadState.conflictApplyAll = 'skip'; return 'skip'; }
    if (v.startsWith('o')) return 'overwrite';
    if (v.startsWith('r')) return 'rename';
    return 'skip';
  }

  function scheduleProgressUi() {
    if (uploadState.rafId) return;
    uploadState.rafId = requestAnimationFrame(() => {
      uploadState.rafId = 0;
      updateProgressIndicators();
    });
  }

  function updateProgressIndicators() {
    let totalBytes = 0;
    let loadedBytes = 0;
    let done = 0;
    let failed = 0;
    let active = 0;
    for (const it of uploadState.queue) {
      totalBytes += (it.size || 0);
      loadedBytes += Math.min(it.size || 0, it.loaded || 0);
      if (it.state === 'done' || it.state === 'skipped') done++;
      else if (it.state === 'error') failed++;
      else if (it.state === 'uploading') active++;

      if (it._barEl) {
        const pct = it.size ? Math.min(100, Math.round((it.loaded / it.size) * 100)) : (it.state === 'done' ? 100 : 0);
        it._barEl.style.width = pct + '%';
      }
      if (it._metaEl) {
        it._metaEl.textContent = formatRowStatus(it);
      }
      if (it._rowEl) {
        it._rowEl.className = 'uq-row ' + (it.state || 'ready');
      }
    }

    const total = uploadState.queue.length;
    const pct = totalBytes > 0 ? Math.min(100, Math.round((loadedBytes / totalBytes) * 100)) : (total && done === total ? 100 : 0);

    let speedStr = '';
    if (uploadState.running && !uploadState.paused && uploadState.startedAt) {
      const elapsedSec = Math.max(0.2, (Date.now() - uploadState.startedAt) / 1000);
      const bps = loadedBytes / elapsedSec;
      if (bps > 1024) {
        const eta = formatEta((totalBytes - loadedBytes) / bps);
        speedStr = ` · ${humanBytes(bps)}/s` + (eta ? ` · ~${eta}` : '');
      }
    }

    const sumEl = qSel('#uploadSummary');
    if (sumEl) {
      sumEl.textContent = `${done}/${total} ${window.LanternI18n?.t('done')||'done'}${failed ? ` · ${failed} ${window.LanternI18n?.t('error')||'failed'}` : ''} · ${humanBytes(loadedBytes)}/${humanBytes(totalBytes)}${speedStr}`;
    }
    const barEl = qSel('#uploadModalBar');
    if (barEl) barEl.style.width = pct + '%';

    const pauseBtn = qSel('#uploadPauseBtn');
    if (pauseBtn) {
      pauseBtn.classList.toggle('hidden', !uploadState.running);
      pauseBtn.textContent = uploadState.paused ? '▶ Resume' : '⏸ Pause';
    }
    const retryBtn = qSel('#uploadRetryBtn');
    if (retryBtn) retryBtn.classList.toggle('hidden', failed === 0);

    // Floating background pill when modal is closed and upload is running or has pending/errors
    const modal = qSel('#uploadModal');
    const pill = qSel('#uploadFloatPill');
    const modalOpen = Boolean(modal && modal.classList.contains('show'));
    if (pill) {
      const showPill = !modalOpen && (uploadState.running || active > 0);
      pill.classList.toggle('hidden', !showPill);
      if (showPill) {
        const ft = qSel('#uploadFloatText');
        const ff = qSel('#uploadFloatFill');
        if (ft) ft.textContent = `${uploadState.paused ? '⏸' : '⬆️'} ${done}/${total} (${pct}%)${speedStr}`;
        if (ff) ff.style.width = pct + '%';
      }
    }
  }

  function formatRowStatus(it) {
    if (it.state === 'done' && it.publishedAfterCancel) return `✓ Published before cancel (${humanBytes(it.size)})`;
    if (it.state === 'done') return `✓ ${window.LanternI18n?.t('done')||'Done'} (${humanBytes(it.size)})`;
    if (it.state === 'canceling') return 'Canceling…';
    if (it.state === 'skipped') return `↷ ${window.LanternI18n?.t('skipped')||'Skipped'}`;
    if (it.state === 'canceled') return `✕ ${window.LanternI18n?.t('canceled')||'Canceled'}`;
    if (it.state === 'error') return `⚠️ ${it.error || 'Error'}`;
    if (it.state === 'uploading') {
      const pct = it.size ? Math.min(100, Math.round((it.loaded / it.size) * 100)) : 0;
      return `${pct}% · ${humanBytes(it.loaded)}/${humanBytes(it.size)}`;
    }
    return `${window.LanternI18n?.t('waiting')||'Queued'} · ${humanBytes(it.size)}`;
  }

  function renderUploadQueue() {
    const titleEl = qSel('#uploadTargetTitle');
    if (titleEl) titleEl.textContent = '⬆️ Upload to: /' + currentDir();
    const box = qSel('#uploadQueue');
    if (!box) return;
    box.textContent = '';
    const frag = document.createDocumentFragment();
    for (const it of uploadState.queue) {
      const row = document.createElement('div');
      row.className = 'uq-row ' + (it.state || 'ready');

      const name = document.createElement('div');
      name.className = 'uq-name';
      const targetPrefix = it.targetPath && it.targetPath !== currentDir() ? `[/${it.targetPath}] ` : '';
      name.textContent = targetPrefix + it.relPath;
      name.title = (it.targetPath ? '/' + it.targetPath + '/' : '/') + it.relPath;

      const meta = document.createElement('div');
      meta.className = 'uq-meta';
      meta.textContent = formatRowStatus(it);

      const act = document.createElement('button');
      act.type = 'button';
      act.className = 'btn small ghost';
      act.textContent = it.state === 'error' ? '↻' : '✕';
      act.title = it.state === 'error' ? 'Retry' : 'Cancel / Remove';
      act.addEventListener('click', () => {
        if (it.state === 'error') {
          it.state = 'ready';
          it.loaded = 0;
          it.error = '';
          renderUploadQueue();
          void startUploadQueue();
        } else {
          cancelUploadItem(it);
        }
      });

      const barWrap = document.createElement('div');
      barWrap.className = 'uq-bar';
      const barFill = document.createElement('span');
      const pct = it.size ? Math.min(100, Math.round((it.loaded / it.size) * 100)) : (it.state === 'done' ? 100 : 0);
      barFill.style.width = pct + '%';
      barWrap.appendChild(barFill);

      it._rowEl = row;
      it._metaEl = meta;
      it._barEl = barFill;

      row.append(name, meta, act, barWrap);
      frag.appendChild(row);
    }
    box.appendChild(frag);
    updateProgressIndicators();
  }

  async function uploadOneQueued(it) {
    if (it.state !== 'ready') return;
    it.state = 'uploading';
    it.error = '';
    scheduleProgressUi();

    const relDir = it.targetPath == null ? currentDir() : it.targetPath;
    let mode = getConflictSetting();

    try {
      if (mode === 'ask') {
        const exists = await preflightUpload(it, relDir);
        if (it._cancelRequested || it.state === 'canceled') {
          it.state = 'canceled';
          scheduleProgressUi();
          return;
        }
        if (exists) {
          mode = askConflictChoice(it.relPath);
          if (mode === 'skip') {
            it.state = 'skipped';
            it.loaded = it.size;
            scheduleProgressUi();
            return;
          }
        }
      }

      const maxAttempts = 3;
      let lastErr = null;
      for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        if (it.state === 'canceled') return;
        try {
          const useChunked = Boolean(it.file && it.file.size >= CHUNK_THRESHOLD_BYTES && typeof it.file.slice === 'function');
          const res = useChunked
            ? await uploadFileChunked(it, relDir, mode)
            : await uploadFileXhr(it, relDir, (loaded) => {
                it.loaded = loaded;
                scheduleProgressUi();
              }, mode);
          if (res && res.canceled) {
            it.state = 'canceled';
            scheduleProgressUi();
            return;
          }
          it.loaded = it.size;
          if (res && res.publishedAfterCancel) {
            it.publishedAfterCancel = true;
            it.state = 'done';
            if (typeof window.toast === 'function') {
              window.toast(`Already published before cancel: ${it.relPath}`);
            }
          } else {
            it.state = res && res.skipped ? 'skipped' : 'done';
          }
          scheduleProgressUi();
          return;
        } catch (err) {
          if (err && err.aborted) {
            it.state = 'canceled';
            scheduleProgressUi();
            return;
          }
          if (err && err.status === 409) {
            mode = askConflictChoice(it.relPath);
            if (mode === 'skip') {
              it.state = 'skipped';
              it.loaded = it.size;
              scheduleProgressUi();
              return;
            }
            continue;
          }
          lastErr = err;
          if (attempt < maxAttempts) {
            await new Promise(r => setTimeout(r, 450 * attempt));
          }
        }
      }
      throw lastErr || new Error('Upload failed');
    } catch (err) {
      it.state = 'error';
      it.error = err?.message || String(err);
      scheduleProgressUi();
    }
  }

  async function pumpQueue() {
    if (uploadState.paused) return;
    const maxPar = getParallelLimit();
    while (!uploadState.paused && uploadState.activeCount < maxPar) {
      const next = uploadState.queue.find(x => x.state === 'ready');
      if (!next) break;
      uploadState.activeCount++;
      uploadOneQueued(next).finally(() => {
        uploadState.activeCount--;
        if (!uploadState.paused && uploadState.queue.some(x => x.state === 'ready')) {
          void pumpQueue();
        } else if (uploadState.activeCount === 0 && !uploadState.paused) {
          finishQueueBatch();
        }
      });
    }
  }

  function finishQueueBatch() {
    uploadState.running = false;
    uploadState.conflictApplyAll = null;
    updateProgressIndicators();
    const doneCount = uploadState.queue.filter(x => x.state === 'done').length;
    const errCount = uploadState.queue.filter(x => x.state === 'error').length;
    if (typeof window.toast === 'function') {
      window.toast(errCount ? `${window.LanternI18n?.t('uploadFinished')||'Upload complete'}: ${doneCount} (${errCount} failed)` : `✓ ${window.LanternI18n?.t('uploadFinished')||'Upload complete'} (${doneCount})`);
    }
    if (typeof window.clearFolderCache === 'function') window.clearFolderCache();
    if (typeof window.softRefresh === 'function') void window.softRefresh();
    if (window.LanternTree?.refresh) void window.LanternTree.refresh();
  }

  async function startUploadQueue() {
    const hasReady = uploadState.queue.some(x => x.state === 'ready');
    if (!hasReady) {
      if (typeof window.toast === 'function') window.toast(window.LanternI18n?.t('uploadEmpty') || 'No queued files to upload');
      return;
    }
    uploadState.paused = false;
    if (!uploadState.running) {
      uploadState.running = true;
      uploadState.startedAt = Date.now();
    }
    updateProgressIndicators();
    await pumpQueue();
  }

  function togglePause() {
    if (!uploadState.running) return;
    uploadState.paused = !uploadState.paused;
    updateProgressIndicators();
    if (!uploadState.paused) void pumpQueue();
  }

  function retryFailed() {
    let n = 0;
    for (const it of uploadState.queue) {
      if (it.state === 'error') {
        it.state = 'ready';
        it.loaded = 0;
        it.error = '';
        n++;
      }
    }
    if (n) {
      renderUploadQueue();
      void startUploadQueue();
    }
  }

  function enqueueUploadItems(items, targetPath, autoStart = null) {
    const dest = targetPath == null ? currentDir() : String(targetPath).replace(/^\/+|\/+$/g, '');
    const shouldAuto = autoStart === null ? (window.APP?.defaults?.upload_auto_start !== false) : Boolean(autoStart);
    const arr = Array.from(items || []).map(it => ({
      id: uploadState.nextId++,
      file: it.file || it,
      relPath: String(it.relPath || it.file?.webkitRelativePath || it.file?.name || it.name || 'file').replace(/^\/+/, ''),
      size: Number(it.size ?? it.file?.size ?? 0),
      loaded: 0,
      state: 'ready',
      error: '',
      targetPath: dest,
    }));
    if (!arr.length) return 0;
    uploadState.queue.push(...arr);
    renderUploadQueue();
    if (shouldAuto || uploadState.running) {
      void startUploadQueue();
    }
    return arr.length;
  }

  function addUploadFiles(files, targetPath = null) {
    const items = Array.from(files || []).map(f => ({
      file: f,
      relPath: f.webkitRelativePath || f.name,
      size: f.size || 0,
    }));
    return enqueueUploadItems(items, targetPath);
  }

  async function traverseEntry(entry, prefix, out) {
    if (entry.isFile) {
      await new Promise(res => entry.file(
        f => { out.push({ file: f, relPath: (prefix + f.name).replace(/^\/+/, ''), size: f.size || 0 }); res(); },
        () => res()
      ));
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      let batch = [];
      do {
        batch = await new Promise(res => reader.readEntries(res, () => res([])));
        for (const child of batch) await traverseEntry(child, prefix + entry.name + '/', out);
      } while (batch.length);
    }
  }

  async function itemsFromDrop(ev) {
    const out = [];
    const dt = ev.dataTransfer;
    const items = Array.from(dt?.items || []);
    if (items.length && typeof items[0].webkitGetAsEntry === 'function') {
      const entries = items.map(it => it.webkitGetAsEntry()).filter(Boolean);
      for (const entry of entries) await traverseEntry(entry, '', out);
    }
    if (out.length) return out;
    return Array.from(dt?.files || []).map(f => ({
      file: f,
      relPath: f.webkitRelativePath || f.name,
      size: f.size || 0,
    }));
  }

  async function handleDropToTarget(ev, targetRel = null) {
    const dest = targetRel == null ? currentDir() : String(targetRel).replace(/^\/+|\/+$/g, '');
    const items = await itemsFromDrop(ev);
    if (!items.length) return 0;
    const count = enqueueUploadItems(items, dest, true);
    if (count && typeof window.toast === 'function') {
      window.toast(`${window.LanternI18n?.t('uploadAdded')||'Added to upload queue'}: ${count} → /${dest}`);
    }
    return count;
  }

  let uploadReturnFocus = null;
  function handleUploadModalKeydown(ev) {
    const m = qSel('#uploadModal');
    if (!m || !m.classList.contains('show')) return;
    if (ev.key === 'Escape') {
      ev.preventDefault();
      ev.stopPropagation();
      closeUploadDialog();
      return;
    }
    if (ev.key === 'Tab') {
      const focusables = Array.from(m.querySelectorAll('button:not([disabled]):not(.hidden), [href], input:not([disabled]):not(.hidden), select:not([disabled]):not(.hidden), [tabindex]:not([tabindex="-1"])'))
        .filter(el => el.offsetParent !== null);
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (ev.shiftKey && document.activeElement === first) {
        ev.preventDefault();
        last.focus();
      } else if (!ev.shiftKey && document.activeElement === last) {
        ev.preventDefault();
        first.focus();
      }
    }
  }

  function openUploadDialog() {
    uploadReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const m = qSel('#uploadModal');
    if (!m) return;
    renderUploadQueue();
    m.classList.add('show');
    document.addEventListener('keydown', handleUploadModalKeydown, true);
    const target = qSel('#uploadCloseBtn') || qSel('#uploadDrop');
    try { target?.focus?.(); } catch (_) {}
  }

  function closeUploadDialog() {
    const m = qSel('#uploadModal');
    if (m) m.classList.remove('show');
    document.removeEventListener('keydown', handleUploadModalKeydown, true);
    updateProgressIndicators();
    const ret = uploadReturnFocus;
    uploadReturnFocus = null;
    try { ret?.focus?.(); } catch (_) {}
  }

  function clearUploadQueue() {
    if (uploadState.running) {
      uploadState.queue = uploadState.queue.filter(x => x.state === 'uploading' || x.state === 'ready');
    } else {
      uploadState.queue = [];
    }
    renderUploadQueue();
  }

  function initUploadUi() {
    const drop = qSel('#uploadDrop');
    const fi = qSel('#fileInput');
    const foi = qSel('#folderInput');
    if (drop) {
      drop.addEventListener('click', () => fi?.click());
      drop.addEventListener('dragover', e => { e.preventDefault(); e.stopPropagation(); drop.classList.add('drag'); });
      drop.addEventListener('dragleave', () => drop.classList.remove('drag'));
      drop.addEventListener('drop', async e => {
        e.preventDefault();
        e.stopPropagation();
        drop.classList.remove('drag');
        await handleDropToTarget(e, currentDir());
      });
    }
    if (fi) {
      fi.addEventListener('change', () => {
        if (fi.files?.length) addUploadFiles(fi.files, currentDir());
        fi.value = '';
      });
    }
    if (foi) {
      foi.addEventListener('change', () => {
        if (foi.files?.length) addUploadFiles(foi.files, currentDir());
        foi.value = '';
      });
    }
  }

  window.uploadState = uploadState;
  window.LanternUpload = {
    state: uploadState,
    cancelItem: cancelUploadItem,
    init: initUploadUi,
    state: uploadState,
    humanBytes,
    enqueueUploadItems,
    addUploadFiles,
    handleDropToTarget,
    startUploadQueue,
    togglePause,
    retryFailed,
    renderUploadQueue,
    openUploadDialog,
    closeUploadDialog,
    clearUploadQueue,
  };

  window.humanBytes = humanBytes;
  window.openUploadDialog = openUploadDialog;
  window.closeUploadDialog = closeUploadDialog;
  window.pickUploadFiles = () => qSel('#fileInput')?.click();
  window.pickUploadFolder = () => qSel('#folderInput')?.click();
  window.chooseFiles = openUploadDialog;
  window.chooseFolder = openUploadDialog;
  window.startUploadQueue = startUploadQueue;
  window.clearUploadQueue = clearUploadQueue;
  window.addUploadFiles = addUploadFiles;
  window.enqueueUploadItems = enqueueUploadItems;
})();
