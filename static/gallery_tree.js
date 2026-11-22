/* Lantern v9.25 — WAI-ARIA APG Windows Explorer-Style Lazy Folder Tree, i18n & Per-Tab State */
(() => {
  'use strict';

  // Shared EN (default) / VI localization dictionary across all Gallery modules (LANG-01)
  const I18N = {
    en: {
      upload: 'Upload', newFolder: 'New', newFile: 'New File', options: 'Options',
      modeExplorer: 'Explorer', modeGallery: 'Gallery', filterAll: 'All', filterPhotos: 'Photos', filterVideos: 'Videos',
      preview: 'Preview', close: 'Close', selectToPreview: 'Select a file to preview',
      selectAll: 'Select all', clearSel: 'Clear', open: 'Open', download: 'Download', copy: 'Copy',
      move: 'Move', rename: 'Rename', duplicate: 'Duplicate', batchRename: 'Batch', extract: 'Extract',
      delete: 'Delete', paste: 'Paste', more: 'More', folders: 'Folders', foldersNav: 'Folder navigation',
      optionsTitle: 'View & Explorer Options', optViewLayout: 'Layout', optSort: 'Sort by',
      optFoldersFirst: 'Folders before files', optShowHidden: 'Show hidden & system (this tab)',
      optFolderMosaic: 'Folder 2×2 preview mosaic', optThumbFit: 'Thumbnail framing',
      optPreviewAnim: 'Mosaic animation', optPageLimit: 'Items per page', optLanguage: 'Language',
      uploadSub: 'Drop files or folders anytime. Large files (≥32 MB) upload in resumable 16 MB chunks.',
      dropHere: 'Drop files or folders here', orPickBelow: 'or use the buttons below',
      selectFiles: 'Select Files', selectFolder: 'Select Folder', onConflict: 'On conflict:',
      startUpload: 'Start Upload', scopeHere: 'Here', scopeAll: 'All',
      emptyFolder: 'This folder is empty', emptyDropHint: 'Drop files or folders here to upload',
      noMatchingMedia: 'No matching photos or videos in this folder', clearFilter: 'Clear filter',
      switchExplorer: 'Switch to Explorer', loading: 'Loading…', loadingMore: 'Loading more…',
      retry: 'Retry', loadError: 'Could not load folder contents', previewError: 'Could not load preview',
      brokenImage: 'This image could not be displayed.',
      items: 'items', selected: 'selected', image: 'Image', video: 'Video', audio: 'Audio', media: 'Media',
      resolution: 'Resolution', duration: 'Duration', subtitles: 'Subtitles',
      done: 'Done', skipped: 'Skipped', canceled: 'Canceled', waiting: 'Queued', error: 'Error',
      uploadAdded: 'Added to upload queue', uploadFinished: 'Upload complete', uploadEmpty: 'No queued files to upload',
      copiedToast: 'Copied to clipboard (Ctrl+V to paste)', cutToast: 'Cut to clipboard (Ctrl+V to move)',
      linkCopied: 'Link copied to clipboard', confirmDelete: 'Permanently delete selected item(s)?',
      promptNewFolder: 'New folder name:', promptNewFile: 'New file name (e.g. notes.txt):',
      promptRename: 'Rename to:', promptMove: 'Move selected item(s) to folder:',
      promptExtract: 'Extract archive to folder:', promptArchiveFmt: 'Archive format (zip or tar):',
      promptBatchFind: 'Batch rename — find text in name:', promptBatchRepl: 'Replace with:',
      promptExt: 'Add preview extension or pattern (e.g. .env.local):',
      previewUnsupported: 'Preview not available for this file type. Use Download instead.',
      cropSavedNew: 'Saved cropped copy', cropSavedOver: 'Overwrote original image',
      cropConfirmOver: 'Overwrite original image?',
      dragError: 'Drag & drop error', propsError: 'Could not load properties',
      treeLoadError: 'Could not load folder',
    },
    vi: {
      upload: 'Tải lên', newFolder: 'Thư mục mới', newFile: 'File mới', options: 'Tuỳ chọn',
      modeExplorer: 'Quản lý file', modeGallery: 'Thư viện ảnh', filterAll: 'Tất cả', filterPhotos: 'Ảnh', filterVideos: 'Video',
      preview: 'Xem trước', close: 'Đóng', selectToPreview: 'Chọn một file để xem trước',
      selectAll: 'Chọn hết', clearSel: 'Bỏ chọn', open: 'Mở', download: 'Tải xuống', copy: 'Sao chép',
      move: 'Di chuyển', rename: 'Đổi tên', duplicate: 'Nhân bản', batchRename: 'Đổi hàng loạt', extract: 'Giải nén',
      delete: 'Xoá', paste: 'Dán', more: 'Thêm', folders: 'Thư mục', foldersNav: 'Cây thư mục',
      optionsTitle: 'Tuỳ chọn hiển thị', optViewLayout: 'Bố cục', optSort: 'Sắp xếp',
      optFoldersFirst: 'Thư mục lên trước', optShowHidden: 'Hiện file ẩn & hệ thống (tab này)',
      optFolderMosaic: 'Ảnh ghép 2×2 thư mục', optThumbFit: 'Khung thumbnail',
      optPreviewAnim: 'Hiệu ứng thư mục', optPageLimit: 'Số mục mỗi trang', optLanguage: 'Ngôn ngữ',
      uploadSub: 'Kéo thả file/folder bất cứ lúc nào. File nặng (≥32 MB) tự chia khối 16 MB.',
      dropHere: 'Kéo thả file hoặc thư mục vào đây', orPickBelow: 'hoặc chọn bằng nút bên dưới',
      selectFiles: 'Chọn file', selectFolder: 'Chọn thư mục', onConflict: 'Khi trùng tên:',
      startUpload: 'Bắt đầu tải lên', scopeHere: 'Hiện tại', scopeAll: 'Tất cả',
      emptyFolder: 'Thư mục trống', emptyDropHint: 'Kéo thả file hoặc thư mục vào đây để tải lên',
      noMatchingMedia: 'Không có ảnh hoặc video phù hợp trong thư mục này', clearFilter: 'Xoá bộ lọc',
      switchExplorer: 'Chuyển sang Quản lý file', loading: 'Đang tải…', loadingMore: 'Đang tải thêm…',
      retry: 'Thử lại', loadError: 'Không thể tải danh sách thư mục', previewError: 'Không đọc được xem trước',
      brokenImage: 'Không thể hiển thị hình ảnh này.',
      items: 'mục', selected: 'đã chọn', image: 'Ảnh', video: 'Video', audio: 'Âm thanh', media: 'Media',
      resolution: 'Độ phân giải', duration: 'Thời lượng', subtitles: 'Phụ đề',
      done: 'Xong', skipped: 'Bỏ qua', canceled: 'Đã huỷ', waiting: 'Chờ', error: 'Lỗi',
      uploadAdded: 'Đã thêm vào hàng đợi tải lên', uploadFinished: 'Tải lên hoàn tất', uploadEmpty: 'Không có file chờ tải lên',
      copiedToast: 'Đã sao chép (Ctrl+V để dán)', cutToast: 'Đã cắt (Ctrl+V để di chuyển)',
      linkCopied: 'Đã sao chép liên kết', confirmDelete: 'Xoá vĩnh viễn các mục đã chọn?',
      promptNewFolder: 'Tên thư mục mới:', promptNewFile: 'Tên file mới (vd: notes.txt):',
      promptRename: 'Đổi tên thành:', promptMove: 'Di chuyển các mục đã chọn tới thư mục:',
      promptExtract: 'Giải nén tới thư mục:', promptArchiveFmt: 'Định dạng nén (zip hoặc tar):',
      promptBatchFind: 'Đổi tên hàng loạt — tìm chuỗi:', promptBatchRepl: 'Thay bằng:',
      promptExt: 'Thêm đuôi/pattern xem nhanh (vd: .env.local):',
      previewUnsupported: 'Chưa hỗ trợ xem nhanh loại file này. Hãy dùng nút Tải xuống.',
      cropSavedNew: 'Đã lưu ảnh crop mới', cropSavedOver: 'Đã ghi đè ảnh gốc',
      cropConfirmOver: 'Ghi đè ảnh gốc?',
      dragError: 'Lỗi kéo thả', propsError: 'Không đọc được thuộc tính',
      treeLoadError: 'Không thể tải thư mục',
    },
  };

  window.LanternI18n = {
    dict: I18N,
    lang: () => (localStorage.getItem('lanDrive:lang') === 'vi' ? 'vi' : 'en'),
    t: (key, fallback = '') => {
      const l = localStorage.getItem('lanDrive:lang') === 'vi' ? 'vi' : 'en';
      return (I18N[l] && I18N[l][key]) || (I18N.en && I18N.en[key]) || fallback || key;
    },
  };

  // Strictly per-tab state (CFG-02): sessionStorage is natively scoped per browser tab,
  // survives same-tab reloads (including the first reload), and never leaks to newly opened tabs.
  const SHOW_HIDDEN_TAB_KEY = 'lanDrive:tab:show_hidden';
  let memShowHidden = false;

  window.LanternTabState = {
    getShowHidden: () => {
      try {
        const v = sessionStorage.getItem(SHOW_HIDDEN_TAB_KEY);
        if (v !== null) return v === '1';
      } catch (_) {}
      return memShowHidden;
    },
    setShowHidden: (on) => {
      memShowHidden = Boolean(on);
      try {
        sessionStorage.setItem(SHOW_HIDDEN_TAB_KEY, memShowHidden ? '1' : '0');
      } catch (_) {}
      return memShowHidden;
    },
  };

  const TREE_WIDTH_KEY = 'lanDrive:treeWidth';
  const TREE_COLLAPSED_KEY = 'lanDrive:treeCollapsed';

  const treeState = {
    nodes: new Map(),      // rel -> { path, name, children: [...], loaded: true }
    errors: new Map(),     // rel -> error string
    expanded: new Set(['']),
    loading: new Set(),
    activePath: '',
    focusedPath: '',
    rootName: (window.APP && window.APP.rootName) || 'Root',
    syncSeq: 0,
  };

  function normRel(p) {
    return String(p || '').replace(/^\/+|\/+$/g, '');
  }

  function announceTree(msg) {
    const live = document.getElementById('treeLive');
    if (live) live.textContent = String(msg || '');
  }

  function isMobileViewport() {
    return typeof window !== 'undefined' && Number(window.innerWidth || 1200) <= 900;
  }

  function setBackgroundInert(isInert) {
    ['topHeader', 'browserArea', 'statusBar'].forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      if (isInert) {
        el.setAttribute('aria-hidden', 'true');
        try { el.inert = true; } catch (_) {}
      } else {
        el.removeAttribute('aria-hidden');
        try { el.inert = false; } catch (_) {}
      }
    });
  }

  function syncTreeToggleAria() {
    const btn = document.getElementById('treeToggleBtn');
    const pane = document.getElementById('treePane');
    if (!btn) return;
    if (isMobileViewport()) {
      const open = document.body.classList.contains('tree-mobile-open');
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (pane) {
        if (open) {
          pane.setAttribute('role', 'dialog');
          pane.setAttribute('aria-modal', 'true');
          pane.removeAttribute('aria-hidden');
        } else {
          pane.removeAttribute('role');
          pane.removeAttribute('aria-modal');
          pane.setAttribute('aria-hidden', 'true');
        }
      }
    } else {
      const open = !document.body.classList.contains('tree-collapsed');
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (pane) {
        pane.removeAttribute('role');
        pane.removeAttribute('aria-modal');
        pane.removeAttribute('aria-hidden');
      }
      setBackgroundInert(false);
    }
  }

  function closeMobileTree(restoreFocus = false) {
    const wasOpen = document.body.classList.contains('tree-mobile-open');
    document.body.classList.remove('tree-mobile-open');
    document.getElementById('treeBackdrop')?.classList.add('hidden');
    setBackgroundInert(false);
    syncTreeToggleAria();
    if (wasOpen && restoreFocus) {
      document.getElementById('treeToggleBtn')?.focus();
    }
  }

  function openMobileTree() {
    document.body.classList.add('tree-mobile-open');
    document.getElementById('treeBackdrop')?.classList.remove('hidden');
    setBackgroundInert(true);
    syncTreeToggleAria();
    if (!treeState.nodes.size) {
      void syncToPath(typeof window.currentPath === 'function' ? window.currentPath() : '');
    }
    requestAnimationFrame(() => {
      const body = document.getElementById('treeBody');
      const target = body?.querySelector('.tree-row[tabindex="0"]') || document.getElementById('treeCloseBtn');
      target?.focus();
    });
  }

  function togglePane() {
    if (isMobileViewport()) {
      if (document.body.classList.contains('tree-mobile-open')) closeMobileTree(true);
      else openMobileTree();
      return;
    }
    const next = !document.body.classList.contains('tree-collapsed');
    document.body.classList.toggle('tree-collapsed', next);
    localStorage.setItem(TREE_COLLAPSED_KEY, next ? '1' : '0');
    syncTreeToggleAria();
    if (!next && !treeState.nodes.size) {
      void syncToPath(typeof window.currentPath === 'function' ? window.currentPath() : '');
    }
  }

  function initLayout() {
    const pane = document.getElementById('treePane');
    const resizer = document.getElementById('treeResizer');
    if (!pane) return;

    const savedW = Number(localStorage.getItem(TREE_WIDTH_KEY) || 256);
    const clampedW = Math.max(170, Math.min(460, Number.isFinite(savedW) ? savedW : 256));
    document.documentElement.style.setProperty('--tree-w', clampedW + 'px');

    const collapsed = localStorage.getItem(TREE_COLLAPSED_KEY) === '1';
    document.body.classList.toggle('tree-collapsed', collapsed);
    syncTreeToggleAria();

    // Trap Tab focus inside mobile drawer when open (A11Y-04)
    pane.addEventListener('keydown', (ev) => {
      if (!isMobileViewport() || !document.body.classList.contains('tree-mobile-open')) return;
      if (ev.key === 'Escape') {
        ev.preventDefault();
        ev.stopPropagation();
        closeMobileTree(true);
        return;
      }
      if (ev.key === 'Tab') {
        const focusables = Array.from(pane.querySelectorAll('button:not([disabled]):not(.hidden), [role="treeitem"][tabindex="0"]'))
          .filter(el => el.offsetParent !== null || el.getAttribute('role') === 'treeitem');
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
    });

    if (resizer) {
      let startX = 0;
      let startW = clampedW;
      const onMove = (ev) => {
        const w = Math.max(170, Math.min(460, Math.round(startW + (ev.clientX - startX))));
        document.documentElement.style.setProperty('--tree-w', w + 'px');
      };
      const onUp = () => {
        resizer.classList.remove('dragging');
        const curW = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--tree-w'), 10) || 256;
        localStorage.setItem(TREE_WIDTH_KEY, String(curW));
        window.removeEventListener('pointermove', onMove);
        window.removeEventListener('pointerup', onUp);
      };
      resizer.addEventListener('pointerdown', (ev) => {
        ev.preventDefault();
        startX = ev.clientX;
        startW = pane.getBoundingClientRect().width || 256;
        resizer.classList.add('dragging');
        window.addEventListener('pointermove', onMove);
        window.addEventListener('pointerup', onUp);
      });
    }

    const body = document.getElementById('treeBody');
    if (body && !body.dataset.kbWired) {
      body.dataset.kbWired = '1';
      body.addEventListener('keydown', handleTreeKeydown);
    }
    window.addEventListener('resize', syncTreeToggleAria);
  }

  async function fetchNode(rel, withAncestors = false) {
    const clean = normRel(rel);
    const showHid = window.LanternTabState.getShowHidden() ? '1' : '0';
    const qs = new URLSearchParams({ path: clean, show_hidden: showHid, show_system: showHid });
    if (withAncestors) qs.set('ancestors', '1');
    const r = await fetch('/api/tree?' + qs.toString(), { cache: 'no-store' });
    const data = await r.json().catch(() => ({}));
    if (!r.ok || !data.ok) throw new Error(data.error || `HTTP ${r.status}`);
    treeState.errors.delete(clean);
    if (withAncestors && data.nodes) {
      if (data.rootName) treeState.rootName = data.rootName;
      Object.entries(data.nodes).forEach(([k, v]) => {
        const nk = normRel(k);
        treeState.errors.delete(nk);
        treeState.nodes.set(nk, { ...v, loaded: true });
      });
    } else {
      treeState.nodes.set(clean, { ...data, loaded: true });
    }
    return data;
  }

  async function syncToPath(rel, forceReload = false) {
    const clean = normRel(rel);
    const seq = ++treeState.syncSeq;
    treeState.activePath = clean;
    if (!treeState.focusedPath || !isPathVisible(treeState.focusedPath)) {
      treeState.focusedPath = clean;
    }
    const parts = clean ? clean.split('/') : [];
    treeState.expanded.add('');
    let acc = '';
    for (const p of parts) {
      acc = acc ? acc + '/' + p : p;
      treeState.expanded.add(acc);
    }
    const missingAncestor = forceReload || !treeState.nodes.has('') || (clean && !treeState.nodes.has(clean));
    if (missingAncestor) {
      try {
        await fetchNode(clean, true);
      } catch (e) {
        if (seq !== treeState.syncSeq) return;
        treeState.errors.set(clean, e?.message || 'Load failed');
        announceTree(window.LanternI18n.t('treeLoadError') + ': ' + (e?.message || ''));
      }
    }
    if (seq !== treeState.syncSeq) return;
    renderTree(true, false);
  }

  function isPathVisible(rel) {
    const clean = normRel(rel);
    if (clean === '') return true;
    const parts = clean.split('/');
    let acc = '';
    for (let i = 0; i < parts.length - 1; i++) {
      acc = acc ? acc + '/' + parts[i] : parts[i];
      if (!treeState.expanded.has(acc)) return false;
    }
    return treeState.expanded.has('');
  }

  function parentRelOf(rel) {
    const clean = normRel(rel);
    if (!clean) return '';
    const idx = clean.lastIndexOf('/');
    return idx < 0 ? '' : clean.slice(0, idx);
  }

  async function toggleExpand(rel, preserveFocus = false) {
    const clean = normRel(rel);
    if (treeState.expanded.has(clean)) {
      treeState.expanded.delete(clean);
      // If focused item was inside collapsed subtree, move focus to collapsed parent (A11Y-01)
      if (treeState.focusedPath && (treeState.focusedPath === clean || treeState.focusedPath.startsWith(clean ? clean + '/' : ''))) {
        treeState.focusedPath = clean;
      }
      renderTree(false, preserveFocus);
      return;
    }
    treeState.expanded.add(clean);
    treeState.errors.delete(clean);
    if (!treeState.nodes.has(clean)) {
      treeState.loading.add(clean);
      announceTree(window.LanternI18n.t('loading'));
      renderTree(false, preserveFocus);
      try {
        await fetchNode(clean, false);
      } catch (e) {
        treeState.errors.set(clean, e?.message || 'Failed');
        announceTree(window.LanternI18n.t('treeLoadError'));
        if (typeof window.toast === 'function') window.toast(window.LanternI18n.t('error') + ': ' + e.message);
      } finally {
        treeState.loading.delete(clean);
      }
    }
    renderTree(false, preserveFocus);
  }

  function collapseAll() {
    treeState.expanded.clear();
    treeState.expanded.add('');
    treeState.focusedPath = '';
    renderTree(false, false);
  }

  async function refresh(targetRel = null) {
    const hadFocus = Boolean(document.activeElement && document.getElementById('treeBody')?.contains(document.activeElement));
    if (targetRel !== null) {
      const clean = normRel(targetRel);
      treeState.nodes.delete(clean);
      treeState.errors.delete(clean);
      try { await fetchNode(clean, false); } catch (e) { treeState.errors.set(clean, e?.message || 'Failed'); }
      renderTree(false, hadFocus);
      return;
    }
    treeState.nodes.clear();
    treeState.errors.clear();
    await syncToPath(treeState.activePath, true);
    if (hadFocus) focusTreeRow(treeState.focusedPath);
  }

  function getVisibleRows() {
    const body = document.getElementById('treeBody');
    if (!body) return [];
    return Array.from(body.querySelectorAll('.tree-row[role="treeitem"]'));
  }

  function focusTreeRow(rel) {
    const clean = normRel(rel);
    const rows = getVisibleRows();
    if (!rows.length) return;
    let target = rows.find(r => (r.dataset.treeRel || '') === clean);
    if (!target) target = rows.find(r => (r.dataset.treeRel || '') === treeState.activePath) || rows[0];
    if (!target) return;
    treeState.focusedPath = target.dataset.treeRel || '';
    rows.forEach(r => { r.tabIndex = r === target ? 0 : -1; });
    target.focus();
    target.scrollIntoView?.({ block: 'nearest' });
  }

  function activateTreeRow(rel) {
    const clean = normRel(rel);
    treeState.focusedPath = clean;
    const wasMobile = isMobileViewport() && document.body.classList.contains('tree-mobile-open');
    if (wasMobile) closeMobileTree(false);
    if (typeof window.navigateToFolder === 'function') {
      void window.navigateToFolder(clean).then(() => {
        if (wasMobile) document.getElementById('grid')?.focus();
      });
    }
  }

  function handleTreeKeydown(ev) {
    const row = ev.target instanceof Element ? ev.target.closest('.tree-row[role="treeitem"]') : null;
    if (!row) return;
    const rows = getVisibleRows();
    const idx = rows.indexOf(row);
    if (idx < 0) return;
    const rel = row.dataset.treeRel || '';
    const hasChildren = row.dataset.hasChildren === '1';
    const isExpanded = row.getAttribute('aria-expanded') === 'true';

    if (ev.key === 'ArrowDown') {
      ev.preventDefault();
      if (idx + 1 < rows.length) focusTreeRow(rows[idx + 1].dataset.treeRel || '');
      return;
    }
    if (ev.key === 'ArrowUp') {
      ev.preventDefault();
      if (idx - 1 >= 0) focusTreeRow(rows[idx - 1].dataset.treeRel || '');
      return;
    }
    if (ev.key === 'Home') {
      ev.preventDefault();
      focusTreeRow(rows[0].dataset.treeRel || '');
      return;
    }
    if (ev.key === 'End') {
      ev.preventDefault();
      focusTreeRow(rows[rows.length - 1].dataset.treeRel || '');
      return;
    }
    if (ev.key === 'ArrowRight') {
      ev.preventDefault();
      if (!hasChildren) return;
      if (!isExpanded) {
        void toggleExpand(rel, true);
      } else if (idx + 1 < rows.length) {
        const nextRel = rows[idx + 1].dataset.treeRel || '';
        const prefix = rel ? rel + '/' : '';
        if (nextRel.startsWith(prefix)) focusTreeRow(nextRel);
      }
      return;
    }
    if (ev.key === 'ArrowLeft') {
      ev.preventDefault();
      if (hasChildren && isExpanded) {
        void toggleExpand(rel, true);
      } else if (rel !== '') {
        focusTreeRow(parentRelOf(rel));
      }
      return;
    }
    if (ev.key === 'Enter' || ev.key === ' ') {
      ev.preventDefault();
      activateTreeRow(rel);
      return;
    }
    if (ev.key === 'Escape') {
      if (typeof window.closeContextMenu === 'function') window.closeContextMenu(false);
      if (isMobileViewport() && document.body.classList.contains('tree-mobile-open')) {
        ev.preventDefault();
        closeMobileTree(true);
      }
    }
  }

  function attachDropHandlers(row, targetRel) {
    row.addEventListener('dragover', (ev) => {
      const types = Array.from(ev.dataTransfer?.types || []);
      if (!types.includes('application/x-lantern-paths') && !types.includes('Files')) return;
      ev.preventDefault();
      ev.stopPropagation();
      ev.dataTransfer.dropEffect = ev.ctrlKey ? 'copy' : 'move';
      row.classList.add('drag-over');
    });
    row.addEventListener('dragleave', () => {
      row.classList.remove('drag-over');
    });
    row.addEventListener('drop', async (ev) => {
      row.classList.remove('drag-over');
      const dt = ev.dataTransfer;
      if (!dt) return;
      const rawLantern = dt.getData('application/x-lantern-paths');
      if (rawLantern) {
        ev.preventDefault();
        ev.stopPropagation();
        try {
          const parsed = JSON.parse(rawLantern);
          const paths = (Array.isArray(parsed) ? parsed : []).map(x => typeof x === 'string' ? x : x.path).filter(Boolean);
          if (paths.length && typeof window.transferPathsToFolder === 'function') {
            await window.transferPathsToFolder(paths, targetRel, ev.ctrlKey ? 'copy' : 'move');
          }
        } catch (err) {
          if (typeof window.toast === 'function') window.toast(window.LanternI18n.t('error') + ': ' + err.message);
        }
        return;
      }
      if ((dt.items && dt.items.length) || (dt.files && dt.files.length)) {
        ev.preventDefault();
        ev.stopPropagation();
        if (window.LanternUpload?.handleDropToTarget) {
          await window.LanternUpload.handleDropToTarget(ev, targetRel);
        }
      }
    });
  }

  function renderTree(scrollActive = false, restoreFocus = false) {
    const body = document.getElementById('treeBody');
    if (!body) return;
    body.setAttribute('aria-label', window.LanternI18n.t('foldersNav', 'Folder navigation'));
    const wasTreeFocused = restoreFocus || Boolean(document.activeElement && body.contains(document.activeElement));

    const visiblePaths = [];
    const collectVisible = (rel, hasChildren) => {
      visiblePaths.push(rel);
      if (hasChildren && treeState.expanded.has(rel)) {
        const node = treeState.nodes.get(rel);
        if (node && Array.isArray(node.children)) {
          for (const ch of node.children) collectVisible(ch.rel, Boolean(ch.hasChildren));
        }
      }
    };
    const rootNode = treeState.nodes.get('');
    const rootHasChildren = rootNode ? (rootNode.children || []).length > 0 : true;
    collectVisible('', rootHasChildren);

    if (!visiblePaths.includes(treeState.focusedPath)) {
      treeState.focusedPath = visiblePaths.includes(treeState.activePath) ? treeState.activePath : '';
    }

    const frag = document.createDocumentFragment();

    const buildNode = (container, rel, label, depth, hasChildren, posInSet, setSize) => {
      const isExpanded = hasChildren && treeState.expanded.has(rel);
      const isActive = treeState.activePath === rel;
      const isFocusable = treeState.focusedPath === rel;

      const row = document.createElement('div');
      row.className = 'tree-row' + (isActive ? ' active' : '');
      row.dataset.treeRel = rel;
      row.dataset.hasChildren = hasChildren ? '1' : '0';
      row.setAttribute('role', 'treeitem');
      row.setAttribute('aria-level', String(depth + 1));
      row.setAttribute('aria-posinset', String(posInSet));
      row.setAttribute('aria-setsize', String(setSize));
      row.setAttribute('aria-selected', isActive ? 'true' : 'false');
      if (hasChildren) {
        row.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');
      }
      row.tabIndex = isFocusable ? 0 : -1;
      row.style.paddingLeft = (6 + depth * 14) + 'px';
      row.title = rel ? '/' + rel : '/';

      const twist = document.createElement('span');
      twist.className = 'tree-twist' + (hasChildren ? '' : ' tree-twist-empty');
      twist.setAttribute('aria-hidden', 'true');
      twist.textContent = isExpanded ? '▾' : '▸';
      twist.addEventListener('click', (ev) => {
        ev.stopPropagation();
        if (hasChildren) {
          treeState.focusedPath = rel;
          void toggleExpand(rel, true);
        }
      });

      const icon = document.createElement('span');
      icon.className = 'tree-icon';
      icon.setAttribute('aria-hidden', 'true');
      icon.textContent = rel === '' ? '🖥️' : (isExpanded ? '📂' : '📁');

      const text = document.createElement('span');
      text.className = 'tree-label';
      text.textContent = label;

      row.append(twist, icon, text);
      row.addEventListener('click', () => {
        activateTreeRow(rel);
      });
      row.addEventListener('dblclick', () => {
        if (hasChildren) void toggleExpand(rel, true);
      });
      row.addEventListener('focus', () => {
        treeState.focusedPath = rel;
        getVisibleRows().forEach(r => { r.tabIndex = r === row ? 0 : -1; });
      });
      row.addEventListener('contextmenu', (ev) => {
        if (typeof window.openTreeContextMenu === 'function') {
          window.openTreeContextMenu(ev, rel);
        }
      });
      attachDropHandlers(row, rel);
      container.appendChild(row);

      if (isExpanded) {
        const group = document.createElement('div');
        group.className = 'tree-group';
        group.setAttribute('role', 'group');

        if (treeState.loading.has(rel)) {
          const ld = document.createElement('div');
          ld.className = 'tree-loading';
          ld.style.paddingLeft = (26 + depth * 14) + 'px';
          ld.textContent = window.LanternI18n.t('loading', 'Loading…');
          group.appendChild(ld);
          container.appendChild(group);
          return;
        }
        const errMsg = treeState.errors.get(rel);
        if (errMsg) {
          const err = document.createElement('div');
          err.className = 'tree-error';
          err.style.paddingLeft = (24 + depth * 14) + 'px';
          const sp = document.createElement('span');
          sp.textContent = window.LanternI18n.t('treeLoadError') + ': ' + errMsg;
          const retryBtn = document.createElement('button');
          retryBtn.type = 'button';
          retryBtn.textContent = window.LanternI18n.t('retry', 'Retry');
          retryBtn.addEventListener('click', (ev) => {
            ev.stopPropagation();
            void refresh(rel);
          });
          err.append(sp, retryBtn);
          group.appendChild(err);
          container.appendChild(group);
          return;
        }
        const node = treeState.nodes.get(rel);
        if (node && Array.isArray(node.children) && node.children.length) {
          const len = node.children.length;
          node.children.forEach((ch, i) => {
            buildNode(group, ch.rel, ch.name, depth + 1, Boolean(ch.hasChildren), i + 1, len);
          });
          container.appendChild(group);
        }
      }
    };

    buildNode(frag, '', treeState.rootName || 'Root', 0, rootHasChildren, 1, 1);

    body.textContent = '';
    body.appendChild(frag);

    if (wasTreeFocused) {
      const fRow = getVisibleRows().find(r => (r.dataset.treeRel || '') === treeState.focusedPath);
      fRow?.focus();
    } else if (scrollActive) {
      const activeEl = body.querySelector('.tree-row.active');
      activeEl?.scrollIntoView?.({ block: 'nearest' });
    }
  }

  window.LanternTree = {
    init: () => {
      initLayout();
      const startPath = typeof window.currentPath === 'function' ? window.currentPath() : (window.APP?.currentPath || '');
      void syncToPath(startPath, true);
    },
    state: treeState,
    syncToPath,
    refresh,
    togglePane,
    collapseAll,
    toggleExpand,
    focusTreeRow,
    closeMobileTree,
    openMobileTree,
  };
  window.toggleTreePane = togglePane;
  window.closeMobileTree = closeMobileTree;
})();
