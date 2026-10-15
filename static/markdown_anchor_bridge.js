/* Source-aware navigation across Markdown Preview, Visual and Source.
   Coordinates are source lines, not pixel offsets. Never modifies a document. */
(() => {
  'use strict';
  const SELECTOR = 'h1,h2,h3,h4,h5,h6,p,li,tr,pre,blockquote';
  const normalize = text => String(text || '').replace(/\s+/g, ' ').trim();
  const positiveLine = line => Math.max(1, Math.trunc(Number(line) || 1));
  function offsetForLine(source, line) {
    const wanted = positiveLine(line);
    let at = 0;
    for (let current = 1; current < wanted; current++) {
      const next = source.indexOf('\n', at);
      if (next < 0) return source.length;
      at = next + 1;
    }
    return at;
  }
  function lineForOffset(source, offset) {
    let line = 1;
    const end = Math.max(0, Math.min(source.length, Math.trunc(offset) || 0));
    for (let i = 0; i < end; i++) if (source[i] === '\n') line++;
    return line;
  }
  function closestLine(lines, requested) {
    const sorted = lines.filter(x => Number.isSafeInteger(x) && x > 0).sort((a, b) => a - b);
    if (!sorted.length) return null;
    const target = positiveLine(requested);
    let best = sorted[0];
    for (const line of sorted) { if (line > target) break; best = line; }
    return best;
  }
  function sourceSelection(source, bookmark) {
    const needle = bookmark?.selectedText;
    if (!needle || needle.length > 512 || needle.includes('\n')) return null;
    const start = offsetForLine(source, bookmark.line);
    // Selection can span inline markup, but never search beyond its source
    // block. Inexact or repeated matches intentionally fall back to a line.
    const limit = source.indexOf('\n', start);
    const end = limit < 0 ? source.length : limit;
    const segment = source.slice(start, end);
    const first = segment.indexOf(needle);
    if (first < 0 || segment.indexOf(needle, first + needle.length) >= 0) return null;
    return {start: start + first, end: start + first + needle.length};
  }
  function selectLine(area, line, bookmark = null) {
    const content = area.value;
    const selection = bookmark ? sourceSelection(content, bookmark) : null;
    const at = offsetForLine(content, line);
    area.setSelectionRange(selection?.start ?? at, selection?.end ?? at);
    const style = getComputedStyle(area);
    const height = Number.parseFloat(style.lineHeight) || 21;
    area.scrollTop = Math.max(0, (positiveLine(line) - 2) * height);
    area.focus({preventScroll: true});
    return selection?.start ?? at;
  }
  function anchorFromElement(element) {
    if (!element?.closest) return null;
    const block = element.closest('[data-l]');
    const line = Number(block?.getAttribute('data-l'));
    if (!Number.isSafeInteger(line) || line <= 0) return null;
    const parent = block.closest('article.md-preview');
    if (!parent) return null;
    const value = normalize(block.textContent);
    let ordinal = 0;
    for (const other of parent.querySelectorAll('[data-l]')) {
      if (other === block) break;
      if (other.tagName === block.tagName && normalize(other.textContent) === value) ordinal++;
    }
    return {line, blockTag: block.tagName, text: value.slice(0, 512), ordinal};
  }
  function captureViewport(root, selector = '[data-l]') {
    if (!root || root.hidden) return null;
    const nodes = root.querySelectorAll(selector);
    let first = null;
    for (const el of nodes) {
      const box = el.getBoundingClientRect();
      if (box.bottom <= 72 || box.top >= innerHeight) continue;
      if (!first) first = el;
      if (box.top >= 72) return anchorFromElement(el);
    }
    return first ? anchorFromElement(first) : nodes.length ? anchorFromElement(nodes[0]) : null;
  }
  function capturePreview(preview) {
    const selection = globalThis.getSelection?.();
    const node = selection?.anchorNode;
    const origin = node?.nodeType === 1 ? node : node?.parentElement;
    if (origin && preview.contains(origin)) {
      const anchor = anchorFromElement(origin);
      if (anchor) {
        const selected = normalize(selection.toString());
        if (selected && selected.length <= 512) anchor.selectedText = selected;
        return anchor;
      }
    }
    return captureViewport(preview);
  }
  function captureSource(area) {
    const style = getComputedStyle(area);
    const height = Number.parseFloat(style.lineHeight) || 21;
    const startLine = Math.max(1, 1 + Math.floor(area.scrollTop / height));
    const cursorLine = lineForOffset(area.value, area.selectionStart);
    const visibleLines = Math.max(1, Math.floor(area.clientHeight / height));
    // Scrolling without moving the caret should navigate from the viewport,
    // not the stale cursor at the start of the document.
    const line = cursorLine >= startLine && cursorLine < startLine + visibleLines ? cursorLine : startLine;
    const bookmark = {line};
    if (line === cursorLine) {
      bookmark.column = area.selectionStart - offsetForLine(area.value, line);
      const selected = area.value.slice(area.selectionStart, area.selectionEnd);
      if (selected && selected.length <= 512 && !selected.includes('\n')) bookmark.selectedText = selected;
    }
    return bookmark;
  }
  function findVisualBlock(host, bookmark) {
    if (!host || !bookmark?.text) return null;
    const matching = [...host.querySelectorAll(SELECTOR)]
      .filter(x => x.tagName === bookmark.blockTag && normalize(x.textContent) === bookmark.text);
    return matching.length === 1 ? matching[0] : matching[bookmark.ordinal] || null;
  }
  function visualAnchorFromElement(element, host, preview, paged = null) {
    if (!element?.closest || !host?.contains(element)) return null;
    const block = element.closest(SELECTOR);
    if (!block || !host.contains(block)) return null;
    const text = normalize(block.textContent);
    if (!text || text.length > 512) return null;
    const local = [...host.querySelectorAll(SELECTOR)].filter(x => x.tagName === block.tagName && normalize(x.textContent) === text);
    const ordinal = local.indexOf(block);
    let matching = [...preview.querySelectorAll('[data-l]')].filter(x =>
      x.tagName === block.tagName && normalize(x.textContent) === text);
    if (paged?.active && paged.page && paged.source) {
      matching = matching.filter(x => {
        const at = offsetForLine(paged.source, Number(x.getAttribute('data-l')));
        return at >= paged.page.start && at < paged.page.end;
      });
    }
    const found = matching[ordinal];
    return found ? anchorFromElement(found) : null;
  }
  function captureVisual(host, preview, paged = null) {
    if (!host || !preview) return null;
    const selection = globalThis.getSelection?.();
    const node = selection?.anchorNode;
    const origin = node?.nodeType === 1 ? node : node?.parentElement;
    if (origin && host.contains(origin)) {
      const bookmark = visualAnchorFromElement(origin, host, preview, paged);
      if (bookmark) {
        const selected = normalize(selection.toString());
        if (selected && selected.length <= 512) bookmark.selectedText = selected;
        // Clicking a sticky mode button may scroll the page before its
        // pointerdown handler. A real editor selection remains authoritative.
        if (!selection?.isCollapsed || document.activeElement === host) return bookmark;
        const box = origin.getBoundingClientRect();
        if (box.bottom > 72 && box.top < innerHeight) return bookmark;
      }
    }
    for (const node of host.querySelectorAll(SELECTOR)) {
      const box = node.getBoundingClientRect();
      if (box.bottom > 72 && box.top < innerHeight)
        return visualAnchorFromElement(node, host, preview, paged);
    }
    return null;
  }
  function capture(mode, preview = document.querySelector('article.md-preview')) {
    if (!preview) return null;
    if (mode === 'source') {
      const source = document.querySelector('textarea.md-source-area');
      return source ? captureSource(source) : null;
    }
    if (mode === 'visual' || mode === 'paged') {
      const paged = globalThis.__lanternMdPaged;
      const host = document.querySelector('.md-visual-host .ProseMirror');
      return captureVisual(host, preview, mode === 'paged' ? paged : null);
    }
    return capturePreview(preview);
  }
  function previewAnchorAtLine(preview, bookmark) {
    const all = [...preview.querySelectorAll('[data-l]')];
    const line = closestLine(all.map(el => Number(el.getAttribute('data-l'))), bookmark.line);
    const candidates = all.filter(el => Number(el.getAttribute('data-l')) === line);
    const chosen = candidates.find(el => el.tagName === bookmark.blockTag) || candidates.at(-1);
    if (!chosen) return null;
    return {node:chosen, bookmark: {...anchorFromElement(chosen), selectedText:bookmark.selectedText}};
  }
  function restorePreview(preview, bookmark) {
    if (!preview || !bookmark) return false;
    const target = previewAnchorAtLine(preview, bookmark);
    if (!target) return false;
    target.node.scrollIntoView({block: 'start', behavior: 'instant'});
    return true;
  }
  function sourceOffsetToPage(source, line, index) {
    const at = offsetForLine(source, line);
    const pages = index?.pages || [];
    if (!pages.length) return -1;
    let lo = 0, hi = pages.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (pages[mid].end <= at) lo = mid + 1;
      else hi = mid;
    }
    return lo;
  }
  function selectVisualText(block, text) {
    const selection = globalThis.getSelection?.();
    if (!selection || !document.createRange) return;
    const walk = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
    const nodes = []; let joined = '';
    while (walk.nextNode()) { nodes.push({node: walk.currentNode, start: joined.length}); joined += walk.currentNode.textContent; }
    if (!nodes.length) return;
    const first = text ? joined.indexOf(text) : -1;
    const match = first >= 0 && joined.indexOf(text, first + text.length) < 0;
    const from = match ? first : 0;
    const to = match ? first + text.length : from;
    function boundary(at) {
      const part = nodes.findLast(x => x.start <= at) || nodes[0];
      return {node:part.node, offset:Math.min(part.node.length, at - part.start)};
    }
    const start = boundary(from), end = boundary(to);
    const range = document.createRange();
    range.setStart(start.node, start.offset);range.setEnd(end.node, end.offset);
    selection.removeAllRanges();selection.addRange(range);
  }
  async function restore(mode, bookmark, preview = document.querySelector('article.md-preview')) {
    if (!bookmark || !preview) return false;
    if (mode === 'preview' && !preview.hidden) return restorePreview(preview, bookmark);
    if (mode === 'source') {
      const area = document.querySelector('textarea.md-source-area');
      if (!area) return false;
      selectLine(area, bookmark.line, bookmark);
      return true;
    }
    if (mode === 'visual' || mode === 'paged') {
      const paged = globalThis.__lanternMdPaged;
      if (paged?.active && paged.index?.pages?.length) {
        const target = sourceOffsetToPage(paged.source, bookmark.line, paged.index);
        if (target >= 0 && target !== paged.pageNumber && !await paged.go(target)) return false;
      }
      const host = document.querySelector('.md-visual-host .ProseMirror');
      if (!host) return false;
      const resolved = bookmark.text ? bookmark : previewAnchorAtLine(preview, bookmark)?.bookmark;
      const block = findVisualBlock(host, resolved);
      if (!block) return false;
      block.scrollIntoView({block:'center', behavior:'instant'});
      host.focus({preventScroll:true});
      selectVisualText(block, resolved?.selectedText);
      return true;
    }
    return false;
  }
  function installPreviewContextMenu() {
    const preview = document.querySelector('article.md-preview');
    if (!preview?.querySelector('[data-l]')) return;
    let menu;
    const cleanup = () => { menu?.remove(); menu = null; };
    preview.addEventListener('contextmenu', event => {
      const selected = normalize(globalThis.getSelection?.()?.toString());
      if (!selected) return;
      const bookmark = capturePreview(preview);
      if (!bookmark?.selectedText) return;
      event.preventDefault();cleanup();
      const button = document.createElement('button');
      button.type = 'button';button.className = 'btn';
      button.textContent = 'Edit selection in Visual';
      button.style.cssText = 'position:fixed;z-index:99';
      button.style.left = Math.max(4, Math.min(innerWidth - 220, event.clientX)) + 'px';
      button.style.top = Math.max(4, Math.min(innerHeight - 40, event.clientY)) + 'px';
      button.addEventListener('click', () => {
        cleanup();void globalThis.__lanternMdVisual?.open('visual', bookmark);
      });
      document.body.append(button);menu = button;
    });
    document.addEventListener('click', e => {
      if (menu && !menu.contains(e.target)) cleanup();
    }, true);
  }
  const api = {offsetForLine, lineForOffset, closestLine, normalizedText:normalize,
    sourceSelection, selectLine, anchorFromElement, captureViewport, capture,
    restorePreview, sourceOffsetToPage, restore};
  globalThis.LanternAnchorBridge = api;
  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', installPreviewContextMenu);
    else installPreviewContextMenu();
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
