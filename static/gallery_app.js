/* Lantern v9.25 — Windows-Grade File Explorer & Gallery Core */
(() => {
  'use strict';

  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const defaults = window.APP?.defaults || {};

  function prefKey(k) { return 'lanDrive:' + k; }
  function pref(k, fallback) { const v = localStorage.getItem(prefKey(k)); return v === null ? fallback : v; }

  const state = {
    view: pref('view', defaults.default_view || 'grid'),
    sort: pref('sort', defaults.default_sort || 'name-asc'),
    limit: Number(pref('limit', String(defaults.page_limit || 220))),
    foldersFirst: pref('folders_first', String(defaults.folders_first ?? true)) !== 'false',
    recursiveDepth: pref('recursive_depth', '0'),
    thumbFit: pref('thumb_fit', defaults.thumb_fit || 'contain'),
    folderPreview: pref('folder_preview', String(defaults.folder_preview_enabled ?? true)) !== 'false',
    previewAnimation: pref('preview_animation', defaults.folder_preview_animation || 'fade'),
    previewPane: pref('preview_pane_enabled', 'false') === 'true',
    uploadConflict: pref('upload_conflict', defaults.upload_conflict || 'ask'),
    pluginEnabled: Boolean(window.APP?.plugin?.enabled),
    items: [],
    offset: 0,
    total: 0,
    hasMore: false,
    loading: false,
    selected: new Set(),
    lastSelectedRel: '',
    clipboard: null, // { mode: 'copy' | 'cut', paths: [...] }
    listPreview: null,
    dragCandidate: null,
    dragSelecting: false,
    dragMode: null,
    suppressClick: false,
    searchTimer: 0,
    navHistory: [String(window.APP?.currentPath || '').replace(/^\/+|\/+$/g, '')],
    navIndex: 0,
  };
  window.LanternAppState = state;

  const grid = $('#grid');
  const q = $('#q');
  const sidePreview = $('#sidePreview');
  const toastBox = $('#toast');

  function escHtml(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function enc(s) { return encodeURIComponent(String(s || '')).replace(/%2F/g, '/'); }
  function currentPath() { return String(window.APP?.currentPath || '').replace(/^\/+|\/+$/g, ''); }
  function selectedArray() { return Array.from(state.selected); }
  function fileUrl(rel) { return '/' + enc(rel); }
  function previewUrl(rel) { return '/api/plugin/preview?p=' + encodeURIComponent(rel); }
  function isMediaKind(kind) { return Boolean(window.LanternMedia?.isMediaKind?.(kind)); }
  function findLoadedItem(rel) { return state.items.find(it => !it.special && it.rel === rel) || null; }

  function toast(msg) {
    if (!toastBox) { console.log(msg); return; }
    const el = document.createElement('div');
    el.textContent = String(msg || '');
    toastBox.appendChild(el);
    setTimeout(() => el.remove(), 3200);
  }

  function cachePrefix() { return 'lanDrive:list:' + location.pathname + ':'; }
  function cacheKey() { return cachePrefix() + state.sort + ':' + state.limit + ':' + state.recursiveDepth + ':' + String(state.foldersFirst) + ':' + (q?.value || ''); }
  function clearFolderCache() {
    try {
      const p = cachePrefix();
      Object.keys(sessionStorage).forEach(k => { if (k.startsWith(p)) sessionStorage.removeItem(k); });
    } catch (_) {}
  }

  function savePrefs(patch) {
    try {
      if (patch.default_view !== undefined) localStorage.setItem(prefKey('view'), String(patch.default_view));
      if (patch.default_sort !== undefined) localStorage.setItem(prefKey('sort'), String(patch.default_sort));
      if (patch.page_limit !== undefined) localStorage.setItem(prefKey('limit'), String(patch.page_limit));
      if (patch.folders_first !== undefined) localStorage.setItem(prefKey('folders_first'), String(patch.folders_first));
      if (patch.thumb_fit !== undefined) localStorage.setItem(prefKey('thumb_fit'), String(patch.thumb_fit));
      if (patch.folder_preview_enabled !== undefined) localStorage.setItem(prefKey('folder_preview'), String(patch.folder_preview_enabled));
      if (patch.folder_preview_animation !== undefined) localStorage.setItem(prefKey('preview_animation'), String(patch.folder_preview_animation));
      if (patch.upload_conflict !== undefined) localStorage.setItem(prefKey('upload_conflict'), String(patch.upload_conflict));
    } catch (_) {}
    fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    }).catch(() => {});
  }

  async function api(path, data) {
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data || {}),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.error) throw new Error(j.error || `HTTP ${r.status}`);
    return j;
  }

  // ---------------- SPA Navigation & Windows Address Bar ----------------
  function renderBreadcrumbs(relPath) {
    const bar = $('#crumbsBar');
    if (!bar) return;
    const clean = String(relPath || '').replace(/^\/+|\/+$/g, '');
    const parts = clean ? clean.split('/') : [];
    const html = [];
    if (parts.length) {
      const parentRel = parts.slice(0, -1).join('/');
      const parentHref = parentRel ? '/' + enc(parentRel) + '/' : '/';
      html.push(`<a class="crumb-back" data-action="back" data-rel="${escHtml(parentRel)}" href="${parentHref}" onclick="return goParentFolder(event, '${parentHref}')">↩ Back</a>`);
    }
    html.push(`<a data-rel="" href="/" onclick="return navigateCrumb(event, '')">Root</a>`);
    const acc = [];
    for (const p of parts) {
      acc.push(p);
      const cur = acc.join('/');
      const href = '/' + enc(cur) + '/';
      html.push(`<span class="crumb-sep">/</span><a data-rel="${escHtml(cur)}" href="${href}" onclick="return navigateCrumb(event, ${JSON.stringify(cur)})">${escHtml(p)}</a>`);
    }
    bar.innerHTML = html.join('');
    updateNavButtons();
  }

  function updateNavButtons() {
    const backBtn = $('#navBackBtn');
    const fwdBtn = $('#navFwdBtn');
    const upBtn = $('#navUpBtn');
    if (backBtn) backBtn.disabled = state.navIndex <= 0;
    if (fwdBtn) fwdBtn.disabled = state.navIndex >= state.navHistory.length - 1;
    if (upBtn) upBtn.disabled = !currentPath();
  }

  async function navigateToFolder(relPath, opts = {}) {
    const clean = String(relPath || '').replace(/^\/+|\/+$/g, '');
    const href = clean ? '/' + enc(clean) + '/' : '/';
    if (window.APP) window.APP.currentPath = clean;
    state.selected.clear();
    state.lastSelectedRel = '';
    if (q && !opts.keepSearch) q.value = '';

    if (!opts.skipHistory) {
      const prev = state.navHistory[state.navIndex];
      if (prev !== clean) {
        state.navHistory = state.navHistory.slice(0, state.navIndex + 1);
        state.navHistory.push(clean);
        state.navIndex = state.navHistory.length - 1;
      }
      if (location.pathname !== href) {
        try { history.pushState({ lanternPath: clean }, document.title, href); } catch (_) {}
      }
    }
    renderBreadcrumbs(clean);
    const upTitle = $('#uploadTargetTitle');
    if (upTitle) upTitle.textContent = '⬆️ Upload vào: /' + clean;
    if (window.LanternTree?.syncToPath) void window.LanternTree.syncToPath(clean, false);
    await loadMore(true);
    if (grid) grid.scrollTop = 0;
  }

  function navigateCrumb(ev, rel) {
    if (ev && (ev.ctrlKey || ev.metaKey || ev.button === 1)) return true;
    if (ev) { ev.preventDefault(); ev.stopPropagation(); }
    void navigateToFolder(rel);
    return false;
  }

  function navHistoryBack() {
    if (state.navIndex <= 0) return;
    state.navIndex--;
    const target = state.navHistory[state.navIndex];
    const href = target ? '/' + enc(target) + '/' : '/';
    try { history.replaceState({ lanternPath: target }, document.title, href); } catch (_) {}
    void navigateToFolder(target, { skipHistory: true });
  }

  function navHistoryForward() {
    if (state.navIndex >= state.navHistory.length - 1) return;
    state.navIndex++;
    const target = state.navHistory[state.navIndex];
    const href = target ? '/' + enc(target) + '/' : '/';
    try { history.replaceState({ lanternPath: target }, document.title, href); } catch (_) {}
    void navigateToFolder(target, { skipHistory: true });
  }

  function navParentFolder() {
    const cur = currentPath();
    if (!cur) return;
    const parts = cur.split('/').filter(Boolean);
    parts.pop();
    void navigateToFolder(parts.join('/'));
  }

  function goParentFolder(ev, _href) {
    if (ev && (ev.ctrlKey || ev.metaKey || ev.button === 1)) return true;
    if (ev) { ev.preventDefault(); ev.stopPropagation(); }
    navParentFolder();
    return false;
  }

  function openAddressEditor() {
    const wrap = $('#addressWrap');
    const crumbs = $('#crumbsBar');
    const inp = $('#addressInput');
    if (!wrap || !crumbs || !inp) return;
    wrap.classList.add('editing');
    crumbs.classList.add('hidden');
    inp.classList.remove('hidden');
    inp.value = currentPath();
    inp.focus();
    inp.select();
  }

  function closeAddressEditor() {
    const wrap = $('#addressWrap');
    const crumbs = $('#crumbsBar');
    const inp = $('#addressInput');
    if (!wrap || !crumbs || !inp) return;
    wrap.classList.remove('editing');
    inp.classList.add('hidden');
    crumbs.classList.remove('hidden');
  }

  function initAddressBar() {
    const wrap = $('#addressWrap');
    const inp = $('#addressInput');
    if (!wrap || !inp) return;
    wrap.addEventListener('click', (ev) => {
      if (ev.target.closest('a')) return;
      openAddressEditor();
    });
    inp.addEventListener('blur', closeAddressEditor);
    inp.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape') { ev.preventDefault(); closeAddressEditor(); return; }
      if (ev.key === 'Enter') {
        ev.preventDefault();
        const target = inp.value.trim().replace(/^\/+|\/+$/g, '');
        closeAddressEditor();
        void navigateToFolder(target);
      }
    });
  }

  window.addEventListener('popstate', (ev) => {
    const p = ev.state && typeof ev.state.lanternPath === 'string'
      ? ev.state.lanternPath
      : decodeURIComponent(location.pathname).replace(/^\/+|\/+$/g, '');
    void navigateToFolder(p, { skipHistory: true });
  });

  // ---------------- View Modes, Selection & Status Bar ----------------
  function applyView() {
    if (!grid) return;
    const v = state.view || 'grid';
    grid.classList.toggle('list', v === 'list');
    grid.classList.toggle('view-details', v === 'details');
    grid.classList.toggle('view-large', v === 'large');
    document.body.classList.toggle('view-list', v === 'list' || v === 'details');
    document.body.classList.toggle('preview-pane', Boolean(state.previewPane));
    document.body.classList.remove('thumb-cover', 'thumb-contain');
    document.body.classList.add('thumb-' + (state.thumbFit === 'cover' ? 'cover' : 'contain'));
    $$('.view-toggle button').forEach(b => b.classList.toggle('active', b.dataset.view === v));
    const pb = $('#previewPaneBtn');
    if (pb) {
      pb.classList.toggle('active', Boolean(state.previewPane));
      pb.textContent = state.previewPane ? '👁 Preview on' : '👁 Preview';
    }
    localStorage.setItem(prefKey('view'), v);
    if (state.previewPane) ensureSidePreview();
    else clearSidePreview();
  }

  function setView(v) { state.view = v; applyView(); savePrefs({ default_view: v }); }
  function togglePreviewPane() {
    state.previewPane = !state.previewPane;
    localStorage.setItem(prefKey('preview_pane_enabled'), String(state.previewPane));
    applyView();
  }

  function syncControls() {
    const s = $('#sortSelect'); if (s) s.value = state.sort;
    const l = $('#limitSelect'); if (l) l.value = String(state.limit);
    const ff = $('#foldersFirst'); if (ff) ff.checked = state.foldersFirst;
    const rd = $('#recursiveDepth'); if (rd) rd.value = state.recursiveDepth;
    const tf = $('#thumbFit'); if (tf) tf.value = state.thumbFit;
    const fp = $('#folderPreviewToggle'); if (fp) fp.checked = state.folderPreview;
    const pa = $('#previewAnim'); if (pa) pa.value = state.previewAnimation;
    const uc = $('#uploadConflict'); if (uc) uc.value = state.uploadConflict;
  }

  function isArchiveCard(card) { return Boolean(card && card.dataset.isdir === '0' && card.dataset.kind === 'archive'); }
  function selectedCards() { return selectedArray().map(rel => document.querySelector(`.card[data-rel="${CSS.escape(rel)}"]`)).filter(Boolean); }

  function updateStatusBar() {
    const realItems = state.items.filter(x => !x.special);
    const stItems = $('#statusItems');
    if (stItems) stItems.textContent = `${realItems.length}${state.hasMore ? '+' : ''} mục${state.total > realItems.length ? ` (tổng ${state.total})` : ''}`;

    const stSel = $('#statusSel');
    const n = state.selected.size;
    if (stSel) {
      if (n > 0) {
        let selBytes = 0;
        for (const rel of state.selected) {
          const it = findLoadedItem(rel);
          if (it && !it.is_dir && it.size) selBytes += Number(it.size);
        }
        const sz = selBytes > 0 && window.humanBytes ? ` · ${window.humanBytes(selBytes)}` : '';
        stSel.textContent = `${n} mục đã chọn${sz}`;
        stSel.classList.remove('hidden');
      } else {
        stSel.classList.add('hidden');
      }
    }

    const stClip = $('#statusClip');
    if (stClip) {
      if (state.clipboard && state.clipboard.paths.length) {
        const verb = state.clipboard.mode === 'cut' ? 'cắt (Move)' : 'sao chép (Copy)';
        stClip.textContent = `📋 ${state.clipboard.paths.length} mục đã ${verb} — Ctrl+V để dán`;
        stClip.classList.remove('hidden');
      } else {
        stClip.classList.add('hidden');
      }
    }
  }

  function updateSelectionUI() {
    if (!grid) return;
    const cutSet = new Set(state.clipboard?.mode === 'cut' ? state.clipboard.paths : []);
    $$('.card').forEach(c => {
      const rel = c.dataset.rel;
      if (!rel) return;
      c.classList.toggle('selected', state.selected.has(rel));
      c.classList.toggle('is-cut', cutSet.has(rel));
    });
    const n = state.selected.size;
    const count = $('#selCount');
    if (count) count.textContent = n ? `${n} chọn` : '';
    const one = n === 1 ? document.querySelector(`.card[data-rel="${CSS.escape(selectedArray()[0] || '')}"]`) : null;
    const oneFile = Boolean(one && one.dataset.isdir === '0');
    const canPreview = Boolean(oneFile && one.dataset.preview === '1');
    const canExtract = Boolean(one && isArchiveCard(one));

    $('#pasteBtn')?.classList.toggle('hidden', !(state.clipboard && state.clipboard.paths.length));
    $('#deleteBtn')?.classList.toggle('hidden', !n);
    $('#downloadBtn')?.classList.toggle('hidden', !n);
    $('#archiveBtn')?.classList.toggle('hidden', !n);
    $('#copyBtn')?.classList.toggle('hidden', !n);
    $('#moveBtn')?.classList.toggle('hidden', !n);
    $('#duplicateBtn')?.classList.toggle('hidden', !n);
    $('#batchRenameBtn')?.classList.toggle('hidden', n < 2);
    $('#extractBtn')?.classList.toggle('hidden', !canExtract);
    $('#renameBtn')?.classList.toggle('hidden', n !== 1);
    $('#shareBtn')?.classList.toggle('hidden', n !== 1);
    $('#previewBtn')?.classList.toggle('hidden', !canPreview);
    updateStatusBar();
  }

  function toggleSelect(rel, ev) {
    if (ev) { ev.preventDefault(); ev.stopPropagation(); }
    closeContextMenu();
    if (!rel) return;
    if (ev && ev.shiftKey && state.lastSelectedRel) {
      const rels = $$('.card[data-rel]').map(c => c.dataset.rel);
      const a = rels.indexOf(state.lastSelectedRel);
      const b = rels.indexOf(rel);
      if (a >= 0 && b >= 0) {
        const [lo, hi] = a < b ? [a, b] : [b, a];
        for (let i = lo; i <= hi; i++) state.selected.add(rels[i]);
        updateSelectionUI();
        return;
      }
    }
    if (state.selected.has(rel)) state.selected.delete(rel);
    else state.selected.add(rel);
    state.lastSelectedRel = rel;
    updateSelectionUI();
  }

  function clearSel() { state.selected.clear(); state.lastSelectedRel = ''; updateSelectionUI(); }
  function selectVisible() { $$('.card[data-rel]').forEach(c => state.selected.add(c.dataset.rel)); updateSelectionUI(); }

  // ---------------- Rendering & Listing ----------------
  function sortDirFor(key) { const cur = state.sort || 'name-asc'; return cur.startsWith(key + '-') && cur.endsWith('asc') ? 'desc' : 'asc'; }
  function sortByHeader(key) { sortCards(key + '-' + sortDirFor(key)); }
  function sortArrow(key) { const cur = state.sort || ''; return cur.startsWith(key + '-') ? (cur.endsWith('asc') ? ' ▲' : ' ▼') : ''; }

  function listHeaderHTML() {
    return `<div class="list-head"><span></span><button onclick="sortByHeader('name')">Name${sortArrow('name')}</button><button class="col-mtime" onclick="sortByHeader('mtime')">Date modified${sortArrow('mtime')}</button><button class="col-type" onclick="sortByHeader('type')">Type${sortArrow('type')}</button><button class="col-size" onclick="sortByHeader('size')">Size${sortArrow('size')}</button></div>`;
  }

  function cardHTML(it) {
    if (it.special === 'back') {
      return `<article class="card special-back"><div class="card-main" onclick="navParentFolder()"><div class="thumbwrap"><span class="fileicon">↩️</span></div><div class="meta"><div class="name">.. (Thư mục cha)</div><div class="sub">Quay lại</div></div><div class="detail-col col-mtime"></div><div class="detail-col col-type">Folder</div><div class="detail-col col-size"></div></div></article>`;
    }
    const rel = it.rel || '';
    const isDir = it.is_dir ? '1' : '0';
    const kind = it.kind || 'other';
    const badge = it.is_dir ? 'DIR' : (it.ext ? it.ext.replace('.', '').toUpperCase() : kind.toUpperCase());
    let thumbHtml = `<span class="fileicon">${escHtml(it.icon || (it.is_dir ? '📁' : '📄'))}</span>`;
    if (it.is_dir && state.folderPreview) {
      thumbHtml = `<div class="folder-mosaic" data-folder-preview="${escHtml(rel)}"><span class="fileicon">📁</span></div>`;
    } else if (it.thumb) {
      thumbHtml = `<img class="thumb" loading="lazy" decoding="async" src="${escHtml(it.thumb)}" alt="${escHtml(it.name)}" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'fileicon',textContent:'${it.kind === 'video' ? '🎬' : '🖼️'}'}))">`;
    }
    const subText = it.is_dir ? (it.mtime_text || 'Folder') : [it.size_text, it.mtime_text].filter(Boolean).join(' · ');
    return `<article class="card" draggable="true" data-rel="${escHtml(rel)}" data-isdir="${isDir}" data-kind="${escHtml(kind)}" data-rawname="${escHtml(it.name)}" data-preview="${it.can_preview ? '1' : '0'}" oncontextmenu="openContextMenu(event,this)"><button type="button" class="check" aria-label="Select" onclick="toggleSelect(${JSON.stringify(rel)},event)"></button><div class="card-main" onclick="openItem(this.parentElement,event)"><div class="thumbwrap">${thumbHtml}<span class="badge">${escHtml(badge)}</span></div><div class="meta"><div class="name" title="${escHtml(it.name)}">${escHtml(it.name)}</div><div class="sub">${escHtml(subText)}</div></div><div class="detail-col col-mtime">${escHtml(it.mtime_text || '')}</div><div class="detail-col col-type">${escHtml(it.is_dir ? 'Folder' : (it.ext || kind))}</div><div class="detail-col col-size">${escHtml(it.is_dir ? '' : (it.size_text || ''))}</div></div></article>`;
  }

  let loaderIO = null;
  function observeLoader() {
    if (loaderIO) loaderIO.disconnect();
    const ld = $('#loader');
    if (!ld || !state.hasMore) return;
    loaderIO = new IntersectionObserver(entries => {
      if (entries.some(e => e.isIntersecting) && !state.loading && state.hasMore) {
        void loadMore(false);
      }
    }, { root: grid, rootMargin: '400px' });
    loaderIO.observe(ld);
  }

  function ensureLoader() {
    const old = $('#loader');
    if (old) old.remove();
    if (state.hasMore) grid.insertAdjacentHTML('beforeend', '<div id="loader" class="loader">Đang tải thêm...</div>');
    observeLoader();
  }

  let renderBatchToken = 0;
  function render() {
    if (!grid) return;
    renderBatchToken++;
    const token = renderBatchToken;
    if (!state.items.length && !state.loading) {
      grid.innerHTML = '<div class="empty"><div><div style="font-size:38px;margin-bottom:8px">📂</div><b>Thư mục trống</b><div class="sub" style="margin-top:4px">Kéo thả file hoặc folder vào đây để upload</div></div></div>';
      updateSelectionUI();
      return;
    }
    const BATCH = 140;
    if (state.items.length <= BATCH) {
      grid.innerHTML = listHeaderHTML() + state.items.map(cardHTML).join('');
      ensureLoader();
      applyView();
      updateSelectionUI();
      setupFolderPreviews();
      wireGridCardDropTargets();
      return;
    }
    grid.innerHTML = listHeaderHTML() + state.items.slice(0, BATCH).map(cardHTML).join('');
    applyView();
    updateSelectionUI();
    setupFolderPreviews();
    wireGridCardDropTargets();
    let idx = BATCH;
    const pump = () => {
      if (token !== renderBatchToken) return;
      const slice = state.items.slice(idx, idx + BATCH);
      if (slice.length) {
        grid.insertAdjacentHTML('beforeend', slice.map(cardHTML).join(''));
        idx += slice.length;
        if (idx < state.items.length) {
          requestAnimationFrame(pump);
          return;
        }
      }
      ensureLoader();
      updateSelectionUI();
      setupFolderPreviews();
      wireGridCardDropTargets();
    };
    requestAnimationFrame(pump);
  }

  function appendRender(newItems) {
    if (!grid) return;
    const old = $('#loader');
    if (old) old.remove();
    if (!grid.querySelector('.list-head')) grid.innerHTML = listHeaderHTML();
    if (newItems && newItems.length) grid.insertAdjacentHTML('beforeend', newItems.map(cardHTML).join(''));
    ensureLoader();
    applyView();
    updateSelectionUI();
    setupFolderPreviews();
    wireGridCardDropTargets();
  }

  let listRev = 0;
  let listController = null;
  async function loadMore(reset = false) {
    if (!grid) return;
    if (reset) {
      listRev++;
      if (listController) { try { listController.abort(); } catch (_) {} }
      state.offset = 0;
    } else if (state.loading) {
      return;
    }
    const myRev = listRev;
    listController = new AbortController();
    state.loading = true;

    const params = new URLSearchParams({
      path: currentPath(),
      offset: String(reset ? 0 : state.offset),
      limit: String(state.limit),
      sort: state.sort,
      q: q?.value || '',
      recursive_depth: (q?.value || '').trim() ? state.recursiveDepth : '0',
      folders_first: String(state.foldersFirst),
    });

    try {
      const r = await fetch('/api/list?' + params.toString(), { cache: 'no-store', signal: listController.signal });
      const data = await r.json();
      if (myRev !== listRev) return;
      if (!r.ok || data.error) throw new Error(data.error || `HTTP ${r.status}`);
      state.hasMore = Boolean(data.hasMore);
      state.offset = Number(data.nextOffset || 0);
      state.total = Number(data.total || 0);
      if (reset) {
        state.items = Array.isArray(data.items) ? data.items : [];
        render();
      } else {
        const added = (Array.isArray(data.items) ? data.items : []).filter(x => !x.special);
        state.items.push(...added);
        appendRender(added);
      }
    } catch (err) {
      if (err && err.name === 'AbortError') return;
      toast('Không tải được danh sách: ' + (err?.message || err));
    } finally {
      if (myRev === listRev) state.loading = false;
      updateStatusBar();
    }
  }

  async function softRefresh() { await loadMore(true); }
  function refreshFolder() { clearFolderCache(); void softRefresh(); window.LanternTree?.refresh?.(currentPath()); }
  function sortCards(mode) { if (mode) state.sort = mode; syncControls(); savePrefs({ default_sort: state.sort }); clearFolderCache(); void loadMore(true); }

  // ---------------- Drag & Drop onto Folder Cards + OS Upload Drop ----------------
  function wireGridCardDropTargets() {
    if (!grid) return;
    $$('.card[data-isdir="1"]').forEach(card => {
      if (card.dataset.dropWired) return;
      card.dataset.dropWired = '1';
      const targetRel = card.dataset.rel || '';
      card.addEventListener('dragover', ev => {
        const types = Array.from(ev.dataTransfer?.types || []);
        if (!types.includes('application/x-lantern-paths') && !types.includes('Files')) return;
        ev.preventDefault();
        ev.stopPropagation();
        ev.dataTransfer.dropEffect = ev.ctrlKey ? 'copy' : 'move';
        card.classList.add('drop-target');
      });
      card.addEventListener('dragleave', () => card.classList.remove('drop-target'));
      card.addEventListener('drop', async ev => {
        card.classList.remove('drop-target');
        const rawLantern = ev.dataTransfer?.getData('application/x-lantern-paths');
        if (rawLantern) {
          ev.preventDefault();
          ev.stopPropagation();
          try {
            const parsed = JSON.parse(rawLantern);
            const paths = (Array.isArray(parsed) ? parsed : []).map(x => typeof x === 'string' ? x : x.path).filter(p => p && p !== targetRel);
            if (paths.length) await transferPathsToFolder(paths, targetRel, ev.ctrlKey ? 'copy' : 'move');
          } catch (err) {
            toast('Lỗi kéo thả: ' + err.message);
          }
          return;
        }
        if (ev.dataTransfer?.files?.length || ev.dataTransfer?.items?.length) {
          ev.preventDefault();
          ev.stopPropagation();
          await window.LanternUpload?.handleDropToTarget?.(ev, targetRel);
        }
      });
    });
  }

  async function transferPathsToFolder(paths, destRel, mode = 'move') {
    const cleanDest = String(destRel || '').replace(/^\/+|\/+$/g, '');
    const filtered = paths.filter(p => {
      const norm = String(p || '').replace(/^\/+|\/+$/g, '');
      if (!norm || norm === cleanDest) return false;
      const parent = norm.includes('/') ? norm.split('/').slice(0, -1).join('/') : '';
      return !(mode === 'move' && parent === cleanDest);
    });
    if (!filtered.length) return;
    try {
      if (mode === 'copy') {
        const r = await api('/api/copy', { paths: filtered, dest: cleanDest, conflict: 'rename' });
        toast(`✓ Đã copy ${r.copied?.length || filtered.length} mục vào /${cleanDest}`);
      } else {
        const r = await api('/api/move', { paths: filtered, dest: cleanDest, conflict: 'rename' });
        toast(`✓ Đã di chuyển ${r.moved?.length || filtered.length} mục vào /${cleanDest}`);
        if (state.clipboard?.mode === 'cut') state.clipboard = null;
      }
      clearFolderCache();
      state.selected.clear();
      await softRefresh();
      if (window.LanternTree?.refresh) void window.LanternTree.refresh();
    } catch (err) {
      toast(`Lỗi ${mode}: ` + err.message);
    }
  }

  // ---------------- Windows Clipboard (Ctrl+C / Ctrl+X / Ctrl+V) ----------------
  function setClipboard(mode, paths = null) {
    const arr = paths || selectedArray();
    if (!arr.length) return;
    state.clipboard = { mode, paths: [...arr] };
    updateSelectionUI();
    toast(mode === 'cut' ? `✂️ Đã cắt ${arr.length} mục (Ctrl+V để dán)` : `📋 Đã sao chép ${arr.length} mục (Ctrl+V để dán)`);
  }

  async function pasteClipboard(targetRel = null) {
    if (!state.clipboard || !state.clipboard.paths.length) return;
    const dest = targetRel == null ? currentPath() : targetRel;
    await transferPathsToFolder(state.clipboard.paths, dest, state.clipboard.mode === 'cut' ? 'move' : 'copy');
  }

  // ---------------- File Operations & Properties ----------------
  async function mkdir(parentRel = null) {
    const name = prompt('Tên thư mục mới:');
    if (!name) return;
    const base = parentRel == null ? currentPath() : parentRel;
    try {
      await api('/api/mkdir', { path: base, name });
      clearFolderCache();
      await softRefresh();
      if (window.LanternTree?.refresh) void window.LanternTree.refresh(base);
    } catch (e) { toast('Lỗi tạo thư mục: ' + e.message); }
  }

  async function newFile() {
    const name = prompt('Tên file mới, ví dụ notes.txt:');
    if (!name) return;
    try { const r = await api('/api/newfile', { path: currentPath(), name }); location.href = r.edit_url; }
    catch (e) { toast('Lỗi tạo file: ' + e.message); }
  }

  async function renameOne() {
    const rel = selectedArray()[0];
    if (!rel) return;
    const old = rel.split('/').pop();
    const name = prompt('Đổi tên thành:', old);
    if (!name || name === old) return;
    try {
      await api('/api/rename', { path: rel, name });
      clearFolderCache();
      state.selected.clear();
      await softRefresh();
      if (window.LanternTree?.refresh) void window.LanternTree.refresh(currentPath());
    } catch (e) { toast('Lỗi rename: ' + e.message); }
  }

  async function copySel() { setClipboard('copy'); }
  async function moveSel() {
    const arr = selectedArray();
    if (!arr.length) return;
    const dest = prompt(`Move ${arr.length} mục đến thư mục (hoặc dùng Ctrl+X rồi Ctrl+V):`, currentPath());
    if (dest === null) return;
    await transferPathsToFolder(arr, dest, 'move');
  }

  async function duplicateSel() {
    const arr = selectedArray();
    if (!arr.length) return;
    try {
      const r = await api('/api/duplicate', { paths: arr, conflict: 'rename' });
      toast(`Đã nhân bản ${r.duplicated?.length || 0} mục`);
      clearFolderCache();
      await softRefresh();
    } catch (e) { toast('Lỗi duplicate: ' + e.message); }
  }

  async function batchRenameSel() {
    const arr = selectedArray();
    if (arr.length < 2) { toast('Batch rename cần chọn ít nhất 2 mục'); return; }
    const find = prompt('Batch rename — tìm chuỗi trong tên:', '');
    if (find === null || find === '') return;
    const repl = prompt('Thay bằng:', '');
    if (repl === null) return;
    const items = arr.map(path => {
      const old = path.split('/').pop();
      return { path, name: old.split(find).join(repl) };
    }).filter(x => x.name && x.name !== x.path.split('/').pop());
    if (!items.length) { toast('Không có tên nào thay đổi'); return; }
    try {
      const r = await api('/api/batch_rename', { items });
      toast(`Đã đổi tên ${r.renamed?.length || 0} mục`);
      state.selected.clear();
      await softRefresh();
    } catch (e) { toast('Lỗi batch rename: ' + e.message); }
  }

  async function extractSelected() {
    const arr = selectedArray();
    const card = arr.length === 1 ? document.querySelector(`.card[data-rel="${CSS.escape(arr[0])}"]`) : null;
    if (!isArchiveCard(card)) { toast('Chỉ giải nén file archive'); return; }
    const dest = prompt('Giải nén đến thư mục:', currentPath());
    if (dest === null) return;
    try {
      const r = await api('/api/extract', { path: arr[0], dest, conflict: 'rename' });
      toast(`Giải nén xong: ${r.written || 0} file`);
      await softRefresh();
      if (window.LanternTree?.refresh) void window.LanternTree.refresh();
    } catch (e) { toast('Lỗi giải nén: ' + e.message); }
  }

  function submitArchive(paths, format = 'zip', compression = 'compress') {
    const arr = paths || selectedArray();
    if (!arr.length) return;
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = '/api/archive';
    const input = document.createElement('input');
    input.name = 'payload';
    input.value = JSON.stringify({ paths: arr, format, compression });
    form.appendChild(input);
    document.body.appendChild(form);
    form.submit();
    form.remove();
  }

  function archiveSelected() {
    const arr = selectedArray();
    if (!arr.length) return;
    const fmt = (prompt('Định dạng nén (zip hoặc tar):', 'zip') || '').trim().toLowerCase();
    if (!['zip', 'tar'].includes(fmt)) return;
    submitArchive(arr, fmt, 'compress');
  }

  async function downloadSelected() {
    const arr = selectedArray();
    if (!arr.length) return;
    const cards = selectedCards();
    if (arr.length === 1 && cards[0]?.dataset.isdir === '0') {
      location.href = '/' + enc(arr[0]) + '?download=1';
      return;
    }
    submitArchive(arr, 'zip', 'compress');
  }

  async function deleteSel() {
    const arr = selectedArray();
    if (!arr.length) return;
    if (!confirm(`Xoá vĩnh viễn ${arr.length} mục?`)) return;
    try {
      await api('/api/delete', { paths: arr });
      clearFolderCache();
      state.selected.clear();
      await softRefresh();
      if (window.LanternTree?.refresh) void window.LanternTree.refresh(currentPath());
    } catch (e) { toast('Lỗi xoá: ' + e.message); }
  }

  async function shareOne() {
    const rel = selectedArray()[0];
    if (!rel) return;
    const url = new URL('/' + enc(rel), location.href).href;
    try {
      if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(url); toast('✓ Đã copy link'); return; }
    } catch (_) {}
    prompt('Copy link:', url);
  }

  async function openPropertiesModal(relPath = null) {
    const target = relPath != null ? relPath : (selectedArray()[0] ?? currentPath());
    const modal = $('#propsModal');
    const title = $('#propsTitle');
    const body = $('#propsBody');
    if (!modal || !body) return;
    if (title) title.textContent = 'Properties — ' + (target || 'Root');
    body.innerHTML = '<div class="sub">Đang đọc thông tin...</div>';
    modal.classList.add('show');
    try {
      const r = await fetch('/api/properties?p=' + encodeURIComponent(target), { cache: 'no-store' });
      const p = await r.json();
      if (!r.ok || !p.ok) throw new Error(p.error || 'Failed');
      const rows = [
        ['Tên', p.name],
        ['Đường dẫn', p.fullPath],
        ['Loại', p.isDir ? 'Thư mục (Folder)' : `${p.kind}${p.mime ? ` (${p.mime})` : ''}`],
        ['Dung lượng', p.sizeText],
      ];
      if (p.isDir) rows.push(['Chứa', `${p.files} file, ${p.folders} thư mục con${p.truncated ? ' (giới hạn quét)' : ''}`]);
      if (p.width && p.height) rows.push(['Độ phân giải', `${p.width} × ${p.height} px${p.format ? ` (${p.format})` : ''}`]);
      rows.push(['Sửa đổi', p.mtimeText], ['Tạo lúc', p.ctimeText]);
      body.innerHTML = rows.map(([k, v]) => `<div class="props-row"><div class="k">${escHtml(k)}</div><div class="v">${escHtml(v)}</div></div>`).join('');
    } catch (err) {
      body.textContent = 'Lỗi đọc properties: ' + err.message;
    }
  }

  // ---------------- Side Preview & Item Open ----------------
  function clearSidePreview() { if (sidePreview) { sidePreview.innerHTML = '<div class="side-empty">Preview off</div>'; state.listPreview = null; } }
  function ensureSidePreview() { if (sidePreview && state.previewPane && !state.listPreview) sidePreview.innerHTML = '<div class="side-empty">Chọn file để preview</div>'; }
  function listCanPreview(card) { return Boolean(card && card.dataset.isdir === '0' && (isMediaKind(card.dataset.kind) || card.dataset.preview === '1' || card.dataset.kind === 'text' || card.dataset.kind === 'pdf')); }

  function renderListPreview(card) {
    if (!sidePreview || !card) return;
    const rel = card.dataset.rel, kind = card.dataset.kind, item = findLoadedItem(rel), name = item?.name || card.dataset.rawname || rel, url = item?.url || fileUrl(rel);
    state.listPreview = rel;
    sidePreview.innerHTML = '<div class="side-title"><span class="side-title-text"></span><div class="side-nav top"><button onclick="togglePreviewPane()" title="Close preview">×</button></div></div><div class="side-body"><button class="side-arrow side-prev" onclick="stepSidePreview(-1)">‹</button><button class="side-arrow side-next" onclick="stepSidePreview(1)">›</button><div class="side-content"></div></div>';
    sidePreview.querySelector('.side-title-text').textContent = name;
    const body = sidePreview.querySelector('.side-content');
    if (kind === 'image') {
      body.innerHTML = `<div class="side-fit-bg" style="background-image:url('${url.replace(/'/g, '%27')}')"></div>`;
      const openBtn = document.createElement('button');
      openBtn.className = 'btn small';
      openBtn.textContent = 'Phóng to / Crop';
      openBtn.onclick = () => window.openPreview('image', url, name, rel);
      sidePreview.querySelector('.side-nav.top')?.prepend(openBtn);
    } else if (kind === 'video') {
      body.innerHTML = `<div class="side-video-fit"><video class="side-video" src="${escHtml(url)}" controls preload="metadata" playsinline></video></div>`;
    } else if (kind === 'audio') {
      body.innerHTML = `<audio class="side-audio" src="${escHtml(url)}" controls preload="metadata"></audio>`;
    } else if (card.dataset.preview === '1') {
      body.innerHTML = `<iframe class="side-frame" src="${escHtml(previewUrl(rel))}"></iframe>`;
    } else if (kind === 'text') {
      body.innerHTML = '<pre class="side-text">Đang đọc...</pre>';
      fetch(url, { headers: { Range: 'bytes=0-199999' } }).then(r => r.text()).then(txt => {
        if (state.listPreview !== rel) return;
        const pre = body.querySelector('pre');
        if (pre) pre.textContent = txt;
      }).catch(e => { body.textContent = 'Không đọc được preview: ' + e.message; });
    }
  }

  function stepSidePreview(delta) {
    const cards = $$('.card[data-rel]').filter(listCanPreview);
    if (!cards.length) return;
    let i = cards.findIndex(c => c.dataset.rel === state.listPreview);
    i = i < 0 ? 0 : (i + delta + cards.length) % cards.length;
    renderListPreview(cards[i]);
  }

  function openItem(card, ev) {
    const rel = card?.dataset?.rel;
    if (!rel) return;
    if (state.suppressClick) { if (ev) { ev.preventDefault(); ev.stopPropagation(); } return; }
    if (ev && (ev.ctrlKey || ev.metaKey || ev.shiftKey)) { toggleSelect(rel, ev); return; }
    closeContextMenu();
    const kind = card.dataset.kind;
    const item = findLoadedItem(rel);
    const name = item?.name || card.dataset.rawname || rel;
    const url = item?.url || fileUrl(rel);
    if (kind === 'folder') {
      void navigateToFolder(rel);
      return;
    }
    if (state.previewPane && listCanPreview(card)) {
      state.selected.clear();
      state.selected.add(rel);
      updateSelectionUI();
      renderListPreview(card);
      return;
    }
    if (isMediaKind(kind)) window.openPreview(kind, url, name, rel);
    else if (card.dataset.preview === '1') location.href = previewUrl(rel);
    else if (kind === 'text') location.href = url + '?edit=1';
    else toast('File này chưa hỗ trợ xem nhanh. Dùng nút Tải để tải xuống.');
  }

  // ---------------- Context Menu ----------------
  let ctxTreeTarget = null;
  function closeContextMenu() { $('#ctxMenu')?.classList.add('hidden'); ctxTreeTarget = null; }

  function openContextMenu(ev, card) {
    ev.preventDefault();
    ev.stopPropagation();
    ctxTreeTarget = null;
    const rel = card?.dataset?.rel || '';
    if (rel && !state.selected.has(rel)) {
      state.selected.clear();
      state.selected.add(rel);
      updateSelectionUI();
    }
    const m = $('#ctxMenu');
    if (!m) return;
    const n = state.selected.size;
    const one = n === 1 ? card : null;
    const isFile = Boolean(one && one.dataset.isdir === '0');
    const show = (act, ok) => m.querySelector(`[data-act="${act}"]`)?.classList.toggle('hidden', !ok);
    show('open', n === 1);
    show('preview', isFile && one.dataset.preview === '1');
    show('edit', isFile && one.dataset.kind === 'text');
    show('rename', n === 1);
    show('download', n >= 1);
    show('copy', n >= 1);
    show('cut', n >= 1);
    show('paste', Boolean(state.clipboard && state.clipboard.paths.length));
    show('move', n >= 1);
    show('duplicate', n >= 1);
    show('batch', n >= 2);
    show('archive', n >= 1);
    show('extract', isArchiveCard(one));
    show('share', n === 1);
    show('properties', n <= 1);
    show('delete', n >= 1);
    m.classList.remove('hidden');
    m.style.left = Math.min(window.innerWidth - m.offsetWidth - 8, ev.clientX) + 'px';
    m.style.top = Math.min(window.innerHeight - m.offsetHeight - 8, ev.clientY) + 'px';
  }

  function openTreeContextMenu(ev, treeRel) {
    ev.preventDefault();
    ev.stopPropagation();
    ctxTreeTarget = treeRel;
    const m = $('#ctxMenu');
    if (!m) return;
    ['preview', 'edit', 'rename', 'download', 'copy', 'cut', 'move', 'duplicate', 'batch', 'archive', 'extract', 'share', 'delete'].forEach(a => m.querySelector(`[data-act="${a}"]`)?.classList.add('hidden'));
    m.querySelector('[data-act="open"]')?.classList.remove('hidden');
    m.querySelector('[data-act="paste"]')?.classList.toggle('hidden', !(state.clipboard && state.clipboard.paths.length));
    m.querySelector('[data-act="properties"]')?.classList.remove('hidden');
    m.classList.remove('hidden');
    m.style.left = Math.min(window.innerWidth - m.offsetWidth - 8, ev.clientX) + 'px';
    m.style.top = Math.min(window.innerHeight - m.offsetHeight - 8, ev.clientY) + 'px';
  }

  function contextAction(act) {
    const treeTarget = ctxTreeTarget;
    closeContextMenu();
    if (treeTarget !== null) {
      if (act === 'open') void navigateToFolder(treeTarget);
      else if (act === 'paste') void pasteClipboard(treeTarget);
      else if (act === 'properties') void openPropertiesModal(treeTarget);
      return;
    }
    const rel = selectedArray()[0];
    const card = rel ? document.querySelector(`.card[data-rel="${CSS.escape(rel)}"]`) : null;
    if (act === 'open' && card) openItem(card);
    else if (act === 'preview' && rel) window.open(previewUrl(rel), '_blank');
    else if (act === 'edit' && rel) location.href = fileUrl(rel) + '?edit=1';
    else if (act === 'rename') void renameOne();
    else if (act === 'download') void downloadSelected();
    else if (act === 'copy') setClipboard('copy');
    else if (act === 'cut') setClipboard('cut');
    else if (act === 'paste') void pasteClipboard();
    else if (act === 'move') void moveSel();
    else if (act === 'duplicate') void duplicateSel();
    else if (act === 'batch') void batchRenameSel();
    else if (act === 'archive') archiveSelected();
    else if (act === 'extract') void extractSelected();
    else if (act === 'share') void shareOne();
    else if (act === 'properties') void openPropertiesModal();
    else if (act === 'delete') void deleteSel();
  }

  // ---------------- Folder Preview Mosaic ----------------
  let folderPreviewIO = null;
  let folderPreviewTimers = [];
  const folderPreviewQueue = [];
  let folderPreviewActive = 0;

  function clearFolderPreviewTimers() { folderPreviewTimers.forEach(t => clearInterval(t)); folderPreviewTimers = []; }
  function renderFolderMosaic(el, items, start = 0) {
    if (!el || !Array.isArray(items) || !items.length) return;
    el.className = 'folder-mosaic ' + (state.previewAnimation || 'fade');
    el.textContent = '';
    for (let i = 0; i < 4; i++) {
      const it = items[(start + i) % items.length];
      const cell = document.createElement('div');
      cell.className = 'cell';
      if (it) {
        const img = document.createElement('img');
        img.loading = 'lazy'; img.decoding = 'async'; img.src = it.thumb || it.url; img.alt = it.name || '';
        cell.appendChild(img);
      }
      el.appendChild(cell);
    }
  }
  async function loadFolderPreview(el) {
    const rel = el.dataset.folderPreview;
    if (!rel || el.dataset.loaded) return;
    el.dataset.loaded = '1';
    try {
      const r = await fetch('/api/folder_preview?p=' + encodeURIComponent(rel), { cache: 'no-store' });
      const j = await r.json();
      if (!r.ok || j.error || !j.items?.length) return;
      renderFolderMosaic(el, j.items, 0);
    } catch (_) {}
  }
  function pumpFolderPreviewQueue() {
    while (folderPreviewActive < 3 && folderPreviewQueue.length) {
      const el = folderPreviewQueue.shift();
      if (!el || !document.body.contains(el) || el.dataset.loaded) continue;
      folderPreviewActive++;
      loadFolderPreview(el).finally(() => { folderPreviewActive--; pumpFolderPreviewQueue(); });
    }
  }
  function setupFolderPreviews() {
    clearFolderPreviewTimers();
    if (folderPreviewIO) folderPreviewIO.disconnect();
    folderPreviewQueue.length = 0;
    folderPreviewActive = 0;
    const els = $$('.folder-mosaic[data-folder-preview]');
    if (!els.length || !state.folderPreview) return;
    folderPreviewIO = new IntersectionObserver(entries => {
      entries.forEach(e => {
        if (e.isIntersecting) {
          folderPreviewQueue.push(e.target);
          folderPreviewIO.unobserve(e.target);
          pumpFolderPreviewQueue();
        }
      });
    }, { root: grid, rootMargin: '300px' });
    els.forEach(el => folderPreviewIO.observe(el));
  }

  // ---------------- System Telemetry ----------------
  async function refreshSysTelemetry() {
    const pill = $('#sysTelemetryPill');
    if (!pill) return;
    try {
      const r = await fetch('/api/sysstats', { cache: 'no-store' });
      const d = await r.json();
      if (!r.ok || !d) return;
      const gpu = d.gpu || d.primaryGpu || null;
      const ram = d.ram || d.memory || null;
      const cpu = d.cpu || null;
      const hasGpu = Boolean(d.hasGpu || (gpu && gpu.available && Number(gpu.vramTotalGb || 0) > 0));
      const barPct = hasGpu
        ? Math.min(100, Math.max(0, Number(gpu.vramPercent || 0)))
        : Math.min(100, Math.max(0, Number(ram?.percent || ram?.ramPercent || 0)));
      const barCls = barPct >= 88 ? 'danger' : (barPct >= 70 ? 'warn' : '');
      const parts = [];
      if (hasGpu) {
        parts.push(`VRAM ${Number(gpu.vramUsedGb || 0).toFixed(1)}/${Number(gpu.vramTotalGb || 0).toFixed(1)}G`);
        parts.push(`GPU ${Math.round(Number(gpu.gpuUtilPercent ?? gpu.utilPercent ?? 0))}%`);
      }
      if (cpu && typeof cpu.loadPercent === 'number') {
        parts.push(`CPU ${Math.round(cpu.loadPercent)}%`);
      }
      if (ram && Number(ram.totalGb || ram.ramTotalGb || 0) > 0) {
        const u = Number(ram.usedGb ?? ram.ramUsedGb ?? 0).toFixed(1);
        const t = Number(ram.totalGb ?? ram.ramTotalGb ?? 0).toFixed(1);
        parts.push(`RAM ${u}/${t}G`);
      }
      const tempVal = d.tempC ?? gpu?.tempC ?? cpu?.tempC;
      if (tempVal !== null && tempVal !== undefined && Number.isFinite(Number(tempVal))) {
        parts.push(`${Math.round(Number(tempVal))}°C`);
      }
      const label = parts.join(' · ') || 'System OK';
      pill.innerHTML = `<span>${hasGpu ? '🎮' : '💻'}</span><span class="sys-vram-bar"><span class="sys-vram-fill ${barCls}" style="width:${barPct}%"></span></span><span>${escHtml(label)}</span>`;
      pill.title = (hasGpu && gpu?.name ? `${gpu.name} · ` : '') + (cpu?.cores ? `${cpu.cores} cores · ` : '') + label;
    } catch (_) {}
  }

  // ---------------- Global Keyboard Shortcuts (Windows File Explorer Parity) ----------------
  function isTypingTarget(el) { return Boolean(el && (['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) || el.isContentEditable)); }

  document.addEventListener('keydown', (e) => {
    if (window.LanternMedia?.handleModalKeydown?.(e)) return;
    if (e.key === 'Escape') {
      closeContextMenu();
      $('#propsModal')?.classList.remove('show');
      if (!isTypingTarget(document.activeElement) && state.selected.size) clearSel();
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'l') { e.preventDefault(); openAddressEditor(); return; }
    if (e.altKey && e.key.toLowerCase() === 'd') { e.preventDefault(); openAddressEditor(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') { e.preventDefault(); q?.focus(); q?.select(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') { e.preventDefault(); window.LanternTree?.togglePane?.(); return; }
    if (e.altKey && e.key === 'ArrowLeft') { e.preventDefault(); navHistoryBack(); return; }
    if (e.altKey && e.key === 'ArrowRight') { e.preventDefault(); navHistoryForward(); return; }
    if (e.altKey && e.key === 'ArrowUp') { e.preventDefault(); navParentFolder(); return; }
    if (e.key === 'F5') { e.preventDefault(); refreshFolder(); return; }

    if (isTypingTarget(document.activeElement)) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') { e.preventDefault(); selectVisible(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'c' && state.selected.size) { e.preventDefault(); setClipboard('copy'); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'x' && state.selected.size) { e.preventDefault(); setClipboard('cut'); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'v' && state.clipboard?.paths?.length) { e.preventDefault(); void pasteClipboard(); return; }
    if (e.key === 'F2' && state.selected.size === 1) { e.preventDefault(); void renameOne(); return; }
    if (e.key === 'Delete' && state.selected.size) { e.preventDefault(); void deleteSel(); return; }
    if (e.key === 'Backspace') { e.preventDefault(); navParentFolder(); return; }
    if (e.altKey && e.key === 'Enter') { e.preventDefault(); void openPropertiesModal(); return; }
    if (e.key === 'Enter' && state.selected.size === 1) {
      const c = document.querySelector(`.card[data-rel="${CSS.escape(selectedArray()[0])}"]`);
      if (c) { e.preventDefault(); openItem(c); }
      return;
    }
    if (e.key === ' ' && state.selected.size === 1) {
      const c = document.querySelector(`.card[data-rel="${CSS.escape(selectedArray()[0])}"]`);
      if (c && c.dataset.isdir === '0') { e.preventDefault(); openItem(c); }
    }
  });

  document.addEventListener('click', (e) => { if (!e.target.closest?.('#ctxMenu')) closeContextMenu(); });

  // Grid OS file drop (never blocks when already uploading!)
  if (grid) {
    grid.addEventListener('dragover', (e) => {
      if (!Array.from(e.dataTransfer?.types || []).includes('Files')) return;
      e.preventDefault();
      grid.classList.add('drag');
    });
    grid.addEventListener('dragleave', (e) => {
      if (e.target === grid) grid.classList.remove('drag');
    });
    grid.addEventListener('drop', async (e) => {
      grid.classList.remove('drag');
      if (e.dataTransfer?.getData('application/x-lantern-paths')) return;
      if (e.dataTransfer?.files?.length || e.dataTransfer?.items?.length) {
        e.preventDefault();
        e.stopPropagation();
        await window.LanternUpload?.handleDropToTarget?.(e, currentPath());
      }
    });
  }

  q?.addEventListener('input', () => {
    const kw = (q.value || '').trim().toLowerCase();
    if (state.recursiveDepth === '0' && !state.hasMore && grid) {
      $$('.card[data-rel]').forEach(c => {
        const nm = (c.dataset.rawname || c.dataset.rel || '').toLowerCase();
        c.classList.toggle('hidden', Boolean(kw && !nm.includes(kw)));
      });
    }
    clearTimeout(state.searchTimer);
    state.searchTimer = setTimeout(() => { clearFolderCache(); void loadMore(true); }, Number(defaults.search_debounce_ms || 180));
  });

  // Expose globals for inline handlers & Lanbot / Terminal integrations
  window.LanternChatContext = { kind: 'files', path: '', folder: () => currentPath(), selected: () => selectedArray() };
  window.currentPath = currentPath;
  window.selectedArray = selectedArray;
  window.toast = toast;
  window.clearFolderCache = clearFolderCache;
  window.loadMore = loadMore;
  window.softRefresh = softRefresh;
  window.refreshFolder = refreshFolder;
  window.navigateToFolder = navigateToFolder;
  window.navigateCrumb = navigateCrumb;
  window.navHistoryBack = navHistoryBack;
  window.navHistoryForward = navHistoryForward;
  window.navParentFolder = navParentFolder;
  window.goParentFolder = goParentFolder;
  window.setView = setView;
  window.togglePreviewPane = togglePreviewPane;
  window.changeSort = sel => sortCards(sel.value);
  window.sortByHeader = sortByHeader;
  window.changeLimit = sel => { state.limit = Number(sel.value || 220); savePrefs({ page_limit: state.limit }); clearFolderCache(); void loadMore(true); };
  window.changeFoldersFirst = el => { state.foldersFirst = Boolean(el.checked); savePrefs({ folders_first: state.foldersFirst }); clearFolderCache(); void loadMore(true); };
  window.changeRecursiveDepth = sel => { state.recursiveDepth = String(sel.value || '0'); localStorage.setItem(prefKey('recursive_depth'), state.recursiveDepth); clearFolderCache(); void loadMore(true); };
  window.changeThumbFit = sel => { state.thumbFit = sel.value === 'cover' ? 'cover' : 'contain'; savePrefs({ thumb_fit: state.thumbFit, folder_preview_fit: state.thumbFit }); applyView(); };
  window.toggleFolderPreview = el => { state.folderPreview = Boolean(el.checked); savePrefs({ folder_preview_enabled: state.folderPreview }); refreshFolder(); };
  window.changePreviewAnimation = sel => { state.previewAnimation = sel.value || 'fade'; savePrefs({ folder_preview_animation: state.previewAnimation }); setupFolderPreviews(); };
  window.changeUploadConflict = sel => { state.uploadConflict = sel.value || 'ask'; savePrefs({ upload_conflict: state.uploadConflict }); };
  window.selectVisible = selectVisible;
  window.clearSel = clearSel;
  window.toggleSelect = toggleSelect;
  window.openItem = openItem;
  window.openContextMenu = openContextMenu;
  window.openTreeContextMenu = openTreeContextMenu;
  window.contextAction = contextAction;
  window.stepSidePreview = stepSidePreview;
  window.transferPathsToFolder = transferPathsToFolder;
  window.pasteClipboard = pasteClipboard;
  window.mkdir = mkdir;
  window.newFile = newFile;
  window.renameOne = renameOne;
  window.copySel = copySel;
  window.moveSel = moveSel;
  window.duplicateSel = duplicateSel;
  window.batchRenameSel = batchRenameSel;
  window.extractSelected = extractSelected;
  window.archiveSelected = archiveSelected;
  window.downloadSelected = downloadSelected;
  window.deleteSel = deleteSel;
  window.shareOne = shareOne;
  window.previewSelected = () => { const rel = selectedArray()[0]; if (rel) window.open(previewUrl(rel), '_blank'); };
  window.addPreviewExtension = async () => {
    const raw = prompt('Thêm đuôi/pattern đọc nhanh, ví dụ .env.local hoặc *.secret:');
    if (!raw) return;
    try { const j = await api('/api/plugin/extensions', { add: raw }); state.pluginEnabled = true; toast('Đã thêm: ' + (j.custom_patterns || []).join(', ')); clearFolderCache(); void loadMore(true); }
    catch (e) { toast('Lỗi plugin: ' + e.message); }
  };
  window.openPropertiesModal = openPropertiesModal;
  window.refreshSysTelemetry = refreshSysTelemetry;

  // Boot
  if (grid) {
    syncControls();
    applyView();
    initAddressBar();
    updateNavButtons();
    window.LanternUpload?.init?.();
    window.LanternTree?.init?.();
    void loadMore(true);
    void refreshSysTelemetry();
    setInterval(() => { if (!document.hidden) void refreshSysTelemetry(); }, 15000);
  }
})();
