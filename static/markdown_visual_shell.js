(() => {
  'use strict';
  // This small controller loads the 2.8 MB editor only when the user selects "Edit visually".
  // The existing read-only preview remains the fast default.
  // --- Step 2 (v7): AST / Block-Level + Line-Level Milkdown Raw Format Protection ---
  function unescapeInlineSegment(segment, referenceText = '') {
    let s = String(segment ?? '');
    if (!referenceText || !referenceText.includes('\\_')) s = s.replace(/\\_/g, '_');
    if (!referenceText || !referenceText.includes('\\--')) s = s.replace(/\\--/g, '--');
    if (!referenceText || !referenceText.includes('\\&')) s = s.replace(/\\&/g, '&');
    s = s.replace(/&#x20;/gi, ' ').replace(/&#32;/g, ' ');
    for (const [escSeq, rawChar] of [
      ['\\*', '*'],
      ['\\[', '['],
      ['\\]', ']'],
      ['\\~', '~'],
      ['\\<', '<'],
      ['\\>', '>'],
    ]) {
      if (s.includes(escSeq) && (!referenceText || !referenceText.includes(escSeq))) {
        s = s.split(escSeq).join(rawChar);
      }
    }
    return s;
  }

  function stripRedundantMilkdownEscapes(mdText, referenceText = '') {
    const lines = String(mdText ?? '').replace(/\r\n?/g, '\n').split('\n');
    let inFence = false;
    return lines.map(line => {
      if (/^\s*(?:`{3,}|~{3,})/.test(line)) {
        inFence = !inFence;
        return line;
      }
      if (inFence) return line;
      // Preserve inline code spans (`...`) untouched while unescaping prose segments
      const parts = line.split(/(`+[^`]*`+)/g);
      return parts.map((part, idx) => (idx % 2 === 1 ? part : unescapeInlineSegment(part, referenceText))).join('');
    }).join('\n');
  }

  function canonicalizeMdLineForCompare(line) {
    const s = String(line ?? '').trim()
      .replace(/\\_/g, '_')
      .replace(/\\--/g, '--')
      .replace(/\\&/g, '&')
      .replace(/&#x20;/gi, ' ')
      .replace(/&#32;/g, ' ');
    if (!s) return '';
    // Normalize GFM table row / divider spacing so Milkdown padding never triggers false diffs
    if (s.startsWith('|') && s.endsWith('|')) {
      const cells = s.slice(1, -1).split('|').map(c => c.trim());
      if (cells.length > 0 && cells.every(c => /^:?-{2,}:?$/.test(c))) {
        return '|' + cells.map(c => {
          const left = c.startsWith(':') ? ':' : '';
          const right = c.endsWith(':') ? ':' : '';
          return left + '---' + right;
        }).join('|') + '|';
      }
      return '|' + cells.map(c => c.replace(/\s+/g, ' ')).join('|') + '|';
    }
    // Normalize horizontal rule variations
    if (/^(?:---+|\*\*\*+|___+)$/.test(s)) return '---';
    // Normalize task list & unordered list markers (*, +, -) to canonical '- ' for equivalence comparison
    const indentMatch = String(line ?? '').match(/^(\s*)/);
    const indentDepth = indentMatch ? Math.floor(indentMatch[1].replace(/\t/g, '  ').length / 2) : 0;
    const indentPrefix = '  '.repeat(indentDepth);
    const taskMatch = s.match(/^[-*+]\s+\[([ xX])\]\s+(.*)$/);
    if (taskMatch) {
      return `${indentPrefix}- [${taskMatch[1].toLowerCase()}] ${taskMatch[2].replace(/\s+/g, ' ')}`;
    }
    const ulMatch = s.match(/^[-*+]\s+(.*)$/);
    if (ulMatch) {
      return `${indentPrefix}- ${ulMatch[1].replace(/\s+/g, ' ')}`;
    }
    const olMatch = s.match(/^(\d+)[.)]\s+(.*)$/);
    if (olMatch) {
      return `${indentPrefix}${olMatch[1]}. ${olMatch[2].replace(/\s+/g, ' ')}`;
    }
    return s.replace(/\s+/g, ' ');
  }

  function detectListBulletMarker(lines) {
    for (const line of lines) {
      const m = String(line ?? '').match(/^\s*([*+-])\s+/);
      if (m) return m[1];
    }
    return null;
  }

  function isCompactPipeTable(lines) {
    for (const line of lines) {
      const s = String(line ?? '').trim();
      if (s.startsWith('|') && s.endsWith('|')) {
        if (/^\|[^\s|]/.test(s)) return true;
        if (/^\|\s+\S/.test(s)) return false;
      }
    }
    return false;
  }

  function splitMarkdownIntoBlocks(normText) {
    const allLines = String(normText ?? '').split('\n');
    let frontmatter = '';
    let i = 0;

    // Extract YAML frontmatter at line 0 if present
    if (allLines[0] === '---') {
      let endFm = -1;
      for (let j = 1; j < allLines.length; j++) {
        if (allLines[j] === '---' || allLines[j] === '...') {
          endFm = j;
          break;
        }
      }
      if (endFm > 0) {
        let fmEndIdx = endFm + 1;
        while (fmEndIdx < allLines.length && !allLines[fmEndIdx].trim()) fmEndIdx++;
        frontmatter = allLines.slice(0, fmEndIdx).join('\n');
        i = fmEndIdx;
      }
    }

    const blocks = [];
    while (i < allLines.length) {
      let blankStart = i;
      while (i < allLines.length && !allLines[i].trim()) i++;
      if (i >= allLines.length) break;
      const blankBefore = allLines.slice(blankStart, i).join('\n');
      const start = i;
      const line = allLines[i];

      // Standalone HTML comment block
      if (/^\s*<!--/.test(line)) {
        while (i < allLines.length && !/-->\s*$/.test(allLines[i])) i++;
        if (i < allLines.length) i++;
        const bLines = allLines.slice(start, i);
        blocks.push({
          type: 'html_comment',
          blankBefore,
          lines: bLines,
          raw: bLines.join('\n'),
          canon: bLines.map(l => l.trim()).join('\n'),
        });
        continue;
      }

      // Fenced code block
      const fenceMatch = line.match(/^\s*(`{3,}|~{3,})/);
      if (fenceMatch) {
        const fence = fenceMatch[1];
        i++;
        while (i < allLines.length && !allLines[i].trim().startsWith(fence)) i++;
        if (i < allLines.length) i++;
        const bLines = allLines.slice(start, i);
        blocks.push({
          type: 'fence',
          blankBefore,
          lines: bLines,
          raw: bLines.join('\n'),
          canon: bLines.join('\n'),
        });
        continue;
      }

      // GFM pipe table
      if (line.trim().startsWith('|') || (i + 1 < allLines.length && /^\s*\|?\s*:?-{2,}:?\s*\|/.test(allLines[i + 1]))) {
        while (i < allLines.length && allLines[i].trim() && (allLines[i].includes('|') || /^\s*:?-{2,}/.test(allLines[i]))) i++;
        const bLines = allLines.slice(start, i);
        blocks.push({
          type: 'table',
          blankBefore,
          lines: bLines,
          raw: bLines.join('\n'),
          canon: bLines.map(canonicalizeMdLineForCompare).filter(Boolean).join('\n'),
          compactTable: isCompactPipeTable(bLines),
        });
        continue;
      }

      // Heading
      if (/^#{1,6}\s+/.test(line)) {
        i++;
        const bLines = allLines.slice(start, i);
        blocks.push({
          type: 'heading',
          blankBefore,
          lines: bLines,
          raw: bLines.join('\n'),
          canon: bLines.map(canonicalizeMdLineForCompare).join('\n'),
        });
        continue;
      }

      // Horizontal rule
      if (/^\s*(?:---+|\*\*\*+|___+)\s*$/.test(line)) {
        i++;
        const bLines = allLines.slice(start, i);
        blocks.push({
          type: 'hr',
          blankBefore,
          lines: bLines,
          raw: bLines.join('\n'),
          canon: '---',
        });
        continue;
      }

      // List block (unordered, ordered, or task list)
      if (/^\s*(?:[-*+]|\d+[.)])\s+/.test(line)) {
        while (
          i < allLines.length &&
          allLines[i].trim() &&
          (/^\s*(?:[-*+]|\d+[.)])\s+/.test(allLines[i]) || /^\s{2,}\S/.test(allLines[i]))
        ) {
          i++;
        }
        const bLines = allLines.slice(start, i);
        blocks.push({
          type: 'list',
          blankBefore,
          lines: bLines,
          raw: bLines.join('\n'),
          canon: bLines.map(canonicalizeMdLineForCompare).filter(Boolean).join('\n'),
          bulletMarker: detectListBulletMarker(bLines),
        });
        continue;
      }

      // Blockquote
      if (/^\s*>/.test(line)) {
        while (i < allLines.length && /^\s*>/.test(allLines[i])) i++;
        const bLines = allLines.slice(start, i);
        blocks.push({
          type: 'blockquote',
          blankBefore,
          lines: bLines,
          raw: bLines.join('\n'),
          canon: bLines.map(canonicalizeMdLineForCompare).filter(Boolean).join('\n'),
        });
        continue;
      }

      // Paragraph / HTML block
      while (
        i < allLines.length &&
        allLines[i].trim() &&
        !/^#{1,6}\s+/.test(allLines[i]) &&
        !/^\s*(?:`{3,}|~{3,})/.test(allLines[i]) &&
        !/^\s*(?:[-*+]|\d+[.)])\s+/.test(allLines[i]) &&
        !/^\s*>/.test(allLines[i]) &&
        !/^\s*(?:---+|\*\*\*+|___+)\s*$/.test(allLines[i]) &&
        !allLines[i].trim().startsWith('|')
      ) {
        i++;
      }
      const bLines = allLines.slice(start, i);
      blocks.push({
        type: 'paragraph',
        blankBefore,
        lines: bLines,
        raw: bLines.join('\n'),
        canon: bLines.map(canonicalizeMdLineForCompare).filter(Boolean).join('\n'),
      });
    }

    return { frontmatter, blocks };
  }

  function reconcileVisualMarkdown(rawSerialized, referenceText) {
    const refRaw = String(referenceText ?? '');
    if (!refRaw) return stripRedundantMilkdownEscapes(rawSerialized);

    const hasCrlf = /\r\n/.test(refRaw);
    const hasTrailingNewline = /\r?\n$/.test(refRaw);
    const refNorm = refRaw.replace(/\r\n?/g, '\n');
    const cleaned = stripRedundantMilkdownEscapes(rawSerialized, refNorm);

    const refParsed = splitMarkdownIntoBlocks(refNorm);
    const cleanParsed = splitMarkdownIntoBlocks(cleaned);

    // Filter out blocks that Milkdown strips (e.g. HTML comments) when checking semantic equivalence
    const refComparableBlocks = refParsed.blocks.filter(b => b.type !== 'html_comment');
    const cleanComparableBlocks = cleanParsed.blocks.filter(b => b.type !== 'html_comment');

    // Fast path: if all comparable blocks have identical canonical forms, return exact referenceText!
    if (
      refComparableBlocks.length === cleanComparableBlocks.length &&
      refComparableBlocks.every((rb, idx) => rb.canon === cleanComparableBlocks[idx].canon)
    ) {
      return refRaw;
    }

    // Secondary fast path: line-level canonical match across non-frontmatter body
    const cleanLines = cleaned.split('\n');
    const refLines = refNorm.split('\n');
    const cleanCanon = cleanLines.map(canonicalizeMdLineForCompare).filter(Boolean);
    const refCanon = refLines.map(canonicalizeMdLineForCompare).filter(Boolean);
    if (cleanCanon.length === refCanon.length && cleanCanon.every((v, idx) => v === refCanon[idx])) {
      return refRaw;
    }

    // Build block-level lookup queues by canonical key so unchanged blocks stay 100% raw
    const refBlockQueues = new Map();
    refComparableBlocks.forEach((rb, idx) => {
      if (!rb.canon) return;
      if (!refBlockQueues.has(rb.canon)) refBlockQueues.set(rb.canon, []);
      refBlockQueues.get(rb.canon).push({ block: rb, index: idx });
    });

    // Global line-level fallback queues for unchanged lines inside modified blocks
    const refLineQueues = new Map();
    refLines.forEach(rLine => {
      const k = canonicalizeMdLineForCompare(rLine);
      if (!k) return;
      if (!refLineQueues.has(k)) refLineQueues.set(k, []);
      refLineQueues.get(k).push(rLine);
    });

    const consumeLinesFromQueue = lines => {
      lines.forEach(l => {
        const k = canonicalizeMdLineForCompare(l);
        const q = k ? refLineQueues.get(k) : null;
        if (q && q.length) q.shift();
      });
    };

    const docBulletMarker = detectListBulletMarker(refLines);
    const outBlocks = [];

    // Preserve standalone HTML comments at top of file if present in referenceText
    let nextRefCommentIdx = 0;
    while (nextRefCommentIdx < refParsed.blocks.length && refParsed.blocks[nextRefCommentIdx].type === 'html_comment') {
      outBlocks.push(refParsed.blocks[nextRefCommentIdx].raw);
      nextRefCommentIdx++;
    }

    cleanParsed.blocks.forEach((cBlock, cIdx) => {
      const bQueue = refBlockQueues.get(cBlock.canon);
      if (bQueue && bQueue.length) {
        const matched = bQueue.shift().block;
        consumeLinesFromQueue(matched.lines);
        outBlocks.push(matched.raw);
        return;
      }

      // This block was modified by the user! Reconcile its lines while preserving list/table conventions
      const alignedRef = refComparableBlocks[Math.min(cIdx, Math.max(0, refComparableBlocks.length - 1))] || null;
      const preferredBullet = (cBlock.type === 'list' && alignedRef?.type === 'list' && alignedRef.bulletMarker)
        ? alignedRef.bulletMarker
        : docBulletMarker;
      const preferCompactTable = cBlock.type === 'table' && alignedRef?.type === 'table' && alignedRef.compactTable;

      const reconciledLines = cBlock.lines.map(cLine => {
        const key = canonicalizeMdLineForCompare(cLine);
        if (!key) return cLine;
        const lq = refLineQueues.get(key);
        if (lq && lq.length) {
          return lq.shift();
        }
        // User-edited line: preserve original bullet marker (* or +) if Milkdown changed it to -
        if (preferredBullet && preferredBullet !== '-') {
          const ulMatch = cLine.match(/^(\s*)[-*+](\s+.*)$/);
          if (ulMatch) {
            return `${ulMatch[1]}${preferredBullet}${ulMatch[2]}`;
          }
        }
        // Preserve compact table pipe formatting if original table had no space padding
        if (preferCompactTable && cLine.trim().startsWith('|') && cLine.trim().endsWith('|')) {
          const innerCells = cLine.trim().slice(1, -1).split('|').map(c => c.trim());
          return '|' + innerCells.join('|') + '|';
        }
        return cLine;
      });
      outBlocks.push(reconciledLines.join('\n'));
    });

    let joined = outBlocks.join('\n\n');
    if (refParsed.frontmatter && !joined.startsWith('---\n')) {
      joined = refParsed.frontmatter + (refParsed.frontmatter.endsWith('\n') ? '' : '\n\n') + joined;
    }
    if (hasTrailingNewline && !joined.endsWith('\n')) {
      joined += '\n';
    } else if (!hasTrailingNewline && joined.endsWith('\n')) {
      joined = joined.replace(/\n+$/, '');
    }
    if (hasCrlf) {
      joined = joined.replace(/\n/g, '\r\n');
    }
    return joined;
  }

  function countGfmPipeCells(line) {
    const trimmed = String(line ?? '').trim();
    if (!trimmed.includes('|')) return 0;
    const inner = trimmed.replace(/^\|/, '').replace(/\|$/, '');
    let count = 1;
    let inCode = false;
    for (let i = 0; i < inner.length; i++) {
      const ch = inner[i];
      if (ch === '\\' && i + 1 < inner.length) {
        i++;
        continue;
      }
      if (ch === '`') {
        inCode = !inCode;
        continue;
      }
      if (ch === '|' && !inCode) count++;
    }
    return count;
  }

  function isGfmSeparatorLine(line) {
    const trimmed = String(line ?? '').trim();
    if (!trimmed.includes('|') || !trimmed.includes('-')) return false;
    const inner = trimmed.replace(/^\|/, '').replace(/\|$/, '');
    const parts = inner.split('|').map(c => c.trim());
    return parts.length > 0 && parts.every(c => /^:?-+:?$/.test(c));
  }

  function prepareVisualTableMarkdown(mdText) {
    const raw = String(mdText ?? '');
    if (!raw.includes('|')) return raw;
    const hasCrlf = raw.includes('\r\n');
    const lines = raw.replace(/\r\n?/g, '\n').split('\n');
    let inFence = false;
    let changed = false;
    for (let i = 0; i + 1 < lines.length; i++) {
      if (/^\s*(?:`{3,}|~{3,})/.test(lines[i])) {
        inFence = !inFence;
        continue;
      }
      if (inFence) continue;
      if (lines[i].includes('|') && isGfmSeparatorLine(lines[i + 1])) {
        const headCols = countGfmPipeCells(lines[i]);
        const sepInner = lines[i + 1].trim().replace(/^\|/, '').replace(/\|$/, '');
        const sepCells = sepInner.split('|').map(c => c.trim());
        if (headCols > 0 && sepCells.length !== headCols) {
          const fixedCells = sepCells.slice(0, headCols);
          while (fixedCells.length < headCols) fixedCells.push('---');
          lines[i + 1] = '| ' + fixedCells.join(' | ') + ' |';
          changed = true;
        }
      }
    }
    if (!changed) return raw;
    const out = lines.join('\n');
    return hasCrlf ? out.replace(/\n/g, '\r\n') : out;
  }

  reconcileVisualMarkdown.reconcileVisualMarkdown = reconcileVisualMarkdown;
  reconcileVisualMarkdown.stripRedundantMilkdownEscapes = stripRedundantMilkdownEscapes;
  reconcileVisualMarkdown.prepareVisualTableMarkdown = prepareVisualTableMarkdown;
  globalThis.LanternReconcileMarkdown = reconcileVisualMarkdown;
  globalThis.LanternPrepareVisualMarkdown = prepareVisualTableMarkdown;
  if (typeof window !== "undefined") {
    window.LanternReconcileMarkdown = reconcileVisualMarkdown;
    window.LanternPrepareVisualMarkdown = prepareVisualTableMarkdown;
  }

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
  const mdBarEl = document.querySelector('.bar.md-bar');
  const syncMdBarHeightVar = () => {
    if (!mdBarEl) return;
    const h = Math.ceil(mdBarEl.getBoundingClientRect().height || mdBarEl.offsetHeight || 82);
    if (h > 20) {
      document.documentElement.style.setProperty('--md-bar-height', `${h}px`);
    }
  };
  syncMdBarHeightVar();
  window.addEventListener('resize', syncMdBarHeightVar, { passive: true });
  if (mdBarEl && typeof ResizeObserver !== 'undefined') {
    try { new ResizeObserver(syncMdBarHeightVar).observe(mdBarEl); } catch {}
  }
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
    function flashFocusSyncTarget(targetEl, _lineNo) {
    if (!targetEl || !(targetEl instanceof HTMLElement)) return;
    // Never mutate DOM classes or children inside CodeMirror (.cm-editor) or ProseMirror ([contenteditable])
    // because their MutationObservers will treat DOM mutations as user text edits!
    if (targetEl.closest('.cm-editor, .ProseMirror, [contenteditable="true"]')) return;
    document.querySelectorAll('.md-focus-sync-flash').forEach(el => el.classList.remove('md-focus-sync-flash'));
    targetEl.classList.add('md-focus-sync-flash');
    setTimeout(() => targetEl.classList.remove('md-focus-sync-flash'), 1500);
  }

  async function restorePosition(mode, bookmark, y = null) {
    // Position mapping is best effort. A stale or unresolvable bookmark must
    // never tear down an otherwise valid editor, especially with unsaved work.
    const effBookmark = bookmark || (view.lastActiveLine ? { line: view.lastActiveLine, column: 0 } : null);
    let matched = false;
    try { matched = !!(effBookmark && await anchorBridge?.restore(mode, effBookmark, preview)); }
    catch (error) { console.warn('Markdown location could not be restored:', error); }
    if (!matched && y !== null) requestAnimationFrame(() => scrollTo(0, y));
    const targetLine = Number(effBookmark?.line || view.lastActiveLine || 0);
    if (targetLine > 0) {
      view.lastActiveLine = targetLine;
      requestAnimationFrame(() => {
        let targetEl = null;
        if (mode === 'preview') {
          const blocks = [...preview.querySelectorAll('[data-l]')];
          targetEl = blocks.find(b => Number(b.getAttribute('data-l')) >= targetLine) || blocks[blocks.length - 1] || null;
        } else if (mode === 'visual') {
          targetEl = view.instance?.sourceBlockAtLine?.(targetLine)
            || view.host?.querySelector('.lantern-md-anchor-highlight')
            || null;
        }
        if (targetEl && mode === 'preview') flashFocusSyncTarget(targetEl, targetLine);
      });
    }
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
    sourceHost: null, visualDiffFallback: null, hunks: [],
    workHash: null, workState: 'clean', ackedText: '', piTurn: null, applyingPi: false,
    savedSincePreview: false, switchingFromPaged: false,
    botUndoStack: [], activeConflicts: [], currentHunkIdx: 0, curtainOpen: false,
    botWatchdogTimer: 0,
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



  const getEditorText = () => {
    if (!view.instance) return '';
    if (view.mode === 'visual') {
      const refText = view.ackedText || view.baseline || '';
      if (refText && typeof view.instance.isCleanFromMount === 'function' && view.instance.isCleanFromMount()) {
        return refText;
      }
      const raw = view.instance.getMarkdown() || '';
      return reconcileVisualMarkdown(raw, refText);
    }
    return view.instance.getMarkdown() || '';
  };
  // HTML textareas normalize CRLF/CR to LF when read. This is not a user edit,
  // so compare against the normalized baseline without rewriting disk bytes.
  const matchesLastSaved = text => text === (view.mode === 'source'
    ? view.lastSaved.replace(/\r\n?/g, '\n') : view.lastSaved);
  const diffApi = () => globalThis.LanternMarkdownDiff;
  const diffBaseline = () => String(view.baseline || '');
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
      const diff = diffApi();
      if (!diff?.applyHunk) throw new Error('Exact diff hunk application is unavailable');
      let next;
      if (action === 'accept') {
        next = diff.applyHunk(before, h, 'forward');
        await api('/api/work/accept-hunk', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({
            path, content:next, expectSavedVersion:state.saved.version,
            expectCurrentVersion:state.currentVersion,
          }),
        });
      } else {
        next = diff.applyHunk(real, h, 'reverse');
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

  const renderSourceDiff = hunks => {
    if (view.mode !== 'source' || !view.instance?.setHunks) return;
    view.instance.setHunks(hunks);
    renderSourceHunkChips(hunks);
  };
  const getDiffViewMode = () => {
    try {
      return localStorage.getItem('lantern-md-diff-view-mode') === 'raw' ? 'raw' : 'visual';
    } catch (_) {
      return 'visual';
    }
  };

  const setDiffViewMode = (nextMode) => {
    const mode = nextMode === 'raw' ? 'raw' : 'visual';
    try { localStorage.setItem('lantern-md-diff-view-mode', mode); } catch (_) {}
    const isRaw = mode === 'raw';
    document.querySelectorAll('.md-preview-deletion').forEach(ghost => {
      const rDiv = ghost.querySelector('.md-preview-deletion-rendered');
      const tDiv = ghost.querySelector('.md-preview-deletion-text');
      const btn = ghost.querySelector('.md-del-view-toggle');
      if (rDiv && tDiv) {
        rDiv.hidden = isRaw;
        tDiv.hidden = !isRaw;
      }
      if (btn) {
        btn.textContent = isRaw ? '👁 Visual' : '📝 Raw';
        btn.title = isRaw ? 'Switch all deletion blocks to Visual rendered HTML' : 'Switch all deletion blocks to Raw Markdown';
      }
    });
    const globalBtn = document.getElementById('mdGlobalDiffViewModeBtn');
    if (globalBtn) {
      globalBtn.textContent = isRaw ? '📝 Diff: Raw' : '👁 Diff: Visual';
    }
  };

  const clearPreviewDiff = () => {
    for (const cell of preview.querySelectorAll('[data-orig-html]')) {
      cell.innerHTML = cell.getAttribute('data-orig-html') || '';
      cell.removeAttribute('data-orig-html');
      cell.classList.remove('md-table-td-mod');
    }
    for (const inlineNode of preview.querySelectorAll('[data-orig-inline-html]')) {
      inlineNode.innerHTML = inlineNode.getAttribute('data-orig-inline-html') || '';
      inlineNode.removeAttribute('data-orig-inline-html');
    }
    for (const act of preview.querySelectorAll('.md-table-row-actions,.md-hunk-floating-pill')) act.remove();
    for (const node of preview.querySelectorAll('.md-preview-diff-add,.md-preview-diff-mod,.md-table-tr-mod,.md-table-tr-add')) {
      node.classList.remove('md-preview-diff-add', 'md-preview-diff-mod', 'md-table-tr-mod', 'md-table-tr-add');
      node.removeAttribute('data-diff-hunk-index');
    }
    for (const ghost of preview.querySelectorAll('.md-preview-deletion,.md-preview-hunk-actions,.md-table-tr-del,.md-conflict-card')) {
      ghost.remove();
    }
  };

  function formatInlineMarkdownHtml(rawLine) {
    const esc = s => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    let s = esc(rawLine);
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    return s;
  }

  function renderWordDiffHtml(oldLine, newLine, mode = 'both') {
    const esc = s => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const diff = diffApi();
    if (!diff?.diffWords) return esc(mode === 'del' ? oldLine : newLine);
    const ops = diff.diffWords(oldLine, newLine);
    return ops.map(op => {
      if (op.type === 'equal') return formatInlineMarkdownHtml(op.text);
      if (op.type === 'del') {
        if (mode === 'add') return '';
        return `<span class="md-diff-word-del">${esc(op.text)}</span>`;
      }
      if (mode === 'del') return '';
      return `<span class="md-diff-word-add">${esc(op.text)}</span>`;
    }).join('');
  }

  function splitPipeRow(line) {
    const trimmed = String(line || '').trim();
    if (!trimmed.startsWith('|') && (trimmed.match(/\|/g) || []).length < 2) return null;
    const inner = trimmed.replace(/^\|/, '').replace(/\|$/, '');
    return inner.split('|').map(c => c.trim());
  }

  function isTableDividerRow(cells) {
    return Array.isArray(cells) && cells.length > 0 && cells.every(c => /^:?-{2,}:?$/.test(c));
  }

  // Render deleted Markdown lines as real formatted HTML (including GFM pipe tables!)
  function renderDeletedMarkdownHtml(baseLines, draftLines = []) {
    const lines = Array.isArray(baseLines) ? baseLines : [];
    const paired = Array.isArray(draftLines) && draftLines.length === lines.length;
    const out = [];
    let inCode = false;
    let codeBuf = [];
    const esc = s => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    let i = 0;
    while (i < lines.length) {
      const line = String(lines[i] ?? '');
      if (line.trim().startsWith('```')) {
        if (!inCode) { inCode = true; codeBuf = []; }
        else {
          inCode = false;
          out.push(`<pre class="md-code"><code>${esc(codeBuf.join('\n'))}</code></pre>`);
        }
        i++;
        continue;
      }
      if (inCode) { codeBuf.push(line); i++; continue; }

      // Check for GFM pipe table block
      const firstCells = splitPipeRow(line);
      if (firstCells) {
        const tableRows = [];
        const draftTableRows = [];
        while (i < lines.length) {
          const cells = splitPipeRow(lines[i]);
          if (!cells) break;
          tableRows.push(cells);
          draftTableRows.push(paired ? splitPipeRow(draftLines[i]) : null);
          i++;
        }
        if (tableRows.length >= 1) {
          let hasHeader = tableRows.length >= 2 && isTableDividerRow(tableRows[1]);
          let html = '<table class="md-del-rendered-table">';
          if (hasHeader) {
            html += '<thead><tr>';
            tableRows[0].forEach((cell, cIdx) => {
              const dCell = draftTableRows[0]?.[cIdx];
              const cellHtml = dCell != null ? renderWordDiffHtml(cell, dCell, 'del') : formatInlineMarkdownHtml(cell);
              html += `<th>${cellHtml}</th>`;
            });
            html += '</tr></thead>';
          }
          html += '<tbody>';
          const startRow = hasHeader ? 2 : 0;
          for (let r = startRow; r < tableRows.length; r++) {
            if (isTableDividerRow(tableRows[r])) continue;
            html += '<tr>';
            tableRows[r].forEach((cell, cIdx) => {
              const dCell = draftTableRows[r]?.[cIdx];
              const cellHtml = dCell != null ? renderWordDiffHtml(cell, dCell, 'del') : formatInlineMarkdownHtml(cell);
              html += `<td>${cellHtml}</td>`;
            });
            html += '</tr>';
          }
          html += '</tbody></table>';
          out.push(html);
          continue;
        }
      }

      const innerHtml = paired ? renderWordDiffHtml(line, draftLines[i], 'del') : formatInlineMarkdownHtml(line);
      const hm = line.match(/^(#{1,6})\s+(.*)$/);
      if (hm) {
        const lvl = hm[1].length;
        const hBody = paired ? renderWordDiffHtml(hm[2], String(draftLines[i] || '').replace(/^#{1,6}\s+/, ''), 'del') : formatInlineMarkdownHtml(hm[2]);
        out.push(`<h${lvl}>${hBody}</h${lvl}>`);
      } else if (line.startsWith('> ')) {
        out.push(`<blockquote>${innerHtml}</blockquote>`);
      } else if (/^\s*[-*+]\s+/.test(line)) {
        const liText = line.replace(/^\s*[-*+]\s+/, '');
        const dLiText = paired ? String(draftLines[i] || '').replace(/^\s*[-*+]\s+/, '') : '';
        const liHtml = paired ? renderWordDiffHtml(liText, dLiText, 'del') : formatInlineMarkdownHtml(liText);
        out.push(`<div class="md-del-list-item">• ${liHtml}</div>`);
      } else if (!line.trim()) {
        out.push('<div style="height:3px"></div>');
      } else {
        out.push(`<p>${innerHtml}</p>`);
      }
      i++;
    }
    if (inCode && codeBuf.length) {
      out.push(`<pre class="md-code"><code>${esc(codeBuf.join('\n'))}</code></pre>`);
    }
    return out.join('\n');
  }

  function createFloatingHunkPill(index, { includeViewToggle = false } = {}) {
    const pill = document.createElement('div');
    pill.className = 'md-hunk-floating-pill';
    if (includeViewToggle) {
      const isRaw = getDiffViewMode() === 'raw';
      const toggleBtn = document.createElement('button');
      toggleBtn.type = 'button';
      toggleBtn.className = 'md-del-view-toggle';
      toggleBtn.textContent = isRaw ? '👁 Visual' : '📝 Raw';
      toggleBtn.title = 'Switch all deletion blocks between Visual HTML and Raw Markdown';
      toggleBtn.addEventListener('click', ev => {
        ev.stopPropagation();
        setDiffViewMode(getDiffViewMode() === 'raw' ? 'visual' : 'raw');
      });
      pill.append(toggleBtn);
    }
    pill.append(hunkButtons(index));
    return pill;
  }

  // v4 In-Table Diff: Render row & cell diffs directly inside <table> at the exact row/cell
  function tryRenderTableHunkInPlace(index, hunk, draftLines) {
    const diff = diffApi();
    if (!diff?.parseTableRowCells) return false;
    const baseLines = Array.isArray(hunk.baseText) ? hunk.baseText.filter(l => l.trim()) : [];
    const nextLines = Array.isArray(hunk.draftText) ? hunk.draftText.filter(l => l.trim()) : [];
    if (!baseLines.length && !nextLines.length) return false;
    if (!baseLines.every(l => diff.parseTableRowCells(l) !== null)) return false;
    if (!nextLines.every(l => diff.parseTableRowCells(l) !== null)) return false;

    let probe = Math.min(Math.max(0, hunk.draftStart), Math.max(0, draftLines.length - 1));
    if (!String(draftLines[probe] || '').trim().startsWith('|') && probe > 0 && String(draftLines[probe - 1] || '').trim().startsWith('|')) {
      probe -= 1;
    }
    if (!String(draftLines[probe] || '').trim().startsWith('|')) return false;
    let tableStartLine = probe;
    while (tableStartLine > 0 && String(draftLines[tableStartLine - 1] || '').trim().startsWith('|')) {
      tableStartLine--;
    }

    const tables = [...preview.querySelectorAll('table')];
    let targetTable = tables.find(t => Number(t.getAttribute('data-l')) === tableStartLine + 1);
    if (!targetTable) {
      targetTable = tables.find(t => {
        const l = Number(t.getAttribute('data-l') || t.closest('[data-l]')?.getAttribute('data-l') || 0);
        return l >= tableStartLine && l <= hunk.draftStart + 2;
      });
    }
    if (!targetTable) return false;

    const tbody = targetTable.tBodies[0] || targetTable.createTBody();
    const bodyRowIdx = Math.max(0, hunk.draftStart - (tableStartLine + 2));

    if (hunk.kind === 'mod' && baseLines.length === nextLines.length && baseLines.length > 0) {
      let actionsMounted = false;
      for (let r = 0; r < nextLines.length; r++) {
        const draftLineNo = hunk.draftStart + r;
        const tr = draftLineNo === tableStartLine
          ? targetTable.tHead?.rows?.[0]
          : tbody.rows[bodyRowIdx + r];
        if (!tr) return false;
        tr.classList.add('md-table-tr-mod', 'md-preview-diff-mod');
        tr.dataset.diffHunkIndex = String(index);
        const oldCells = diff.parseTableRowCells(baseLines[r]) || [];
        const newCells = diff.parseTableRowCells(nextLines[r]) || [];
        for (let c = 0; c < tr.cells.length; c++) {
          const cell = tr.cells[c];
          if (!cell.hasAttribute('data-orig-html')) {
            cell.setAttribute('data-orig-html', cell.innerHTML);
          }
          const oldVal = oldCells[c] ?? '';
          const newVal = newCells[c] ?? '';
          if (oldVal !== newVal) {
            cell.classList.add('md-table-td-mod');
            const wrap = document.createElement('div');
            wrap.className = 'md-table-cell-diff';
            const delBadge = document.createElement('div');
            delBadge.className = 'md-table-cell-old md-preview-deletion';
            delBadge.setAttribute('data-md-diff-ghost', 'true');
            delBadge.innerHTML = renderWordDiffHtml(oldVal, newVal, 'del');
            const addBadge = document.createElement('div');
            addBadge.className = 'md-table-cell-new';
            addBadge.innerHTML = renderWordDiffHtml(oldVal, newVal, 'add');
            wrap.append(delBadge, addBadge);
            cell.innerHTML = '';
            cell.append(wrap);
          }
        }
        if (!actionsMounted && tr.cells.length) {
          const firstCell = tr.cells[0];
          const actWrap = document.createElement('span');
          actWrap.className = 'md-table-row-actions';
          actWrap.append(hunkButtons(index));
          firstCell.prepend(actWrap);
          actionsMounted = true;
        }
      }
      return true;
    }

    let actionsMounted = false;
    const refRow = tbody.rows[bodyRowIdx] || null;
    if (baseLines.length) {
      baseLines.forEach(bLine => {
        const oldCells = diff.parseTableRowCells(bLine) || [];
        const delTr = document.createElement('tr');
        delTr.className = 'md-table-tr-del md-preview-deletion';
        delTr.setAttribute('data-md-diff-ghost', 'true');
        delTr.dataset.diffHunkIndex = String(index);
        const colCount = Math.max(oldCells.length, targetTable.tHead?.rows?.[0]?.cells?.length || oldCells.length);
        for (let c = 0; c < colCount; c++) {
          const td = document.createElement('td');
          td.className = 'md-table-td-del';
          td.innerHTML = formatInlineMarkdownHtml(oldCells[c] ?? '');
          if (c === 0 && !actionsMounted) {
            const actWrap = document.createElement('span');
            actWrap.className = 'md-table-row-actions';
            actWrap.append(hunkButtons(index));
            td.prepend(actWrap);
            actionsMounted = true;
          }
          delTr.append(td);
        }
        if (refRow) tbody.insertBefore(delTr, refRow);
        else tbody.append(delTr);
      });
    }
    if (nextLines.length) {
      for (let r = 0; r < nextLines.length; r++) {
        const addTr = tbody.rows[bodyRowIdx + r];
        if (!addTr) continue;
        addTr.classList.add('md-table-tr-add', hunk.kind === 'mod' ? 'md-preview-diff-mod' : 'md-preview-diff-add');
        addTr.dataset.diffHunkIndex = String(index);
        if (!actionsMounted && addTr.cells.length) {
          const firstCell = addTr.cells[0];
          if (!firstCell.hasAttribute('data-orig-html')) {
            firstCell.setAttribute('data-orig-html', firstCell.innerHTML);
          }
          const actWrap = document.createElement('span');
          actWrap.className = 'md-table-row-actions';
          actWrap.append(hunkButtons(index));
          firstCell.prepend(actWrap);
          actionsMounted = true;
        }
      }
    }
    return true;
  }

  const renderPreviewDiff = (hunks, draftText) => {
    ensureShellStyle();
    clearPreviewDiff();
    const draftLines = String(draftText || '').replace(/\r\n?/g, '\n').split('\n');
    const lineCount = draftLines.length;
    const blocks = [...preview.querySelectorAll('[data-l]')]
      .filter(node => !node.closest('.md-preview-deletion'))
      .map(node => ({node, line: Math.max(0, Number(node.getAttribute('data-l')) - 1)}))
      .filter(item => Number.isSafeInteger(item.line))
      .sort((a, b) => a.line - b.line);

    for (let i = 0; i < blocks.length; i++) {
      blocks[i].end = i + 1 < blocks.length ? blocks[i + 1].line : lineCount;
    }

    const isRawMode = getDiffViewMode() === 'raw';

    for (const [index, hunk] of hunks.entries()) {
      if (tryRenderTableHunkInPlace(index, hunk, draftLines)) {
        continue;
      }

      const matchedBlocks = [];
      if ((hunk.kind === 'add' || hunk.kind === 'mod') && hunk.draftEnd > hunk.draftStart) {
        for (const block of blocks) {
          if (block.line < hunk.draftEnd && block.end > hunk.draftStart) {
            block.node.classList.add(
              hunk.kind === 'add' ? 'md-preview-diff-add' : 'md-preview-diff-mod'
            );
            block.node.dataset.diffHunkIndex = String(index);
            matchedBlocks.push(block.node);
          }
        }
      }

      // 2-Level Inline Word Diff inside modified single blocks in Preview mode (#11)
      const isSingleInlineMod = hunk.kind === 'mod'
        && Array.isArray(hunk.baseText) && Array.isArray(hunk.draftText)
        && hunk.baseText.length === 1 && hunk.draftText.length === 1
        && matchedBlocks.length === 1
        && !splitPipeRow(hunk.baseText[0])
        && ['P', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'LI', 'BLOCKQUOTE'].includes(matchedBlocks[0].tagName);

      if (isSingleInlineMod) {
        const targetNode = matchedBlocks[0];
        if (!targetNode.hasAttribute('data-orig-inline-html')) {
          targetNode.setAttribute('data-orig-inline-html', targetNode.innerHTML);
        }
        const stripMdPrefix = s => String(s || '').replace(/^(?:#{1,6}\s+|>\s+|\s*[-*+]\s+|\s*\d+\.\s+)/, '');
        targetNode.innerHTML = renderWordDiffHtml(stripMdPrefix(hunk.baseText[0]), stripMdPrefix(hunk.draftText[0]), 'both');
        targetNode.append(createFloatingHunkPill(index, { includeViewToggle: false }));
        continue;
      }

      if (Array.isArray(hunk.baseText) && hunk.baseText.length) {
        const ghost = document.createElement('div');
        ghost.className = 'md-preview-deletion';
        ghost.setAttribute('data-md-diff-ghost', 'true');
        ghost.dataset.diffHunkIndex = String(index);

        const renderedDiv = document.createElement('div');
        renderedDiv.className = 'md-preview-deletion-rendered';
        renderedDiv.innerHTML = renderDeletedMarkdownHtml(hunk.baseText, hunk.draftText);
        renderedDiv.hidden = isRawMode;

        const oldRaw = document.createElement('div');
        oldRaw.className = 'md-preview-deletion-text';
        oldRaw.textContent = hunk.baseText.join('\n');
        oldRaw.hidden = !isRawMode;

        const pill = createFloatingHunkPill(index, { includeViewToggle: true });
        ghost.append(pill, renderedDiv, oldRaw);

        const anchor = blocks.find(block => block.line >= hunk.draftStart)?.node || null;
        if (anchor) anchor.insertAdjacentElement('beforebegin', ghost);
        else preview.append(ghost);
      } else if (matchedBlocks.length > 0) {
        matchedBlocks[0].append(createFloatingHunkPill(index, { includeViewToggle: false }));
      } else {
        const toolbar = document.createElement('div');
        toolbar.className = 'md-preview-hunk-actions';
        toolbar.dataset.diffHunkIndex = String(index);
        toolbar.append(hunkButtons(index));
        const anchor = blocks.find(block => block.line >= hunk.draftStart)?.node || null;
        if (anchor) anchor.insertAdjacentElement('beforebegin', toolbar);
        else preview.append(toolbar);
      }
    }

    renderConflictCardsInDom();
  };

  // Keep controls out of ProseMirror's editable DOM. An exact source-line
  // proof locates each toolbar; unproved blocks get actions in the fallback
  // panel, never an arbitrary nearby row.
  function parseTopLevelMarkdownBlocks(mdText) {
    const lines = String(mdText ?? '').replace(/\r\n?/g, '\n').split('\n');
    const blocks = [];
    let i = 0;
    while (i < lines.length) {
      if (!lines[i].trim()) { i++; continue; }
      const start = i;
      const line = lines[i];
      // Fenced code block
      const fenceMatch = line.match(/^\s*(`{3,}|~{3,})/);
      if (fenceMatch) {
        const fence = fenceMatch[1];
        i++;
        while (i < lines.length && !lines[i].trim().startsWith(fence)) i++;
        if (i < lines.length) i++;
        blocks.push({ startLine: start, endLine: i });
        continue;
      }
      // GFM pipe table
      if (line.trim().startsWith('|') || (i + 1 < lines.length && /^\s*\|?\s*:?-{2,}:?\s*\|/.test(lines[i + 1]))) {
        while (i < lines.length && lines[i].trim() && (lines[i].includes('|') || /^\s*:?-{2,}/.test(lines[i]))) i++;
        blocks.push({ startLine: start, endLine: i });
        continue;
      }
      // Heading
      if (/^#{1,6}\s+/.test(line)) {
        i++;
        blocks.push({ startLine: start, endLine: i });
        continue;
      }
      // List block (unordered or ordered)
      if (/^\s*(?:[-*+]|\d+\.)\s+/.test(line)) {
        while (i < lines.length && lines[i].trim() && (/^\s*(?:[-*+]|\d+\.)\s+/.test(lines[i]) || /^\s{2,}\S/.test(lines[i]))) i++;
        blocks.push({ startLine: start, endLine: i });
        continue;
      }
      // Blockquote
      if (/^\s*>/.test(line)) {
        while (i < lines.length && /^\s*>/.test(lines[i])) i++;
        blocks.push({ startLine: start, endLine: i });
        continue;
      }
      // Horizontal rule
      if (/^\s*(?:---+|\*\*\*+|___+)\s*$/.test(line)) {
        i++;
        blocks.push({ startLine: start, endLine: i });
        continue;
      }
      // Paragraph
      while (
        i < lines.length &&
        lines[i].trim() &&
        !/^#{1,6}\s+/.test(lines[i]) &&
        !/^\s*(?:`{3,}|~{3,})/.test(lines[i]) &&
        !/^\s*(?:[-*+]|\d+\.)\s+/.test(lines[i]) &&
        !/^\s*>/.test(lines[i]) &&
        !lines[i].trim().startsWith('|')
      ) {
        i++;
      }
      blocks.push({ startLine: start, endLine: Math.max(start + 1, i) });
    }
    return blocks;
  }

  const clearVisualHunkTools = () => {
    view.host?.querySelectorAll('.md-visual-hunk-actions,.md-visual-dom-pill-anchor,.md-visual-inline-deletion-box').forEach(node => node.remove());
    const pm = view.host?.querySelector('.md-visual-host .ProseMirror');
    if (pm) {
      pm.querySelectorAll('.md-visual-diff-add,.md-visual-diff-mod').forEach(el => {
        el.classList.remove('md-visual-diff-add', 'md-visual-diff-mod');
        el.removeAttribute('data-diff-hunk-index');
      });
    }
    view.host?.querySelector('.md-visual-host')?.classList.remove('has-diff-actions');
  };

  const showVisualHunkTools = (hunks, draftText = '') => {
    clearVisualHunkTools();
    const host = view.host?.querySelector('.md-visual-host');
    const pm = host?.querySelector('.ProseMirror');
    if (!host || !pm) return false;

    const pmChildren = [...pm.children].filter(el => !el.classList.contains('ProseMirror-gapcursor'));
    const mdBlocks = parseTopLevelMarkdownBlocks(draftText || getEditorText());
    const hostRect = host.getBoundingClientRect();
    let mappedCount = 0;

    for (const [index, hunk] of hunks.entries()) {
      let matchedEls = [];
      const primaryBlock = typeof view.instance?.sourceBlockAtLine === 'function'
        ? view.instance.sourceBlockAtLine(hunk.draftStart + 1)
        : null;
      if (primaryBlock && host.contains(primaryBlock)) {
        matchedEls.push(primaryBlock);
      } else if (pmChildren.length && mdBlocks.length) {
        for (let bIdx = 0; bIdx < mdBlocks.length; bIdx++) {
          const mb = mdBlocks[bIdx];
          const overlaps = (hunk.draftEnd > hunk.draftStart)
            ? (mb.startLine < hunk.draftEnd && mb.endLine > hunk.draftStart)
            : (mb.startLine >= hunk.draftStart);
          if (overlaps) {
            const domIdx = Math.min(pmChildren.length - 1, Math.round((bIdx / Math.max(1, mdBlocks.length - 1)) * Math.max(0, pmChildren.length - 1)));
            const el = pmChildren[bIdx] || pmChildren[domIdx];
            if (el && !matchedEls.includes(el)) matchedEls.push(el);
            if (hunk.draftEnd <= hunk.draftStart) break;
          }
        }
        if (!matchedEls.length && pmChildren.length) {
          matchedEls.push(pmChildren[Math.min(pmChildren.length - 1, Math.max(0, hunk.draftStart))]);
        }
      }

      if (!matchedEls.length) continue;
      mappedCount += 1;

      if (hunk.kind === 'add' || hunk.kind === 'mod') {
        matchedEls.forEach(el => {
          el.classList.add(hunk.kind === 'add' ? 'md-visual-diff-add' : 'md-visual-diff-mod');
          el.dataset.diffHunkIndex = String(index);
        });
      }

      const firstEl = matchedEls[0];
      const blockRect = firstEl.getBoundingClientRect();
      const topOffset = Math.max(2, blockRect.top - hostRect.top - 24);

      const pillAnchor = document.createElement('div');
      pillAnchor.className = 'md-visual-dom-pill-anchor';
      pillAnchor.style.top = `${topOffset}px`;
      const hasDel = Array.isArray(hunk.baseText) && hunk.baseText.length > 0;
      const pill = createFloatingHunkPill(index, { includeViewToggle: hasDel });
      pill.style.position = 'static';
      pill.style.opacity = '1';
      pill.style.pointerEvents = 'auto';
      pill.style.transform = 'none';
      pillAnchor.append(pill);

      const showPill = () => pillAnchor.classList.add('is-visible');
      const hidePill = () => pillAnchor.classList.remove('is-visible');
      matchedEls.forEach(el => {
        el.addEventListener('pointerenter', showPill, { passive: true });
        el.addEventListener('pointerleave', hidePill, { passive: true });
      });
      pillAnchor.addEventListener('pointerenter', showPill, { passive: true });
      pillAnchor.addEventListener('pointerleave', hidePill, { passive: true });

      host.append(pillAnchor);
    }
    return mappedCount > 0;
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
    const isRawMode = getDiffViewMode() === 'raw';
    for (const [index, hunk] of hunks.entries()) {
      const ghost = document.createElement('div');
      ghost.className = 'md-preview-deletion';
      ghost.dataset.mdDiffGhost = 'true';
      ghost.dataset.diffHunkIndex = String(index);
      const baseLines = Array.isArray(hunk.baseText) && hunk.baseText.length ? hunk.baseText : (hunk.draftText || []);
      const renderedDiv = document.createElement('div');
      renderedDiv.className = 'md-preview-deletion-rendered';
      renderedDiv.innerHTML = renderDeletedMarkdownHtml(baseLines, hunk.draftText);
      renderedDiv.hidden = isRawMode;
      const oldRaw = document.createElement('div');
      oldRaw.className = 'md-preview-deletion-text';
      oldRaw.textContent = baseLines.join('\n');
      oldRaw.hidden = !isRawMode;
      ghost.append(createFloatingHunkPill(index, { includeViewToggle: true }), renderedDiv, oldRaw);
      panel.append(ghost);
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
    // Pass raw Milkdown text to setPendingDiff so LT(t, e) never fails on e !== t.getMarkdown()
    const rawMilkdownText = view.instance.getMarkdown ? view.instance.getMarkdown() : draftText;
    const result = typeof view.instance.setPendingDiff === 'function'
      ? (view.instance.setPendingDiff(rawMilkdownText, hunks) || {})
      : { mapped: false };
    const domMapped = showVisualHunkTools(hunks, draftText);
    if (result.mapped || domMapped) {
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
    const editorText = getEditorText();
    // Visual serialization can reformat a complex Markdown table without a
    // human edit. Pending diff compares md_temp to the real project bytes.
    const text = matchesLastSaved(editorText) ? view.ackedText : editorText;
    const hunks = diff.diffLines(diffBaseline(), text);
    view.hunks = hunks;
    if (view.mode === 'source') renderSourceDiff(hunks, text);
    else if (view.mode === 'visual') renderVisualDiff(hunks, text);
    document.documentElement.dataset.mdPendingHunks = String(hunks.length);
    updateStickyDiffBar(hunks);
    syncParallelSecondaryPane(text, hunks);
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
          status('File changed in VS Code/Lanbot while you typed. Local text is retained; resolve overlapping edits in Source.', 'warn');
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

  function setBotEditorLock(locked) {
    const isLocked = Boolean(locked);
    root?.classList.toggle('md-bot-turn-locked', isLocked);
    if (view.host) view.host.classList.toggle('md-bot-turn-locked', isLocked);
    if (secondaryPane) secondaryPane.classList.toggle('md-bot-turn-locked', isLocked);
    try {
      if (typeof view.instance?.setReadonly === 'function') {
        view.instance.setReadonly(isLocked);
      }
      if (typeof secondaryVisualInstance?.setReadonly === 'function') {
        secondaryVisualInstance.setReadonly(isLocked);
      }
    } catch (_) {}
    restoreButtons();
  }

  function ensureBotShimmerBanner() {
    let banner = document.getElementById('mdBotShimmerBanner');
    if (banner) return banner;
    ensureShellStyle();
    banner = document.createElement('div');
    banner.id = 'mdBotShimmerBanner';
    banner.className = 'md-bot-shimmer-banner';
    banner.hidden = true;
    const text = document.createElement('span');
    text.id = 'mdBotShimmerText';
    text.textContent = '🔒 File is locked while Lanbot is editing — user edits & mode switches are paused to prevent conflicts';
    const unlockBtn = document.createElement('button');
    unlockBtn.type = 'button';
    unlockBtn.className = 'md-hunk-button';
    unlockBtn.textContent = '✕ Force Unlock (Esc)';
    unlockBtn.addEventListener('click', () => cancelBotTurn());
    banner.append(text, unlockBtn);
    preview.insertAdjacentElement('beforebegin', banner);
    return banner;
  }

  function resetBotWatchdog() {
    clearTimeout(view.botWatchdogTimer);
    if (!view.piTurn) return;
    // Keep file locked for the entire active bot turn (up to 180s idle between stream events);
    // never auto-flush browser draft on watchdog expiry so the bot's disk edits are never overwritten.
    view.botWatchdogTimer = setTimeout(() => {
      if (view.piTurn) {
        view.piTurn = null;
        setBotEditorLock(false);
        const banner = document.getElementById('mdBotShimmerBanner');
        if (banner) banner.hidden = true;
      }
    }, 180000);
  }

  const touchBotTurn = () => {
    if (view.piTurn) resetBotWatchdog();
  };

  const undoLastBotTurn = async () => {
    if (!view.botUndoStack.length) return false;
    const snap = view.botUndoStack.pop();
    if (!snap || typeof snap.text !== 'string') return false;
    await applyWorkingText(snap.text, view.workHash, { backed: false });
    await flushWorkingCopy(snap.text);
    updateStickyDiffBar(view.hunks || []);
    status('Restored document to snapshot before the last Lanbot turn.', 'info');
    return true;
  };

  const beginBotTurn = async (options = {}) => {
    // Issue 5 & 11: Auto-clear stale piTurn lock from any prior finished or aborted turn
    if (view.piTurn) {
      view.piTurn = null;
    }
    if (globalThis.__lanternMdPaged?.active)
      await globalThis.__lanternMdPaged.beginBotTurn();

    let base;
    if (view.active && view.instance) {
      try {
        if (!view.version) {
          const st = await fetchWorkState();
          if (st?.saved) {
            view.version = st.saved.version;
            view.currentVersion = st.currentVersion;
            view.baseline = st.saved.content;
            view.workHash = st.work?.hash || null;
          }
        }
        if (!options?.skipDraftFlush) {
          await saveDraft();
        }
      } catch (_) {}
      base = options?.skipDraftFlush ? (view.ackedText || view.baseline || getEditorText()) : getEditorText();
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
    // Layer 1: Push pre-bot undo checkpoint
    view.botUndoStack.push({ at: Date.now(), text: String(base ?? '') });
    if (view.botUndoStack.length > 10) view.botUndoStack.shift();

    clearTimeout(view.draftTimer);
    clearTimeout(view.checkTimer);
    clearTimeout(splitRenderTimer);
    view.piTurn = {
      base: String(base ?? ''),
      expectedRevision: view.revision,
    };
    setBotEditorLock(true);
    const banner = ensureBotShimmerBanner();
    banner.hidden = false;
    resetBotWatchdog();
    status('🔒 File locked while Lanbot is editing the real .md.', 'info');
    return view.workHash || null;
  };

  const cancelBotTurn = () => {
    clearTimeout(view.botWatchdogTimer);
    view.piTurn = null;
    setBotEditorLock(false);
    const banner = document.getElementById('mdBotShimmerBanner');
    if (banner) banner.hidden = true;
    globalThis.__lanternMdPaged?.cancelBotTurn?.();
  };

  const onWorkLocked = (eventPath, locked) => {
    const normEvent = String(eventPath || '').replace(/\\/g, '/').replace(/^\/+/, '');
    const normPath = String(path || '').replace(/\\/g, '/').replace(/^\/+/, '');
    if (normEvent && normEvent !== normPath) return;
    if (locked) {
      if (!view.piTurn) {
        view.piTurn = {
          base: String(view.ackedText || view.baseline || ''),
          expectedRevision: view.revision,
        };
      }
      setBotEditorLock(true);
      const banner = ensureBotShimmerBanner();
      banner.hidden = false;
      resetBotWatchdog();
      status('🔒 File locked while Lanbot is editing the real .md.', 'info');
    } else if (view.piTurn) {
      cancelBotTurn();
    }
  };

  const applyWorkingText = async (text, hash, { backed = true } = {}) => {
    const next = String(text ?? '');
    const bookmark = capturePosition();
    const y = scrollY;
    if (!view.active || view.mode === 'preview') {
      await renderDraftPreview(next);
      preview.hidden = false;
    } else if (view.mode === 'source' && view.instance?.replaceExternalText) {
      if (view.instance.replaceExternalText(next, {acknowledge: backed})) view.revision += 1;
    } else if (view.mode === 'visual') {
      const engine = await loadBundle();
      const host = view.host?.querySelector('.md-visual-host');
      if (!host) throw new Error('Visual editor host is unavailable');
      view.applyingPi = true;
      try {
        await view.instance?.destroy?.();
        host.textContent = '';
        view.instance = await engine.createVisualMarkdown(host, prepareVisualTableMarkdown(next), changed, path, status);
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
    const normEvent = String(eventPath || '').replace(/\\/g, '/').replace(/^\/+/, '');
    const normPath = String(path || '').replace(/\\/g, '/').replace(/^\/+/, '');
    if (normEvent && normEvent !== normPath) return;
    const turn = view.piTurn || { base: view.ackedText || view.baseline || '', expectedRevision: view.revision };
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
      resetBotWatchdog();
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
    clearTimeout(view.botWatchdogTimer);
    view.piTurn = null;
    setBotEditorLock(false);
    const shimmerEl = document.getElementById('mdBotShimmerBanner');
    if (shimmerEl) shimmerEl.hidden = true;
    view.currentVersion = state.currentVersion;
    if (!humanChanged) {
      await applyWorkingText(piText, serverHash, { backed: true });
      status('Lanbot updated the real .md. Ctrl+S accepts it as the comparison baseline.', 'info');
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
      throw new Error('Unable to reconcile your typing with Lanbot working-copy changes');
    }
    clearTimeout(view.botWatchdogTimer);
    const banner = document.getElementById('mdBotShimmerBanner');
    if (banner) banner.hidden = true;
    if (conflicts.length) {
      view.activeConflicts = conflicts.map((c, idx) => ({ ...c, id: `conflict-${Date.now()}-${idx}`, currentMerged: merged }));
      renderConflictCardsInDom();
      status('Lanbot finished; ' + conflicts.length +
        ' overlapping hunk(s) were skipped because your newer text wins.', 'warn');
    } else if (appliedPiHunks) {
      view.activeConflicts = [];
      status('Lanbot changes merged into the real .md; diff remains visible.', 'info');
    } else {
      view.activeConflicts = [];
      status('Your newer typing is preserved; Lanbot made no additional non-overlapping changes.', 'info');
    }
    updateStickyDiffBar(view.hunks || []);
  };

  // Every edit goes to the project .md, not md_temp. A CAS rejects writes
  // based on stale file versions (VS Code, bot, or another browser).
  let writingReal = null;

  const flushSourcePatches = async () => {
    if (!view.version || !view.instance?.takePendingPatches || view.piTurn) return false;
    if (view.conflict) {
      await drafts.write(getEditorText()).catch(() => {});
      status('Resolve the concurrent Source edit before writing again.', 'error');
      return false;
    }
    if (writingReal) await writingReal;
    if (!view.instance?.hasPendingPatches?.()) return true;

    const task = (async () => {
      while (view.instance?.hasPendingPatches?.()) {
        const batch = view.instance.takePendingPatches();
        if (!batch) break;
        try {
          const result = await api('/api/work/patch', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              path,
              patches: batch.patches,
              expectHash: view.workHash || null,
              baseVersion: view.version,
            }),
          });
          view.instance.acknowledgePatches(batch);
          const persistedText = batch.after.toString();
          view.workHash = result.hash || null;
          view.currentVersion = result.currentVersion;
          view.workState = result.state;
          view.ackedText = persistedText;
          view.lastSaved = persistedText;
          view.conflict = false;
          view.dirty = cleanLineEndings(persistedText) !== cleanLineEndings(view.baseline);
          renderDraftDiff();
        } catch (error) {
          view.instance?.rejectPatches?.(batch);
          const local = getEditorText();
          await drafts.write(local).catch(() => {});
          if (error.status === 409) {
            try {
              const state = await fetchWorkState();
              if (state?.saved) {
                const actual = state.work?.content ?? state.saved.content;
                const merge = diffApi()?.merge3(view.ackedText, local, actual);
                view.currentVersion = state.currentVersion;
                view.workHash = state.work?.hash || null;
                view.workState = state.state || (view.workHash ? 'pending' : 'clean');
                if (merge && !merge.conflicts?.length) {
                  // Rebase only against the freshly fetched CAS version. Reset
                  // the Source adapter's acknowledged coordinates to that real
                  // text, then re-queue the merged local delta as new patches.
                  adoptSavedBaseline(state);
                  view.lastSaved = actual;
                  view.ackedText = actual;
                  view.instance.replaceExternalText(actual, {acknowledge: true});
                  view.instance.replaceExternalText(merge.text, {acknowledge: false});
                  renderDraftDiff();
                  continue;
                }
              }
            } catch (_) {}
            view.conflict = true;
            status('Real .md changed concurrently. Overlapping Source edits are retained locally; review before retrying.', 'error');
            return false;
          }
          if (error.status === 404) {
            view.conflict = true;
            view.workState = 'missing';
            syncStatusVisibility();
            status('Project .md unavailable; local Source recovery text retained.', 'error');
            return false;
          }
          status('Cannot patch project .md: ' + error.message + '. Local Source edit retained.', 'error');
          return false;
        }
      }
      if (view.instance?.hasPendingPatches?.())
        await drafts.write(getEditorText()).catch(() => {});
      else
        await drafts.clear().catch(() => {});
      return true;
    })();

    writingReal = task;
    try { return await task; }
    finally { if (writingReal === task) writingReal = null; }
  };

  const flushWorkingCopy = async (text = getEditorText()) => {
    if (!view.version) return false;
    if (view.piTurn) {
      await drafts.write(text).catch(() => {});
      status('Lanbot is editing the real .md; your typing will merge when its turn ends.', 'warn');
      return false;
    }
    if (view.mode === 'source') return flushSourcePatches();
    if (writingReal) {
      await writingReal;
      if (view.active && view.instance && matchesLastSaved(getEditorText())) return true;
      text = view.active && view.instance ? getEditorText() : text;
    }
    if (text === view.lastSaved) return true;
    if (view.mode === 'visual' && !view.roundtripSafe && !view.approvedReformat) {
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
    if (view.mode === 'source' && view.instance?.hasPendingPatches?.())
      return flushWorkingCopy(text);
    if (matchesLastSaved(text)) return true;
    return flushWorkingCopy(text);
  };
  const queueDraft = () => {
    clearTimeout(view.draftTimer);
    view.draftTimer = setTimeout(() => { void saveDraft(); }, 110);
  };
  const changed = () => {
    if (!view.active || view.applyingPi || view.piTurn) return;
    if (view.mode === 'visual' && typeof view.instance?.isCleanFromMount === 'function' && view.instance.isCleanFromMount()) {
      return;
    }
    view.dirty = true;
    view.revision += 1;
    status(view.conflict ? 'Concurrent file edit: reviewing changes before writing.' :
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
          'Ready. No pending changes.');
        return;
      }
      queueDraft();
      renderDraftDiff();
    }, 45);
  };
  const restoreButtons = () => {
    const paged = !!window.__lanternMdPaged?.active;
    const botLocked = !!view.piTurn;
    root?.classList.toggle('md-editing', view.active || paged);
    trigger.disabled = view.loading || view.saving || paged || botLocked;
    trigger.textContent = paged ? 'Editing by section' : 'Edit visually';
    sourceTrigger.disabled = view.loading || view.saving || botLocked;
    previewTrigger.disabled = view.loading || view.saving || botLocked;
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
  const loadSourceBundle = async () => {
    if (window.LanternSourceEditor) return window.LanternSourceEditor;
    if (window.__lanternSourcePromise) return window.__lanternSourcePromise;
    window.__lanternSourcePromise = new Promise((resolve, reject) => {
      ensureShellStyle();
      const script = document.createElement('script');
      script.src = '/static/vendor/lantern-source-editor.min.js';
      script.nonce = nonce;
      script.onload = () => window.LanternSourceEditor
        ? resolve(window.LanternSourceEditor)
        : reject(new Error('Source editor not initialized'));
      script.onerror = () => reject(new Error('Offline Source editor asset unavailable'));
      document.head.appendChild(script);
    }).catch(err => { window.__lanternSourcePromise = null; throw err; });
    return window.__lanternSourcePromise;
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
    view.sourceHost = null;
    view.visualDiffFallback = null;
    const shell = document.createElement('section');
    shell.className = 'md-visual-shell';
    // Editing actions and status belong to the fixed page header.
    const editorHost = document.createElement('div');
    editorHost.className = 'md-visual-host';
    editorHost.id = 'md-visual-edit-' + escapeCss(path);
    if (kind === 'source') {
      const wrap = document.createElement('div');
      wrap.className = 'md-source-editor-wrap';
      wrap.dataset.wrap = localStorage.getItem('lantern-md-source-wrap') === 'off' ? 'off' : 'on';
      const hunkBar = document.createElement('div');
      hunkBar.className = 'md-source-hunk-list';
      hunkBar.hidden = true;
      const mount = document.createElement('div');
      mount.className = 'md-source-editor-mount';
      wrap.append(hunkBar, mount);
      editorHost.append(wrap);
      view.sourceHost = mount;
      view.sourceHunkBar = hunkBar;
      view.sourceWrapEl = wrap;
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
      if (view.piTurn) status('Wait until Lanbot finishes before accepting diff.', 'warn');
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
      void refreshImageAudit();
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
    if (!view.active || view.loading || view.saving || view.piTurn || kind === view.mode) return;
    const bookmark = requestedBookmark || capturePosition();
    const y = requestedY ?? scrollY;
    const contentNow = getEditorText();
    // Milkdown may emit a mount transaction without changing Markdown.
    // Compare content, not its transient dirty flag, before switching modes.
    const wasDirty = !matchesLastSaved(contentNow);
    if (kind === 'visual' && new Blob([contentNow]).size > FULL_VISUAL_LIMIT_BYTES) {
      if (wasDirty || view.workHash) {
        status('Pending changes — use Source, or Save/Discard before section-based Visual Edit.', 'warn');
        return;
      }
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
    const oldSafe = view.roundtripSafe;
    const oldApproved = view.approvedReformat;
    let engine = null;
    try {
      if (kind === 'visual') engine = await loadBundle();
      else if (kind === 'source') engine = await loadSourceBundle();
    } catch (error) {
      status('Cannot load ' + (kind === 'source' ? 'Source' : 'Visual') +
        ' editor: ' + error.message, 'error');
      return;
    }
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
        view.instance = await engine.createVisualMarkdown(editorHost, prepareVisualTableMarkdown(contents), changed, path, status);
      } else if (kind === 'source') {
        view.instance = engine.createSourceMarkdown(
          view.sourceHost, contents, changed, actionHunk,
          {acknowledgedText: view.ackedText}
        );
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
    if (view.lastRenderedPreviewText === text && preview.innerHTML.trim()) {
      const diff = diffApi();
      const hunks = diff ? diff.diffLines(String(view.baseline || ''), text) : [];
      view.hunks = hunks;
      renderPreviewDiff(hunks, text);
      updateStickyDiffBar(hunks);
      document.documentElement.dataset.mdPendingHunks = String(hunks.length);
      return;
    }
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
    view.lastRenderedPreviewText = text;
    renderPreviewDiff(hunks, text);
    updateStickyDiffBar(hunks);
    document.documentElement.dataset.mdPendingHunks = String(hunks.length);
  }

  async function hydratePendingPreview() {
    if (view.active || view.loading) return;
    try {
      const state = await fetchWorkState();
      if (view.active || view.loading) return;
      if (!state.saved) return;
      if (state.turnActive || state.botLocked) {
        onWorkLocked(path, true);
      }
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
    if (!view.active || view.saving || view.loading || view.piTurn) return;
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
    if (view.piTurn) {
      status('🔒 File is locked while Lanbot is working. Wait for the turn to finish.', 'warn');
      return;
    }
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
      const engine = kind === 'visual'
        ? await loadBundle()
        : kind === 'source'
          ? await loadSourceBundle()
          : null;
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
        view.instance = await engine.createVisualMarkdown(editorHost, prepareVisualTableMarkdown(contents), changed, path, status);
      } else if (kind === 'source') {
        view.instance = engine.createSourceMarkdown(
          view.sourceHost, contents, changed, actionHunk,
          {acknowledgedText: view.ackedText}
        );
      }
      view.mode = kind;
      const restoredDraft = contents !== doc.content;
      view.ackedText = serverWork?.content ?? doc.content;
      const serialized = getEditorText();
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
        'Real .md is live. Ctrl+S accepts the comparison baseline.',
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


  // --- Top-Left Sticky Diff Bar, Interactive 1/N Hunk Picker, Global Diff Mode, Independent Split Scroll + Double-Click to Jump & Telemetry ---
  let splitMode = 'off'; // 'off' | 'E-P' | 'S-P' | 'S-E'
  let splitSwap = false;
  let secondaryPane = null;
  let secondaryVisualInstance = null;
  let syncingSplit = false;
  let splitRenderTimer = 0;
  let lastSecondarySyncedText = '';
  let hunkDropdownOpen = false;
  let scrollMasterRole = 'primary';

  function ensureStickyDiffBar() {
    let bar = document.getElementById('mdStickyDiffBar');
    if (bar) return bar;
    ensureShellStyle();
    bar = document.createElement('div');
    bar.id = 'mdStickyDiffBar';
    bar.className = 'md-sticky-diff-bar';
    bar.hidden = true;
    preview.insertAdjacentElement('beforebegin', bar);
    return bar;
  }

  async function discardAllDiff() {
    if (view.saving || view.piTurn) return;
    try {
      const state = await fetchWorkState();
      if (!state?.saved) return;
      if (state.work?.hash) {
        await api('/api/work/discard', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path, expectHash: state.work.hash }),
        });
      }
      const baseline = state.saved.content;
      view.version = state.saved.version;
      view.currentVersion = state.saved.version;
      view.baseline = baseline;
      view.workHash = null;
      view.workState = 'clean';
      view.ackedText = baseline;
      view.lastSaved = baseline;
      view.dirty = false;
      await drafts.clear().catch(() => {});
      if (view.active) await applyWorkingText(baseline, null, { backed: true });
      else await renderDraftPreview(baseline);
      renderDraftDiff();
      status('Reverted all pending changes back to accepted md_temp baseline.', 'info');
    } catch (err) {
      status('Cannot discard diff: ' + err.message, 'error');
    }
  }

  function jumpToDiffHunk(targetIdx) {
    const hunks = Array.isArray(view.hunks) ? view.hunks : [];
    if (!hunks.length) return;
    view.currentHunkIdx = ((targetIdx % hunks.length) + hunks.length) % hunks.length;
    const h = hunks[view.currentHunkIdx];
    const lineNo = Math.max(1, (h.draftStart || 0) + 1);
    view.lastActiveLine = lineNo;
    if (view.mode === 'source' && view.instance?.restoreBookmark) {
      view.instance.restoreBookmark({ line: lineNo, column: 0 });
    } else if (view.mode === 'visual' && view.instance?.sourceBlockAtLine) {
      const blk = view.instance.sourceBlockAtLine(lineNo);
      if (blk) {
        blk.scrollIntoView({ behavior: 'smooth', block: 'center' });
        flashFocusSyncTarget(blk, lineNo);
      }
    } else {
      const node = preview.querySelector(`[data-diff-hunk-index="${view.currentHunkIdx}"]`)
        || preview.querySelector(`[data-l="${lineNo}"]`);
      if (node) {
        node.scrollIntoView({ behavior: 'smooth', block: 'center' });
        flashFocusSyncTarget(node, lineNo);
      }
    }
    hunkDropdownOpen = false;
    updateStickyDiffBar(hunks);
  }

  function renderConflictCardsInDom() {
    document.querySelectorAll('.md-conflict-card').forEach(el => el.remove());
    const conflicts = Array.isArray(view.activeConflicts) ? view.activeConflicts : [];
    if (!conflicts.length) return;
    const bar = ensureStickyDiffBar();
    conflicts.forEach((conf, cIdx) => {
      const card = document.createElement('div');
      card.className = 'md-conflict-card';
      const head = document.createElement('div');
      head.className = 'md-conflict-head';
      head.textContent = `⚠️ Overlapping edit on lines ${conf.baseStart + 1}–${Math.max(conf.baseStart + 1, conf.baseEnd)} (You & Lanbot edited the same region)`;

      const grid = document.createElement('div');
      grid.className = 'md-conflict-grid';

      const oursPane = document.createElement('div');
      oursPane.className = 'md-conflict-pane ours';
      const oursTitle = document.createElement('div');
      oursTitle.className = 'md-conflict-pane-title';
      oursTitle.textContent = '👤 Layer 1: Your Local Edit (Preserved safely)';
      const oursBody = document.createElement('div');
      oursBody.textContent = (conf.oursText || []).join('\n') || '(Deleted lines)';
      oursPane.append(oursTitle, oursBody);

      const theirsPane = document.createElement('div');
      theirsPane.className = 'md-conflict-pane theirs';
      const theirsTitle = document.createElement('div');
      theirsTitle.className = 'md-conflict-pane-title';
      theirsTitle.textContent = '🏮 Layer 2: Lanbot Proposed Edit';
      const theirsBody = document.createElement('div');
      theirsBody.textContent = (conf.piText || []).join('\n') || '(Deleted lines)';
      theirsPane.append(theirsTitle, theirsBody);

      grid.append(oursPane, theirsPane);

      const actions = document.createElement('div');
      actions.className = 'md-conflict-actions';

      const applyChoice = async mode => {
        const currentDoc = view.active ? getEditorText() : (view.ackedText || view.baseline || '');
        const oursBlock = (conf.oursText || []).join('\n');
        const piBlock = (conf.piText || []).join('\n');
        let nextDoc = currentDoc;
        if (mode === 'theirs' && oursBlock && currentDoc.includes(oursBlock)) {
          nextDoc = currentDoc.replace(oursBlock, piBlock);
        } else if (mode === 'both' && oursBlock && currentDoc.includes(oursBlock)) {
          nextDoc = currentDoc.replace(oursBlock, `${oursBlock}\n${piBlock}`);
        }
        view.activeConflicts.splice(cIdx, 1);
        await applyWorkingText(nextDoc, view.workHash, { backed: false });
        await flushWorkingCopy(nextDoc);
        renderConflictCardsInDom();
      };

      const keepOursBtn = document.createElement('button');
      keepOursBtn.type = 'button';
      keepOursBtn.className = 'md-hunk-button';
      keepOursBtn.textContent = '👤 Keep Mine';
      keepOursBtn.addEventListener('click', () => { void applyChoice('ours'); });

      const acceptAiBtn = document.createElement('button');
      acceptAiBtn.type = 'button';
      acceptAiBtn.className = 'md-hunk-button';
      acceptAiBtn.style.background = '#1f4934';
      acceptAiBtn.style.borderColor = '#55ce7a';
      acceptAiBtn.textContent = '🏮 Accept Lanbot';
      acceptAiBtn.addEventListener('click', () => { void applyChoice('theirs'); });

      const mergeBothBtn = document.createElement('button');
      mergeBothBtn.type = 'button';
      mergeBothBtn.className = 'md-hunk-button';
      mergeBothBtn.textContent = '🔗 Merge Both';
      mergeBothBtn.addEventListener('click', () => { void applyChoice('both'); });

      actions.append(keepOursBtn, acceptAiBtn, mergeBothBtn);
      card.append(head, grid, actions);
      bar.insertAdjacentElement('afterend', card);
    });
  }

  function summarizeHunkSnippet(h) {
    const sample = (Array.isArray(h.draftText) && h.draftText.length ? h.draftText : h.baseText) || [];
    const firstNonEmpty = sample.find(l => String(l || '').trim()) || sample[0] || '';
    const clean = String(firstNonEmpty).trim().replace(/\s+/g, ' ');
    return clean.length > 48 ? clean.slice(0, 48) + '…' : (clean || 'Empty line');
  }

  function updateStickyDiffBar(hunks = view.hunks || []) {
    const bar = ensureStickyDiffBar();
    const count = Array.isArray(hunks) ? hunks.length : 0;
    if (!count && !view.botUndoStack.length) {
      bar.hidden = true;
      bar.textContent = '';
      return;
    }
    bar.hidden = false;
    bar.textContent = '';
    const label = document.createElement('span');
    label.className = 'md-sticky-diff-count';
    label.textContent = count
      ? `🔀 ${count} diff hunk${count > 1 ? 's' : ''} pending`
      : '🛡️ Pre-bot checkpoint ready';

    const actions = document.createElement('div');
    actions.className = 'md-sticky-diff-actions';

    if (count > 0) {
      const navGroup = document.createElement('div');
      navGroup.className = 'md-diff-nav-group';
      const prevBtn = document.createElement('button');
      prevBtn.type = 'button';
      prevBtn.className = 'md-hunk-button';
      prevBtn.textContent = '↑ Prev';
      prevBtn.title = 'Previous diff hunk (Alt+[)';
      prevBtn.addEventListener('click', () => jumpToDiffHunk((view.currentHunkIdx || 0) - 1));

      const safeIdx = Math.min(count, Math.max(1, (view.currentHunkIdx || 0) + 1));
      const navBadgeBtn = document.createElement('button');
      navBadgeBtn.type = 'button';
      navBadgeBtn.id = 'mdDiffHunkPickerBtn';
      navBadgeBtn.className = 'md-diff-nav-badge-btn';
      navBadgeBtn.title = 'Click to view all diff hunks and jump directly';
      navBadgeBtn.textContent = `${safeIdx}/${count} ▾`;

      const dropdown = document.createElement('div');
      dropdown.className = 'md-diff-hunk-dropdown';
      dropdown.hidden = !hunkDropdownOpen;
      hunks.forEach((h, idx) => {
        const opt = document.createElement('button');
        opt.type = 'button';
        opt.className = 'md-diff-hunk-option' + (idx === (view.currentHunkIdx || 0) ? ' active' : '');
        const lineNo = Math.max(1, (h.draftStart || 0) + 1);
        const meta = document.createElement('span');
        meta.className = 'md-diff-hunk-option-meta';
        meta.textContent = `#${idx + 1} · ${String(h.kind || 'mod').toUpperCase()} L${lineNo}`;
        const snip = document.createElement('span');
        snip.className = 'md-diff-hunk-option-snip';
        snip.textContent = summarizeHunkSnippet(h);
        opt.append(meta, snip);
        opt.addEventListener('click', ev => {
          ev.stopPropagation();
          jumpToDiffHunk(idx);
        });
        dropdown.appendChild(opt);
      });

      navBadgeBtn.addEventListener('click', ev => {
        ev.stopPropagation();
        hunkDropdownOpen = !hunkDropdownOpen;
        dropdown.hidden = !hunkDropdownOpen;
      });

      const nextBtn = document.createElement('button');
      nextBtn.type = 'button';
      nextBtn.className = 'md-hunk-button';
      nextBtn.textContent = '↓ Next';
      nextBtn.title = 'Next diff hunk (Alt+])';
      nextBtn.addEventListener('click', () => jumpToDiffHunk((view.currentHunkIdx || 0) + 1));

      navGroup.append(prevBtn, navBadgeBtn, nextBtn, dropdown);
      actions.append(navGroup);

      const diffModeBtn = document.createElement('button');
      diffModeBtn.type = 'button';
      diffModeBtn.id = 'mdGlobalDiffViewModeBtn';
      diffModeBtn.className = 'md-hunk-button';
      const isRaw = getDiffViewMode() === 'raw';
      diffModeBtn.textContent = isRaw ? '📝 Diff: Raw' : '👁 Diff: Visual';
      diffModeBtn.title = 'Toggle all deletion blocks between Visual HTML and Raw Markdown (persisted)';
      diffModeBtn.addEventListener('click', () => {
        setDiffViewMode(getDiffViewMode() === 'raw' ? 'visual' : 'raw');
      });
      actions.append(diffModeBtn);

      const acceptAllBtn = document.createElement('button');
      acceptAllBtn.type = 'button';
      acceptAllBtn.className = 'md-hunk-button';
      acceptAllBtn.style.background = '#1f4934';
      acceptAllBtn.style.borderColor = '#55ce7a';
      acceptAllBtn.textContent = '✓ Accept All (Ctrl+S)';
      acceptAllBtn.addEventListener('click', () => { void save(true); });

      const undoAllBtn = document.createElement('button');
      undoAllBtn.type = 'button';
      undoAllBtn.className = 'md-hunk-button';
      undoAllBtn.style.background = '#3c1d24';
      undoAllBtn.style.borderColor = '#eb6c75';
      undoAllBtn.textContent = '↶ Undo All';
      undoAllBtn.addEventListener('click', () => { void discardAllDiff(); });

      actions.append(acceptAllBtn, undoAllBtn);
    }

    if (view.botUndoStack.length > 0) {
      const undoBotBtn = document.createElement('button');
      undoBotBtn.type = 'button';
      undoBotBtn.className = 'md-hunk-button';
      undoBotBtn.title = 'Restore document snapshot from before the last Lanbot turn';
      undoBotBtn.textContent = '↶ Undo Last Bot Edit';
      undoBotBtn.addEventListener('click', () => { void undoLastBotTurn(); });
      actions.append(undoBotBtn);
    }

    bar.append(label, actions);
  }

  document.addEventListener('click', () => {
    if (hunkDropdownOpen) {
      hunkDropdownOpen = false;
      const dd = document.querySelector('.md-diff-hunk-dropdown');
      if (dd) dd.hidden = true;
    }
  });

  function renderSourceHunkChips(hunks = []) {
    const bar = view.sourceHunkBar;
    if (!bar) return;
    if (!Array.isArray(hunks) || !hunks.length) {
      bar.hidden = true;
      bar.textContent = '';
      return;
    }
    bar.hidden = false;
    bar.textContent = '';
    hunks.forEach((h, idx) => {
      const chip = document.createElement('div');
      chip.className = 'md-source-hunk-chip';
      const tag = document.createElement('span');
      tag.className = 'hunk-line-tag';
      const lineNo = Math.max(1, (h.draftStart || 0) + 1);
      tag.textContent = `#${idx + 1} (${h.kind.toUpperCase()} L${lineNo})`;
      tag.title = 'Click to jump to line ' + lineNo;
      tag.addEventListener('click', () => {
        view.instance?.restoreBookmark?.({ line: lineNo, column: 0 });
      });
      const btns = hunkButtons(idx);
      chip.append(tag, btns);
      bar.append(chip);
    });
  }

  function ensureSecondaryPane() {
    if (secondaryPane) return secondaryPane;
    secondaryPane = document.createElement('div');
    secondaryPane.className = 'md-secondary-pane';
    secondaryPane.dataset.paneRole = 'secondary';
    secondaryPane.hidden = true;
    root?.appendChild(secondaryPane);
    return secondaryPane;
  }

  // --- Step 4 (v7): Independent Split-Pane Scrolling + Double-Click to Jump (No Auto Scroll-Lock Jitter) ---
  function getPrimaryPaneEl() {
    return view.host || null;
  }

  function getSecondaryPaneEl() {
    if (splitMode === 'S-E') return secondaryPane;
    if (splitMode === 'E-P' || splitMode === 'S-P') return preview;
    return null;
  }

  function getTotalDocLines() {
    const txt = view.active ? getEditorText() : (view.ackedText || view.baseline || '');
    return Math.max(1, String(txt || '').split('\n').length);
  }

  function scrollContainerSmoothToElement(containerEl, targetEl) {
    if (!containerEl || !targetEl) return;
    const cRect = containerEl.getBoundingClientRect();
    const tRect = targetEl.getBoundingClientRect();
    const maxScroll = Math.max(0, containerEl.scrollHeight - containerEl.clientHeight);
    if (maxScroll <= 0) {
      targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    const desiredTop = Math.max(
      0,
      Math.min(maxScroll, tRect.top - cRect.top + containerEl.scrollTop - Math.round(containerEl.clientHeight * 0.28))
    );
    containerEl.scrollTo({ top: desiredTop, behavior: 'smooth' });
  }

  function scrollPreviewContainerToLine(containerEl, targetLine, selectedText = '') {
    if (!containerEl) return;
    const blocks = [...preview.querySelectorAll('[data-l]')]
      .filter(el => !el.closest('.md-preview-deletion'))
      .map(el => ({ el, line: Number(el.getAttribute('data-l')) || 1 }))
      .sort((a, b) => a.line - b.line);
    if (!blocks.length) return;
    let best = blocks[0];
    for (const item of blocks) {
      if (item.line <= targetLine) best = item;
      else break;
    }
    if (selectedText && best.el.tagName === 'TABLE') {
      const matchingRow = [...best.el.querySelectorAll('tr')].find(r => r.textContent.includes(selectedText));
      if (matchingRow) {
        scrollContainerSmoothToElement(containerEl, matchingRow);
        flashFocusSyncTarget(matchingRow, targetLine);
        return;
      }
    }
    scrollContainerSmoothToElement(containerEl, best.el);
    flashFocusSyncTarget(best.el, targetLine);
  }

  function scrollVisualPaneToLine(paneEl, visualInst, targetLine, selectedText = '') {
    if (!paneEl) return;
    let targetEl = typeof visualInst?.sourceBlockAtLine === 'function'
      ? visualInst.sourceBlockAtLine(targetLine)
      : null;
    const pm = paneEl.querySelector('.ProseMirror');
    if (!targetEl && pm) {
      const pmChildren = [...pm.children].filter(el => !el.classList.contains('ProseMirror-gapcursor'));
      const mdBlocks = parseTopLevelMarkdownBlocks(getEditorText());
      const blkIdx = mdBlocks.findIndex(b => targetLine - 1 >= b.startLine && targetLine - 1 < b.endLine);
      if (blkIdx >= 0 && pmChildren.length) {
        targetEl = pmChildren[Math.min(pmChildren.length - 1, blkIdx)] || null;
      }
      if (!targetEl && selectedText && pmChildren.length) {
        targetEl = pmChildren.find(el => el.textContent.includes(selectedText)) || null;
      }
      if (!targetEl && pmChildren.length) {
        const ratio = Math.max(0, Math.min(1, (targetLine - 1) / Math.max(1, getTotalDocLines() - 1)));
        targetEl = pmChildren[Math.min(pmChildren.length - 1, Math.round(ratio * (pmChildren.length - 1)))];
      }
    }
    if (targetEl) {
      scrollContainerSmoothToElement(paneEl, targetEl);
      flashFocusSyncTarget(targetEl, targetLine);
    }
  }

  function resolveLineFromPaneEvent(event, role) {
    const target = event?.target instanceof Element ? event.target : null;
    const selectedWord = String(window.getSelection?.()?.toString() || '').trim();
    const docText = view.active ? getEditorText() : (view.ackedText || view.baseline || '');
    const docLines = String(docText || '').split('\n');

    const isSourceRole = (role === 'primary' && (splitMode === 'S-P' || splitMode === 'S-E' || view.mode === 'source'));
    const isPreviewRole = (role === 'secondary' && (splitMode === 'E-P' || splitMode === 'S-P'));
    const isVisualRole = (role === 'primary' && splitMode === 'E-P') || (role === 'secondary' && splitMode === 'S-E');

    if (isSourceRole) {
      const bm = view.instance?.sourceBookmark?.();
      if (bm?.line > 0) {
        return { line: bm.line, selectedText: bm.selectedText || selectedWord };
      }
    }

    if (isPreviewRole && target) {
      const lNode = target.closest('[data-l]');
      if (lNode) {
        let baseLine = Math.max(1, Number(lNode.getAttribute('data-l')) || 1);
        const tr = target.closest('tr');
        if (tr && lNode.tagName === 'TABLE') {
          const allRows = [...lNode.querySelectorAll('tr')];
          const rIdx = allRows.indexOf(tr);
          if (rIdx > 0) baseLine += rIdx + 1;
        }
        return { line: baseLine, selectedText: selectedWord };
      }
    }

    if (isVisualRole && target) {
      const vInst = role === 'primary' ? view.instance : secondaryVisualInstance;
      const paneEl = role === 'primary' ? getPrimaryPaneEl() : getSecondaryPaneEl();
      const pm = paneEl?.querySelector('.ProseMirror');
      const blockEl = target.closest('h1,h2,h3,h4,h5,h6,p,li,tr,pre,blockquote,table');
      if (blockEl && typeof vInst?.sourceLineLocator === 'function') {
        const locator = vInst.sourceLineLocator();
        const locatedLine = locator ? locator(blockEl) : null;
        if (locatedLine && locatedLine > 0) {
          return { line: locatedLine, selectedText: selectedWord };
        }
      }
      if (pm && blockEl) {
        let topBlock = blockEl;
        while (topBlock.parentElement && topBlock.parentElement !== pm) {
          topBlock = topBlock.parentElement;
        }
        const pmChildren = [...pm.children].filter(el => !el.classList.contains('ProseMirror-gapcursor'));
        const bIdx = pmChildren.indexOf(topBlock);
        const mdBlocks = parseTopLevelMarkdownBlocks(docText);
        if (bIdx >= 0 && bIdx < mdBlocks.length) {
          let lineNo = mdBlocks[bIdx].startLine + 1;
          const tr = target.closest('tr');
          if (tr && topBlock.contains(tr)) {
            const rows = [...topBlock.querySelectorAll('tr')];
            const rIdx = rows.indexOf(tr);
            if (rIdx > 0) lineNo += rIdx + 1;
          }
          return { line: lineNo, selectedText: selectedWord };
        }
      }
    }

    // Fallback: search selected word in document lines near lastActiveLine
    if (selectedWord && selectedWord.length >= 2) {
      const matches = [];
      docLines.forEach((l, idx) => {
        if (l.includes(selectedWord)) matches.push(idx + 1);
      });
      if (matches.length === 1) {
        return { line: matches[0], selectedText: selectedWord };
      }
      if (matches.length > 1) {
        const refL = view.lastActiveLine || 1;
        matches.sort((a, b) => Math.abs(a - refL) - Math.abs(b - refL));
        return { line: matches[0], selectedText: selectedWord };
      }
    }

    return { line: view.lastActiveLine || 1, selectedText: selectedWord };
  }

  // On-demand Double-Click Jump between split panes (replaces jittery auto scroll-lock)
  function syncSplitScrollFrom(masterRole, explicitLine = null, selectedText = '') {
    if (splitMode === 'off') return;
    const primaryEl = getPrimaryPaneEl();
    const secondaryEl = getSecondaryPaneEl();
    if (!primaryEl || !secondaryEl) return;

    const targetLine = Math.max(1, Number(explicitLine || view.lastActiveLine || 1));
    view.lastActiveLine = targetLine;

    if (masterRole === 'primary') {
      // Jump Secondary pane to targetLine
      if (splitMode === 'E-P' || splitMode === 'S-P') {
        scrollPreviewContainerToLine(secondaryEl, targetLine, selectedText);
      } else if (splitMode === 'S-E') {
        scrollVisualPaneToLine(secondaryEl, secondaryVisualInstance, targetLine, selectedText);
      }
    } else {
      // Jump Primary pane to targetLine without mutating CodeMirror/ProseMirror DOM nodes
      if (splitMode === 'S-P' || splitMode === 'S-E') {
        try { window.getSelection?.()?.removeAllRanges?.(); } catch (_) {}
        view.instance?.restoreBookmark?.({ line: targetLine, column: 0 });
        const activeCmLine = view.sourceHost?.querySelector('.cm-activeLine');
        if (activeCmLine) {
          scrollContainerSmoothToElement(primaryEl, activeCmLine);
        }
      } else if (splitMode === 'E-P') {
        try { window.getSelection?.()?.removeAllRanges?.(); } catch (_) {}
        scrollVisualPaneToLine(primaryEl, view.instance, targetLine, selectedText);
      }
    }
  }

  function attachPaneScrollListeners(paneEl, role) {
    if (!paneEl || paneEl.dataset.splitScrollBound === role) return;
    paneEl.dataset.splitScrollBound = role;
    paneEl.addEventListener('pointerenter', () => {
      if (splitMode !== 'off') scrollMasterRole = role;
    }, { passive: true });
    // Independent scrolling on both panes; Double-Click jumps the opposite pane smoothly
    paneEl.addEventListener('dblclick', ev => {
      if (splitMode === 'off') return;
      if (ev.target instanceof Element && ev.target.closest('button, a, input, select, summary, .md-hunk-actions, .md-hunk-floating-pill, .md-preview-deletion')) return;
      scrollMasterRole = role;
      const resolved = resolveLineFromPaneEvent(ev, role);
      if (resolved?.line > 0) {
        syncSplitScrollFrom(role, resolved.line, resolved.selectedText || '');
      }
    });
  }

  function bindSplitScrollSync() {
    attachPaneScrollListeners(preview, 'secondary');
  }

  function syncParallelSecondaryPane(currentText, hunks = view.hunks || []) {
    if (splitMode === 'off' || syncingSplit) return;
    const text = typeof currentText === 'string' ? currentText : (view.active ? getEditorText() : view.ackedText);
    if (splitMode === 'E-P' || splitMode === 'S-P') {
      preview.hidden = false;
      preview.dataset.paneRole = 'secondary';
      if (view.host) view.host.dataset.paneRole = 'primary';
      clearTimeout(splitRenderTimer);
      splitRenderTimer = setTimeout(() => {
        void renderDraftPreview(text);
      }, 85);
    } else if (splitMode === 'S-E') {
      const sec = ensureSecondaryPane();
      sec.hidden = false;
      if (view.host) view.host.dataset.paneRole = 'primary';
      // Fix #5: Never recreate secondaryVisualInstance if focus is inside secondary pane or text hasn't changed!
      if (sec.contains(document.activeElement)) return;
      if (cleanLineEndings(text) === cleanLineEndings(lastSecondarySyncedText)) return;
      if (secondaryVisualInstance && view.mode === 'source') {
        clearTimeout(splitRenderTimer);
        splitRenderTimer = setTimeout(async () => {
          if (syncingSplit || sec.contains(document.activeElement)) return;
          if (cleanLineEndings(text) === cleanLineEndings(lastSecondarySyncedText)) return;
          syncingSplit = true;
          try {
            const engine = await loadBundle();
            const mount = sec.querySelector('.md-secondary-visual-mount');
            if (mount) {
              await secondaryVisualInstance?.destroy?.();
              mount.textContent = '';
              lastSecondarySyncedText = text;
              secondaryVisualInstance = await engine.createVisualMarkdown(
                mount,
                text,
                () => {
                  if (syncingSplit || view.mode !== 'source') return;
                  if (!sec.contains(document.activeElement)) return;
                  if (typeof secondaryVisualInstance?.isCleanFromMount === 'function' && secondaryVisualInstance.isCleanFromMount()) return;
                  const vText = reconcileVisualMarkdown(secondaryVisualInstance.getMarkdown(), getEditorText());
                  if (cleanLineEndings(vText) === cleanLineEndings(getEditorText())) return;
                  syncingSplit = true;
                  try {
                    lastSecondarySyncedText = vText;
                    view.instance?.replaceExternalText?.(vText, { acknowledge: false });
                    changed();
                  } finally {
                    syncingSplit = false;
                  }
                },
                path,
                () => {} // No-op status callback so secondary Milkdown never flickers main status bar!
              );
            }
          } catch (_) {
          } finally {
            syncingSplit = false;
          }
        }, 180);
      }
    }
  }

  async function applySplitMode(nextSplit) {
    splitMode = nextSplit;
    const isSplit = splitMode !== 'off';
    ensureShellStyle();
    root?.classList.toggle('md-split-active', isSplit);
    if (root) root.dataset.splitSwap = String(splitSwap);

    if (!isSplit) {
      if (secondaryVisualInstance) {
        await secondaryVisualInstance.destroy?.();
        secondaryVisualInstance = null;
      }
      if (secondaryPane) secondaryPane.hidden = true;
      if (view.active) preview.hidden = true;
      return;
    }

    if (splitMode === 'E-P') {
      if (secondaryPane) secondaryPane.hidden = true;
      if (view.mode !== 'visual') await start('visual');
      preview.hidden = false;
      preview.dataset.paneRole = 'secondary';
      if (view.host) view.host.dataset.paneRole = 'primary';
      await renderDraftPreview(getEditorText());
    } else if (splitMode === 'S-P') {
      if (secondaryPane) secondaryPane.hidden = true;
      if (view.mode !== 'source') await start('source');
      preview.hidden = false;
      preview.dataset.paneRole = 'secondary';
      if (view.host) view.host.dataset.paneRole = 'primary';
      await renderDraftPreview(getEditorText());
    } else if (splitMode === 'S-E') {
      if (view.mode !== 'source') await start('source');
      preview.hidden = true;
      if (view.host) view.host.dataset.paneRole = 'primary';
      const sec = ensureSecondaryPane();
      sec.hidden = false;
      sec.innerHTML = '<div class="md-pane-badge">✏️ Edit visually (E — Live Sync)</div><div class="md-secondary-visual-mount"></div>';
      const mount = sec.querySelector('.md-secondary-visual-mount');
      const engine = await loadBundle();
      const initialText = getEditorText();
      lastSecondarySyncedText = initialText;
      syncingSplit = true;
      try {
        secondaryVisualInstance = await engine.createVisualMarkdown(
          mount,
          initialText,
          () => {
            if (syncingSplit || view.mode !== 'source') return;
            if (!sec.contains(document.activeElement)) return;
            if (typeof secondaryVisualInstance?.isCleanFromMount === 'function' && secondaryVisualInstance.isCleanFromMount()) return;
            const vText = reconcileVisualMarkdown(secondaryVisualInstance.getMarkdown(), getEditorText());
            if (cleanLineEndings(vText) === cleanLineEndings(getEditorText())) return;
            syncingSplit = true;
            try {
              lastSecondarySyncedText = vText;
              view.instance?.replaceExternalText?.(vText, { acknowledge: false });
              changed();
            } finally {
              syncingSplit = false;
            }
          },
          path,
          () => {} // Prevent status bar flicker loop
        );
      } finally {
        syncingSplit = false;
      }
    }
    if (view.host) {
      view.host.dataset.paneRole = 'primary';
      attachPaneScrollListeners(view.host, 'primary');
    }
    if (splitMode === 'E-P' || splitMode === 'S-P') {
      preview.dataset.paneRole = 'secondary';
      attachPaneScrollListeners(preview, 'secondary');
    } else if (splitMode === 'S-E' && secondaryPane) {
      secondaryPane.dataset.paneRole = 'secondary';
      attachPaneScrollListeners(secondaryPane, 'secondary');
    }
  }

  let mdTerminalBundlePromise = null;
  async function ensureMarkdownTerminalLoaded() {
    if (typeof globalThis.toggleTerminal === 'function' && document.getElementById('termDrawer')) {
      return;
    }
    if (mdTerminalBundlePromise) return mdTerminalBundlePromise;
    mdTerminalBundlePromise = (async () => {
      const folderDir = path.includes('/') ? path.split('/').slice(0, -1).join('/') : '';
      if (typeof globalThis.currentPath !== 'function') {
        globalThis.currentPath = () => folderDir;
      }
      if (!globalThis.APP) {
        globalThis.APP = { currentPath: folderDir, defaults: { terminal_enabled: true, terminal_start_height_px: 420 } };
      }
      for (const href of ['/static/vendor/xterm.css', '/static/terminal_scm.css']) {
        if (!document.querySelector(`link[href="${href}"]`)) {
          const link = document.createElement('link');
          link.rel = 'stylesheet';
          link.href = href;
          document.head.appendChild(link);
        }
      }
      if (!document.getElementById('termDrawer')) {
        const td = document.createElement('div');
        td.id = 'termDrawer';
        td.className = 'term-drawer';
        td.style.height = '420px';
        td.setAttribute('role', 'region');
        td.setAttribute('aria-label', 'Terminal');
        document.body.appendChild(td);
      }
      const loadScript = src => new Promise((resolve, reject) => {
        if (document.querySelector(`script[src="${src}"]`)) return resolve();
        const s = document.createElement('script');
        s.src = src;
        if (nonce) s.nonce = nonce;
        s.onload = () => resolve();
        s.onerror = () => reject(new Error(`Failed to load ${src}`));
        document.head.appendChild(s);
      });
      await loadScript('/static/vendor/xterm.js');
      await loadScript('/static/vendor/addon-fit.js');
      await loadScript('/static/terminal_scm.js');
      const gitTabBtn = document.getElementById('lxViewGit');
      if (gitTabBtn) gitTabBtn.style.display = 'none';
    })().catch(err => {
      mdTerminalBundlePromise = null;
      throw err;
    });
    return mdTerminalBundlePromise;
  }

  function mountMarkdownExtraToolbar() {
    const barBottom = document.querySelector('.md-bar .bar-bottom');
    const barTop = document.querySelector('.md-bar .bar-top');
    if (barTop && !document.getElementById('mdTerminalBtn')) {
      const termBtn = document.createElement('button');
      termBtn.type = 'button';
      termBtn.id = 'mdTerminalBtn';
      termBtn.className = 'btn md-terminal-btn';
      termBtn.textContent = '⌨️ Terminal';
      termBtn.title = 'Open or toggle Terminal in current folder (Ctrl+`)';
      termBtn.addEventListener('click', async () => {
        try {
          await ensureMarkdownTerminalLoaded();
          globalThis.toggleTerminal?.();
        } catch (err) {
          status('Cannot open Terminal: ' + err.message, 'error');
        }
      });
      const grow = barTop.querySelector('.grow');
      if (grow) grow.insertAdjacentElement('afterend', termBtn);
      else barTop.appendChild(termBtn);
      document.addEventListener('keydown', ev => {
        if ((ev.ctrlKey || ev.metaKey) && ev.code === 'Backquote' && typeof globalThis.toggleTerminal !== 'function') {
          ev.preventDefault();
          termBtn.click();
        }
      });
    }

    if (!barBottom || barBottom.querySelector('.md-extra-controls')) return;
    const wrap = document.createElement('div');
    wrap.className = 'md-extra-controls';

    const splitGroup = document.createElement('div');
    splitGroup.className = 'md-split-group';
    splitGroup.setAttribute('role', 'group');
    splitGroup.setAttribute('aria-label', 'Parallel Split View');

    const splitButtons = [];
    for (const [id, label, tip] of [
      ['off', '1 Pane', 'Single pane mode'],
      ['E-P', 'E ∥ P', 'Parallel: Edit visually + Preview'],
      ['S-P', 'S ∥ P', 'Parallel: Source + Preview'],
      ['S-E', 'S ∥ E', 'Parallel: Source + Edit visually'],
    ]) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn';
      b.textContent = label;
      b.title = tip;
      b.setAttribute('aria-pressed', String(id === 'off'));
      b.addEventListener('click', () => {
        splitButtons.forEach(x => x.setAttribute('aria-pressed', String(x === b)));
        void applySplitMode(id);
      });
      splitButtons.push(b);
      splitGroup.appendChild(b);
    }

    const swapBtn = document.createElement('button');
    swapBtn.type = 'button';
    swapBtn.className = 'btn';
    swapBtn.textContent = '⇄ Swap L/R';
    swapBtn.title = 'Swap Left and Right panes in Parallel Split mode';
    swapBtn.addEventListener('click', () => {
      splitSwap = !splitSwap;
      if (root) root.dataset.splitSwap = String(splitSwap);
    });

    const wrapBtn = document.createElement('button');
    wrapBtn.type = 'button';
    wrapBtn.className = 'btn';
    const isWrapOn = () => localStorage.getItem('lantern-md-source-wrap') !== 'off';
    const syncWrapBtn = () => {
      const on = isWrapOn();
      wrapBtn.textContent = on ? '↵ Wrap: ON' : '→ Wrap: OFF';
      wrapBtn.setAttribute('aria-pressed', String(on));
      if (view.sourceWrapEl) view.sourceWrapEl.dataset.wrap = on ? 'on' : 'off';
    };
    syncWrapBtn();
    wrapBtn.addEventListener('click', () => {
      const next = isWrapOn() ? 'off' : 'on';
      localStorage.setItem('lantern-md-source-wrap', next);
      syncWrapBtn();
    });

    // --- v7.5: Version Diff Button (Date -> Hover Time Flyout) right next to Wrap: OFF ---
    const versionWrap = document.createElement('div');
    versionWrap.className = 'md-version-diff-wrap';
    const versionBtn = document.createElement('button');
    versionBtn.type = 'button';
    versionBtn.id = 'mdVersionDiffBtn';
    versionBtn.className = 'btn';
    versionBtn.textContent = '🕒 Version ▾';
    versionBtn.title = 'Browse saved versions by Date & Time and revert .md to compare diffs';
    const versionMenu = document.createElement('div');
    versionMenu.id = 'mdVersionDiffMenu';
    versionMenu.className = 'md-version-diff-menu';
    versionMenu.hidden = true;
    versionWrap.append(versionBtn, versionMenu);

    const applyRestoredVersion = async (vItem) => {
      if (view.saving || view.loading || view.piTurn) return;
      versionMenu.hidden = true;
      try {
        const res = await api('/api/md/versions/restore', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path, versionId: vItem.id, version: vItem.version }),
        });
        const baselineDoc = res.saved;
        const workDoc = res.work;
        const nextText = workDoc ? workDoc.content : (baselineDoc ? baselineDoc.content : '');
        if (baselineDoc) {
          view.version = baselineDoc.version;
          view.baseline = baselineDoc.content;
        }
        view.currentVersion = res.currentVersion || vItem.version;
        view.workHash = workDoc?.hash || null;
        view.workState = res.state || (view.workHash ? 'pending' : 'clean');
        view.ackedText = nextText;
        view.lastSaved = nextText;
        view.dirty = Boolean(workDoc);
        if (view.active && view.instance) {
          await applyWorkingText(nextText, view.workHash, { backed: true });
        } else {
          await renderDraftPreview(nextText);
        }
        syncParallelSecondaryPane(nextText);
        status(`Switched .md to version ${vItem.dateLabel} ${vItem.timeLabel} (${view.dirty ? 'showing diff vs last Ctrl+S' : 'matches Ctrl+S baseline'}).`, 'info');
        void refreshImageAudit();
      } catch (err) {
        status('Version switch failed: ' + err.message, 'error');
      }
    };

    const loadAndRenderVersionMenu = async () => {
      ensureShellStyle();
      versionMenu.innerHTML = '<div style="padding:6px 10px;color:#9fb6ca;font-size:11.5px">Loading versions…</div>';
      try {
        const data = await api('/api/md/versions?p=' + encodeURIComponent(path));
        const groups = Array.isArray(data.groups) ? data.groups : [];
        versionMenu.textContent = '';
        if (!groups.length) {
          versionMenu.innerHTML = '<div style="padding:6px 10px;color:#9fb6ca;font-size:11.5px">No saved versions yet. Press Ctrl+S to record a version.</div>';
          return;
        }
        groups.forEach((grp, gIdx) => {
          const dateRow = document.createElement('div');
          dateRow.className = 'md-version-date-item' + (gIdx === 0 ? ' is-open' : '');
          const leftLabel = document.createElement('span');
          leftLabel.textContent = grp.dateSub && grp.dateLabel !== 'Today'
            ? `${grp.dateLabel} (${grp.dateSub})`
            : (grp.dateLabel === 'Today' && grp.dateSub ? `Today, ${grp.dateSub}` : grp.dateLabel);
          const rightMeta = document.createElement('span');
          rightMeta.className = 'md-version-date-sub';
          rightMeta.textContent = `${(grp.items || []).length} ▸`;
          dateRow.append(leftLabel, rightMeta);

          const subList = document.createElement('div');
          subList.className = 'md-version-time-sublist';
          (grp.items || []).forEach(vItem => {
            const tBtn = document.createElement('button');
            tBtn.type = 'button';
            tBtn.className = 'md-version-time-btn'
              + (vItem.isCurrent ? ' is-current' : '')
              + (vItem.isBaseline ? ' is-baseline' : '');
            const tSpan = document.createElement('span');
            tSpan.textContent = vItem.timeLabel;
            const tagSpan = document.createElement('span');
            tagSpan.className = 'md-version-tag';
            tagSpan.textContent = vItem.isCurrent && vItem.isBaseline
              ? '● Current / Saved'
              : vItem.isCurrent
                ? '● Active'
                : vItem.isBaseline
                  ? '★ Last Ctrl+S'
                  : `${Math.max(1, Math.round((vItem.bytes || 0) / 1024))} KB`;
            tBtn.append(tSpan, tagSpan);
            tBtn.title = `Revert .md to ${grp.dateLabel} ${vItem.timeFull} and show diff`;
            tBtn.addEventListener('click', ev => {
              ev.stopPropagation();
              void applyRestoredVersion(vItem);
            });
            subList.appendChild(tBtn);
          });

          dateRow.addEventListener('mouseenter', () => {
            versionMenu.querySelectorAll('.md-version-date-item').forEach(el => el.classList.remove('is-open'));
            dateRow.classList.add('is-open');
          });
          dateRow.addEventListener('click', ev => {
            ev.stopPropagation();
            const openNow = dateRow.classList.contains('is-open');
            versionMenu.querySelectorAll('.md-version-date-item').forEach(el => el.classList.remove('is-open'));
            if (!openNow) dateRow.classList.add('is-open');
          });

          dateRow.appendChild(subList);
          versionMenu.appendChild(dateRow);
        });
      } catch (err) {
        versionMenu.innerHTML = `<div style="padding:6px 10px;color:#fca5a5;font-size:11.5px">${err.message}</div>`;
      }
    };

    versionBtn.addEventListener('click', ev => {
      ev.stopPropagation();
      const willOpen = versionMenu.hidden;
      versionMenu.hidden = !willOpen;
      if (willOpen) void loadAndRenderVersionMenu();
    });

    // --- v7.5: Missing / Unreferenced Image Warning Pill on Toolbar Row ---
    const auditWrap = document.createElement('div');
    auditWrap.className = 'md-image-audit-wrap';
    const auditBtn = document.createElement('button');
    auditBtn.type = 'button';
    auditBtn.id = 'mdImageAuditBadge';
    auditBtn.className = 'btn md-image-audit-btn';
    auditBtn.hidden = true;
    const auditPopover = document.createElement('div');
    auditPopover.id = 'mdImageAuditPopover';
    auditPopover.className = 'md-image-audit-popover';
    auditPopover.hidden = true;
    auditWrap.append(auditBtn, auditPopover);

    auditBtn.addEventListener('click', ev => {
      ev.stopPropagation();
      auditPopover.hidden = !auditPopover.hidden;
    });

    document.addEventListener('click', ev => {
      if (!versionWrap.contains(ev.target)) versionMenu.hidden = true;
      if (!auditWrap.contains(ev.target)) auditPopover.hidden = true;
    });

    wrap.append(splitGroup, swapBtn, wrapBtn, versionWrap, auditWrap);
    const statusEl = barBottom.querySelector('[data-md-status]');
    if (statusEl) statusEl.insertAdjacentElement('beforebegin', wrap);
    else barBottom.appendChild(wrap);
    void refreshImageAudit();
  }

  let imageAuditTimer = 0;
  async function refreshImageAudit() {
    clearTimeout(imageAuditTimer);
    imageAuditTimer = setTimeout(async () => {
      const badge = document.getElementById('mdImageAuditBadge');
      const pop = document.getElementById('mdImageAuditPopover');
      if (!badge || !pop) return;
      try {
        const res = await fetch('/api/md/image-audit?p=' + encodeURIComponent(path), { cache: 'no-store', credentials: 'same-origin' });
        if (!res.ok) return;
        const d = await res.json();
        const missing = Array.isArray(d.missing) ? d.missing : [];
        const unused = Array.isArray(d.unreferenced) ? d.unreferenced : [];
        const refCount = Number(d.referencedCount || 0);
        ensureShellStyle();
        if (missing.length > 0 || unused.length > 0) {
          badge.hidden = false;
          badge.classList.add('is-warn');
          badge.classList.remove('is-ok');
          const parts = [];
          if (missing.length > 0) parts.push(`${missing.length} missing`);
          if (unused.length > 0) parts.push(`${unused.length} unused`);
          badge.textContent = `⚠️ Images: ${parts.join(' · ')}`;
          badge.title = 'Click to inspect missing or unreferenced images in this folder';
          pop.textContent = '';
          if (missing.length > 0) {
            const sec = document.createElement('div');
            sec.className = 'md-image-audit-sec';
            const t = document.createElement('div');
            t.className = 'md-image-audit-title';
            t.textContent = `❌ Missing images referenced in .md (${missing.length}):`;
            const ul = document.createElement('ul');
            ul.className = 'md-image-audit-list';
            missing.forEach(m => {
              const li = document.createElement('li');
              li.textContent = m;
              ul.appendChild(li);
            });
            sec.append(t, ul);
            pop.appendChild(sec);
          }
          if (unused.length > 0) {
            const sec = document.createElement('div');
            sec.className = 'md-image-audit-sec';
            const t = document.createElement('div');
            t.className = 'md-image-audit-title';
            t.style.color = '#fcd34d';
            t.textContent = `⚠️ Unreferenced images in folder/assets (${unused.length}):`;
            const ul = document.createElement('ul');
            ul.className = 'md-image-audit-list';
            ul.style.color = '#fde68a';
            unused.forEach(u => {
              const li = document.createElement('li');
              li.textContent = u;
              ul.appendChild(li);
            });
            sec.append(t, ul);
            pop.appendChild(sec);
          }
        } else if (refCount > 0) {
          badge.hidden = false;
          badge.classList.remove('is-warn');
          badge.classList.add('is-ok');
          badge.textContent = `🖼️ Images OK (${refCount})`;
          badge.title = 'All referenced images exist and no unused images found';
          pop.innerHTML = `<div style="color:#86efac;font-weight:700">✓ All ${refCount} image reference(s) exist on disk and 0 unused images in folder.</div>`;
        } else {
          badge.hidden = true;
          pop.hidden = true;
        }
      } catch (_) {}
    }, 120);
  }

  // Track active line in Preview/Visual/Source for Ghost Cursor & Focus Sync (#7)
  document.addEventListener('pointerdown', ev => {
    const target = ev.target instanceof Element ? ev.target : null;
    if (!target) return;
    const lNode = target.closest('[data-l]');
    if (lNode) {
      const l = Number(lNode.getAttribute('data-l'));
      if (l > 0) view.lastActiveLine = l;
    } else if (view.active) {
      const pos = capturePosition();
      if (pos?.line > 0) view.lastActiveLine = pos.line;
    }
  }, { passive: true });

  bindSplitScrollSync();
  mountMarkdownExtraToolbar();
  // Pre-warm bundles on idle for lag-free mode switching
  setTimeout(() => { if (!document.hidden) { void loadSourceBundle().catch(() => {}); } }, 600);

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
    if (e.key === 'Escape' && view.piTurn) {
      cancelBotTurn();
      return;
    }
    if (e.altKey && (e.key === '[' || e.key === ']')) {
      if (Array.isArray(view.hunks) && view.hunks.length) {
        e.preventDefault();
        jumpToDiffHunk((view.currentHunkIdx || 0) + (e.key === ']' ? 1 : -1));
      }
      return;
    }
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
    beginBotTurn, cancelBotTurn, touchBotTurn, onWorkLocked, onWorkChanged, undoLastBotTurn, jumpToDiffHunk,
    reconcileVisualMarkdown, syncSplitScrollFrom, refreshImageAudit };
})();
