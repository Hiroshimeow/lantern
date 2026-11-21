/* Lantern v9.25 — Windows-Grade File Explorer & Gallery Core */
(() => {
  'use strict';

  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const defaults = window.APP?.defaults || {};
  const t = (k, fb = '') => window.LanternI18n?.t?.(k, fb) || fb || k;
  const isMobileViewport = () => Number(window.innerWidth || 1200) <= 900;

  function prefKey(k) { return 'lanDrive:' + k; }
  function pref(k, fallback) { const v = localStorage.getItem(prefKey(k)); return v === null ? fallback : v; }

  const state = {
    view: pref('view', defaults.default_view || 'grid'),
    sort: pref('sort', defaults.default_sort || 'name-asc'),
    limit: Number(pref('page_limit', pref('limit', String(defaults.page_limit || 220)))),
    foldersFirst: pref('folders_first', String(defaults.folders_first ?? true)) !== 'false',
    recursiveDepth: pref('recursive_depth', '0'),
    thumbFit: pref('thumb_fit', 'contain'),
    folderPreview: pref('folder_preview', String(defaults.folder_preview_enabled ?? true)) !== 'false',
    previewAnimation: pref('preview_animation', defaults.folder_preview_animation || 'fade'),
    previewPane: !isMobileViewport() && pref('preview_pane_enabled', 'false') === 'true',
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
    appMode: pref('app_mode', 'explorer'),
    mediaFilter: 'all',
    showHidden: Boolean(window.LanternTabState?.getShowHidden?.()),
    lang: pref('lang', 'en'),
    lastError: null,
  };
  window.LanternAppState = state;
  window.state = state;

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

  function pathHref(path) {
    const clean = String(path || '').replace(/^\/+|\/+$/g, '');
    return clean ? '/' + enc(clean) + '/' : '/';
  }
  function scrollKey(path = currentPath()) { return 'lanDrive:scroll:' + pathHref(path); }
  function cachePrefixForPath(path) { return 'lanDrive:list:' + pathHref(path) + ':'; }
  function cachePrefix() { return cachePrefixForPath(currentPath()); }
  function cacheKeyForPath(path, queryOverride = null) {
    const mf = activeMediaFilterParam();
    const query = queryOverride === null ? (q?.value || '') : String(queryOverride);
    return cachePrefixForPath(path) + state.sort + ':' + state.limit + ':' + state.recursiveDepth + ':' + String(state.foldersFirst) + ':' + query + (mf ? ':' + mf : '');
  }
  function cacheKey() { return cacheKeyForPath(currentPath()); }
  function readListCacheForPath(path, queryOverride = null) {
    try {
      const raw = sessionStorage.getItem(cacheKeyForPath(path, queryOverride));
      const cached = raw ? JSON.parse(raw) : null;
      return cached && Array.isArray(cached.items) ? cached : null;
    } catch (_) {
      return null;
    }
  }
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
      if (patch.page_limit !== undefined) { localStorage.setItem(prefKey('limit'), String(patch.page_limit)); localStorage.setItem(prefKey('page_limit'), String(patch.page_limit)); }
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
      html.push(`<a class="crumb-back" data-action="back" data-rel="${escHtml(parentRel)}" href="${parentHref}">↩ Back</a>`);
    }
    html.push(`<a data-rel="" href="/">Root</a>`);
    const acc = [];
    for (const part of parts) {
      acc.push(part);
      const cur = acc.join('/');
      const href = '/' + enc(cur) + '/';
      html.push(`<span class="crumb-sep">/</span><a data-rel="${escHtml(cur)}" href="${href}">${escHtml(part)}</a>`);
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

  let navGen = 0;
  let navAbortCtrl = null;

  function syncUrlToCurrentPath() {
    const cur = currentPath();
    const curHref = cur ? '/' + enc(cur) + '/' : '/';
    if (location.pathname !== curHref) {
      try { history.replaceState({ lanternPath: cur, lanternNavIndex: state.navIndex }, document.title, curHref); } catch (_) {}
    }
  }

  async function navigateToFolder(relPath, opts = {}) {
    const clean = String(relPath || '').replace(/^\/+|\/+$/g, '');
    const href = clean ? '/' + enc(clean) + '/' : '/';
    // Persist the outgoing entry before changing path. This is required for
    // both native and in-app Back/Forward so a deep scroll position survives
    // the round trip; the target cache is read independently below.
    try { sessionStorage.setItem(scrollKey(), String(window.scrollY)); } catch (_) {}
    saveListCache({ preserveDeep: true });
    const historyCache = (opts.fromPopstate || typeof opts.commitNavIndex === 'number')
      ? readListCacheForPath(clean, '')
      : null;
    const searchVal = opts.keepSearch ? (q?.value || '') : '';
    const myNavGen = ++navGen;
    if (navAbortCtrl) { try { navAbortCtrl.abort(); } catch (_) {} }
    const ctrl = new AbortController();
    navAbortCtrl = ctrl;

    const params = new URLSearchParams({
      path: clean,
      offset: '0',
      limit: String(state.limit),
      sort: state.sort,
      q: searchVal,
      recursive_depth: searchVal.trim() ? state.recursiveDepth : '0',
      folders_first: String(state.foldersFirst),
      show_hidden: state.showHidden ? '1' : '0',
      show_system: state.showHidden ? '1' : '0',
    });
    const mf = activeMediaFilterParam();
    if (mf) params.set('media_filter', mf);

    let data;
    try {
      const r = await fetch('/api/list?' + params.toString(), { cache: 'no-store', signal: ctrl.signal });
      data = await r.json().catch(() => ({}));
      if (myNavGen !== navGen) return false;
      if (!r.ok || data.error) {
        if (opts.fromPopstate) syncUrlToCurrentPath();
        toast(t('error') + ': ' + (data.error || `HTTP ${r.status}`));
        return false;
      }
    } catch (err) {
      if (err && err.name === 'AbortError') return false;
      if (myNavGen !== navGen) return false;
      if (opts.fromPopstate) syncUrlToCurrentPath();
      toast(t('error') + ': ' + String(err?.message || err || 'Network error'));
      return false;
    }

    if (myNavGen !== navGen) return false;

    listRevision++;
    if (window.APP) window.APP.currentPath = clean;
    state.selected.clear();
    state.lastSelectedRel = '';
    if (q && !opts.keepSearch) q.value = '';

    if (typeof opts.commitNavIndex === 'number') {
      state.navIndex = opts.commitNavIndex;
      if (location.pathname !== href) {
        try { history.replaceState({ lanternPath: clean, lanternNavIndex: state.navIndex }, document.title, href); } catch (_) {}
      }
    } else if (!opts.skipHistory) {
      const prev = state.navHistory[state.navIndex];
      if (prev !== clean) {
        state.navHistory = state.navHistory.slice(0, state.navIndex + 1);
        state.navHistory.push(clean);
        state.navIndex = state.navHistory.length - 1;
      }
      if (location.pathname !== href) {
        try { history.pushState({ lanternPath: clean, lanternNavIndex: state.navIndex }, document.title, href); } catch (_) {}
      }
    } else if (location.pathname !== href) {
      try { history.replaceState({ lanternPath: clean, lanternNavIndex: state.navIndex }, document.title, href); } catch (_) {}
    }

    renderBreadcrumbs(clean);
    const upTitle = $('#uploadTargetTitle');
    if (upTitle) upTitle.textContent = '⬆️ Upload to: /' + clean;
    if (window.LanternTree?.syncToPath) void window.LanternTree.syncToPath(clean, false);

    const incoming = Array.isArray(data.items) ? data.items : [];
    const seen = new Set();
    state.items = incoming.filter(x => {
      if (x.special) return true;
      const k = x.rel || x.name;
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    });
    state.offset = Number(data.nextOffset || 0);
    state.hasMore = Boolean(data.hasMore);
    state.total = Number(data.total || 0);
    state.lastError = null;
    listDataKey = listContextKey();
    lastListFetchAt = Date.now();

    // Back/Forward must restore the loaded window before revalidation. A
    // first-page response alone silently drops deep-page context (and makes
    // native Back return 100 rows instead of the previously loaded 500).
    if (historyCache && Number(historyCache.offset || 0) > state.offset) {
      state.items = historyCache.items;
      state.offset = Number(historyCache.offset || state.offset);
      state.hasMore = Boolean(historyCache.hasMore);
      state.total = Number(historyCache.total || state.offset);
      listDataKey = listContextKey();
      render({ settled: true });
      if (historyCache.gridScrollTop && grid) grid.scrollTop = Number(historyCache.gridScrollTop);
      const cachedScroll = historyCache.scrollY ?? Number(sessionStorage.getItem(scrollKey(clean)) || 0);
      if (cachedScroll) window.scrollTo(0, cachedScroll);
      await softRefresh();
      if (myNavGen !== navGen || currentPath() !== clean) return false;
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      if (myNavGen !== navGen || currentPath() !== clean) return false;
      if (historyCache.gridScrollTop && grid) grid.scrollTop = Number(historyCache.gridScrollTop);
      if (cachedScroll) window.scrollTo(0, cachedScroll);
      return true;
    }
    render({ settled: true });
    saveListCache({ preserveDeep: true });
    if (typeof window.scrollTo === 'function') window.scrollTo(0, 0);
    if (!getVisibleItems().length && state.hasMore) {
      await loadMore(false);
    }
    return true;
  }

  function navigateCrumb(ev, rel) {
    if (ev && (ev.ctrlKey || ev.metaKey || ev.button === 1)) return true;
    if (ev) { ev.preventDefault(); ev.stopPropagation(); }
    void navigateToFolder(rel);
    return false;
  }

  function navHistoryBack() {
    if (state.navIndex <= 0) return;
    const targetIdx = state.navIndex - 1;
    const target = state.navHistory[targetIdx];
    void navigateToFolder(target, { skipHistory: true, commitNavIndex: targetIdx });
  }

  function navHistoryForward() {
    if (state.navIndex >= state.navHistory.length - 1) return;
    const targetIdx = state.navIndex + 1;
    const target = state.navHistory[targetIdx];
    void navigateToFolder(target, { skipHistory: true, commitNavIndex: targetIdx });
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
    const statedIdx = Number(ev.state?.lanternNavIndex);
    const targetIdx = Number.isInteger(statedIdx) && state.navHistory[statedIdx] === p
      ? statedIdx
      : state.navHistory.indexOf(p);
    void navigateToFolder(p, {
      skipHistory: true,
      fromPopstate: true,
      ...(targetIdx >= 0 ? { commitNavIndex: targetIdx } : {}),
    });
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
    $$('.view-toggle button').forEach(b => { const on = b.dataset.view === v; b.classList.toggle('active', on); b.setAttribute('aria-pressed', on ? 'true' : 'false'); });
    const pb = $('#previewPaneBtn');
    if (pb) {
      pb.classList.toggle('active', Boolean(state.previewPane));
      pb.setAttribute('aria-pressed', state.previewPane ? 'true' : 'false');
      pb.textContent = state.previewPane ? `👁 ${t('preview')} ✓` : `👁 ${t('preview')}`;
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
    const os = $('#optSortSelect'); if (os) os.value = state.sort;
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
    if (stItems) stItems.textContent = `${realItems.length}${state.hasMore ? '+' : ''} ${t('items')}${state.total > realItems.length ? ` (${state.total} total)` : ''}`;

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
        stSel.textContent = `${n} selected${sz}`;
        stSel.classList.remove('hidden');
      } else {
        stSel.classList.add('hidden');
      }
    }

    const stClip = $('#statusClip');
    if (stClip) {
      if (state.clipboard && state.clipboard.paths.length) {
        const verb = state.clipboard.mode === 'cut' ? 'Cut' : 'Copied';
        stClip.textContent = `📋 ${state.clipboard.paths.length} ${verb} — Ctrl+V`;
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
      const isSel = state.selected.has(rel);
      c.classList.toggle('selected', isSel);
      c.classList.toggle('is-cut', cutSet.has(rel));
      const chk = c.querySelector('.check');
      if (chk) chk.setAttribute('aria-pressed', isSel ? 'true' : 'false');
    });
    const n = state.selected.size;
    const selLabel = n ? `${n} ${t('selected')}` : '';
    const count = $('#selCount');
    if (count) count.textContent = selLabel;
    const mCount = $('#mobileSelCount');
    if (mCount) mCount.textContent = selLabel;
    document.body.classList.toggle('has-selection', n > 0);
    const live = $('#a11yLive');
    if (live && n > 0) live.textContent = selLabel;
    const one = n === 1 ? document.querySelector(`.card[data-rel="${CSS.escape(selectedArray()[0] || '')}"]`) : null;
    const oneFile = Boolean(one && one.dataset.isdir === '0');
    const canPreview = Boolean(oneFile && one.dataset.preview === '1');
    const canExtract = Boolean(one && isArchiveCard(one));

    $('#pasteBtn')?.classList.toggle('hidden', !(state.clipboard && state.clipboard.paths.length));
    $('#selectionBar')?.classList.toggle('hidden', n === 0);
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
      return `<article class="card special-back" data-name=".."><div class="card-main" onclick="navParentFolder()"><div class="thumbwrap"><span class="fileicon">↩️</span></div><div class="meta"><div class="name">.. (Parent folder)</div><div class="sub">Up</div></div><div class="detail-col col-mtime"></div><div class="detail-col col-type">Folder</div><div class="detail-col col-size"></div></div></article>`;
    }
    const rel = it.rel || '';
    const isDir = it.is_dir ? '1' : '0';
    const kind = it.kind || 'other';
    const ext = it.ext || (!it.is_dir && it.name && it.name.includes('.') ? '.' + it.name.split('.').pop().toLowerCase() : '');
    const sizeText = it.sizeText || it.size_text || '';
    const mtimeText = it.mtimeText || it.mtime_text || '';
    const canPreview = Boolean(it.preview || it.can_preview);
    const badge = it.is_dir ? 'DIR' : (ext ? ext.replace('.', '').toUpperCase() : kind.toUpperCase());
    let thumbHtml = `<span class="fileicon" aria-hidden="true">${escHtml(it.icon || (it.is_dir ? '📁' : '📄'))}</span>`;
    if (it.is_dir && state.folderPreview) {
      thumbHtml = `<div class="folder-mosaic" data-folder-preview="${escHtml(rel)}"><span class="fileicon" aria-hidden="true">📁</span></div>`;
    } else if (it.thumb) {
      const fallbackUrl = it.kind === 'image' ? escHtml(it.url || fileUrl(rel)) : '';
      thumbHtml = `<img class="thumb" loading="lazy" decoding="async" src="${escHtml(it.thumb)}" data-fallback="${fallbackUrl}" alt="${escHtml(it.name)}" onerror="if(this.dataset.fallback&&this.src.indexOf(this.dataset.fallback)<0){this.src=this.dataset.fallback;this.dataset.fallback='';}else{this.replaceWith(Object.assign(document.createElement('span'),{className:'fileicon',textContent:'${it.kind === 'video' ? '🎬' : '🖼️'}'}));}">`;
    }
    const subText = it.is_dir ? (mtimeText || 'Folder') : [sizeText, mtimeText].filter(Boolean).join(' · ');
    return `<article class="card" draggable="true" data-rel="${escHtml(rel)}" data-isdir="${isDir}" data-kind="${escHtml(kind)}" data-rawname="${escHtml(it.name)}" data-preview="${canPreview ? '1' : '0'}"><button type="button" class="check" aria-pressed="false" aria-label="Select ${escHtml(it.name)}"></button><div class="card-main"><div class="thumbwrap">${thumbHtml}<span class="badge">${escHtml(badge)}</span></div><div class="meta"><div class="name" title="${escHtml(it.name)}">${escHtml(it.name)}</div><div class="sub">${escHtml(subText)}</div></div><div class="detail-col col-mtime">${escHtml(mtimeText)}</div><div class="detail-col col-type">${escHtml(it.is_dir ? 'Folder' : (ext || kind))}</div><div class="detail-col col-size">${escHtml(it.is_dir ? '' : sizeText)}</div></div></article>`;
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
    }, { rootMargin: '900px' });
    loaderIO.observe(ld);
  }

  function ensureLoader() {
    const old = $('#loader');
    if (old) old.remove();
    if (state.hasMore) grid.insertAdjacentHTML('beforeend', '<div id="loader" class="loader">Loading more...</div>');
    observeLoader();
  }

  function render(opts = {}) {
    if (!grid) return;
    const visibleList = getVisibleItems();
    if (state.lastError && !visibleList.length) {
      grid.innerHTML = `<div class="error-state" role="alert"><div style="font-size:34px">⚠️</div><b>${escHtml(t('loadError'))}</b><div class="sub">${escHtml(state.lastError)}</div><button type="button" class="btn small primary" onclick="loadMore(true)">↻ ${escHtml(t('retry'))}</button></div>`;
      updateSelectionUI();
      return;
    }
    if (!visibleList.length) {
      if (!opts.settled && (state.loading || state.hasMore)) {
        grid.innerHTML = `<div class="loader" role="status">${escHtml(t('loading'))}</div>`;
        updateSelectionUI();
        return;
      }
      if (state.appMode === 'gallery') {
        grid.innerHTML = `<div class="empty"><div><div style="font-size:38px;margin-bottom:8px">🖼️</div><b>${escHtml(t('noMatchingMedia'))}</b><div style="margin-top:10px;display:flex;gap:8px;justify-content:center;flex-wrap:wrap"><button type="button" class="btn small" onclick="setMediaFilter('all')">${escHtml(t('clearFilter'))}</button><button type="button" class="btn small primary" onclick="setAppMode('explorer')">${escHtml(t('switchExplorer'))}</button></div></div></div>`;
      } else {
        grid.innerHTML = `<div class="empty"><div><div style="font-size:38px;margin-bottom:8px">📂</div><b>${escHtml(t('emptyFolder'))}</b><div class="sub" style="margin-top:4px">${escHtml(t('emptyDropHint'))}</div></div></div>`;
      }
      ensureLoader();
      updateSelectionUI();
      return;
    }
    grid.innerHTML = listHeaderHTML() + visibleList.map(cardHTML).join('');
    ensureLoader();
    applyView();
    updateSelectionUI();
    setupFolderPreviews();
    wireGridCardDropTargets();
  }

  function appendRender(newItems) {
    if (!grid) return;
    const old = $('#loader');
    if (old) old.remove();
    const filtered = (newItems || []).filter(isItemVisible);
    if (!grid.querySelector('.list-head')) grid.innerHTML = listHeaderHTML();
    if (filtered.length) grid.insertAdjacentHTML('beforeend', filtered.map(cardHTML).join(''));
    ensureLoader();
    applyView();
    updateSelectionUI();
    setupFolderPreviews();
    wireGridCardDropTargets();
  }

  let listWork = null;
  let pendingListUpdate = null;
  let listRevision = 0;
  let listDataKey = null;
  let listRetryRequired = false;
  let appendRepairUsed = false;
  let lastListFetchAt = 0;
  const MAX_AUTO_MEDIA_PAGES = 25;

  function activeMediaFilterParam() {
    if (state.appMode !== 'gallery') return '';
    if (state.mediaFilter === 'image') return 'image';
    if (state.mediaFilter === 'video') return 'video';
    return 'media';
  }

  function listQuery() {
    const query = {
      path: currentPath(),
      sort: state.sort,
      q: q?.value || '',
      recursive_depth: (q?.value || '').trim() ? state.recursiveDepth : '0',
      folders_first: String(state.foldersFirst),
      show_hidden: state.showHidden ? '1' : '0',
      show_system: state.showHidden ? '1' : '0',
    };
    const mf = activeMediaFilterParam();
    if (mf) query.media_filter = mf;
    return query;
  }

  function listContextKey() {
    return JSON.stringify([listQuery(), state.limit]);
  }

  function saveListCache({ preserveDeep = false } = {}) {
    try {
      if (listDataKey !== listContextKey()) return;
      if (preserveDeep) {
        const existingRaw = sessionStorage.getItem(cacheKey());
        if (existingRaw) {
          const existing = JSON.parse(existingRaw);
          // A normal navigation fetch starts at page one. Keep a deeper cached
          // window until it is explicitly revalidated, otherwise a repeated
          // history entry loses the scrollable rows it must restore.
          if (Number(existing?.offset || 0) > Number(state.offset || 0)) return;
        }
      }
      sessionStorage.setItem(cacheKey(), JSON.stringify({
        items: state.items,
        offset: state.offset,
        hasMore: state.hasMore,
        total: state.total,
        scrollY: window.scrollY,
        gridScrollTop: grid ? grid.scrollTop : 0,
        ts: Date.now(),
      }));
    } catch (_) {}
  }

  function hydrateCache() {
    try {
      const raw = sessionStorage.getItem(cacheKey());
      if (!raw) return false;
      const c = JSON.parse(raw);
      if (!Array.isArray(c.items)) return false;
      state.items = c.items;
      state.offset = c.offset ?? c.items.filter(it => !it.special).length;
      state.hasMore = Boolean(c.hasMore);
      state.total = Number(c.total || state.offset);
      listDataKey = listContextKey();
      render({ settled: true });
      requestAnimationFrame(() => {
        if (grid && c.gridScrollTop) grid.scrollTop = Number(c.gridScrollTop);
        const wy = c.scrollY ?? Number(sessionStorage.getItem(scrollKey()) || 0);
        if (wy) window.scrollTo(0, wy);
      });
      return true;
    } catch (_) {
      return false;
    }
  }

  function captureListViewport() {
    const visible = [];
    if (grid) {
      for (const card of grid.querySelectorAll('.card[data-rel]')) {
        const rect = card.getBoundingClientRect();
        if (card.dataset.rel && rect.bottom > 0 && rect.top < window.innerHeight) {
          visible.push({ rel: card.dataset.rel, top: rect.top });
        }
      }
    }
    return { y: window.scrollY, gridY: grid ? grid.scrollTop : 0, visible };
  }

  function restoreListViewport(viewport) {
    if (!viewport || !grid) return;
    const gridScrolls = grid.scrollHeight > grid.clientHeight + 2;
    for (const anchor of viewport.visible) {
      const card = grid.querySelector(`.card[data-rel="${CSS.escape(anchor.rel)}"]`);
      if (card) {
        const delta = card.getBoundingClientRect().top - anchor.top;
        if (gridScrolls) grid.scrollTop += delta;
        else window.scrollBy(0, delta);
        return;
      }
    }
    if (gridScrolls) grid.scrollTop = viewport.gridY;
    else window.scrollTo(0, viewport.y);
  }

  function canLazyRefresh() {
    return !document.hidden
      && Boolean(grid)
      && !state.loading
      && !state.selected.size
      && !state.listPreview
      && !$('#modal')?.classList.contains('show')
      && !$('#uploadModal')?.classList.contains('show')
      && !$('#termDrawer')?.classList.contains('show');
  }

  function refreshWhenActive(minAgeMs = 5000) {
    if (canLazyRefresh() && Date.now() - lastListFetchAt >= minAgeMs) {
      void softRefresh();
    }
  }

  window.addEventListener('pagehide', () => {
    if (grid) {
      try { sessionStorage.setItem(scrollKey(), String(window.scrollY)); } catch (_) {}
      saveListCache();
    }
  });
  window.addEventListener('pageshow', (e) => {
    if (grid && e.persisted) setTimeout(() => void softRefresh(), 0);
  });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) refreshWhenActive();
  });
  window.addEventListener('focus', () => refreshWhenActive());
  setInterval(() => refreshWhenActive(30000), 30000);

  async function performListUpdate(kind, revision, autoDepth = 0) {
    const query = listQuery();
    const key = listContextKey();
    const isCurrent = () => revision === listRevision && key === listContextKey();
    const reset = kind === 'reset' || listDataKey !== key;
    const append = kind === 'append' && !reset;
    const target = append ? 0 : Math.max(state.limit, reset ? 0 : state.offset);
    let offset = append ? state.offset : 0;
    let next = append ? state.items.slice() : [];
    let more = true;
    let total = null;
    const appended = [];

    if (reset && autoDepth === 0) {
      state.lastError = null;
      grid.innerHTML = `<div class="loader" role="status">${escHtml(t('loading'))}</div>`;
    }

    try {
      do {
        const limit = append ? state.limit : Math.min(1000, Math.max(20, target - offset));
        const params = new URLSearchParams({ ...query, offset: String(offset), limit: String(limit) });
        const r = await fetch('/api/list?' + params.toString(), { cache: 'no-store' });
        const j = await r.json().catch(() => ({}));
        if (!isCurrent()) return;
        if (!r.ok || j.error) throw new Error(j.error || `HTTP ${r.status}`);
        if (!Array.isArray(j.items)) throw new Error('Invalid listing response');
        const cursor = Number(j.nextOffset);
        if (!Number.isSafeInteger(cursor) || cursor < offset || (j.hasMore && cursor === offset)) {
          throw new Error('Invalid listing cursor');
        }
        if (total !== null && j.total !== total) {
          throw new Error('Directory changed during refresh; refresh again');
        }
        total = Number(j.total ?? cursor);
        next.push(...j.items);
        appended.push(...j.items);
        offset = cursor;
        more = Boolean(j.hasMore);
      } while (!append && more && offset < target);

      if (!isCurrent()) return;
      const real = next.filter(it => !it.special);
      const paths = new Set(real.map(it => it.rel));
      if (paths.size !== real.length) {
        if (append && !appendRepairUsed) {
          appendRepairUsed = true;
          pendingListUpdate = 'refresh';
          return;
        }
        throw new Error('Directory changed during refresh; refresh again');
      }

      const wasBlocked = listRetryRequired;
      listRetryRequired = false;
      if (append) appendRepairUsed = false;
      state.lastError = null;

      const changed = JSON.stringify(state.items) !== JSON.stringify(next);
      const paginationChanged = state.hasMore !== more;
      const viewport = !reset && !append && changed ? captureListViewport() : null;
      const selected = reset ? [] : selectedArray();
      const previewBefore = state.listPreview && state.items.find(it => it.rel === state.listPreview);

      state.items = next;
      state.offset = offset;
      state.hasMore = more;
      state.total = total ?? offset;
      listDataKey = key;
      state.selected = new Set(selected.filter(rel => paths.has(rel)));
      reconcileSelectionToVisible(false);

      if (state.listPreview && !paths.has(state.listPreview)) clearSidePreview();

      if (changed || reset) {
        if (append) appendRender(appended);
        else render({ settled: true });
      } else if (paginationChanged || wasBlocked) {
        ensureLoader();
      }

      const previewAfter = state.listPreview && next.find(it => it.rel === state.listPreview);
      if (previewAfter && previewBefore?.url !== previewAfter.url && state.previewPane) {
        const card = [...grid.querySelectorAll('.card[data-rel]')].find(el => el.dataset.rel === state.listPreview);
        if (card) renderListPreview(card);
      }

      if (viewport) restoreListViewport(viewport);
      if (reset) {
        if (grid) grid.scrollTop = 0;
        window.scrollTo(0, 0);
      }
      lastListFetchAt = Date.now();
      saveListCache();

      if (!getVisibleItems().length && state.hasMore && autoDepth < MAX_AUTO_MEDIA_PAGES) {
        await performListUpdate('append', revision, autoDepth + 1);
      }
    } catch (e) {
      if (isCurrent()) {
        listRetryRequired = true;
        if (loaderIO) loaderIO.disconnect();
        state.lastError = String(e?.message || e || 'Network error');
        const loader = $('#loader');
        if (loader) {
          loader.innerHTML = `<button type="button" class="btn small" onclick="refreshFolder()">↻ ${escHtml(t('retry'))}</button>`;
        } else if (reset || !getVisibleItems().length) {
          render();
        }
        toast(t('error') + ': ' + state.lastError);
      }
    }
  }

  function requestListUpdate(kind) {
    if (!grid) return Promise.resolve();
    if (kind === 'append') {
      if (listWork || !state.hasMore || listRetryRequired) return listWork || Promise.resolve();
    } else {
      listRevision++;
      appendRepairUsed = false;
    }
    if (kind === 'reset' || pendingListUpdate !== 'reset') pendingListUpdate = kind;
    if (listWork) return listWork;
    state.loading = true;
    updateSelectionUI();
    listWork = (async () => {
      try {
        while (pendingListUpdate) {
          const action = pendingListUpdate;
          pendingListUpdate = null;
          await performListUpdate(action, listRevision);
        }
      } finally {
        state.loading = false;
        listWork = null;
        updateSelectionUI();
        if (!listRetryRequired) observeLoader();
      }
    })();
    return listWork;
  }

  function loadMore(reset = false) { return requestListUpdate(reset ? 'reset' : 'append'); }
  function softRefresh() { return requestListUpdate('refresh'); }
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
            toast(t('dragError') + ': ' + err.message);
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
        toast(`✓ ${t('copy')}: ${r.copied?.length || filtered.length} → /${cleanDest}`);
      } else {
        const r = await api('/api/move', { paths: filtered, dest: cleanDest, conflict: 'rename' });
        toast(`✓ ${t('move')}: ${r.moved?.length || filtered.length} → /${cleanDest}`);
        if (state.clipboard?.mode === 'cut') state.clipboard = null;
      }
      clearFolderCache();
      state.selected.clear();
      await softRefresh();
      if (window.LanternTree?.refresh) void window.LanternTree.refresh();
    } catch (err) {
      toast(`${t('error')} (${mode}): ` + err.message);
    }
  }

  // ---------------- Windows Clipboard (Ctrl+C / Ctrl+X / Ctrl+V) ----------------
  function setClipboard(mode, paths = null) {
    const arr = paths || selectedArray();
    if (!arr.length) return;
    state.clipboard = { mode, paths: [...arr] };
    updateSelectionUI();
    toast(mode === 'cut' ? `✂️ ${t('cutToast')} (${arr.length})` : `📋 ${t('copiedToast')} (${arr.length})`);
  }

  async function pasteClipboard(targetRel = null) {
    if (!state.clipboard || !state.clipboard.paths.length) return;
    const dest = targetRel == null ? currentPath() : targetRel;
    await transferPathsToFolder(state.clipboard.paths, dest, state.clipboard.mode === 'cut' ? 'move' : 'copy');
  }

  // ---------------- File Operations & Properties ----------------
  async function mkdir(parentRel = null) {
    const name = prompt(t('promptNewFolder'));
    if (!name) return;
    const base = parentRel == null ? currentPath() : parentRel;
    try {
      await api('/api/mkdir', { path: base, name });
      clearFolderCache();
      await softRefresh();
      if (window.LanternTree?.refresh) void window.LanternTree.refresh(base);
    } catch (e) { toast(t('error') + ': ' + e.message); }
  }

  async function newFile() {
    const name = prompt(t('promptNewFile'));
    if (!name) return;
    try { const r = await api('/api/newfile', { path: currentPath(), name }); location.href = r.edit_url; }
    catch (e) { toast(t('error') + ': ' + e.message); }
  }

  async function renameOne() {
    const rel = selectedArray()[0];
    if (!rel) return;
    const old = rel.split('/').pop();
    const name = prompt(t('promptRename'), old);
    if (!name || name === old) return;
    try {
      await api('/api/rename', { path: rel, name });
      clearFolderCache();
      state.selected.clear();
      await softRefresh();
      if (window.LanternTree?.refresh) void window.LanternTree.refresh(currentPath());
    } catch (e) { toast(t('error') + ': ' + e.message); }
  }

  async function copySel() { setClipboard('copy'); }
  async function moveSel() {
    const arr = selectedArray();
    if (!arr.length) return;
    const dest = prompt(t('promptMove'), currentPath());
    if (dest === null) return;
    await transferPathsToFolder(arr, dest, 'move');
  }

  async function duplicateSel() {
    const arr = selectedArray();
    if (!arr.length) return;
    try {
      const r = await api('/api/duplicate', { paths: arr, conflict: 'rename' });
      toast(`✓ ${t('duplicate')}: ${r.duplicated?.length || 0}`);
      clearFolderCache();
      await softRefresh();
    } catch (e) { toast(t('error') + ': ' + e.message); }
  }

  async function batchRenameSel() {
    const arr = selectedArray();
    if (arr.length < 2) { toast('Select at least 2 items for batch rename'); return; }
    const find = prompt(t('promptBatchFind'), '');
    if (find === null || find === '') return;
    const repl = prompt(t('promptBatchRepl'), '');
    if (repl === null) return;
    const items = arr.map(path => {
      const old = path.split('/').pop();
      return { path, name: old.split(find).join(repl) };
    }).filter(x => x.name && x.name !== x.path.split('/').pop());
    if (!items.length) { toast('No filenames changed'); return; }
    try {
      const r = await api('/api/batch_rename', { items });
      toast(`✓ ${t('rename')}: ${r.renamed?.length || 0}`);
      state.selected.clear();
      await softRefresh();
    } catch (e) { toast(t('error') + ': ' + e.message); }
  }

  async function extractSelected() {
    const arr = selectedArray();
    const card = arr.length === 1 ? document.querySelector(`.card[data-rel="${CSS.escape(arr[0])}"]`) : null;
    if (!isArchiveCard(card)) { toast('Only archive files can be extracted'); return; }
    const dest = prompt(t('promptExtract'), currentPath());
    if (dest === null) return;
    try {
      const r = await api('/api/extract', { path: arr[0], dest, conflict: 'rename' });
      toast(`✓ ${t('extract')}: ${r.written || 0}`);
      await softRefresh();
      if (window.LanternTree?.refresh) void window.LanternTree.refresh();
    } catch (e) { toast(t('error') + ': ' + e.message); }
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
    const fmt = (prompt(t('promptArchiveFmt'), 'zip') || '').trim().toLowerCase();
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

  function reconcileSelectionToVisible(updateUi = true) {
    const vis = new Set(getVisibleItems().filter(x => !x.special && x.rel).map(x => x.rel));
    let removed = false;
    for (const rel of Array.from(state.selected)) {
      if (!vis.has(rel)) {
        state.selected.delete(rel);
        removed = true;
      }
    }
    if (state.lastSelectedRel && !vis.has(state.lastSelectedRel)) {
      state.lastSelectedRel = '';
    }
    if (removed && updateUi) updateSelectionUI();
    return removed;
  }

  async function deleteSel() {
    reconcileSelectionToVisible(true);
    const arr = selectedArray();
    if (!arr.length) return;
    const names = arr.map(p => p.split('/').pop() || p);
    const previewList = names.slice(0, 10).map(n => '• ' + n).join('\n');
    const extra = names.length > 10 ? `\n… and ${names.length - 10} more` : '';
    if (!confirm(`${t('confirmDelete')} (${arr.length}):\n\n${previewList}${extra}`)) return;
    try {
      await api('/api/delete', { paths: arr });
      clearFolderCache();
      state.selected.clear();
      await softRefresh();
      if (window.LanternTree?.refresh) void window.LanternTree.refresh(currentPath());
    } catch (e) { toast(t('error') + ': ' + e.message); }
  }

  async function shareOne() {
    const rel = selectedArray()[0];
    if (!rel) return;
    const url = new URL('/' + enc(rel), location.href).href;
    try {
      if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(url); toast('✓ ' + t('linkCopied')); return; }
    } catch (_) {}
    prompt('Copy link:', url);
  }

  let propsReturnFocus = null;
  function closePropsModal() {
    const modal = $('#propsModal');
    if (modal) modal.classList.remove('show');
    const ret = propsReturnFocus;
    propsReturnFocus = null;
    try { ret?.focus?.(); } catch (_) {}
  }
  async function openPropertiesModal(relPath = null) {
    propsReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const target = relPath != null ? relPath : (selectedArray()[0] ?? currentPath());
    const modal = $('#propsModal');
    const title = $('#propsTitle');
    const body = $('#propsBody');
    if (!modal || !body) return;
    if (title) title.textContent = 'Properties — ' + (target || 'Root');
    body.innerHTML = `<div class="sub">${escHtml(t('loading'))}</div>`;
    modal.classList.add('show');
    $('#propsCloseBtn')?.focus?.();
    try {
      const r = await fetch('/api/properties?p=' + encodeURIComponent(target), { cache: 'no-store' });
      const p = await r.json();
      if (!r.ok || !p.ok) throw new Error(p.error || 'Failed');
      const rows = [
        ['Name', p.name],
        ['Path', p.fullPath],
        ['Type', p.isDir ? 'Folder' : `${p.kind}${p.mime ? ` (${p.mime})` : ''}`],
        ['Size', p.sizeText],
      ];
      if (p.isDir) rows.push(['Contains', `${p.files} files, ${p.folders} folders${p.truncated ? ' (scan cap)' : ''}`]);
      if (p.width && p.height) rows.push(['Dimensions', `${p.width} × ${p.height} px${p.format ? ` (${p.format})` : ''}`]);
      rows.push(['Modified', p.mtimeText], ['Created', p.ctimeText]);
      body.innerHTML = rows.map(([k, v]) => `<div class="props-row"><div class="k">${escHtml(k)}</div><div class="v">${escHtml(v)}</div></div>`).join('');
    } catch (err) {
      body.textContent = t('propsError') + ': ' + err.message;
    }
  }

  // ---------------- Side Preview & Item Open ----------------
  function closeSidePreview() {
    state.previewPane = false;
    state.listPreview = null;
    if (!isMobileViewport()) localStorage.setItem(prefKey('preview_pane_enabled'), 'false');
    applyView();
  }
  function clearSidePreview() {
    const body = $('#sidePreviewBody');
    const title = $('#sidePreviewTitle');
    const acts = $('#sidePreviewActions');
    if (title) title.textContent = t('preview', 'Preview');
    if (acts) acts.textContent = '';
    if (body) body.innerHTML = `<div class="side-empty">${escHtml(t('selectToPreview'))}</div>`;
    state.listPreview = null;
  }
  function ensureSidePreview() {
    if (state.previewPane && !state.listPreview) clearSidePreview();
  }
  function listCanPreview(card) { return Boolean(card && card.dataset.isdir === '0' && (isMediaKind(card.dataset.kind) || card.dataset.preview === '1' || card.dataset.kind === 'text' || card.dataset.kind === 'pdf')); }

  function renderListPreview(card) {
    if (!sidePreview || !card) return;
    const rel = card.dataset.rel, kind = card.dataset.kind, item = findLoadedItem(rel), name = item?.name || card.dataset.rawname || rel, url = item?.url || fileUrl(rel);
    state.listPreview = rel;
    const title = $('#sidePreviewTitle');
    const acts = $('#sidePreviewActions');
    const wrap = $('#sidePreviewBody');
    if (title) title.textContent = name;
    if (acts) acts.textContent = '';
    if (!wrap) return;
    wrap.innerHTML = '<button class="side-arrow side-prev" onclick="stepSidePreview(-1)" aria-label="Previous">‹</button><button class="side-arrow side-next" onclick="stepSidePreview(1)" aria-label="Next">›</button><div class="side-content"></div>';
    const body = wrap.querySelector('.side-content');
    if (kind === 'image') {
      body.innerHTML = `<div class="side-fit-bg" style="background-image:url('${url.replace(/'/g, '%27')}')"></div>`;
      const openBtn = document.createElement('button');
      openBtn.className = 'btn small';
      openBtn.textContent = 'Open / Crop';
      openBtn.onclick = () => window.openPreview('image', url, name, rel);
      $('#sidePreviewActions')?.prepend(openBtn);
    } else if (kind === 'video') {
      body.innerHTML = `<div class="side-video-fit"><video class="side-video" src="${escHtml(url)}" controls preload="metadata" playsinline></video></div>`;
    } else if (kind === 'audio') {
      body.innerHTML = `<audio class="side-audio" src="${escHtml(url)}" controls preload="metadata"></audio>`;
    } else if (card.dataset.preview === '1') {
      body.innerHTML = `<iframe class="side-frame" src="${escHtml(previewUrl(rel))}"></iframe>`;
    } else if (kind === 'text') {
      body.innerHTML = '<pre class="side-text">Loading...</pre>';
      fetch(url, { headers: { Range: 'bytes=0-199999' } }).then(r => r.text()).then(txt => {
        if (state.listPreview !== rel) return;
        const pre = body.querySelector('pre');
        if (pre) pre.textContent = txt;
      }).catch(e => { body.textContent = t('previewError') + ': ' + e.message; });
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
    else toast(t('previewUnsupported'));
  }

  // ---------------- Context Menu (WAI-ARIA Menu Pattern + 4-Edge Clamping) ----------------
  let ctxTreeTarget = null;
  let ctxTriggerEl = null;

  function visibleMenuItems(m) {
    return Array.from(m?.querySelectorAll?.('[role="menuitem"]:not(.hidden)') || []);
  }

  function positionMenuInViewport(m, clientX, clientY) {
    const vw = Number(window.innerWidth || 1200);
    const vh = Number(window.innerHeight || 800);
    const mw = m.offsetWidth || 200;
    const mh = m.offsetHeight || 260;
    const left = Math.max(8, Math.min(vw - mw - 8, Number(clientX || 8)));
    const top = Math.max(8, Math.min(vh - mh - 8, Number(clientY || 8)));
    m.style.left = left + 'px';
    m.style.top = top + 'px';
  }

  function closeContextMenu(restoreFocus = false) {
    const m = $('#ctxMenu');
    if (m) m.classList.add('hidden');
    $('#mobileMoreActBtn')?.setAttribute('aria-expanded', 'false');
    ctxTreeTarget = null;
    const ret = ctxTriggerEl;
    ctxTriggerEl = null;
    if (restoreFocus) {
      try { ret?.focus?.(); } catch (_) {}
    }
  }

  function focusFirstMenuItem(m) {
    const items = visibleMenuItems(m);
    if (items.length) items[0].focus();
  }

  function openContextMenu(ev, card, opts = {}) {
    ev.preventDefault();
    ev.stopPropagation();
    closeOptionsMenu(false);
    ctxTreeTarget = null;
    ctxTriggerEl = opts.triggerEl || (document.activeElement instanceof HTMLElement ? document.activeElement : null);
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
    show('selectAll', Boolean(opts.includeSelectionControls));
    show('clearSel', Boolean(opts.includeSelectionControls) && n > 0);
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
    positionMenuInViewport(m, ev.clientX, ev.clientY);
    if (opts.triggerEl === $('#mobileMoreActBtn')) {
      $('#mobileMoreActBtn')?.setAttribute('aria-expanded', 'true');
    }
    focusFirstMenuItem(m);
  }

  function openTreeContextMenu(ev, treeRel) {
    ev.preventDefault();
    ev.stopPropagation();
    closeOptionsMenu(false);
    ctxTreeTarget = treeRel;
    ctxTriggerEl = ev.currentTarget instanceof HTMLElement ? ev.currentTarget : null;
    const m = $('#ctxMenu');
    if (!m) return;
    ['selectAll', 'clearSel', 'preview', 'edit', 'rename', 'download', 'copy', 'cut', 'move', 'duplicate', 'batch', 'archive', 'extract', 'share', 'delete'].forEach(a => m.querySelector(`[data-act="${a}"]`)?.classList.add('hidden'));
    m.querySelector('[data-act="open"]')?.classList.remove('hidden');
    m.querySelector('[data-act="paste"]')?.classList.toggle('hidden', !(state.clipboard && state.clipboard.paths.length));
    m.querySelector('[data-act="properties"]')?.classList.remove('hidden');
    m.classList.remove('hidden');
    positionMenuInViewport(m, ev.clientX, ev.clientY);
    focusFirstMenuItem(m);
  }

  $('#ctxMenu')?.addEventListener('keydown', (ev) => {
    const m = $('#ctxMenu');
    if (!m || m.classList.contains('hidden')) return;
    const items = visibleMenuItems(m);
    if (!items.length) return;
    const idx = items.indexOf(document.activeElement);
    if (ev.key === 'ArrowDown') {
      ev.preventDefault();
      items[(idx + 1 + items.length) % items.length].focus();
    } else if (ev.key === 'ArrowUp') {
      ev.preventDefault();
      items[(idx - 1 + items.length) % items.length].focus();
    } else if (ev.key === 'Home') {
      ev.preventDefault();
      items[0].focus();
    } else if (ev.key === 'End') {
      ev.preventDefault();
      items[items.length - 1].focus();
    } else if (ev.key === 'Escape') {
      ev.preventDefault();
      ev.stopPropagation();
      closeContextMenu(true);
    } else if (ev.key === 'Tab') {
      closeContextMenu(false);
    }
  });

  function contextAction(act) {
    const treeTarget = ctxTreeTarget;
    closeContextMenu(false);
    if (act === 'selectAll') { selectVisible(); return; }
    if (act === 'clearSel') { clearSel(); return; }
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
      if (!$('#ctxMenu')?.classList.contains('hidden')) { closeContextMenu(true); return; }
      if (!$('#optionsMenu')?.classList.contains('hidden')) { closeOptionsMenu(true); return; }
      if ($('#propsModal')?.classList.contains('show')) { closePropsModal(); return; }
      if (isMobileViewport() && document.body.classList.contains('tree-mobile-open')) { window.closeMobileTree?.(true); return; }
      if (isMobileViewport() && state.previewPane) { closeSidePreview(); return; }
      if (!isTypingTarget(document.activeElement) && state.selected.size) clearSel();
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'l') { e.preventDefault(); openAddressEditor(); return; }
    if (e.altKey && e.key.toLowerCase() === 'd') { e.preventDefault(); openAddressEditor(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') { e.preventDefault(); if (isMobileViewport()) { toggleMobileSearch(true); } else { q?.focus(); q?.select(); } return; }
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
  window.cacheKey = cacheKey;
  window.clearFolderCache = clearFolderCache;
  window.reconcileSelectionToVisible = reconcileSelectionToVisible;
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
    const raw = prompt(t('promptExt'));
    if (!raw) return;
    try { const j = await api('/api/plugin/extensions', { add: raw }); state.pluginEnabled = true; toast('Added: ' + (j.custom_patterns || []).join(', ')); clearFolderCache(); void loadMore(true); }
    catch (e) { toast(t('error') + ': ' + e.message); }
  };
  window.openPropertiesModal = openPropertiesModal;
  window.closePropsModal = closePropsModal;
  window.closeContextMenu = closeContextMenu;
  window.refreshSysTelemetry = refreshSysTelemetry;


  // ---------------- Explorer vs Gallery Mode, Options Popover, Mobile Search & EN/VI i18n ----------------
  function applyLanguage() {
    document.documentElement.lang = state.lang === 'vi' ? 'vi' : 'en';
    $$('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      if (key) el.textContent = t(key, el.textContent);
    });
    const ls = $('#langSelect');
    if (ls) ls.value = state.lang;
    const tb = $('#treeBody');
    if (tb) tb.setAttribute('aria-label', t('foldersNav', 'Folder navigation'));
    updateSelectionUI();
    updateStatusBar();
  }

  function setLanguage(lang) {
    state.lang = lang === 'vi' ? 'vi' : 'en';
    localStorage.setItem(prefKey('lang'), state.lang);
    applyLanguage();
    render();
  }

  function isItemVisible(it) {
    if (!it) return false;
    if (state.appMode !== 'gallery') return true;
    if (it.special === 'back') return false;
    if (it.is_dir) return true;
    if (state.mediaFilter === 'image') return it.kind === 'image';
    if (state.mediaFilter === 'video') return it.kind === 'video';
    return it.kind === 'image' || it.kind === 'video' || it.kind === 'audio';
  }

  function getVisibleItems() {
    return state.items.filter(isItemVisible);
  }

  function applyAppMode() {
    const isGallery = state.appMode === 'gallery';
    document.body.classList.toggle('mode-gallery', isGallery);
    $$('.mode-toggle button').forEach(b => {
      const on = b.dataset.mode === state.appMode;
      b.classList.toggle('active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    $('#galleryFilterBar')?.classList.toggle('hidden', !isGallery);
    $$('#galleryFilterBar button').forEach(b => {
      const on = b.dataset.media === state.mediaFilter;
      b.classList.toggle('active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }

  function setAppMode(mode) {
    const next = mode === 'gallery' ? 'gallery' : 'explorer';
    const changed = state.appMode !== next;
    state.appMode = next;
    localStorage.setItem(prefKey('app_mode'), state.appMode);
    if (state.appMode === 'gallery' && state.view !== 'large' && state.view !== 'grid') {
      state.view = 'large';
    }
    applyAppMode();
    reconcileSelectionToVisible(true);
    if (changed && state.hasMore) {
      void loadMore(true);
    } else if (changed && state.appMode === 'gallery' && !getVisibleItems().length) {
      void loadMore(true);
    } else if (changed && state.appMode === 'explorer') {
      void loadMore(true);
    } else {
      render();
    }
  }

  function setMediaFilter(filter) {
    const next = ['all', 'image', 'video'].includes(filter) ? filter : 'all';
    const changed = state.mediaFilter !== next;
    state.mediaFilter = next;
    applyAppMode();
    reconcileSelectionToVisible(true);
    if (changed && (state.hasMore || !getVisibleItems().length)) {
      void loadMore(true);
    } else {
      render();
    }
  }

  function closeOptionsMenu(restoreFocus = false) {
    const m = $('#optionsMenu');
    if (m) m.classList.add('hidden');
    $('#optionsBtn')?.setAttribute('aria-expanded', 'false');
    if (restoreFocus) $('#optionsBtn')?.focus?.();
  }
  function toggleOptionsMenu(ev) {
    if (ev) { ev.preventDefault(); ev.stopPropagation(); }
    closeContextMenu(false);
    const m = $('#optionsMenu');
    if (!m) return;
    const willOpen = m.classList.contains('hidden');
    m.classList.toggle('hidden', !willOpen);
    $('#optionsBtn')?.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
    if (willOpen) {
      const firstCtrl = m.querySelector('button:not([disabled]), select:not([disabled]), input:not([disabled])');
      firstCtrl?.focus?.();
    }
  }

  $('#optionsMenu')?.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape') {
      ev.preventDefault();
      ev.stopPropagation();
      closeOptionsMenu(true);
    }
  });

  function toggleShowHidden(el) {
    const on = Boolean(el?.checked);
    state.showHidden = on;
    window.LanternTabState?.setShowHidden?.(on);
    clearFolderCache();
    void softRefresh();
    if (window.LanternTree?.refresh) void window.LanternTree.refresh();
  }

  function toggleMobileSearch(force = null) {
    const bar = $('#mobileSearchBar');
    const inp = $('#mobileQ');
    if (!bar) return;
    const willOpen = force === null ? bar.classList.contains('hidden') : Boolean(force);
    bar.classList.toggle('hidden', !willOpen);
    $('#mobileSearchBtn')?.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
    if (willOpen && inp) {
      inp.value = q?.value || '';
      inp.focus();
    } else if (!willOpen) {
      $('#mobileSearchBtn')?.focus?.();
    }
  }

  function clearSearchInput() {
    if (q) q.value = '';
    const mq = $('#mobileQ');
    if (mq) mq.value = '';
    $('#searchClearBtn')?.classList.add('hidden');
    clearFolderCache();
    void loadMore(true);
  }

  function openMobileSelectionMenu(ev) {
    if (ev) { ev.preventDefault(); ev.stopPropagation(); }
    const rel = selectedArray()[0];
    const card = rel ? document.querySelector(`.card[data-rel="${CSS.escape(rel)}"]`) : null;
    const trigger = $('#mobileMoreActBtn');
    const rect = trigger?.getBoundingClientRect?.() || { left: window.innerWidth - 210, top: window.innerHeight - 80 };
    openContextMenu(
      { preventDefault(){}, stopPropagation(){}, clientX: Math.max(8, rect.left - 120), clientY: Math.max(12, rect.top - 320) },
      card,
      { includeSelectionControls: true, triggerEl: trigger }
    );
  }

  // Event delegation on #grid (FILE-01)
  if (grid) {
    grid.addEventListener('click', (ev) => {
      const target = ev.target instanceof Element ? ev.target : null;
      if (!target) return;
      const checkBtn = target.closest('.check');
      if (checkBtn) {
        const card = checkBtn.closest('.card[data-rel]');
        if (card) toggleSelect(card.dataset.rel, ev);
        return;
      }
      const backCard = target.closest('.card.special-back');
      if (backCard) { navParentFolder(); return; }
      const main = target.closest('.card[data-rel] .card-main');
      if (main) {
        const card = main.closest('.card[data-rel]');
        if (card) openItem(card, ev);
      }
    });
    grid.addEventListener('contextmenu', (ev) => {
      const card = ev.target instanceof Element ? ev.target.closest('.card[data-rel]') : null;
      if (card) openContextMenu(ev, card);
    });
  }

  // Event delegation on #crumbsBar
  const crumbsBar = $('#crumbsBar');
  if (crumbsBar) {
    crumbsBar.addEventListener('click', (ev) => {
      const a = ev.target instanceof Element ? ev.target.closest('a[data-rel]') : null;
      if (!a) return;
      if (ev.ctrlKey || ev.metaKey || ev.button === 1) return;
      ev.preventDefault();
      ev.stopPropagation();
      void navigateToFolder(a.dataset.rel || '');
    });
  }

  const mobileQ = $('#mobileQ');
  if (mobileQ) {
    mobileQ.addEventListener('input', () => {
      if (q) q.value = mobileQ.value;
      clearTimeout(state.searchTimer);
      state.searchTimer = setTimeout(() => { clearFolderCache(); void loadMore(true); }, Number(defaults.search_debounce_ms || 180));
    });
  }

  document.addEventListener('click', (e) => {
    if (!e.target.closest?.('#optionsMenu') && !e.target.closest?.('#optionsBtn')) closeOptionsMenu();
  });

  window.setAppMode = setAppMode;
  window.setMediaFilter = setMediaFilter;
  window.toggleOptionsMenu = toggleOptionsMenu;
  window.closeOptionsMenu = closeOptionsMenu;
  window.toggleShowHidden = toggleShowHidden;
  window.setLanguage = setLanguage;
  window.closeSidePreview = closeSidePreview;
  window.toggleMobileSearch = toggleMobileSearch;
  window.clearSearchInput = clearSearchInput;
  window.openMobileSelectionMenu = openMobileSelectionMenu;

  // Boot
  if (grid) {
    syncControls();
    const sh = $('#showHiddenToggle'); if (sh) sh.checked = state.showHidden;
    applyLanguage();
    applyAppMode();
    applyView();
    initAddressBar();
    updateNavButtons();
    window.LanternUpload?.init?.();
    window.LanternTree?.init?.();
    if (hydrateCache()) void softRefresh(); else void loadMore(true);
    void refreshSysTelemetry();
    setInterval(() => { if (!document.hidden) void refreshSysTelemetry(); }, 15000);
  }
})();
