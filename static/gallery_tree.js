/* Lantern v9.25 — Windows Explorer-Style Lazy Folder Tree Sidebar */
(() => {
  'use strict';

  const TREE_WIDTH_KEY = 'lanDrive:treeWidth';
  const TREE_COLLAPSED_KEY = 'lanDrive:treeCollapsed';

  const treeState = {
    nodes: new Map(),      // rel -> { path, name, children: [...], loaded: true }
    expanded: new Set(['']),
    loading: new Set(),
    activePath: '',
    rootName: (window.APP && window.APP.rootName) || 'Root',
  };

  function normRel(p) {
    return String(p || '').replace(/^\/+|\/+$/g, '');
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
  }

  function togglePane() {
    const next = !document.body.classList.contains('tree-collapsed');
    document.body.classList.toggle('tree-collapsed', next);
    localStorage.setItem(TREE_COLLAPSED_KEY, next ? '1' : '0');
    if (!next && !treeState.nodes.size) {
      void syncToPath(typeof window.currentPath === 'function' ? window.currentPath() : '');
    }
  }

  async function fetchNode(rel, withAncestors = false) {
    const clean = normRel(rel);
    const qs = new URLSearchParams({ path: clean });
    if (withAncestors) qs.set('ancestors', '1');
    const r = await fetch('/api/tree?' + qs.toString(), { cache: 'no-store' });
    const data = await r.json();
    if (!r.ok || !data.ok) throw new Error(data.error || 'Tree load failed');
    if (withAncestors && data.nodes) {
      if (data.rootName) treeState.rootName = data.rootName;
      Object.entries(data.nodes).forEach(([k, v]) => {
        treeState.nodes.set(normRel(k), { ...v, loaded: true });
      });
    } else {
      treeState.nodes.set(clean, { ...data, loaded: true });
    }
    return data;
  }

  async function syncToPath(rel, forceReload = false) {
    const clean = normRel(rel);
    treeState.activePath = clean;
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
        console.warn('Tree sync failed:', e);
      }
    }
    renderTree(true);
  }

  async function toggleExpand(rel) {
    const clean = normRel(rel);
    if (treeState.expanded.has(clean)) {
      treeState.expanded.delete(clean);
      renderTree(false);
      return;
    }
    treeState.expanded.add(clean);
    if (!treeState.nodes.has(clean)) {
      treeState.loading.add(clean);
      renderTree(false);
      try {
        await fetchNode(clean, false);
      } catch (e) {
        if (typeof window.toast === 'function') window.toast('Không mở được thư mục: ' + e.message);
      } finally {
        treeState.loading.delete(clean);
      }
    }
    renderTree(false);
  }

  function collapseAll() {
    treeState.expanded.clear();
    treeState.expanded.add('');
    renderTree(false);
  }

  async function refresh(targetRel = null) {
    if (targetRel !== null) {
      const clean = normRel(targetRel);
      treeState.nodes.delete(clean);
      try { await fetchNode(clean, false); } catch (_) {}
      renderTree(false);
      return;
    }
    treeState.nodes.clear();
    await syncToPath(treeState.activePath, true);
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
          if (typeof window.toast === 'function') window.toast('Lỗi kéo thả: ' + err.message);
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

  function renderTree(scrollActive = false) {
    const body = document.getElementById('treeBody');
    if (!body) return;
    const frag = document.createDocumentFragment();

    const addRow = (rel, label, depth, hasChildren) => {
      const isExpanded = treeState.expanded.has(rel);
      const isActive = treeState.activePath === rel;
      const row = document.createElement('div');
      row.className = 'tree-row' + (isActive ? ' active' : '');
      row.dataset.treeRel = rel;
      row.setAttribute('role', 'treeitem');
      row.setAttribute('aria-expanded', hasChildren ? String(isExpanded) : 'false');
      row.style.paddingLeft = (6 + depth * 15) + 'px';
      row.title = rel ? '/' + rel : '/';

      const twist = document.createElement('span');
      twist.className = 'tree-twist' + (hasChildren ? '' : ' empty');
      twist.textContent = isExpanded ? '▾' : '▸';
      twist.addEventListener('click', (ev) => {
        ev.stopPropagation();
        if (hasChildren) void toggleExpand(rel);
      });

      const icon = document.createElement('span');
      icon.className = 'tree-icon';
      icon.textContent = rel === '' ? '🖥️' : (isExpanded ? '📂' : '📁');

      const text = document.createElement('span');
      text.className = 'tree-label';
      text.textContent = label;

      row.append(twist, icon, text);
      row.addEventListener('click', () => {
        if (typeof window.navigateToFolder === 'function') {
          void window.navigateToFolder(rel);
        }
      });
      row.addEventListener('dblclick', () => {
        if (hasChildren) void toggleExpand(rel);
      });
      row.addEventListener('contextmenu', (ev) => {
        if (typeof window.openTreeContextMenu === 'function') {
          window.openTreeContextMenu(ev, rel);
        }
      });
      attachDropHandlers(row, rel);
      frag.appendChild(row);

      if (isExpanded) {
        if (treeState.loading.has(rel)) {
          const ld = document.createElement('div');
          ld.className = 'tree-loading';
          ld.style.paddingLeft = (26 + depth * 15) + 'px';
          ld.textContent = 'Đang tải…';
          frag.appendChild(ld);
          return;
        }
        const node = treeState.nodes.get(rel);
        if (node && Array.isArray(node.children)) {
          for (const ch of node.children) {
            addRow(ch.rel, ch.name, depth + 1, Boolean(ch.hasChildren));
          }
        }
      }
    };

    const rootNode = treeState.nodes.get('');
    const rootHasChildren = rootNode ? (rootNode.children || []).length > 0 : true;
    addRow('', treeState.rootName || 'Root', 0, rootHasChildren);

    body.textContent = '';
    body.appendChild(frag);

    if (scrollActive) {
      const activeEl = body.querySelector('.tree-row.active');
      if (activeEl) activeEl.scrollIntoView({ block: 'nearest' });
    }
  }

  window.LanternTree = {
    init: () => {
      initLayout();
      const startPath = typeof window.currentPath === 'function' ? window.currentPath() : (window.APP?.currentPath || '');
      void syncToPath(startPath, true);
    },
    syncToPath,
    refresh,
    togglePane,
    collapseAll,
    toggleExpand,
  };
  window.toggleTreePane = togglePane;
})();
