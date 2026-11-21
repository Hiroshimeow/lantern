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
    joined = joined.replace(/!\[([^\]]*)\]\((assets\/[^)\s]+)\s+"[^"]*"\)/g, "![$1]($2)");
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

  function splitGfmRowCells(line) {
    const trimmed = String(line ?? '').trim().replace(/^\|/, '').replace(/\|$/, '');
    const cells = [];
    let cur = '';
    let inCode = false;
    for (let i = 0; i < trimmed.length; i++) {
      const ch = trimmed[i];
      if (ch === '\\' && i + 1 < trimmed.length) {
        if (trimmed[i + 1] === '|') {
          cur += '|';
        } else {
          cur += ch + trimmed[i + 1];
        }
        i++;
        continue;
      }
      if (ch === '`') {
        inCode = !inCode;
        cur += ch;
        continue;
      }
      if (ch === '|' && !inCode) {
        cells.push(cur.trim());
        cur = '';
        continue;
      }
      cur += ch;
    }
    cells.push(cur.trim());
    return cells;
  }

  function prepareVisualTableMarkdown(mdText) {
    const raw = String(mdText ?? '');
    if (!raw.includes('|')) return raw;
    const hasCrlf = raw.includes('\r\n');
    const lines = raw.replace(/\r\n?/g, '\n').split('\n');
    const outLines = [];
    let inFence = false;
    let changed = false;
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (/^\s*(?:`{3,}|~{3,})/.test(line)) {
        inFence = !inFence;
        outLines.push(line);
        i++;
        continue;
      }
      if (inFence) {
        outLines.push(line);
        i++;
        continue;
      }
      if (i + 1 < lines.length && line.includes('|') && isGfmSeparatorLine(lines[i + 1])) {
        if (outLines.length > 0 && outLines[outLines.length - 1].trim() !== '') {
          outLines.push('');
          changed = true;
        }
        const headCells = splitGfmRowCells(line);
        const headCols = headCells.length;
        const normHead = '| ' + headCells.join(' | ') + ' |';
        if (normHead !== line) changed = true;
        outLines.push(normHead);

        const sepInner = lines[i + 1].trim().replace(/^\|/, '').replace(/\|$/, '');
        const sepCells = sepInner.split('|').map(c => c.trim());
        const fixedSep = sepCells.slice(0, headCols).map(c => /^:?-+:?$/.test(c) ? c : '---');
        while (fixedSep.length < headCols) fixedSep.push('---');
        const normSep = '| ' + fixedSep.join(' | ') + ' |';
        if (normSep !== lines[i + 1]) changed = true;
        outLines.push(normSep);
        i += 2;

        while (i < lines.length && lines[i].trim() !== '' && lines[i].includes('|') && !/^\s*(?:`{3,}|~{3,})/.test(lines[i])) {
          if (isGfmSeparatorLine(lines[i])) {
            changed = true;
            i++;
            continue;
          }
          const rowCells = splitGfmRowCells(lines[i]);
          if (rowCells.length !== headCols || !lines[i].trim().startsWith('|') || !lines[i].trim().endsWith('|')) {
            const fixedRow = rowCells.slice(0, headCols);
            while (fixedRow.length < headCols) fixedRow.push('');
            outLines.push('| ' + fixedRow.join(' | ') + ' |');
            changed = true;
          } else {
            outLines.push(lines[i]);
          }
          i++;
        }
        continue;
      }
      outLines.push(line);
      i++;
    }
    if (!changed) return raw;
    const out = outLines.join('\n');
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

  const sourceTrigger = document.querySelector('[data-action="mode-source"]');
  const previewTrigger = document.querySelector('[data-action="mode-preview"]');
  const preview = document.querySelector('article.md-preview');
  const topActions = document.querySelector('[data-md-edit-actions]');
  const topStatus = document.querySelector('[data-md-status]');
  const saveHeader = document.querySelector('[data-action="md-save"]');
  const draftHeader = document.querySelector('[data-action="md-download-draft"]');
  const backHeader = document.querySelector('[data-action="md-back-preview"]');
  if (!sourceTrigger || !previewTrigger || !preview) return;
  const trigger = document.querySelector('[data-action="visual-edit"]') || (typeof document.createElement === 'function' ? document.createElement('button') : { disabled: false, textContent: '', setAttribute: () => {}, addEventListener: () => {}, getAttribute: () => null });

  const path = sourceTrigger.getAttribute('data-path') || previewTrigger.getAttribute('data-path') || trigger.getAttribute('data-path');
  const nonce = document.currentScript?.nonce || document.querySelector('script[nonce]')?.nonce || document.querySelector('script[nonce]')?.getAttribute('nonce') || '';
  // Files near 41 KiB fit in one editor; retain paged editing for larger
  // documents to cap ProseMirror work and preserve byte-exact page boundaries.
  const FULL_VISUAL_LIMIT_BYTES = Number.MAX_SAFE_INTEGER; // v9.22: Hybrid Option 1+3 DOCX Visual Editor handles all sizes without Milkdown
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
    mode: 'preview', get active() { return this.mode === 'visual' || this.mode === 'source' || this.mode === 'paged'; },
    loading: false, instance: null, version: null, currentVersion: null,
    dirty: false, revision: 0, savedRevision: 0, saving: false, conflict: false,
    baseline: '', lastSaved: '', roundtripSafe: false, approvedReformat: false,
    draftTimer: 0, diffTimer: 0, checkTimer: 0, host: null, status: null,
    saveButton: null, closeButton: null, details: null,
    sourceHost: null, visualDiffFallback: null, hunks: [],
    workHash: null, workState: 'clean', ackedText: '', realText: '', realVersion: null, userDraftText: null, piTurn: null, applyingPi: false,
    savedSincePreview: false, switchingFromPaged: false,
    botUndoStack: [], undoHistoryStack: [], activeConflicts: [], currentHunkIdx: 0, curtainOpen: false,
    botWatchdogTimer: 0,
  };
  const pushUndoSnapshot = (textToSave) => {
    const snap = typeof textToSave === 'string' ? textToSave : (view.active ? getEditorText() : (view.ackedText || view.baseline || ''));
    if (!snap) return;
    const last = view.undoHistoryStack[view.undoHistoryStack.length - 1];
    if (!last || last.text !== snap) {
      view.undoHistoryStack.push({ text: snap, at: Date.now() });
      if (view.undoHistoryStack.length > 30) view.undoHistoryStack.shift();
    }
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

  function isLineInsideCodeFence(fullText, targetLineIdx) {
    const lines = String(fullText ?? '').replace(/\r\n?/g, '\n').split('\n');
    const limit = Math.min(lines.length, Math.max(0, Number(targetLineIdx || 0)));
    let inFence = false;
    for (let i = 0; i < limit; i++) {
      if (/^\s*(?:`{3,}|~{3,})/.test(lines[i])) inFence = !inFence;
    }
    return inFence;
  }

  function splitMultiImageAddHunks(rawHunks, baseText, draftText) {
    const list = Array.isArray(rawHunks) ? rawHunks : [];
    if (!list.length) return list;
    const imgLineRe = /!\[[^\]]*\]\([^)]+\)|<img\b[^>]*>/i;
    const fenceLineRe = /^\s*(?:`{3,}|~{3,})/;
    const isTablePipeLine = l => countGfmPipeCells(l) >= 2;
    const out = [];

    for (const h of list) {
      const dLines = Array.isArray(h.draftText) ? h.draftText : [];
      const bLines = Array.isArray(h.baseText) ? h.baseText : [];
      const imgIndices = [];
      dLines.forEach((line, idx) => {
        if (imgLineRe.test(String(line || ''))) imgIndices.push(idx);
      });

      // 1. Multi-image addition: split each pasted image into its own addressable hunk
      if (h.kind === 'add' && bLines.length === 0 && imgIndices.length >= 2) {
        for (let k = 0; k < imgIndices.length; k++) {
          const segStart = k === 0 ? 0 : imgIndices[k];
          const segEnd = k + 1 < imgIndices.length ? imgIndices[k + 1] : dLines.length;
          const subLines = dLines.slice(segStart, segEnd);
          out.push({
            ...h,
            kind: 'add',
            baseStart: h.baseStart,
            baseEnd: h.baseEnd,
            draftStart: h.draftStart + segStart,
            draftEnd: h.draftStart + segEnd,
            baseText: [],
            draftText: subLines,
            _isSplitSubHunk: true,
            _parentDraftStart: h.draftStart,
            _parentDraftEnd: h.draftEnd,
            _segStart: segStart,
            _segEnd: segEnd,
          });
        }
        continue;
      }

      // Keep fenced code block hunks atomic so code blocks diff & save as a single block
      const hasFence = bLines.some(l => fenceLineRe.test(String(l || '')))
        || dLines.some(l => fenceLineRe.test(String(l || '')))
        || isLineInsideCodeFence(baseText, h.baseStart)
        || isLineInsideCodeFence(draftText, h.draftStart);
      if (hasFence) {
        out.push(h);
        continue;
      }

      // 2. Equal-length multi-line modification (tables, lists, paragraphs): split per changed line/row
      // so clicking Save/Undo on a specific row/line saves/undoes ONLY that row/line!
      if (h.kind === 'mod' && bLines.length === dLines.length && bLines.length > 1) {
        for (let k = 0; k < bLines.length; k++) {
          if (bLines[k] === dLines[k]) continue;
          if (isGfmSeparatorLine(bLines[k]) && isGfmSeparatorLine(dLines[k])) continue;
          out.push({
            ...h,
            kind: 'mod',
            baseStart: h.baseStart + k,
            baseEnd: h.baseStart + k + 1,
            draftStart: h.draftStart + k,
            draftEnd: h.draftStart + k + 1,
            baseText: [bLines[k]],
            draftText: [dLines[k]],
            _isSplitLineHunk: true,
          });
        }
        continue;
      }

      // 3. Unequal-length table hunks (e.g. modified rows + added/deleted rows in an existing table)
      const bNonEmpty = bLines.filter(l => String(l || '').trim());
      const dNonEmpty = dLines.filter(l => String(l || '').trim());
      const bAllTable = bNonEmpty.length > 0 && bNonEmpty.every(isTablePipeLine);
      const dAllTable = dNonEmpty.length > 0 && dNonEmpty.every(isTablePipeLine);

      if (bAllTable && dAllTable && bLines.length !== dLines.length) {
        const pairCount = Math.min(bLines.length, dLines.length);
        for (let k = 0; k < pairCount; k++) {
          if (bLines[k] === dLines[k]) continue;
          if (isGfmSeparatorLine(bLines[k]) && isGfmSeparatorLine(dLines[k])) continue;
          out.push({
            ...h,
            kind: 'mod',
            baseStart: h.baseStart + k,
            baseEnd: h.baseStart + k + 1,
            draftStart: h.draftStart + k,
            draftEnd: h.draftStart + k + 1,
            baseText: [bLines[k]],
            draftText: [dLines[k]],
            _isSplitLineHunk: true,
          });
        }
        for (let k = pairCount; k < dLines.length; k++) {
          if (!String(dLines[k] || '').trim()) continue;
          out.push({
            ...h,
            kind: 'add',
            baseStart: h.baseStart + bLines.length,
            baseEnd: h.baseStart + bLines.length,
            draftStart: h.draftStart + k,
            draftEnd: h.draftStart + k + 1,
            baseText: [],
            draftText: [dLines[k]],
            _isSplitSubHunk: true,
          });
        }
        for (let k = pairCount; k < bLines.length; k++) {
          if (!String(bLines[k] || '').trim()) continue;
          out.push({
            ...h,
            kind: 'del',
            baseStart: h.baseStart + k,
            baseEnd: h.baseStart + k + 1,
            draftStart: h.draftStart + dLines.length,
            draftEnd: h.draftStart + dLines.length,
            baseText: [bLines[k]],
            draftText: [],
            _isSplitLineHunk: true,
          });
        }
        continue;
      }

      // 4. Multiple body rows added or deleted inside an existing table (without a table separator row)
      if (h.kind === 'add' && bLines.length === 0 && dLines.length > 1 && dAllTable && !dLines.some(isGfmSeparatorLine)) {
        for (let k = 0; k < dLines.length; k++) {
          if (!String(dLines[k] || '').trim()) continue;
          out.push({
            ...h,
            kind: 'add',
            baseStart: h.baseStart,
            baseEnd: h.baseEnd,
            draftStart: h.draftStart + k,
            draftEnd: h.draftStart + k + 1,
            baseText: [],
            draftText: [dLines[k]],
            _isSplitSubHunk: true,
          });
        }
        continue;
      }
      if (h.kind === 'del' && dLines.length === 0 && bLines.length > 1 && bAllTable && !bLines.some(isGfmSeparatorLine)) {
        for (let k = 0; k < bLines.length; k++) {
          if (!String(bLines[k] || '').trim()) continue;
          out.push({
            ...h,
            kind: 'del',
            baseStart: h.baseStart + k,
            baseEnd: h.baseStart + k + 1,
            draftStart: h.draftStart,
            draftEnd: h.draftStart,
            baseText: [bLines[k]],
            draftText: [],
            _isSplitLineHunk: true,
          });
        }
        continue;
      }

      out.push(h);
    }
    return out;
  }

  function annotateThreeWayHunks(rawHunks, baseText, currentText) {
    const diff = diffApi();
    const baseStr = String(baseText ?? '');
    const currStr = String(currentText ?? '');
    const initialList = Array.isArray(rawHunks) ? rawHunks : [];
    const list = splitMultiImageAddHunks(initialList, baseStr, currStr);
    if (!diff || !list.length) return list;
    const realStr = String(view.realText !== undefined && view.realText !== null && view.realText !== '' ? view.realText : baseStr);
    const activeEditorDirty = Boolean(view.active && view.instance && !matchesLastSaved(getEditorText()));
    const hasExplicitUserDraft = activeEditorDirty || (
      view.userDraftText !== null &&
      view.userDraftText !== undefined &&
      String(view.userDraftText) !== realStr
    );
    const userStr = activeEditorDirty
      ? getEditorText()
      : (hasExplicitUserDraft ? String(view.userDraftText) : realStr);
    const botHunks = splitMultiImageAddHunks(diff.diffLines(baseStr, realStr) || [], baseStr, realStr);
    const userHunks = hasExplicitUserDraft ? splitMultiImageAddHunks(diff.diffLines(baseStr, userStr) || [], baseStr, userStr) : [];
    const normHunkLines = arr => (Array.isArray(arr) ? arr : []).map(l => String(l || '').trim()).filter(Boolean).join('\n');
    const baseLinesArr = baseStr.replace(/\r\n?/g, '\n').split('\n');
    const overlapsBase = (a, b) => {
      if (!a || !b) return false;
      if (a.baseStart === a.baseEnd && b.baseStart === b.baseEnd) {
        if (a.baseStart === b.baseStart) {
          if (a._isSplitSubHunk && b._isSplitSubHunk) return a.draftStart === b.draftStart;
          return true;
        }
        if (Math.abs(a.baseStart - b.baseStart) === 1) {
          const minB = Math.min(a.baseStart, b.baseStart);
          if (!String(baseLinesArr[minB] || '').trim() || normHunkLines(a.draftText) === normHunkLines(b.draftText)) {
            return true;
          }
        }
        return false;
      }
      if (a.baseStart === b.baseStart && a.baseEnd === b.baseEnd) return true;
      return Math.max(a.baseStart, b.baseStart) < Math.min(Math.max(a.baseStart + 1, a.baseEnd), Math.max(b.baseStart + 1, b.baseEnd));
    };
    list.forEach(h => {
      const bh = botHunks.find(x => overlapsBase(h, x)) || null;
      const uh = userHunks.find(x => overlapsBase(h, x)) || null;
      const bJoin = bh ? normHunkLines(bh.draftText) : null;
      const uJoin = uh ? normHunkLines(uh.draftText) : null;
      if (bh && uh && bJoin !== uJoin) {
        // Case 3: Both Bot (Diff A) & User (Diff B) modified this region into 3 distinct versions -> 2-Tier Diff
        h.source = 'both';
        h.botHunk = bh;
        h.userHunk = uh;
        h.botText = bh.draftText || [];
        h.userText = uh.draftText || [];
      } else if (uh && !bh) {
        // Case 2: Only User modified vs History (Diff B) -> Blue & Red
        h.source = 'user';
        h.userHunk = h._isSplitSubHunk ? h : uh;
      } else {
        // Case 1: Only Bot modified vs History (Diff A) -> Green & Red
        h.source = 'bot';
        h.botHunk = h._isSplitSubHunk ? h : (bh || h);
        h.userHunk = uh || null;
      }
    });
    return list;
  }

  function applyHunksToBaseText(baseText, hunksToApply) {
    const diff = diffApi();
    const baseStr = String(baseText ?? '');
    const list = (Array.isArray(hunksToApply) ? hunksToApply : []).filter(Boolean);
    if (!list.length) return baseStr;
    // Sort hunks in descending baseStart order so applying each hunk never shifts earlier base line indices
    const sorted = [...list].sort((a, b) => {
      const aStart = Number(a.baseStart ?? 0);
      const bStart = Number(b.baseStart ?? 0);
      if (bStart !== aStart) return bStart - aStart;
      return Number(b.baseEnd ?? 0) - Number(a.baseEnd ?? 0);
    });
    const hasEolCrLf = baseStr.includes('\r\n');
    const eol = hasEolCrLf ? '\r\n' : '\n';
    const lines = baseStr.replace(/\r\n?/g, '\n').split('\n');
    for (const h of sorted) {
      const bStart = Math.max(0, Math.min(lines.length, Number(h.baseStart ?? 0)));
      const bEnd = Math.max(bStart, Math.min(lines.length, Number(h.baseEnd ?? bStart)));
      const replacement = Array.isArray(h.draftText) ? h.draftText : [];
      lines.splice(bStart, bEnd - bStart, ...replacement);
    }
    return lines.join(eol);
  }

  function spliceLinesInText(targetText, startLine, endLine, replacementLines) {
    const src = String(targetText ?? '');
    const eol = src.includes('\r\n') ? '\r\n' : '\n';
    const lines = src.replace(/\r\n?/g, '\n').split('\n');
    const s = Math.max(0, Math.min(lines.length, Number(startLine ?? 0)));
    const e = Math.max(s, Math.min(lines.length, Number(endLine ?? s)));
    const rep = Array.isArray(replacementLines) ? replacementLines : [];
    lines.splice(s, e - s, ...rep);
    return lines.join(eol);
  }

  const hunkButtons = (index, tier = null, source = null) => {
    const group = document.createElement('span');
    const effSource = tier || source || view.hunks?.[index]?.source || 'bot';
    group.className = 'md-hunk-actions' + (effSource === 'user' ? ' is-user-blue' : ' is-bot-green');
    for (const [action, label] of [['accept', '✓ Save'], ['undo', '↶ Undo']]) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'md-hunk-button' + (effSource === 'user' ? ' is-user-blue' : '');
      button.textContent = label;
      button.title = action === 'accept'
        ? 'Merge & save this change into the real file and History baseline'
        : 'Undo this change and restore previous content';
      button.addEventListener('click', event => {
        event.stopPropagation();
        void actionHunk(index, action, tier);
      });
      group.append(button);
    }
    return group;
  };

  function renderVisualDiffLinesHtml(baseLines, targetLines, source = 'bot') {
    const bArr = Array.isArray(baseLines) ? baseLines : [];
    const tArr = Array.isArray(targetLines) ? targetLines : [];
    const maxLen = Math.max(bArr.length, tArr.length);
    const out = [];
    const stripPrefix = s => String(s || '').replace(/^(?:#{1,6}\s+|>\s+|\s*[-*+]\s+|\s*\d+[.)]\s+)/, '');
    let i = 0;
    while (i < maxLen) {
      const bLine = i < bArr.length ? String(bArr[i] ?? '') : '';
      const tLine = i < tArr.length ? String(tArr[i] ?? '') : '';
      const refLine = tLine || bLine;
      if (!refLine.trim()) { i++; continue; }
      if (splitPipeRow(refLine)) {
        const rowsHtml = [];
        while (i < maxLen) {
          const bL = i < bArr.length ? String(bArr[i] ?? '') : '';
          const tL = i < tArr.length ? String(tArr[i] ?? '') : '';
          const rL = tL || bL;
          if (!rL.trim() || !splitPipeRow(rL)) break;
          const bCells = bL ? (splitPipeRow(bL) || []) : [];
          const tCells = tL ? (splitPipeRow(tL) || []) : [];
          if (isTableDividerRow(bCells) || isTableDividerRow(tCells)) { i++; continue; }
          const colCount = Math.max(bCells.length, tCells.length);
          const tds = [];
          for (let c = 0; c < colCount; c++) {
            const bC = bCells[c] ?? '';
            const tC = tCells[c] ?? '';
            const cellDiff = (bL && tL)
              ? renderWordDiffHtml(bC, tC, 'both', source)
              : (tL ? renderWordDiffHtml('', tC, 'add', source) : renderWordDiffHtml(bC, '', 'del', source));
            tds.push(`<td>${cellDiff}</td>`);
          }
          rowsHtml.push(`<tr>${tds.join('')}</tr>`);
          i++;
        }
        if (rowsHtml.length) {
          out.push(`<table class="md-del-rendered-table"><tbody>${rowsHtml.join('')}</tbody></table>`);
        }
        continue;
      }
      const hm = refLine.match(/^\s*(#{1,6})\s+/);
      const isBullet = /^\s*[-*+]\s+/.test(refLine);
      const olMatch = refLine.match(/^\s*(\d+[.)])\s+/);
      const isQuote = /^\s*>\s?/.test(refLine);
      const diffHtml = (bLine && tLine)
        ? renderWordDiffHtml(stripPrefix(bLine), stripPrefix(tLine), 'both', source)
        : (tLine
            ? renderWordDiffHtml('', stripPrefix(tLine), 'add', source)
            : renderWordDiffHtml(stripPrefix(bLine), '', 'del', source));
      if (hm) {
        const lvl = hm[1].length;
        out.push(`<h${lvl} style="margin:2px 0">${diffHtml}</h${lvl}>`);
      } else if (isBullet) {
        out.push(`<div class="md-del-list-item">• ${diffHtml}</div>`);
      } else if (olMatch) {
        out.push(`<div class="md-del-list-item">${olMatch[1]} ${diffHtml}</div>`);
      } else if (isQuote) {
        out.push(`<blockquote>${diffHtml}</blockquote>`);
      } else {
        out.push(`<p style="margin:2px 0">${diffHtml}</p>`);
      }
      i++;
    }
    return out.join('\n');
  }

  function createTwoTierDiffBlock(index, hunk) {
    const box = document.createElement('div');
    box.className = 'md-two-tier-diff';
    box.dataset.diffHunkIndex = String(index);
    const isRawMode = getDiffViewMode() === 'raw';
    const baseArr = Array.isArray(hunk.baseText) ? hunk.baseText : [];
    const botArr = Array.isArray(hunk.botText) ? hunk.botText : [];
    const userArr = Array.isArray(hunk.userText) ? hunk.userText : [];

    // Tier 1: Bot (Green & Red, Visual HTML by default)
    const botTier = document.createElement('div');
    botTier.className = 'md-two-tier-row is-bot-tier';
    const botBody = document.createElement('div');
    botBody.className = 'md-two-tier-body';
    const botRendered = document.createElement('div');
    botRendered.className = 'md-preview-deletion-rendered';
    botRendered.innerHTML = renderVisualDiffLinesHtml(baseArr, botArr, 'bot');
    botRendered.hidden = isRawMode;
    const botRaw = document.createElement('div');
    botRaw.className = 'md-preview-deletion-text';
    botRaw.textContent = botArr.join('\n');
    botRaw.hidden = !isRawMode;
    botBody.append(botRendered, botRaw);
    botTier.append(botBody, hunkButtons(index, 'bot', 'bot'));

    // Tier 2: User (Blue & Red, Visual HTML by default)
    const userTier = document.createElement('div');
    userTier.className = 'md-two-tier-row is-user-blue';
    const userBody = document.createElement('div');
    userBody.className = 'md-two-tier-body';
    const userRendered = document.createElement('div');
    userRendered.className = 'md-preview-deletion-rendered';
    userRendered.innerHTML = renderVisualDiffLinesHtml(baseArr, userArr, 'user');
    userRendered.hidden = isRawMode;
    const userRaw = document.createElement('div');
    userRaw.className = 'md-preview-deletion-text';
    userRaw.textContent = userArr.join('\n');
    userRaw.hidden = !isRawMode;
    userBody.append(userRendered, userRaw);
    userTier.append(userBody, hunkButtons(index, 'user', 'user'));

    box.append(botTier, userTier);
    return box;
  }

  const actionHunk = async (index, action, tier = null) => {
    if (view.saving || view.loading) {
      status('Wait for the current operation before changing a diff hunk.', 'warn');
      return;
    }
    if (view.baseline) pushUndoSnapshot(view.baseline);
    pushUndoSnapshot();
    // Only flush active editor draft if the user actually typed unsaved changes in the editor
    if (view.active && view.instance && !matchesLastSaved(getEditorText())) {
      if (!(await saveDraft())) return;
    }
    try {
      const diff = diffApi();
      if (!diff?.diffLines) throw new Error('Exact diff hunk application is unavailable');

      if (!view.version || !view.baseline) {
        const initSt = await fetchWorkState();
        if (!initSt?.saved) return;
        view.version = initSt.saved.version;
        view.currentVersion = initSt.currentVersion;
        view.realVersion = initSt.realVersion || initSt.currentVersion;
        view.baseline = initSt.saved.content;
        view.realText = initSt.realContent ?? initSt.work?.realContent ?? initSt.saved.content;
        view.userDraftText = initSt.userDraft?.content ?? null;
        view.ackedText = initSt.work?.content ?? initSt.saved.content;
      }

      const before = String(view.baseline ?? '');
      const real = String(view.realText !== undefined && view.realText !== null && view.realText !== '' ? view.realText : before);
      const mergedNow = String(
        (view.active && view.instance && !matchesLastSaved(getEditorText()))
          ? getEditorText()
          : (view.ackedText || view.lastRenderedPreviewText || real)
      );
      const hasUserDraft = (
        view.userDraftText !== null &&
        view.userDraftText !== undefined &&
        cleanLineEndings(String(view.userDraftText)) !== cleanLineEndings(real)
      ) || cleanLineEndings(mergedNow) !== cleanLineEndings(real);
      const user = hasUserDraft ? String(view.userDraftText ?? mergedNow) : real;

      const allHunks = annotateThreeWayHunks(diff.diffLines(before, mergedNow), before, mergedNow);
      const h = allHunks[index] || view.hunks?.[index];
      if (!h) return;

      const normHunkLines = arr => (Array.isArray(arr) ? arr : []).map(l => String(l || '').trim()).filter(Boolean).join('\n');
      const beforeLinesArr = before.replace(/\r\n?/g, '\n').split('\n');
      const overlapsBase = (a, b) => {
        if (!a || !b) return false;
        if (a.baseStart === a.baseEnd && b.baseStart === b.baseEnd) {
          if (a.baseStart === b.baseStart) {
            if (a._isSplitSubHunk && b._isSplitSubHunk) return a.draftStart === b.draftStart;
            return true;
          }
          if (Math.abs(a.baseStart - b.baseStart) === 1) {
            const minB = Math.min(a.baseStart, b.baseStart);
            if (!String(beforeLinesArr[minB] || '').trim() || normHunkLines(a.draftText) === normHunkLines(b.draftText)) {
              return true;
            }
          }
          return false;
        }
        if (a.baseStart === b.baseStart && a.baseEnd === b.baseEnd) return true;
        return Math.max(a.baseStart, b.baseStart) < Math.min(Math.max(a.baseStart + 1, a.baseEnd), Math.max(b.baseStart + 1, b.baseEnd));
      };

      const botHunks = splitMultiImageAddHunks(diff.diffLines(before, real) || [], before, real);
      const userHunks = splitMultiImageAddHunks(diff.diffLines(before, user) || [], before, user);
      const effSource = tier || (h.source === 'both' ? 'user' : (h.source || 'bot'));

      let nextBaseline = before;
      let nextReal = real;
      let nextMerged = mergedNow;
      let nextUser = null;

      if (action === 'accept') {
        if (h.source === 'both' && tier === 'bot') {
          const botLines = Array.isArray(h.botText) ? h.botText : (h.botHunk?.draftText || h.draftText || []);
          nextBaseline = spliceLinesInText(before, h.baseStart, h.baseEnd, botLines);
          nextReal = real;
          nextMerged = spliceLinesInText(mergedNow, h.draftStart, h.draftEnd, botLines);
          nextUser = cleanLineEndings(nextMerged) === cleanLineEndings(nextReal) ? null : nextMerged;
        } else {
          // Accepting a 1-tier Bot hunk, 1-tier User hunk, or User tier of a 2-tier hunk:
          // Save h.draftText into temp_md (nextBaseline) and ensure real (file gốc) has it without duplication!
          nextBaseline = spliceLinesInText(before, h.baseStart, h.baseEnd, h.draftText);
          nextMerged = mergedNow;
          if (effSource === 'bot' && h.source !== 'both') {
            // Bot's change is already in real (file gốc)! Never splice it into real a second time!
            nextReal = real;
          } else if (!hasUserDraft || cleanLineEndings(mergedNow) === cleanLineEndings(nextBaseline)) {
            nextReal = mergedNow;
          } else if (h._isSplitSubHunk) {
            const tokStr = (h.draftText || []).join('\n').trim();
            if (tokStr && real.includes(tokStr)) {
              nextReal = real;
            } else {
              const rLines = real.replace(/\r\n?/g, '\n').split('\n');
              const insAt = Math.max(0, Math.min(rLines.length, h.baseStart));
              nextReal = spliceLinesInText(real, insAt, insAt, h.draftText);
            }
          } else {
            const uh = h.userHunk || userHunks.find(x => overlapsBase(h, x)) || h;
            nextReal = applyHunksToBaseText(before, botHunks.filter(x => !overlapsBase(x, uh)).concat([uh]));
          }
          nextUser = cleanLineEndings(nextMerged) === cleanLineEndings(nextReal) ? null : nextMerged;
        }
      } else {
        // action === 'undo'
        nextBaseline = before;
        if (h.source === 'both' && tier === 'user') {
          // Undo User tier in 2-tier conflict -> restore Bot's tier (h.botText)
          const botLines = Array.isArray(h.botText) ? h.botText : (h.botHunk?.draftText || h.baseText || []);
          nextReal = real;
          nextMerged = spliceLinesInText(mergedNow, h.draftStart, h.draftEnd, botLines);
          nextUser = cleanLineEndings(nextMerged) === cleanLineEndings(nextReal) ? null : nextMerged;
        } else if (h.source === 'both' && tier === 'bot') {
          // Undo Bot tier in 2-tier conflict -> revert Bot's change in real to baseText, keep User's change
          const bh = h.botHunk || botHunks.find(x => overlapsBase(h, x)) || h;
          nextReal = applyHunksToBaseText(before, botHunks.filter(x => x !== bh && !overlapsBase(x, bh)));
          nextMerged = mergedNow;
          nextUser = cleanLineEndings(nextMerged) === cleanLineEndings(nextReal) ? null : nextMerged;
        } else {
          // Undo a 1-tier Bot hunk or 1-tier User hunk: revert h.draftStart..h.draftEnd in mergedNow to h.baseText
          nextMerged = spliceLinesInText(mergedNow, h.draftStart, h.draftEnd, h.baseText);
          if (effSource === 'bot') {
            if (!hasUserDraft) {
              nextReal = nextMerged;
              nextUser = null;
            } else {
              const bh = h.botHunk || botHunks.find(x => overlapsBase(h, x)) || h;
              nextReal = h._isSplitSubHunk
                ? spliceLinesInText(real, Math.min(h.draftStart, real.replace(/\r\n?/g, '\n').split('\n').length), Math.min(h.draftEnd, real.replace(/\r\n?/g, '\n').split('\n').length), h.baseText)
                : applyHunksToBaseText(before, botHunks.filter(x => x !== bh && !overlapsBase(x, bh)));
              nextUser = cleanLineEndings(nextMerged) === cleanLineEndings(nextReal) ? null : nextMerged;
            }
          } else {
            nextReal = real;
            nextUser = cleanLineEndings(nextMerged) === cleanLineEndings(nextReal) ? null : nextMerged;
          }
        }
      }

      const prevSavedVersion = view.version;
      const prevCurrentVersion = view.currentVersion;

      // Optimistic state & DOM update (<10ms instant response before network call!)
      view.baseline = nextBaseline;
      view.realText = nextReal;
      view.userDraftText = nextUser;
      view.ackedText = nextMerged;
      view.lastSaved = nextMerged;
      view.dirty = cleanLineEndings(nextMerged) !== cleanLineEndings(nextBaseline);
      restoreButtons();

      if (view.active && view.instance) {
        if (nextMerged !== getEditorText()) {
          await applyWorkingText(nextMerged, view.workHash, { backed: true });
        } else {
          renderDraftDiff();
        }
      } else {
        if (cleanLineEndings(nextMerged) === cleanLineEndings(view.lastRenderedPreviewText || '')) {
          const nextHunks = annotateThreeWayHunks(diff.diffLines(nextBaseline, nextMerged), nextBaseline, nextMerged);
          view.hunks = nextHunks;
          renderPreviewDiff(nextHunks, nextMerged);
          updateStickyDiffBar(nextHunks);
          document.documentElement.dataset.mdPendingHunks = String(nextHunks.length);
        } else {
          void renderDraftPreview(nextMerged);
        }
      }

      status(action === 'accept'
        ? 'Merged & saved this hunk into the real .md and History baseline.'
        : 'Reverted this hunk; other edits remain.', 'info');

      const fresh = await api('/api/work/accept-hunk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path,
          content: nextBaseline,
          nextRealContent: nextReal,
          nextUserContent: nextUser,
          expectSavedVersion: prevSavedVersion,
          expectCurrentVersion: prevCurrentVersion,
        }),
      });
      if (fresh?.saved) {
        view.version = fresh.saved.version;
        view.currentVersion = fresh.currentVersion;
        view.realVersion = fresh.realVersion || fresh.currentVersion;
        view.workHash = fresh.work?.hash || null;
        view.workState = fresh.state || (view.workHash ? 'pending' : 'clean');
        view.userDraftText = fresh.userDraft?.content ?? nextUser;
      } else if (fresh?.version) {
        view.version = fresh.version;
        view.currentVersion = fresh.currentVersion || view.currentVersion;
        view.realVersion = fresh.realVersion || view.realVersion;
        view.workState = fresh.state || view.workState;
      }
      void refreshImageAudit();
    } catch (error) {
      status('Diff action refused: ' + error.message, 'error');
      void refreshDiskBaseline({ quiet: true });
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
    document.querySelectorAll('.md-preview-deletion, .md-two-tier-row').forEach(ghost => {
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

  const clearPreviewDiff = (targetPreview = preview) => {
    if (!targetPreview) return;
    for (const cell of targetPreview.querySelectorAll('[data-orig-html]')) {
      cell.innerHTML = cell.getAttribute('data-orig-html') || '';
      cell.removeAttribute('data-orig-html');
      cell.removeAttribute('data-orig-cell-md');
      cell.removeAttribute('data-new-cell-md');
      cell.classList.remove('md-table-td-mod', 'is-user-blue');
    }
    for (const inlineNode of targetPreview.querySelectorAll('[data-orig-inline-html]')) {
      inlineNode.innerHTML = inlineNode.getAttribute('data-orig-inline-html') || '';
      inlineNode.removeAttribute('data-orig-inline-html');
    }
    for (const act of targetPreview.querySelectorAll('.md-table-row-actions,.md-hunk-floating-pill')) act.remove();
    for (const node of targetPreview.querySelectorAll('.md-preview-diff-add,.md-preview-diff-mod,.md-diff-user-blue,.is-user-blue,.md-table-tr-mod,.md-table-tr-add,.md-diff-img-frame')) {
      node.classList.remove('md-preview-diff-add', 'md-preview-diff-mod', 'md-diff-user-blue', 'is-user-blue', 'md-table-tr-mod', 'md-table-tr-add', 'md-diff-img-frame');
      node.removeAttribute('data-diff-hunk-index');
    }
    for (const ghost of targetPreview.querySelectorAll('.md-table-td-del-col,.md-preview-deletion,.md-preview-hunk-actions,.md-table-tr-del,.md-conflict-card,.md-two-tier-diff')) {
      ghost.remove();
    }
  };

  function resolveMarkdownImgHref(rawTarget) {
    const clean = String(rawTarget || '').trim().replace(/^<|>$/g, '').split(/\s+["']/)[0].trim();
    if (!clean) return '';
    if (/^(?:https?:|data:|blob:|\/)/i.test(clean)) return clean;
    const dir = path.includes('/') ? path.split('/').slice(0, -1).join('/') : '';
    const joined = (dir ? dir + '/' + clean : clean).replace(/^\/+/, '');
    return '/' + joined.split('/').map(seg => encodeURIComponent(decodeURIComponent(seg))).join('/');
  }

  function formatInlineMarkdownHtml(rawLine) {
    const esc = s => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const stash = [];
    const keep = htmlFrag => {
      const tok = `\u0000IMG${stash.length}\u0000`;
      stash.push(htmlFrag);
      return tok;
    };
    let work = String(rawLine || '');
    work = work.replace(/!\[([^\]]*)\]\(([^)\r\n]+)\)/g, (_m, alt, target) => {
      const resolved = resolveMarkdownImgHref(target);
      if (!resolved) return esc(_m);
      return keep(`<img src="${esc(resolved)}" alt="${esc(alt)}" data-md-src="${esc(target.trim())}" class="md-inline-cell-img" style="max-height:140px;max-width:100%;vertical-align:middle;border-radius:4px">`);
    });
    let s = esc(work);
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/~~([^~]+)~~/g, '<del>$1</del>');
    s = s.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    for (let i = stash.length - 1; i >= 0; i--) {
      s = s.split(`\u0000IMG${i}\u0000`).join(stash[i]);
    }
    return s;
  }

  function renderWordDiffHtml(oldLine, newLine, mode = 'both', source = 'bot') {
    const esc = s => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const diff = diffApi();
    const addCls = source === 'user' ? 'md-diff-word-add is-user-blue' : 'md-diff-word-add';
    const hasImgSyntax = /!\[[^\]]*\]\([^)\r\n]+\)|<img\b/i.test(String(oldLine || '') + ' ' + String(newLine || ''));
    if (hasImgSyntax) {
      if (mode === 'del') return oldLine ? `<span class="md-diff-word-del">${formatInlineMarkdownHtml(oldLine)}</span>` : '';
      if (mode === 'add') return newLine ? `<span class="${addCls}">${formatInlineMarkdownHtml(newLine)}</span>` : '';
      const delPart = oldLine ? `<span class="md-diff-word-del">${formatInlineMarkdownHtml(oldLine)}</span> ` : '';
      const addPart = newLine ? `<span class="${addCls}">${formatInlineMarkdownHtml(newLine)}</span>` : '';
      return delPart + addPart;
    }
    if (!diff?.diffWords) return esc(mode === 'del' ? oldLine : newLine);
    const ops = diff.diffWords(oldLine, newLine);
    return ops.map(op => {
      if (op.type === 'equal') return formatInlineMarkdownHtml(op.text);
      if (op.type === 'del') {
        if (mode === 'add') return '';
        return `<span class="md-diff-word-del">${esc(op.text)}</span>`;
      }
      if (mode === 'del') return '';
      return `<span class="${addCls}">${esc(op.text)}</span>`;
    }).join('');
  }

  function splitPipeRow(line) {
    const trimmed = String(line || '').trim();
    if (!trimmed.startsWith('|') || !trimmed.endsWith('|') || trimmed.length < 3) return null;
    return splitGfmRowCells(trimmed);
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

  function createFloatingHunkPill(index, { includeViewToggle = false, source = null, isTableCell = false } = {}) {
    const pill = document.createElement('div');
    pill.className = 'md-hunk-floating-pill' + (isTableCell ? ' is-table-cell-pill' : '');
    pill.setAttribute('contenteditable', 'false');
    pill.setAttribute('data-md-diff-ghost', 'true');
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
    pill.append(hunkButtons(index, null, source));
    return pill;
  }

  function attachFloatingPillAboveChangedWords(targetNode, pill) {
    if (!targetNode || !pill) return;
    const alignPill = () => {
      const firstWord = targetNode.querySelector('.md-diff-word-add, .md-diff-word-del');
      if (firstWord && firstWord instanceof HTMLElement) {
        const leftPx = Math.max(0, firstWord.offsetLeft);
        const topPx = firstWord.offsetTop - 10;
        pill.style.left = `${leftPx}px`;
        pill.style.top = `${topPx}px`;
        pill.style.right = 'auto';
      }
    };
    targetNode.append(pill);
    requestAnimationFrame(alignPill);
    targetNode.addEventListener('pointerenter', alignPill, { passive: true });
  }

  // v4/v9.2 In-Table Diff: Render row & cell diffs directly inside <table> at the exact row/cell
  // Handles GFM separator rows (| :--- |), header + body hunks, unequal row counts, and 2-tier (Bot+User) table diffs (replaces legacy firstCell.prepend(actWrap))!
  function tryRenderTableHunkInPlace(index, hunk, draftLines, targetPreview = preview) {
    const diff = diffApi();
    if (!diff?.parseTableRowCells) return false;
    const isAnyTablePipeLine = l => {
      const cells = splitPipeRow(l);
      return cells !== null && cells.length > 0;
    };
    const isDataTablePipeLine = l => {
      const cells = splitPipeRow(l);
      return cells !== null && cells.length > 0 && !isTableDividerRow(cells);
    };

    const rawBaseLines = Array.isArray(hunk.baseText) ? hunk.baseText.filter(l => l.trim()) : [];
    const rawNextLines = Array.isArray(hunk.draftText) ? hunk.draftText.filter(l => l.trim()) : [];
    const rawBotLines = Array.isArray(hunk.botText) ? hunk.botText.filter(l => l.trim()) : [];
    if (!rawBaseLines.length && !rawNextLines.length) return false;
    if (!rawBaseLines.every(isAnyTablePipeLine)) return false;
    if (!rawNextLines.every(isAnyTablePipeLine)) return false;

    const baseLines = rawBaseLines.filter(isDataTablePipeLine);
    const nextLines = rawNextLines.filter(isDataTablePipeLine);
    const botRowLines = rawBotLines.filter(isDataTablePipeLine);

    let probe = Math.min(Math.max(0, hunk.draftStart), Math.max(0, draftLines.length - 1));
    if (!String(draftLines[probe] || '').trim().startsWith('|') && probe > 0 && String(draftLines[probe - 1] || '').trim().startsWith('|')) {
      probe -= 1;
    }
    if (!String(draftLines[probe] || '').trim().startsWith('|')) return false;
    let tableStartLine = probe;
    while (tableStartLine > 0 && String(draftLines[tableStartLine - 1] || '').trim().startsWith('|')) {
      tableStartLine--;
    }

    const tables = [...(targetPreview || preview).querySelectorAll('table')];
    let targetTable = tables.find(t => Number(t.getAttribute('data-l')) === tableStartLine + 1);
    if (!targetTable) {
      targetTable = tables.find(t => {
        const l = Number(t.getAttribute('data-l') || t.closest('[data-l]')?.getAttribute('data-l') || 0);
        return l >= tableStartLine && l <= hunk.draftStart + 3;
      });
    }
    if (!targetTable) return false;

    if (!baseLines.length && !nextLines.length) return true;
    const tbody = targetTable.tBodies[0] || targetTable.createTBody();
    const nonDelRows = [...tbody.rows].filter(r => !r.classList.contains('md-table-tr-del'));
    const includesHeader = hunk.draftStart <= tableStartLine;
    const bodyRowIdx = includesHeader ? 0 : Math.max(0, hunk.draftStart - (tableStartLine + 2));
    const findBodyTr = (draftLineZeroIdx, fallbackBodyIdx) => {
      const targetOneIdx = draftLineZeroIdx + 1;
      const byDataL = nonDelRows.find(r => Number(r.getAttribute('data-l')) === targetOneIdx)
        || (targetPreview || preview).querySelector(`tr[data-l="${targetOneIdx}"]`);
      if (byDataL) return byDataL;
      return nonDelRows[fallbackBodyIdx] || null;
    };

    const ensureDeletedHeaderCols = (maxOldCols) => {
      const headTr = targetTable.tHead?.rows?.[0];
      if (!headTr || headTr.cells.length >= maxOldCols) return;
      const baseAllLines = String(view.baseline || '').replace(/\r\n?/g, '\n').split('\n');
      let baseTblStart = Math.min(Math.max(0, hunk.baseStart), Math.max(0, baseAllLines.length - 1));
      while (baseTblStart > 0 && String(baseAllLines[baseTblStart - 1] || '').trim().startsWith('|')) baseTblStart--;
      const baseHeadCells = diff.parseTableRowCells(baseAllLines[baseTblStart] || '') || splitPipeRow(baseAllLines[baseTblStart] || '') || [];
      for (let c = headTr.cells.length; c < maxOldCols; c++) {
        const th = document.createElement('th');
        th.className = 'md-table-td-del md-table-td-del-col md-preview-deletion';
        th.setAttribute('data-md-diff-ghost', 'true');
        const hLabel = baseHeadCells[c] || `Col ${c + 1}`;
        th.innerHTML = `<span class="md-diff-word-del" title="Deleted column">${formatInlineMarkdownHtml(hLabel)}</span>`;
        headTr.appendChild(th);
      }
    };

    const applyCellDiffToTr = (tr, oldRowStr, newRowStr, botRowStr) => {
      if (!tr) return false;
      const oldCells = diff.parseTableRowCells(oldRowStr) || splitPipeRow(oldRowStr) || [];
      const newCells = diff.parseTableRowCells(newRowStr) || splitPipeRow(newRowStr) || [];
      const botCells = botRowStr
        ? (diff.parseTableRowCells(botRowStr) || splitPipeRow(botRowStr) || [])
        : (hunk.source === 'bot' ? newCells : oldCells);
      let rowHasUser = false;
      let rowHasBot = false;
      let rowChanged = false;
      const domColCount = tr.cells.length;
      if (oldCells.length > domColCount) {
        ensureDeletedHeaderCols(oldCells.length);
      }
      for (let c = 0; c < domColCount; c++) {
        const cell = tr.cells[c];
        if (!cell.hasAttribute('data-orig-html')) {
          cell.setAttribute('data-orig-html', cell.innerHTML);
        }
        const oldVal = oldCells[c] ?? '';
        const newVal = newCells[c] ?? '';
        const botVal = botCells[c] ?? oldVal;
        if (oldVal !== newVal || oldVal !== botVal) {
          rowChanged = true;
          cell.classList.add('md-table-td-mod');
          cell.dataset.origCellMd = oldVal;
          cell.dataset.newCellMd = newVal;
          const wrap = document.createElement('div');
          wrap.className = 'md-table-cell-diff';
          let pillSource = 'bot';
          if (botVal !== oldVal && newVal !== botVal && newVal !== oldVal) {
            rowHasBot = true;
            rowHasUser = true;
            pillSource = 'user';
            const delBadge = document.createElement('div');
            delBadge.className = 'md-table-cell-old md-preview-deletion';
            delBadge.setAttribute('data-md-diff-ghost', 'true');
            delBadge.innerHTML = formatInlineMarkdownHtml(oldVal);
            const botBadge = document.createElement('div');
            botBadge.className = 'md-table-cell-new';
            botBadge.innerHTML = renderWordDiffHtml(oldVal, botVal, 'add', 'bot');
            const userBadge = document.createElement('div');
            userBadge.className = 'md-table-cell-new is-user-blue';
            userBadge.innerHTML = renderWordDiffHtml(oldVal, newVal, 'add', 'user');
            wrap.append(delBadge, botBadge, userBadge);
          } else {
            const cellSource = (botVal !== oldVal && newVal === botVal)
              ? 'bot'
              : ((botVal === oldVal && newVal !== oldVal) ? 'user' : (hunk.source === 'user' ? 'user' : 'bot'));
            pillSource = cellSource;
            if (cellSource === 'user') {
              rowHasUser = true;
              cell.classList.add('is-user-blue');
            } else {
              rowHasBot = true;
            }
            const delBadge = document.createElement('div');
            delBadge.className = 'md-table-cell-old md-preview-deletion';
            delBadge.setAttribute('data-md-diff-ghost', 'true');
            delBadge.innerHTML = renderWordDiffHtml(oldVal, newVal, 'del', cellSource);
            const addBadge = document.createElement('div');
            addBadge.className = 'md-table-cell-new' + (cellSource === 'user' ? ' is-user-blue' : '');
            addBadge.innerHTML = renderWordDiffHtml(oldVal, newVal, 'add', cellSource);
            wrap.append(delBadge, addBadge);
          }
          const cellPill = createFloatingHunkPill(index, {
            includeViewToggle: false,
            source: pillSource,
            isTableCell: true,
          });
          cell.innerHTML = '';
          cell.append(wrap, cellPill);
        }
      }
      // Render any deleted rightmost columns (when baseline row had more columns than the new row)
      if (oldCells.length > domColCount) {
        const isHeadTr = tr.parentElement?.tagName === 'THEAD';
        for (let c = domColCount; c < oldCells.length; c++) {
          rowChanged = true;
          const oldVal = oldCells[c] ?? '';
          const delCell = document.createElement(isHeadTr ? 'th' : 'td');
          delCell.className = 'md-table-td-del md-table-td-del-col md-preview-deletion';
          delCell.setAttribute('data-md-diff-ghost', 'true');
          const cellSource = hunk.source === 'user' ? 'user' : 'bot';
          if (cellSource === 'user') rowHasUser = true;
          else rowHasBot = true;
          const innerHtml = oldVal
            ? `<span class="md-diff-word-del">${formatInlineMarkdownHtml(oldVal)}</span>`
            : `<span class="md-diff-word-del md-del-empty-col" title="Deleted empty column">∅ (deleted col)</span>`;
          delCell.innerHTML = innerHtml;
          if (c === oldCells.length - 1) {
            delCell.style.position = 'relative';
            delCell.append(createFloatingHunkPill(index, {
              includeViewToggle: false,
              source: cellSource,
              isTableCell: true,
            }));
          }
          tr.appendChild(delCell);
        }
      }
      if (rowChanged) {
        tr.classList.add('md-table-tr-mod', 'md-preview-diff-mod');
        if (rowHasUser && !rowHasBot) tr.classList.add('is-user-blue');
        tr.dataset.diffHunkIndex = String(index);
      }
      return true;
    };

    if (hunk.kind === 'mod' && baseLines.length > 0 && nextLines.length > 0) {
      let bOffset = 0;
      let nOffset = 0;
      if (includesHeader && targetTable.tHead?.rows?.[0]) {
        applyCellDiffToTr(
          targetTable.tHead.rows[0],
          baseLines[0],
          nextLines[0],
          hunk.source === 'both' ? botRowLines[0] : null
        );
        bOffset = 1;
        nOffset = 1;
      }
      const remBase = baseLines.slice(bOffset);
      const remNext = nextLines.slice(nOffset);
      const remBot = botRowLines.slice(bOffset);
      const pairCount = Math.min(remBase.length, remNext.length);
      for (let r = 0; r < pairCount; r++) {
        const tr = findBodyTr(hunk.draftStart + nOffset + r, bodyRowIdx + r);
        if (!tr) break;
        applyCellDiffToTr(
          tr,
          remBase[r],
          remNext[r],
          hunk.source === 'both' ? remBot[r] : null
        );
      }
      // Any extra rows in remNext beyond remBase are newly added rows in the table
      let actionsMounted = pairCount > 0 || bOffset > 0;
      for (let r = pairCount; r < remNext.length; r++) {
        const addTr = findBodyTr(hunk.draftStart + nOffset + r, bodyRowIdx + r);
        if (!addTr) continue;
        addTr.classList.add('md-table-tr-add', 'md-preview-diff-add');
        if (hunk.source === 'user') addTr.classList.add('is-user-blue');
        addTr.dataset.diffHunkIndex = String(index);
        if (!actionsMounted && addTr.cells.length) {
          const lastCell = addTr.cells[addTr.cells.length - 1];
          if (!lastCell.hasAttribute('data-orig-html')) lastCell.setAttribute('data-orig-html', lastCell.innerHTML);
          lastCell.style.position = 'relative';
          lastCell.append(createFloatingHunkPill(index, { includeViewToggle: false, source: hunk.source, isTableCell: true }));
          actionsMounted = true;
        }
      }
      // Any extra rows in remBase beyond remNext are deleted rows from the table
      const refAfterPair = findBodyTr(hunk.draftStart + nOffset + pairCount, bodyRowIdx + pairCount) || null;
      for (let r = pairCount; r < remBase.length; r++) {
        const oldCells = diff.parseTableRowCells(remBase[r]) || splitPipeRow(remBase[r]) || [];
        const delTr = document.createElement('tr');
        delTr.className = 'md-table-tr-del md-preview-deletion';
        delTr.setAttribute('data-md-diff-ghost', 'true');
        delTr.dataset.diffHunkIndex = String(index);
        const colCount = Math.max(oldCells.length, targetTable.tHead?.rows?.[0]?.cells?.length || oldCells.length);
        for (let c = 0; c < colCount; c++) {
          const td = document.createElement('td');
          td.className = 'md-table-td-del';
          td.innerHTML = formatInlineMarkdownHtml(oldCells[c] ?? '');
          if (c === colCount - 1 && !actionsMounted) {
            td.style.position = 'relative';
            td.append(createFloatingHunkPill(index, { includeViewToggle: false, source: hunk.source, isTableCell: true }));
            actionsMounted = true;
          }
          delTr.append(td);
        }
        if (refAfterPair) tbody.insertBefore(delTr, refAfterPair);
        else tbody.append(delTr);
      }
      return true;
    }

    let actionsMounted = false;
    const refRow = findBodyTr(hunk.draftStart, bodyRowIdx) || null;
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
          if (c === colCount - 1 && !actionsMounted) {
            td.style.position = 'relative';
            td.append(createFloatingHunkPill(index, { includeViewToggle: false, source: hunk.source, isTableCell: true }));
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
        const addTr = findBodyTr(hunk.draftStart + r, bodyRowIdx + r);
        if (!addTr) continue;
        addTr.classList.add('md-table-tr-add', hunk.kind === 'mod' ? 'md-preview-diff-mod' : 'md-preview-diff-add');
        if (hunk.source === 'user') addTr.classList.add('is-user-blue');
        addTr.dataset.diffHunkIndex = String(index);
        if (!actionsMounted && addTr.cells.length) {
          const lastCell = addTr.cells[addTr.cells.length - 1];
          if (!lastCell.hasAttribute('data-orig-html')) {
            lastCell.setAttribute('data-orig-html', lastCell.innerHTML);
          }
          lastCell.style.position = 'relative';
          lastCell.append(createFloatingHunkPill(index, { includeViewToggle: false, source: hunk.source, isTableCell: true }));
          actionsMounted = true;
        }
      }
    }
    return true;
  }

  const renderPreviewDiff = (hunks, draftText, targetPreview = preview) => {
    const surface = targetPreview || preview;
    ensureShellStyle();
    clearPreviewDiff(surface);
    const draftLines = String(draftText || '').replace(/\r\n?/g, '\n').split('\n');
    const lineCount = draftLines.length;
    const blocks = [...surface.querySelectorAll('[data-l]')]
      .filter(node => !node.closest('.md-preview-deletion') && node.tagName !== 'TR')
      .map(node => ({node, line: Math.max(0, Number(node.getAttribute('data-l')) - 1)}))
      .filter(item => Number.isSafeInteger(item.line))
      .sort((a, b) => a.line - b.line);

    for (let i = 0; i < blocks.length; i++) {
      blocks[i].end = i + 1 < blocks.length ? blocks[i + 1].line : lineCount;
    }

    const isRawMode = getDiffViewMode() === 'raw';

    for (const [index, hunk] of hunks.entries()) {
      if (tryRenderTableHunkInPlace(index, hunk, draftLines, surface)) {
        continue;
      }
      if (hunk.source === 'both') {
        const twoTier = createTwoTierDiffBlock(index, hunk);
        const anchor = blocks.find(block => block.line >= hunk.draftStart)?.node || null;
        if (anchor) anchor.insertAdjacentElement('beforebegin', twoTier);
        else surface.append(twoTier);
        continue;
      }

      const matchedBlocks = [];
      if ((hunk.kind === 'add' || hunk.kind === 'mod') && hunk.draftEnd > hunk.draftStart) {
        for (const block of blocks) {
          if (block.line < hunk.draftEnd && block.end > hunk.draftStart) {
            block.node.classList.add(
              hunk.kind === 'add' ? 'md-preview-diff-add' : 'md-preview-diff-mod'
            );
            if (hunk.source === 'user') block.node.classList.add('md-diff-user-blue', 'is-user-blue');
            block.node.dataset.diffHunkIndex = String(index);
            block.node.querySelectorAll?.('img').forEach(imgEl => {
              imgEl.classList.add('md-diff-img-frame');
              if (hunk.source === 'user') imgEl.classList.add('is-user-blue');
            });
            matchedBlocks.push(block.node);
          }
        }
      }

      // v9.1 Per-Line Inline Word Diff inside single or multi-line modified blocks (li, p, h1..h6, blockquote)
      const baseArr = Array.isArray(hunk.baseText) ? hunk.baseText : [];
      const draftArr = Array.isArray(hunk.draftText) ? hunk.draftText : [];
      const baseNonEmpty = baseArr.filter(l => String(l || '').trim().length > 0);
      const draftNonEmpty = draftArr.filter(l => String(l || '').trim().length > 0);
      const canPairDirect = baseArr.length === matchedBlocks.length && draftArr.length === matchedBlocks.length;
      const canPairNonEmpty = baseNonEmpty.length === matchedBlocks.length && draftNonEmpty.length === matchedBlocks.length;
      const imgMdRe = /!\[[^\]]*\]\([^)]+\)|<img\b/i;
      const hasImgInHunk = baseArr.some(l => imgMdRe.test(String(l || '')))
        || draftArr.some(l => imgMdRe.test(String(l || '')))
        || matchedBlocks.some(b => Boolean(b.querySelector?.('img')));

      // Highlight any added/modified <img> inside matchedBlocks with a clear diff frame + pill
      if (hasImgInHunk && matchedBlocks.length > 0) {
        matchedBlocks.forEach(b => {
          b.querySelectorAll?.('img').forEach(imgEl => {
            imgEl.classList.add('md-diff-img-frame');
            if (hunk.source === 'user') imgEl.classList.add('is-user-blue');
          });
        });
      }

      // Fenced Code Block (<pre class="md-code">) in-place diff rendering
      if (hunk.kind === 'mod' && matchedBlocks.length === 1 && matchedBlocks[0].tagName === 'PRE' && matchedBlocks[0].classList.contains('md-code')) {
        const preNode = matchedBlocks[0];
        const codeNode = preNode.querySelector('code') || preNode;
        const stripFence = arr => arr.filter(l => !/^\s*(?:`{3,}|~{3,})/.test(String(l || ''))).join('\n');
        const bCode = stripFence(baseArr);
        const dCode = stripFence(draftArr);
        if (!codeNode.hasAttribute('data-orig-inline-html')) {
          codeNode.setAttribute('data-orig-inline-html', codeNode.innerHTML);
        }
        codeNode.innerHTML = renderWordDiffHtml(bCode, dCode, 'both', hunk.source);
        preNode.style.position = 'relative';
        preNode.append(createFloatingHunkPill(index, { includeViewToggle: false, source: hunk.source }));
        continue;
      }

      const isInlineBlockMod = hunk.kind === 'mod'
        && !hasImgInHunk
        && matchedBlocks.length >= 1
        && (canPairDirect || canPairNonEmpty)
        && !baseArr.some(splitPipeRow)
        && !draftArr.some(splitPipeRow)
        && !baseArr.some(l => /^\s*(?:`{3,}|~{3,})/.test(String(l || '')))
        && !draftArr.some(l => /^\s*(?:`{3,}|~{3,})/.test(String(l || '')))
        && matchedBlocks.every(b => ['P', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'LI', 'BLOCKQUOTE'].includes(b.tagName));

      if (isInlineBlockMod) {
        const stripMdPrefix = s => String(s || '').replace(/^(?:#{1,6}\s+|>\s+|\s*[-*+]\s+(?:\[[ xX]\]\s+)?|\s*\d+[.)]\s+(?:\[[ xX]\]\s+)?)/, '');
        const bList = canPairDirect ? baseArr : baseNonEmpty;
        const dList = canPairDirect ? draftArr : draftNonEmpty;
        for (let k = 0; k < matchedBlocks.length; k++) {
          const targetNode = matchedBlocks[k];
          const bStr = stripMdPrefix(bList[k]);
          const dStr = stripMdPrefix(dList[k]);
          if (bStr === dStr) {
            targetNode.classList.remove('md-preview-diff-mod', 'md-diff-user-blue', 'is-user-blue');
            targetNode.removeAttribute('data-diff-hunk-index');
            continue;
          }
          if (!targetNode.hasAttribute('data-orig-inline-html')) {
            targetNode.setAttribute('data-orig-inline-html', targetNode.innerHTML);
          }
          const existingCheckbox = targetNode.querySelector('input[type="checkbox"]');
          const cbClone = existingCheckbox ? existingCheckbox.cloneNode(true) : null;
          targetNode.innerHTML = renderWordDiffHtml(bStr, dStr, 'both', hunk.source);
          if (cbClone) targetNode.prepend(cbClone);
          const pill = createFloatingHunkPill(index, { includeViewToggle: false, source: hunk.source });
          attachFloatingPillAboveChangedWords(targetNode, pill);
        }
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
        else surface.append(ghost);
      } else if (matchedBlocks.length > 0) {
        matchedBlocks[0].append(createFloatingHunkPill(index, { includeViewToggle: false }));
      } else {
        const toolbar = document.createElement('div');
        toolbar.className = 'md-preview-hunk-actions';
        toolbar.dataset.diffHunkIndex = String(index);
        toolbar.append(hunkButtons(index));
        const anchor = blocks.find(block => block.line >= hunk.draftStart)?.node || null;
        if (anchor) anchor.insertAdjacentElement('beforebegin', toolbar);
        else surface.append(toolbar);
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
          if (hunk.source === 'user') el.classList.add('md-diff-user-blue', 'is-user-blue');
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
    const isUnchangedFromSaved = matchesLastSaved(editorText);
    const text = isUnchangedFromSaved ? view.ackedText : editorText;
    const realRef = String(view.realText !== undefined && view.realText !== null && view.realText !== '' ? view.realText : view.baseline || '');
    if (!isUnchangedFromSaved && cleanLineEndings(editorText) !== cleanLineEndings(realRef)) {
      view.userDraftText = editorText;
    } else if (cleanLineEndings(text) === cleanLineEndings(realRef)) {
      view.userDraftText = null;
    }
    const hunks = annotateThreeWayHunks(diff.diffLines(diffBaseline(), text), diffBaseline(), text);
    view.hunks = hunks;
    if (view.mode === 'source') renderSourceDiff(hunks, text);
    else if (view.mode === 'visual') renderVisualDiff(hunks, text);
    document.documentElement.dataset.mdPendingHunks = String(hunks.length);
    updateStickyDiffBar(hunks);
    syncParallelSecondaryPane(text, hunks);
    return hunks;
  };
  const DIFF_SOURCE_DEBOUNCE_MS = 500;
  const DIFF_SOURCE_FAST_DEBOUNCE_MS = 120;
  const queueDiff = () => {
    clearTimeout(view.diffTimer);
    const delay = view.mode === 'source' ? DIFF_SOURCE_DEBOUNCE_MS : 180;
    view.diffTimer = setTimeout(renderDraftDiff, delay);
  };
  const fetchWorkState = () => api('/api/work?p=' + encodeURIComponent(path));

  const adoptSavedBaseline = state => {
    if (!state?.saved) return false;
    view.version = state.saved.version; // md_temp, not the project .md
    view.baseline = state.saved.content;
    view.realText = state.realContent ?? state.work?.realContent ?? state.saved.content;
    view.realVersion = state.realVersion || state.currentVersion;
    view.userDraftText = state.userDraft?.content ?? null;
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
    if (refreshingReal || view.loading || view.saving || document.hidden) return false;
    if (activeLiveEditorCleanup || preview.querySelector('[contenteditable="true"]')) return false;
    refreshingReal = true;
    try {
      const state = await fetchWorkState();
      if (!state?.saved) return false;
      const currentVersion = state.currentVersion;
      const realVersion = state.realVersion || state.work?.realHash || state.currentVersion;
      const realText = state.work?.content ?? state.saved.content;
      const wasMissing = view.workState === 'missing';
      const versionUnchanged = (
        currentVersion === view.currentVersion &&
        (!state.realVersion || state.realVersion === view.realVersion) &&
        state.saved.version === view.version &&
        !wasMissing
      );
      if (versionUnchanged)
        return false;
      if (!wasMissing && !view.active) {
        const nextBaseClean = cleanLineEndings(state.saved.content);
        const nextRealClean = cleanLineEndings(state.realContent ?? state.work?.realContent ?? state.saved.content);
        const nextMergedClean = cleanLineEndings(realText);
        const curBaseClean = cleanLineEndings(view.baseline);
        const curRealClean = cleanLineEndings(view.realText || view.baseline);
        const curMergedClean = cleanLineEndings(view.lastRenderedPreviewText || view.ackedText || view.baseline);
        if (nextBaseClean === curBaseClean && nextRealClean === curRealClean && nextMergedClean === curMergedClean) {
          view.version = state.saved.version;
          view.currentVersion = currentVersion;
          view.realVersion = realVersion;
          view.workHash = state.work?.hash || null;
          view.workState = state.state || (view.workHash ? 'pending' : 'clean');
          return false;
        }
      }
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
        view.realVersion = realVersion;
        view.workHash = state.work?.hash || null;
        view.lastSaved = realText;
        view.ackedText = realText;
        await applyWorkingText(merge.text, view.workHash, {backed: false});
        return flushWorkingCopy(merge.text);
      }
      adoptSavedBaseline(state);
      syncStatusVisibility();
      view.currentVersion = currentVersion;
      view.realVersion = realVersion;
      view.workHash = state.work?.hash || null;
      view.lastSaved = realText;
      view.ackedText = realText;
      if (view.active && view.instance) {
        await applyWorkingText(realText, view.workHash, {backed: true});
      } else {
        await renderDraftPreview(realText);
      }
      if (view.piTurn) {
        view.piTurn.expectedRevision = view.revision;
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

  function setBotEditorLock(_locked) {
    root?.classList.remove('md-bot-turn-locked');
    if (view.host) view.host.classList.remove('md-bot-turn-locked');
    if (secondaryPane) secondaryPane.classList.remove('md-bot-turn-locked');
    restoreButtons();
  }

  function ensureBotShimmerBanner() {
    const existing = document.getElementById('mdBotShimmerBanner');
    if (existing) existing.remove();
    const dummy = document.createElement('div');
    dummy.hidden = true;
    return dummy;
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
      view.realVersion = state.realVersion || state.currentVersion;
      view.baseline = state.saved.content;
      view.realText = state.realContent ?? state.work?.realContent ?? state.saved.content;
      view.userDraftText = state.userDraft?.content ?? null;
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
    resetBotWatchdog();
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
      resetBotWatchdog();
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
      if (typeof view.instance?.replaceExternalText === 'function') {
        view.applyingPi = true;
        try {
          await view.instance.replaceExternalText(next, { acknowledge: backed });
        } finally {
          view.applyingPi = false;
        }
        view.revision += 1;
      } else {
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
    if (!view.version || !view.instance?.takePendingPatches) return false;
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
              allowConcurrent: true,
              userDraft: true,
            }),
          });
          view.instance.acknowledgePatches(batch);
          const persistedText = batch.after.toString();
          if (view.ackedText && cleanLineEndings(view.ackedText) !== cleanLineEndings(persistedText)) {
            if (!view.undoHistoryStack.length && view.baseline && cleanLineEndings(view.baseline) !== cleanLineEndings(view.ackedText)) {
              pushUndoSnapshot(view.baseline);
            }
            pushUndoSnapshot(view.ackedText);
          } else if (!view.undoHistoryStack.length && view.baseline && cleanLineEndings(view.baseline) !== cleanLineEndings(persistedText)) {
            pushUndoSnapshot(view.baseline);
          }
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
      body: JSON.stringify({path, content:bodyText, expectHash:hash, baseVersion:version, allowConcurrent:true, userDraft:true}),
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
        if (view.ackedText && cleanLineEndings(view.ackedText) !== cleanLineEndings(persistedText)) {
          if (!view.undoHistoryStack.length && view.baseline && cleanLineEndings(view.baseline) !== cleanLineEndings(view.ackedText)) {
            pushUndoSnapshot(view.baseline);
          }
          pushUndoSnapshot(view.ackedText);
        } else if (!view.undoHistoryStack.length && view.baseline && cleanLineEndings(view.baseline) !== cleanLineEndings(persistedText)) {
          pushUndoSnapshot(view.baseline);
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
    if (!view.active || view.applyingPi) return;
    if (view.mode === 'visual' && typeof view.instance?.isCleanFromMount === 'function' && view.instance.isCleanFromMount()) {
      return;
    }
    view.dirty = true;
    view.revision += 1;
    if (view.conflict) {
      status('Concurrent file edit: reviewing changes before writing.', 'error');
    }
    clearTimeout(view.checkTimer);
    const observedRevision = view.revision;
    const checkDelay = view.mode === 'visual' ? 150 : 60;
    view.checkTimer = setTimeout(() => {
      if (!view.active || !view.instance || observedRevision !== view.revision) return;
      const curText = getEditorText();
      if (matchesLastSaved(curText)) {
        view.dirty = cleanLineEndings(curText) !== cleanLineEndings(view.baseline);
        queueDraft();
        queueDiff();
        return;
      }
      queueDraft();
      queueDiff();
    }, checkDelay);
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
    if (topActions) topActions.hidden = !(view.active || paged || view.dirty);
    syncStatusVisibility();
  };

  const ensureShellStyle = () => {
    if (document.querySelector('link[href="/static/markdown_visual_shell.css"]')) return;
    const sheet = document.createElement('link');
    sheet.rel = 'stylesheet';
    sheet.href = '/static/markdown_visual_shell.css';
    document.head.appendChild(sheet);
  };

  // v9.22 Zero-Milkdown Hybrid Option 1 + Option 3 DOCX-Style Visual Editor
  async function createDocxHybridVisualEditor(editorHost, initialMarkdown, onChanged, docPath, onStatus) {
    ensureShellStyle();
    editorHost.textContent = '';
    let currentMd = String(initialMarkdown ?? '');
    let cleanFromMount = true;
    let activeLineIdx = 0;
    let activeBlockEl = null;
    let activeTableInfo = null;
    let localUndoStack = [];
    let localRedoStack = [];
    let activeCleanup = null;

    const pushLocalUndo = (prevMd = currentMd) => {
      if (!localUndoStack.length || localUndoStack[localUndoStack.length - 1] !== prevMd) {
        localUndoStack.push(prevMd);
        if (localUndoStack.length > 80) localUndoStack.shift();
      }
      localRedoStack = [];
    };

    const studio = document.createElement('div');
    studio.className = 'md-docx-studio';

    // 1. Sticky DOCX Formatting Ribbon
    const ribbon = document.createElement('div');
    ribbon.className = 'md-docx-ribbon';
    ribbon.setAttribute('role', 'toolbar');
    ribbon.setAttribute('aria-label', 'DOCX Visual Formatting Toolbar');
    ribbon.innerHTML = `
      <div class="md-docx-group">
        <button type="button" class="md-docx-btn" data-docx-cmd="undo" title="Undo (Ctrl+Z)">↶</button>
        <button type="button" class="md-docx-btn" data-docx-cmd="redo" title="Redo (Ctrl+Y)">↷</button>
      </div>
      <span class="md-docx-sep"></span>
      <div class="md-docx-group">
        <button type="button" class="md-docx-btn" data-docx-cmd="block-p" title="Normal Paragraph">P</button>
        <button type="button" class="md-docx-btn" data-docx-cmd="block-h1" title="Heading 1 (#)">H1</button>
        <button type="button" class="md-docx-btn" data-docx-cmd="block-h2" title="Heading 2 (##)">H2</button>
        <button type="button" class="md-docx-btn" data-docx-cmd="block-h3" title="Heading 3 (###)">H3</button>
        <button type="button" class="md-docx-btn" data-docx-cmd="block-quote" title="Blockquote (>)">❝ Quote</button>
        <button type="button" class="md-docx-btn" data-docx-cmd="block-callout" title="Callout Box (> [!NOTE])">💡 Callout</button>
        <button type="button" class="md-docx-btn" data-docx-cmd="block-code" title="Code Block (\`\`\`)">&lt;/&gt; Code</button>
      </div>
      <span class="md-docx-sep"></span>
      <div class="md-docx-group">
        <button type="button" class="md-docx-btn" data-docx-cmd="bold" title="Bold (Ctrl+B)"><b>B</b></button>
        <button type="button" class="md-docx-btn" data-docx-cmd="italic" title="Italic (Ctrl+I)"><i>I</i></button>
        <button type="button" class="md-docx-btn" data-docx-cmd="strike" title="Strikethrough (~~)"><s>S</s></button>
        <button type="button" class="md-docx-btn" data-docx-cmd="inline-code" title="Inline Code (\`code\`)"><code>&lt;&gt;</code></button>
        <button type="button" class="md-docx-btn" data-docx-cmd="highlight" title="Highlight (==text==)">🖍</button>
        <button type="button" class="md-docx-btn" data-docx-cmd="link" title="Insert Hyperlink (Ctrl+K)">🔗 Link</button>
      </div>
      <span class="md-docx-sep"></span>
      <div class="md-docx-group">
        <button type="button" class="md-docx-btn" data-docx-cmd="ul" title="Bullet List (- item)">• List</button>
        <button type="button" class="md-docx-btn" data-docx-cmd="ol" title="Numbered List (1. item)">1. List</button>
        <button type="button" class="md-docx-btn" data-docx-cmd="task" title="Task Checklist (- [ ] item)">☑ Task</button>
      </div>
      <span class="md-docx-sep"></span>
      <div class="md-docx-group">
        <button type="button" class="md-docx-btn" data-docx-cmd="insert-table" title="Insert 3×3 Table">⊞ +Table</button>
        <button type="button" class="md-docx-btn" data-docx-cmd="insert-hr" title="Insert Horizontal Rule (---)">― Rule</button>
        <button type="button" class="md-docx-btn" data-docx-cmd="insert-p" title="Insert New Paragraph Below">＋ Block</button>
        <button type="button" class="md-docx-btn" data-docx-cmd="toggle-raw-block" title="Option 1+3 Hybrid: Edit raw Markdown syntax of active block (Alt+M)">⌨ Hybrid Syntax</button>
      </div>
      <div class="md-docx-block-actions" data-docx-block-actions>
        <span class="md-docx-block-tag" data-docx-block-tag>L1</span>
        <button type="button" class="md-docx-btn" data-docx-blk="up" title="Move Block Up">↑</button>
        <button type="button" class="md-docx-btn" data-docx-blk="down" title="Move Block Down">↓</button>
        <button type="button" class="md-docx-btn" data-docx-blk="dup" title="Duplicate Block">⧉</button>
        <button type="button" class="md-docx-btn" data-docx-blk="del" title="Delete Block">🗑</button>
      </div>
    `;

    // 2. Contextual Table Studio Bar
    const tableBar = document.createElement('div');
    tableBar.className = 'md-docx-table-bar';
    tableBar.hidden = true;
    tableBar.innerHTML = `
      <span class="md-docx-table-label">⊞ Table Studio:</span>
      <button type="button" class="md-docx-btn" data-docx-table="row-above" title="Insert Row Above">+Row ↑</button>
      <button type="button" class="md-docx-btn" data-docx-table="row-below" title="Insert Row Below">+Row ↓</button>
      <button type="button" class="md-docx-btn" data-docx-table="row-del" title="Delete Current Row">−Row</button>
      <span class="md-docx-sep"></span>
      <button type="button" class="md-docx-btn" data-docx-table="col-left" title="Insert Column Left">+Col ←</button>
      <button type="button" class="md-docx-btn" data-docx-table="col-right" title="Insert Column Right">+Col →</button>
      <button type="button" class="md-docx-btn" data-docx-table="col-del" title="Delete Current Column">−Col</button>
      <span class="md-docx-sep"></span>
      <button type="button" class="md-docx-btn" data-docx-table="align-left" title="Align Column Left">⬅ Left</button>
      <button type="button" class="md-docx-btn" data-docx-table="align-center" title="Align Column Center">⬌ Center</button>
      <button type="button" class="md-docx-btn" data-docx-table="align-right" title="Align Column Right">➡ Right</button>
    `;

    // 3. DOCX Page Canvas
    const canvas = document.createElement('div');
    canvas.className = 'md-docx-canvas';
    const surface = document.createElement('article');
    surface.className = 'md-preview md-docx-surface';
    canvas.appendChild(surface);

    const bottomDock = document.createElement('div');
    bottomDock.className = 'md-docx-bottom-dock';
    bottomDock.append(tableBar, ribbon);
    studio.append(canvas, bottomDock);
    editorHost.appendChild(studio);

    const blockTagEl = ribbon.querySelector('[data-docx-block-tag]');
    const updateBlockTag = (tag, lineOneBased) => {
      if (blockTagEl) blockTagEl.textContent = `${tag || 'BLOCK'} · L${Math.max(1, lineOneBased || 1)}`;
    };

    const renderSurfaceFromMarkdown = async (mdText, { preserveActive = false } = {}) => {
      const res = await api('/api/md/render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: docPath || path, content: mdText }),
      });
      const holder = document.createElement('div');
      holder.innerHTML = String(res.html || '');
      const nextArt = holder.querySelector('article.md-preview');
      if (nextArt) {
        const needsMermaid = patchPreviewDomIncrementally(surface, nextArt);
        if (needsMermaid) {
          await globalThis.__lanternMarkdownPreview?.refresh?.(surface);
        }
      }
      if (!preserveActive) {
        activeBlockEl = surface.querySelector(`[data-l="${activeLineIdx + 1}"]`) || surface.querySelector('[data-l]');
        if (activeBlockEl) {
          surface.querySelectorAll('.md-docx-active-block').forEach(el => el.classList.remove('md-docx-active-block'));
          activeBlockEl.classList.add('md-docx-active-block');
          updateBlockTag(activeBlockEl.tagName, Number(activeBlockEl.getAttribute('data-l')) || 1);
        }
      }
    };

    const applyNextMarkdown = async (nextRawMd, msg = '', { reRender = true, recordUndo = true } = {}) => {
      const refEolSource = String(view.baseline || currentMd || '');
      const docEol = refEolSource.includes('\r\n') ? '\r\n' : '\n';
      const normalized = String(nextRawMd ?? '').replace(/\r\n?/g, '\n').split('\n').join(docEol);
      if (cleanLineEndings(normalized) === cleanLineEndings(currentMd)) return false;
      if (recordUndo) pushLocalUndo(currentMd);
      currentMd = normalized;
      cleanFromMount = false;
      if (reRender) {
        await renderSurfaceFromMarkdown(currentMd);
      }
      if (typeof onChanged === 'function') onChanged();
      if (msg && typeof onStatus === 'function') onStatus(msg, 'info');
      return true;
    };

    // Initial render of surface from preview or server
    if (preview && preview.innerHTML.trim() && cleanLineEndings(currentMd) === cleanLineEndings(view.lastRenderedPreviewText || view.ackedText || view.baseline || '')) {
      surface.innerHTML = preview.innerHTML;
      clearPreviewDiff(surface);
    } else {
      await renderSurfaceFromMarkdown(currentMd);
    }

    const resolveActiveBlockSpan = () => {
      const lines = currentMd.replace(/\r\n?/g, '\n').split('\n');
      const blocks = parseTopLevelMarkdownBlocks(currentMd);
      const found = blocks.find(b => activeLineIdx >= b.startLine && activeLineIdx < b.endLine)
        || blocks.find(b => Math.abs(b.startLine - activeLineIdx) <= 1)
        || { startLine: Math.max(0, Math.min(lines.length - 1, activeLineIdx)), endLine: Math.min(lines.length, activeLineIdx + 1) };
      return { lines, startLine: found.startLine, endLine: Math.max(found.startLine + 1, found.endLine) };
    };

    const openHybridRawBlockEditor = () => {
      if (activeCleanup) activeCleanup(true);
      const { lines, startLine, endLine } = resolveActiveBlockSpan();
      const targetDom = surface.querySelector(`[data-l="${startLine + 1}"]`) || activeBlockEl || surface.querySelector('[data-l]');
      if (!targetDom) return;
      const origBlockMd = lines.slice(startLine, endLine).join('\n');
      const ta = document.createElement('textarea');
      ta.className = 'md-docx-raw-block-editor';
      ta.value = origBlockMd;
      ta.rows = Math.max(3, Math.min(18, origBlockMd.split('\n').length + 1));
      targetDom.hidden = true;
      targetDom.insertAdjacentElement('afterend', ta);
      ta.focus();

      let closed = false;
      const finishRaw = async (commit) => {
        if (closed) return;
        closed = true;
        activeCleanup = null;
        const nextVal = ta.value.replace(/\r\n?/g, '\n');
        ta.remove();
        targetDom.hidden = false;
        if (!commit || nextVal === origBlockMd) return;
        const freshLines = currentMd.replace(/\r\n?/g, '\n').split('\n');
        freshLines.splice(startLine, endLine - startLine, ...nextVal.split('\n'));
        await applyNextMarkdown(freshLines.join('\n'), `Updated block L${startLine + 1} via Hybrid Syntax.`);
      };
      activeCleanup = finishRaw;
      ta.addEventListener('keydown', ev => {
        if (ev.key === 'Escape') {
          ev.preventDefault();
          void finishRaw(false);
        } else if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) {
          ev.preventDefault();
          void finishRaw(true);
        } else if (ev.key.toLowerCase() === 's' && (ev.ctrlKey || ev.metaKey)) {
          ev.preventDefault();
          void finishRaw(true).then(() => save(true));
        }
      });
      ta.addEventListener('blur', () => { void finishRaw(true); });
    };

    const executeTableOperation = async (op) => {
      if (activeCleanup) activeCleanup(true);
      if (!activeTableInfo) return;
      const { tableStartIdx, rowIdx, colIdx } = activeTableInfo;
      const lines = currentMd.replace(/\r\n?/g, '\n').split('\n');
      let tStart = Math.max(0, Math.min(lines.length - 1, tableStartIdx));
      while (tStart > 0 && String(lines[tStart - 1] || '').trim().startsWith('|')) tStart--;
      let tEnd = tStart;
      while (tEnd < lines.length && String(lines[tEnd] || '').trim().startsWith('|')) tEnd++;
      if (tEnd - tStart < 2) return;

      const tableLines = lines.slice(tStart, tEnd);
      const parsedRows = tableLines.map(l => splitGfmRowCells(l));
      const colCount = Math.max(1, ...parsedRows.map(r => r.length));
      parsedRows.forEach(r => { while (r.length < colCount) r.push(''); });

      const targetRow = Math.max(0, Math.min(parsedRows.length - 1, rowIdx));
      const targetCol = Math.max(0, Math.min(colCount - 1, colIdx));

      if (op === 'row-above' || op === 'row-below') {
        const insertAt = op === 'row-above' ? Math.max(2, targetRow) : Math.max(2, targetRow + 1);
        const blankRow = new Array(colCount).fill('New cell');
        parsedRows.splice(insertAt, 0, blankRow);
      } else if (op === 'row-del') {
        if (parsedRows.length <= 3 || targetRow < 2) return;
        parsedRows.splice(targetRow, 1);
      } else if (op === 'col-left' || op === 'col-right') {
        const insertCol = op === 'col-left' ? targetCol : targetCol + 1;
        parsedRows.forEach((r, rIdx) => {
          if (rIdx === 0) r.splice(insertCol, 0, `Col ${insertCol + 1}`);
          else if (rIdx === 1) r.splice(insertCol, 0, '---');
          else r.splice(insertCol, 0, '');
        });
      } else if (op === 'col-del') {
        if (colCount <= 1) return;
        parsedRows.forEach(r => r.splice(targetCol, 1));
      } else if (op === 'align-left' || op === 'align-center' || op === 'align-right') {
        if (parsedRows.length >= 2) {
          parsedRows[1][targetCol] = op === 'align-left' ? ':---' : (op === 'align-center' ? ':---:' : '---:');
        }
      }

      const serializedTable = parsedRows.map(r => '| ' + r.join(' | ') + ' |');
      lines.splice(tStart, tEnd - tStart, ...serializedTable);
      await applyNextMarkdown(lines.join('\n'), `Table updated (${op}).`);
    };

    tableBar.addEventListener('mousedown', ev => {
      if (ev.target.closest('button')) ev.preventDefault();
    });
    tableBar.addEventListener('click', ev => {
      const btn = ev.target.closest('[data-docx-table]');
      if (!btn) return;
      ev.stopPropagation();
      void executeTableOperation(btn.getAttribute('data-docx-table'));
    });

    ribbon.addEventListener('mousedown', ev => {
      if (ev.target.closest('button')) ev.preventDefault();
    });
    ribbon.addEventListener('click', async ev => {
      const blkBtn = ev.target.closest('[data-docx-blk]');
      if (blkBtn) {
        ev.stopPropagation();
        if (activeCleanup) activeCleanup(true);
        const action = blkBtn.getAttribute('data-docx-blk');
        const blocks = parseTopLevelMarkdownBlocks(currentMd);
        const lines = currentMd.replace(/\r\n?/g, '\n').split('\n');
        const bIdx = blocks.findIndex(b => activeLineIdx >= b.startLine && activeLineIdx < b.endLine);
        if (bIdx < 0) return;
        const curB = blocks[bIdx];
        const slice = lines.slice(curB.startLine, curB.endLine);
        if (action === 'up' && bIdx > 0) {
          const prevB = blocks[bIdx - 1];
          const prevSlice = lines.slice(prevB.startLine, prevB.endLine);
          lines.splice(prevB.startLine, curB.endLine - prevB.startLine, ...slice, '', ...prevSlice);
          activeLineIdx = prevB.startLine;
          await applyNextMarkdown(lines.join('\n'), 'Moved block up.');
        } else if (action === 'down' && bIdx < blocks.length - 1) {
          const nextB = blocks[bIdx + 1];
          const nextSlice = lines.slice(nextB.startLine, nextB.endLine);
          lines.splice(curB.startLine, nextB.endLine - curB.startLine, ...nextSlice, '', ...slice);
          activeLineIdx = curB.startLine + nextSlice.length + 1;
          await applyNextMarkdown(lines.join('\n'), 'Moved block down.');
        } else if (action === 'dup') {
          lines.splice(curB.endLine, 0, '', ...slice);
          activeLineIdx = curB.endLine + 1;
          await applyNextMarkdown(lines.join('\n'), 'Duplicated block.');
        } else if (action === 'del') {
          if (blocks.length <= 1) return;
          lines.splice(curB.startLine, Math.min(lines.length - curB.startLine, (curB.endLine - curB.startLine) + 1));
          activeLineIdx = Math.max(0, curB.startLine - 1);
          await applyNextMarkdown(lines.join('\n'), 'Deleted block.');
        }
        return;
      }

      const cmdBtn = ev.target.closest('[data-docx-cmd]');
      if (!cmdBtn) return;
      ev.stopPropagation();
      const cmd = cmdBtn.getAttribute('data-docx-cmd');

      if (cmd === 'undo') {
        if (activeCleanup) activeCleanup(true);
        if (!localUndoStack.length) return;
        const prev = localUndoStack.pop();
        localRedoStack.push(currentMd);
        await applyNextMarkdown(prev, 'Undo in Visual Editor.', { recordUndo: false });
        return;
      }
      if (cmd === 'redo') {
        if (activeCleanup) activeCleanup(true);
        if (!localRedoStack.length) return;
        const next = localRedoStack.pop();
        localUndoStack.push(currentMd);
        await applyNextMarkdown(next, 'Redo in Visual Editor.', { recordUndo: false });
        return;
      }
      if (cmd === 'toggle-raw-block') {
        openHybridRawBlockEditor();
        return;
      }

      const editingNode = surface.querySelector('[contenteditable="true"]');
      if (editingNode && ['bold', 'italic', 'strike', 'inline-code', 'highlight', 'link'].includes(cmd)) {
        const sel = window.getSelection?.();
        const selectedTxt = (sel && !sel.isCollapsed && editingNode.contains(sel.anchorNode)) ? sel.toString() : '';
        if (cmd === 'bold' && typeof document.execCommand === 'function') {
          document.execCommand('bold');
          return;
        }
        if (cmd === 'italic' && typeof document.execCommand === 'function') {
          document.execCommand('italic');
          return;
        }
        if (cmd === 'strike' && typeof document.execCommand === 'function') {
          document.execCommand('strikeThrough');
          return;
        }
        const wrapTarget = selectedTxt || 'text';
        let replacementHtml = '';
        if (cmd === 'inline-code') replacementHtml = `<code>${wrapTarget}</code>`;
        else if (cmd === 'highlight') replacementHtml = `<mark>${wrapTarget}</mark>`;
        else if (cmd === 'link') {
          const url = prompt('Enter link URL:', 'https://') || 'https://';
          replacementHtml = `<a href="${url}">${selectedTxt || 'link'}</a>`;
        }
        if (replacementHtml && typeof document.execCommand === 'function') {
          document.execCommand('insertHTML', false, replacementHtml);
          return;
        }
      }

      if (activeCleanup) activeCleanup(true);
      const lines = currentMd.replace(/\r\n?/g, '\n').split('\n');
      const idx = Math.max(0, Math.min(lines.length - 1, activeLineIdx));
      const curLine = String(lines[idx] ?? '');
      const cleanBody = curLine.replace(/^(\s*(?:[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+|#{1,6}\s+|>\s*(?:\[![A-Z]+\]\s*)?))/, '').trim() || 'New text';

      if (cmd === 'block-p') lines[idx] = cleanBody;
      else if (cmd === 'block-h1') lines[idx] = `# ${cleanBody}`;
      else if (cmd === 'block-h2') lines[idx] = `## ${cleanBody}`;
      else if (cmd === 'block-h3') lines[idx] = `### ${cleanBody}`;
      else if (cmd === 'block-quote') lines[idx] = `> ${cleanBody}`;
      else if (cmd === 'block-callout') lines.splice(idx, 1, '> [!NOTE]', `> ${cleanBody}`);
      else if (cmd === 'block-code') lines.splice(idx, 1, '```', cleanBody, '```');
      else if (cmd === 'ul') lines[idx] = `- ${cleanBody}`;
      else if (cmd === 'ol') lines[idx] = `1. ${cleanBody}`;
      else if (cmd === 'task') lines[idx] = `- [ ] ${cleanBody}`;
      else if (cmd === 'bold') lines[idx] = curLine.includes('**') ? curLine : `**${cleanBody}**`;
      else if (cmd === 'italic') lines[idx] = `*${cleanBody}*`;
      else if (cmd === 'strike') lines[idx] = `~~${cleanBody}~~`;
      else if (cmd === 'inline-code') lines[idx] = `\`${cleanBody}\``;
      else if (cmd === 'highlight') lines[idx] = `==${cleanBody}==`;
      else if (cmd === 'link') lines[idx] = `[${cleanBody}](https://example.com)`;
      else if (cmd === 'insert-hr') {
        lines.splice(idx + 1, 0, '', '---', '');
        activeLineIdx = idx + 2;
      } else if (cmd === 'insert-p') {
        lines.splice(idx + 1, 0, '', 'New paragraph.');
        activeLineIdx = idx + 2;
      } else if (cmd === 'insert-table') {
        const tbl = [
          '',
          '| Column 1 | Column 2 | Column 3 |',
          '| :--- | :--- | :--- |',
          '| Cell 1 | Cell 2 | Cell 3 |',
          '| Cell 4 | Cell 5 | Cell 6 |',
          '',
        ];
        lines.splice(idx + 1, 0, ...tbl);
        activeLineIdx = idx + 2;
      }
      await applyNextMarkdown(lines.join('\n'), `Applied ${cmd} in Visual Editor.`);
    });

    surface.addEventListener('change', ev => {
      const cb = ev.target;
      if (!(cb instanceof HTMLInputElement) || cb.type !== 'checkbox') return;
      const li = cb.closest('[data-l]');
      if (!li) return;
      const lineIdx = Math.max(0, (Number(li.getAttribute('data-l')) || 1) - 1);
      const lines = currentMd.replace(/\r\n?/g, '\n').split('\n');
      if (lineIdx < lines.length && /^(\s*(?:[-*+]|\d+[.)])\s+\[)[ xX](\])/.test(lines[lineIdx])) {
        lines[lineIdx] = lines[lineIdx].replace(/^(\s*(?:[-*+]|\d+[.)])\s+\[)[ xX](\])/, `$1${cb.checked ? 'x' : ' '}$2`);
        void applyNextMarkdown(lines.join('\n'), 'Toggled task item in Visual Editor.', { reRender: false });
      }
    });

    surface.addEventListener('click', ev => {
      const sel = window.getSelection?.();
      if (sel && !sel.isCollapsed && String(sel.toString() || '').trim().length > 0) return;
      const target = ev.target instanceof Element ? ev.target : null;
      if (!target || target.closest('a, button, input, textarea, .md-hunk-actions, .md-hunk-floating-pill, .md-two-tier-diff, .md-preview-deletion, img')) return;

      const lNode = target.closest('[data-l]');
      if (lNode && surface.contains(lNode)) {
        activeBlockEl = lNode;
        activeLineIdx = Math.max(0, (Number(lNode.getAttribute('data-l')) || 1) - 1);
        view.lastActiveLine = activeLineIdx + 1;
        surface.querySelectorAll('.md-docx-active-block').forEach(el => el.classList.remove('md-docx-active-block'));
        lNode.classList.add('md-docx-active-block');
        updateBlockTag(lNode.tagName, activeLineIdx + 1);
      }

      const cell = target.closest('td, th');
      const table = cell?.closest('table');
      if (cell && table && surface.contains(table) && !cell.closest('.md-table-tr-del')) {
        tableBar.hidden = false;
        if (cell.getAttribute('contenteditable') === 'true') return;
        if (activeCleanup) activeCleanup(true);

        const lines = currentMd.replace(/\r\n?/g, '\n').split('\n');
        const tr = cell.closest('tr');
        const trAttrLine = Number(tr?.getAttribute('data-l') || 0);
        const tableAttrLine = Math.max(1, Number(table.getAttribute('data-l') || table.closest('[data-l]')?.getAttribute('data-l') || 1));
        let tableStartIdx = Math.min(lines.length - 1, tableAttrLine - 1);
        while (tableStartIdx > 0 && String(lines[tableStartIdx - 1] || '').trim().startsWith('|')) tableStartIdx--;
        while (tableStartIdx < lines.length && !String(lines[tableStartIdx] || '').trim().startsWith('|')) tableStartIdx++;

        const isHeader = Boolean(tr && tr.parentElement?.tagName === 'THEAD');
        const tbodyRows = [...(table.tBodies[0]?.rows || [])].filter(r => !r.classList.contains('md-table-tr-del'));
        const bodyIdx = tbodyRows.indexOf(tr);
        const targetLineIdx = trAttrLine > 0 ? (trAttrLine - 1) : (isHeader ? tableStartIdx : (tableStartIdx + 2 + Math.max(0, bodyIdx)));
        const colIdx = [...tr.cells].indexOf(cell);
        if (targetLineIdx < 0 || targetLineIdx >= lines.length || colIdx < 0) return;

        activeLineIdx = targetLineIdx;
        activeTableInfo = {
          tableStartIdx,
          rowIdx: targetLineIdx - tableStartIdx,
          colIdx,
          isHeader,
        };
        updateBlockTag(`CELL R${activeTableInfo.rowIdx + 1}C${colIdx + 1}`, targetLineIdx + 1);

        const rowCells = splitGfmRowCells(lines[targetLineIdx]);
        const origCellMd = (rowCells[colIdx] ?? serializeInlineEditableNode(cell, { allowNewlines: false })).trim();
        const newBadges = cell.querySelectorAll('.md-table-cell-diff > .md-table-cell-new');
        const editEl = newBadges.length > 0 ? newBadges[newBadges.length - 1] : cell;
        const savedHtml = editEl.innerHTML;
        if (newBadges.length > 0) editEl.innerHTML = formatInlineMarkdownHtml(origCellMd);

        editEl.setAttribute('contenteditable', 'true');
        editEl.setAttribute('spellcheck', 'false');
        editEl.classList.add('md-docx-inline-editing');
        editEl.focus({ preventScroll: true });

        let done = false;
        const finishCell = (commit, moveDelta = 0) => {
          if (done) return;
          done = true;
          activeCleanup = null;
          editEl.removeAttribute('contenteditable');
          editEl.classList.remove('md-docx-inline-editing');
          if (!commit) {
            editEl.innerHTML = savedHtml;
            return;
          }
          const curVal = serializeInlineEditableNode(editEl, { allowNewlines: false }).replace(/\|/g, '\\|').trim();
          if (curVal !== origCellMd) {
            const freshLines = currentMd.replace(/\r\n?/g, '\n').split('\n');
            if (targetLineIdx < freshLines.length) {
              const freshCells = splitGfmRowCells(freshLines[targetLineIdx]);
              while (freshCells.length <= colIdx) freshCells.push('');
              freshCells[colIdx] = curVal;
              freshLines[targetLineIdx] = '| ' + freshCells.join(' | ') + ' |';
              editEl.innerHTML = formatInlineMarkdownHtml(curVal);
              void applyNextMarkdown(freshLines.join('\n'), `Updated cell L${targetLineIdx + 1}.`, { reRender: false });
            }
          } else {
            editEl.innerHTML = savedHtml;
          }
          if (moveDelta !== 0) {
            const editableCells = [...table.querySelectorAll('th, td')].filter(c => !c.closest('.md-table-tr-del'));
            const curFlat = editableCells.indexOf(cell);
            const nextCell = editableCells[curFlat + moveDelta];
            if (nextCell) {
              nextCell.click();
            } else if (moveDelta > 0 && curFlat === editableCells.length - 1) {
              void executeTableOperation('row-below');
            }
          }
        };
        activeCleanup = finishCell;
        const onKey = kev => {
          if (kev.key === 'Escape') { kev.preventDefault(); finishCell(false, 0); }
          else if (kev.key === 'Enter' && !kev.shiftKey) { kev.preventDefault(); finishCell(true, 0); }
          else if (kev.key === 'Tab') { kev.preventDefault(); finishCell(true, kev.shiftKey ? -1 : 1); }
          else if (kev.altKey && kev.key.toLowerCase() === 'm') { kev.preventDefault(); openHybridRawBlockEditor(); }
          else if ((kev.ctrlKey || kev.metaKey) && kev.key.toLowerCase() === 's') {
            kev.preventDefault();
            finishCell(true, 0);
            setTimeout(() => { void save(true); }, 60);
          }
        };
        const onBlur = () => {
          editEl.removeEventListener('keydown', onKey);
          editEl.removeEventListener('blur', onBlur);
          finishCell(true, 0);
        };
        editEl.addEventListener('keydown', onKey);
        editEl.addEventListener('blur', onBlur);
        return;
      }

      tableBar.hidden = true;
      activeTableInfo = null;

      const preNode = target.closest('pre.md-code[data-l]');
      if (preNode && surface.contains(preNode)) {
        const codeEl = preNode.querySelector('code') || preNode;
        if (codeEl.getAttribute('contenteditable') === 'true') return;
        if (activeCleanup) activeCleanup(true);
        const lines = currentMd.replace(/\r\n?/g, '\n').split('\n');
        const hintIdx = Math.max(0, (Number(preNode.getAttribute('data-l')) || 1) - 1);
        let fStart = hintIdx;
        while (fStart >= 0 && !/^\s*(`{3,}|~{3,})/.test(String(lines[fStart] || ''))) fStart--;
        if (fStart < 0) fStart = hintIdx;
        const fMatch = String(lines[fStart] || '').match(/^\s*(`{3,}|~{3,})/);
        const fTok = fMatch ? fMatch[1] : '```';
        let fEnd = fStart + 1;
        while (fEnd < lines.length && !String(lines[fEnd] || '').trim().startsWith(fTok)) fEnd++;
        const origBody = lines.slice(fStart + 1, fEnd).join('\n');
        const savedHtml = codeEl.innerHTML;
        codeEl.textContent = origBody;
        codeEl.setAttribute('contenteditable', 'true');
        codeEl.setAttribute('spellcheck', 'false');
        codeEl.classList.add('md-docx-inline-editing');
        codeEl.focus({ preventScroll: true });

        let done = false;
        const finishCode = (commit) => {
          if (done) return;
          done = true;
          activeCleanup = null;
          codeEl.removeAttribute('contenteditable');
          codeEl.classList.remove('md-docx-inline-editing');
          if (!commit) { codeEl.innerHTML = savedHtml; return; }
          const nextBody = String(codeEl.innerText ?? codeEl.textContent ?? '').replace(/\r\n?/g, '\n').replace(/\n$/, '');
          if (nextBody === origBody) { codeEl.innerHTML = savedHtml; return; }
          const fresh = currentMd.replace(/\r\n?/g, '\n').split('\n');
          fresh.splice(fStart + 1, Math.max(0, fEnd - (fStart + 1)), ...nextBody.split('\n'));
          void applyNextMarkdown(fresh.join('\n'), `Updated code block L${fStart + 1}.`, { reRender: false });
        };
        activeCleanup = finishCode;
        codeEl.addEventListener('keydown', kev => {
          if (kev.key === 'Escape') { kev.preventDefault(); finishCode(false); }
          else if (kev.key === 'Enter' && (kev.ctrlKey || kev.metaKey)) { kev.preventDefault(); finishCode(true); }
        });
        codeEl.addEventListener('blur', () => finishCode(true), { once: true });
        return;
      }

      const blockNode = target.closest('li[data-l], p[data-l], h1[data-l], h2[data-l], h3[data-l], h4[data-l], h5[data-l], h6[data-l], blockquote[data-l]');
      if (!blockNode || !surface.contains(blockNode)) return;
      if (blockNode.getAttribute('contenteditable') === 'true') return;
      if (activeCleanup) activeCleanup(true);

      const isHeading = /^H[1-6]$/.test(blockNode.tagName);
      const allowNewlines = !isHeading;
      const lines = currentMd.replace(/\r\n?/g, '\n').split('\n');
      const hintLineIdx = Math.max(0, (Number(blockNode.getAttribute('data-l')) || 1) - 1);
      const hiddenGhosts = [...blockNode.querySelectorAll('.md-diff-word-del, [data-md-diff-ghost]')];
      hiddenGhosts.forEach(g => { g.hidden = true; });
      blockNode.querySelectorAll('.md-hunk-floating-pill, .md-hunk-actions, input[type="checkbox"]').forEach(el => {
        el.setAttribute('contenteditable', 'false');
      });

      const initialSer = serializeInlineEditableNode(blockNode, { allowNewlines });
      const origPlain = stripMarkdownLineSyntaxForMatch(initialSer);
      const targetLineIdx = findBestMatchingLineIndex(lines, hintLineIdx, origPlain);
      activeLineIdx = targetLineIdx;
      const spanEndIdx = blockNode.tagName === 'P' ? computeParagraphSpanEnd(lines, targetLineIdx) : (targetLineIdx + 1);
      const spanCount = Math.max(1, spanEndIdx - targetLineIdx);
      const origRawLine = String(lines[targetLineIdx] ?? '');
      const prefixMatch = origRawLine.match(/^(\s*(?:[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+|#{1,6}\s+|>\s?))/);
      const linePrefix = prefixMatch ? prefixMatch[1] : '';
      const savedHtml = blockNode.innerHTML;
      const origBlockMd = spanCount > 1 ? lines.slice(targetLineIdx, spanEndIdx).join('\n') : initialSer;

      blockNode.setAttribute('contenteditable', 'true');
      blockNode.setAttribute('spellcheck', 'false');
      blockNode.classList.add('md-docx-inline-editing');
      blockNode.focus({ preventScroll: true });

      let closed = false;
      const finishBlock = (commit, insertNewBlockBelow = false) => {
        if (closed) return;
        closed = true;
        activeCleanup = null;
        blockNode.removeAttribute('contenteditable');
        blockNode.classList.remove('md-docx-inline-editing');
        hiddenGhosts.forEach(g => { g.hidden = false; });
        if (!commit) {
          blockNode.innerHTML = savedHtml;
          return;
        }
        const nextInlineMd = serializeInlineEditableNode(blockNode, { allowNewlines });
        const freshLines = currentMd.replace(/\r\n?/g, '\n').split('\n');
        const resolvedIdx = spanCount > 1 ? targetLineIdx : findBestMatchingLineIndex(freshLines, targetLineIdx, origPlain);
        if (resolvedIdx < 0 || resolvedIdx >= freshLines.length) return;

        const changedBlock = nextInlineMd !== origBlockMd;
        const replacementLines = (changedBlock ? nextInlineMd : origBlockMd)
          .split('\n')
          .map((l, idx) => (idx === 0 && !l.startsWith(linePrefix) ? linePrefix + l : l));

        if (insertNewBlockBelow) {
          const nextPrefix = /^\s*[-*+]\s+\[[ xX]\]\s+/.test(linePrefix)
            ? linePrefix.replace(/\[[xX]\]/, '[ ]')
            : (/^\s*[-*+]\s+/.test(linePrefix) ? linePrefix : (/^\s*\d+[.)]\s+/.test(linePrefix) ? '1. ' : ''));
          const newItemLine = nextPrefix ? `${nextPrefix}New item` : 'New paragraph';
          const insertExtra = nextPrefix ? [newItemLine] : ['', newItemLine];
          freshLines.splice(resolvedIdx, spanCount, ...replacementLines, ...insertExtra);
          activeLineIdx = resolvedIdx + replacementLines.length + (nextPrefix ? 0 : 1);
          void applyNextMarkdown(freshLines.join('\n'), `Inserted new block at L${activeLineIdx + 1}.`, { reRender: true });
          return;
        }

        if (!changedBlock) {
          blockNode.innerHTML = savedHtml;
          return;
        }
        const canPatchInPlace = replacementLines.length === spanCount;
        if (canPatchInPlace) {
          const existingCb = blockNode.querySelector('input[type="checkbox"]');
          const cbClone = existingCb ? existingCb.cloneNode(true) : null;
          blockNode.innerHTML = nextInlineMd.split('\n').map(formatInlineMarkdownHtml).join('<br>');
          if (cbClone) blockNode.prepend(cbClone);
        }
        freshLines.splice(resolvedIdx, spanCount, ...replacementLines);
        void applyNextMarkdown(freshLines.join('\n'), `Updated L${resolvedIdx + 1}.`, { reRender: !canPatchInPlace });
      };
      activeCleanup = finishBlock;

      const onKeyDown = kev => {
        if (kev.key === 'Escape') {
          kev.preventDefault();
          finishBlock(false);
        } else if (kev.altKey && kev.key.toLowerCase() === 'm') {
          kev.preventDefault();
          openHybridRawBlockEditor();
        } else if (kev.key === 'Enter') {
          if (kev.ctrlKey || kev.metaKey) {
            kev.preventDefault();
            finishBlock(true, true);
          } else if (isHeading && !kev.shiftKey) {
            kev.preventDefault();
            finishBlock(true, false);
          } else if (kev.shiftKey) {
            kev.preventDefault();
            if (typeof document.execCommand === 'function') document.execCommand('insertLineBreak');
          } else {
            kev.preventDefault();
            finishBlock(true, false);
          }
        } else if ((kev.ctrlKey || kev.metaKey) && kev.key.toLowerCase() === 's') {
          kev.preventDefault();
          finishBlock(true, false);
          setTimeout(() => { void save(true); }, 60);
        }
      };
      const onBlur = () => {
        blockNode.removeEventListener('keydown', onKeyDown);
        blockNode.removeEventListener('blur', onBlur);
        finishBlock(true, false);
      };
      blockNode.addEventListener('keydown', onKeyDown);
      blockNode.addEventListener('blur', onBlur);
    });

    return {
      getMarkdown() {
        return currentMd;
      },
      isCleanFromMount() {
        return cleanFromMount;
      },
      async replaceExternalText(nextText, { acknowledge = false } = {}) {
        if (activeCleanup) activeCleanup(false);
        currentMd = String(nextText ?? '');
        cleanFromMount = Boolean(acknowledge);
        await renderSurfaceFromMarkdown(currentMd);
        return true;
      },
      setPendingDiff(mdText, hunks) {
        if (Array.isArray(hunks) && hunks.length) {
          renderPreviewDiff(hunks, mdText || currentMd, surface);
        } else {
          clearPreviewDiff(surface);
        }
        return { mapped: true, unanchored: 0 };
      },
      clearPendingDiff() {
        clearPreviewDiff(surface);
      },
      sourceLineLocator() {
        return (el) => {
          const blk = el?.closest?.('[data-l]');
          return blk ? (Number(blk.getAttribute('data-l')) || null) : null;
        };
      },
      sourceBlockAtLine(lineNo) {
        const blocks = [...surface.querySelectorAll('[data-l]')]
          .filter(el => !el.closest('.md-preview-deletion'))
          .map(el => ({ el, line: Number(el.getAttribute('data-l')) || 1 }))
          .sort((a, b) => a.line - b.line);
        if (!blocks.length) return null;
        let best = blocks[0];
        for (const item of blocks) {
          if (item.line <= lineNo) best = item;
          else break;
        }
        return best.el;
      },
      restoreBookmark(bm) {
        const line = bm?.line || 1;
        const blk = this.sourceBlockAtLine(line);
        if (blk) {
          blk.scrollIntoView({ behavior: 'smooth', block: 'center' });
          flashFocusSyncTarget(blk, line);
        }
      },
      focus() {
        const firstBlk = activeBlockEl || surface.querySelector('[data-l]');
        if (firstBlk) {
          surface.querySelectorAll('.md-docx-active-block').forEach(el => el.classList.remove('md-docx-active-block'));
          firstBlk.classList.add('md-docx-active-block');
        }
      },
      destroy() {
        if (activeCleanup) activeCleanup(true);
        studio.remove();
      },
    };
  }

  const loadBundle = async () => {
    ensureShellStyle();
    return { createVisualMarkdown: createDocxHybridVisualEditor };
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
  const loadCropBundle = async () => {
    if (globalThis.LanternImageCrop) return globalThis.LanternImageCrop;
    try {
      const mod = await import('/static/vendor/lantern-image-crop.min.js');
      if (mod?.openCrop) {
        globalThis.LanternImageCrop = mod;
        return mod;
      }
    } catch (_) {}
    if (window.__lanternCropPromise) return window.__lanternCropPromise;
    window.__lanternCropPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.type = 'module';
      script.src = '/static/vendor/lantern-image-crop.min.js';
      if (nonce) script.nonce = nonce;
      script.onload = () => globalThis.LanternImageCrop
        ? resolve(globalThis.LanternImageCrop)
        : reject(new Error('Crop editor not initialized'));
      script.onerror = () => reject(new Error('Offline Crop editor asset unavailable'));
      document.head.appendChild(script);
    }).catch(err => { window.__lanternCropPromise = null; throw err; });
    return window.__lanternCropPromise;
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
      mount.addEventListener('paste', async ev => {
        if (document.querySelector('dialog.lantern-crop-dialog[open], .lantern-crop-dialog')) return;
        const extracted = await extractOrUploadClipboardImages(ev);
        if (!extracted || !extracted.length) return;
        try {
          // v9.24: Insert as a single clean line (1 line per image, no extra blank lines above/below!)
          const singleLineInsertion = extracted.join(' ');
          if (typeof view.instance?.insertText === 'function') {
            view.instance.insertText(singleLineInsertion);
          } else if (view.instance?.replaceExternalText) {
            const cur = getEditorText();
            const bm = view.instance?.sourceBookmark?.();
            const lines = cur.replace(/\r\n?/g, '\n').split('\n');
            const lineIdx = bm?.line ? Math.max(0, Math.min(lines.length - 1, bm.line - 1)) : (lines.length - 1);
            if (lines[lineIdx] && lines[lineIdx].trim().startsWith('|')) {
              const cells = splitGfmRowCells(lines[lineIdx]);
              const targetCol = Math.max(0, cells.findIndex(c => !c.trim()));
              cells[targetCol >= 0 ? targetCol : 0] = (cells[targetCol >= 0 ? targetCol : 0] ? cells[targetCol >= 0 ? targetCol : 0] + ' ' : '') + singleLineInsertion;
              lines[lineIdx] = '| ' + cells.join(' | ') + ' |';
            } else {
              lines.splice(lineIdx + 1, 0, singleLineInsertion);
            }
            view.instance.replaceExternalText(lines.join('\n'), { acknowledge: false });
          }
          changed();
          clearTimeout(view.diffTimer);
          renderDraftDiff();
          void refreshImageAudit();
          status(`Pasted ${extracted.length} image(s) into Source (1 line).`, 'info');
        } catch (err) {
          status('Source image paste failed: ' + err.message, 'error');
        }
      }, true);
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
    if (window.__lanternMdPaged?.active) {
      return window.__lanternMdPaged.save(true);
    }
    if (view.loading || view.saving || view.conflict) {
      return;
    }
    if (view.baseline) pushUndoSnapshot(view.baseline);
    pushUndoSnapshot();
    if (view.active && view.instance && !(await saveDraft())) return;
    if (writingReal) await writingReal;
    view.saving = true;
    restoreButtons();
    try {
      const state = await fetchWorkState();
      if (!state.saved) throw new Error('Project Markdown file is unavailable');
      const curCheck = state.work?.content ?? state.userDraft?.content ?? state.realContent ?? state.saved.content;
      if (!state.work && !state.userDraft && cleanLineEndings(curCheck) === cleanLineEndings(state.saved.content)) {
        view.dirty = false;
        if (manual) status('No changes to save (already matches latest version).', 'info');
        return;
      }
      const result = await api('/api/work/save', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          path, expectHash:state.work?.hash || null,
          expectSavedVersion:state.saved.version,
        }),
      });
      const current = typeof result.mergedContent === 'string'
        ? result.mergedContent
        : (state.work?.content ?? state.saved.content);
      view.version = result.version;
      view.currentVersion = result.version;
      view.realVersion = result.version;
      view.baseline = current;
      view.realText = current;
      view.userDraftText = null;
      view.workHash = null;
      view.workState = 'clean';
      view.ackedText = current;
      view.lastSaved = current;
      if (view.active && view.instance && getEditorText() !== current) {
        await applyWorkingText(current, null, { backed: true });
      }
      view.dirty = false;
      await drafts.clear().catch(() => {});
      if (view.active) {
        renderDraftDiff();
        view.instance?.focus?.();
      } else {
        await renderDraftPreview(current);
      }
      if (manual) status('Saved version.', 'info');
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
    if (!view.active || view.loading || view.saving || kind === view.mode) return;
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
        wasDirty ? '' :
        kind === 'source' ? '' :
        '',
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

  function syncDomNodeAttributes(targetEl, sourceEl) {
    if (!targetEl || !sourceEl) return;
    const nextAttrs = new Set();
    for (const attr of [...sourceEl.attributes]) {
      nextAttrs.add(attr.name);
      if (targetEl.getAttribute(attr.name) !== attr.value) {
        targetEl.setAttribute(attr.name, attr.value);
      }
    }
    for (const attr of [...targetEl.attributes]) {
      if (!nextAttrs.has(attr.name)) {
        targetEl.removeAttribute(attr.name);
      }
    }
  }

  function patchTableDomInPlace(oldWrap, newWrap) {
    syncDomNodeAttributes(oldWrap, newWrap);
    const oldTable = oldWrap.tagName === 'TABLE' ? oldWrap : oldWrap.querySelector('table');
    const newTable = newWrap.tagName === 'TABLE' ? newWrap : newWrap.querySelector('table');
    if (!oldTable || !newTable) {
      oldWrap.innerHTML = newWrap.innerHTML;
      return;
    }
    syncDomNodeAttributes(oldTable, newTable);
    const oldThead = oldTable.tHead;
    const newThead = newTable.tHead;
    if (oldThead && newThead) {
      const oldHRow = oldThead.rows[0];
      const newHRow = newThead.rows[0];
      if (oldHRow && newHRow && oldHRow.cells.length === newHRow.cells.length) {
        syncDomNodeAttributes(oldHRow, newHRow);
        for (let c = 0; c < newHRow.cells.length; c++) {
          if (oldHRow.cells[c].innerHTML !== newHRow.cells[c].innerHTML) {
            oldHRow.cells[c].innerHTML = newHRow.cells[c].innerHTML;
          }
        }
      } else {
        oldThead.innerHTML = newThead.innerHTML;
      }
    } else if (newThead && !oldThead) {
      oldTable.prepend(newThead.cloneNode(true));
    } else if (oldThead && !newThead) {
      oldThead.remove();
    }

    const oldTbody = oldTable.tBodies[0] || oldTable.createTBody();
    const newTbody = newTable.tBodies[0];
    if (!newTbody) {
      oldTbody.innerHTML = '';
      return;
    }
    const oldRows = [...oldTbody.rows];
    const newRows = [...newTbody.rows];
    const maxRows = Math.max(oldRows.length, newRows.length);
    for (let r = 0; r < maxRows; r++) {
      const oTr = oldRows[r];
      const nTr = newRows[r];
      if (oTr && nTr) {
        syncDomNodeAttributes(oTr, nTr);
        if (oTr.cells.length === nTr.cells.length) {
          for (let c = 0; c < nTr.cells.length; c++) {
            if (oTr.cells[c].innerHTML !== nTr.cells[c].innerHTML) {
              oTr.cells[c].innerHTML = nTr.cells[c].innerHTML;
            }
          }
        } else {
          oTr.innerHTML = nTr.innerHTML;
        }
      } else if (!oTr && nTr) {
        oldTbody.appendChild(nTr.cloneNode(true));
      } else if (oTr && !nTr) {
        oTr.remove();
      }
    }
  }

  function patchBlockElementInPlace(oldEl, newEl) {
    if (!oldEl || !newEl || oldEl.tagName !== newEl.tagName) return false;
    if (oldEl.classList.contains('mermaid-diagram') && newEl.classList.contains('mermaid-diagram')) {
      const oldSrc = oldEl.querySelector('.mermaid-source')?.textContent || '';
      const newSrc = newEl.querySelector('.mermaid-source')?.textContent || '';
      if (oldSrc === newSrc) {
        syncDomNodeAttributes(oldEl, newEl);
        return false; // Preserve already-rendered Mermaid SVG
      }
      oldEl.replaceWith(newEl.cloneNode(true));
      return true;
    }
    if ((oldEl.classList.contains('table-wrap') && newEl.classList.contains('table-wrap')) || oldEl.tagName === 'TABLE') {
      patchTableDomInPlace(oldEl, newEl);
      return false;
    }
    if (['UL', 'OL', 'BLOCKQUOTE'].includes(oldEl.tagName)) {
      syncDomNodeAttributes(oldEl, newEl);
      const oldItems = [...oldEl.children];
      const newItems = [...newEl.children];
      const maxLen = Math.max(oldItems.length, newItems.length);
      for (let i = 0; i < maxLen; i++) {
        const oIt = oldItems[i];
        const nIt = newItems[i];
        if (oIt && nIt && oIt.tagName === nIt.tagName) {
          syncDomNodeAttributes(oIt, nIt);
          if (oIt.innerHTML !== nIt.innerHTML) {
            oIt.innerHTML = nIt.innerHTML;
          }
        } else if (oIt && nIt) {
          oIt.replaceWith(nIt.cloneNode(true));
        } else if (!oIt && nIt) {
          oldEl.appendChild(nIt.cloneNode(true));
        } else if (oIt && !nIt) {
          oIt.remove();
        }
      }
      return false;
    }
    syncDomNodeAttributes(oldEl, newEl);
    if (oldEl.innerHTML !== newEl.innerHTML) {
      oldEl.innerHTML = newEl.innerHTML;
    }
    return false;
  }

  function isSameBlockStructure(oldEl, newEl) {
    if (!oldEl || !newEl || oldEl.tagName !== newEl.tagName) return false;
    if (oldEl.classList.contains('table-wrap') !== newEl.classList.contains('table-wrap')) return false;
    if (oldEl.classList.contains('mermaid-diagram') && newEl.classList.contains('mermaid-diagram')) {
      return (oldEl.querySelector('.mermaid-source')?.textContent || '') === (newEl.querySelector('.mermaid-source')?.textContent || '');
    }
    if (oldEl.classList.contains('table-wrap') || oldEl.tagName === 'TABLE') {
      const oT = oldEl.tagName === 'TABLE' ? oldEl : oldEl.querySelector('table');
      const nT = newEl.tagName === 'TABLE' ? newEl : newEl.querySelector('table');
      if (!oT || !nT) return false;
      return (oT.tHead?.innerText || '').trim() === (nT.tHead?.innerText || '').trim();
    }
    return oldEl.innerHTML === newEl.innerHTML;
  }

  function patchPreviewDomIncrementally(targetPreview, nextArticle) {
    clearPreviewDiff();
    const oldKids = [...targetPreview.children];
    const newKids = [...nextArticle.children];
    if (!oldKids.length) {
      targetPreview.innerHTML = nextArticle.innerHTML;
      return true;
    }
    let needsMermaid = false;
    if (oldKids.length === newKids.length) {
      for (let i = 0; i < newKids.length; i++) {
        if (oldKids[i].tagName === newKids[i].tagName && oldKids[i].classList.contains('table-wrap') === newKids[i].classList.contains('table-wrap')) {
          if (patchBlockElementInPlace(oldKids[i], newKids[i])) needsMermaid = true;
        } else {
          const clone = newKids[i].cloneNode(true);
          if (clone.classList?.contains('mermaid-diagram')) needsMermaid = true;
          oldKids[i].replaceWith(clone);
        }
      }
      return needsMermaid;
    }

    let start = 0;
    while (
      start < oldKids.length &&
      start < newKids.length &&
      isSameBlockStructure(oldKids[start], newKids[start])
    ) {
      if (patchBlockElementInPlace(oldKids[start], newKids[start])) needsMermaid = true;
      start++;
    }
    let oldEnd = oldKids.length - 1;
    let newEnd = newKids.length - 1;
    while (
      oldEnd >= start &&
      newEnd >= start &&
      isSameBlockStructure(oldKids[oldEnd], newKids[newEnd])
    ) {
      if (patchBlockElementInPlace(oldKids[oldEnd], newKids[newEnd])) needsMermaid = true;
      oldEnd--;
      newEnd--;
    }

    const anchorNode = oldEnd + 1 < oldKids.length ? oldKids[oldEnd + 1] : null;
    const oldMid = oldKids.slice(start, oldEnd + 1);
    const newMid = newKids.slice(start, newEnd + 1);
    const usedOld = new Set();

    for (let k = 0; k < newMid.length; k++) {
      const nNode = newMid[k];
      let matchedOld = null;
      for (let j = 0; j < oldMid.length; j++) {
        if (usedOld.has(j)) continue;
        if (isSameBlockStructure(oldMid[j], nNode)) {
          matchedOld = oldMid[j];
          usedOld.add(j);
          break;
        }
      }
      if (!matchedOld && k < oldMid.length && !usedOld.has(k) && oldMid[k].tagName === nNode.tagName && oldMid[k].classList.contains('table-wrap') === nNode.classList.contains('table-wrap')) {
        matchedOld = oldMid[k];
        usedOld.add(k);
      }
      if (matchedOld) {
        if (patchBlockElementInPlace(matchedOld, nNode)) needsMermaid = true;
        if (anchorNode && anchorNode.parentNode === targetPreview) {
          targetPreview.insertBefore(matchedOld, anchorNode);
        } else {
          targetPreview.appendChild(matchedOld);
        }
      } else {
        const clone = nNode.cloneNode(true);
        if (clone.classList?.contains('mermaid-diagram')) needsMermaid = true;
        if (anchorNode && anchorNode.parentNode === targetPreview) {
          targetPreview.insertBefore(clone, anchorNode);
        } else {
          targetPreview.appendChild(clone);
        }
      }
    }
    oldMid.forEach((oNode, j) => {
      if (!usedOld.has(j)) oNode.remove();
    });
    return needsMermaid;
  }

  function captureAllPreviewScrollStates(overrideWinY = null) {
    const contentEl = document.querySelector('.content');
    const tableScrolls = [...preview.querySelectorAll('.table-wrap')].map(tw => ({
      scrollLeft: tw.scrollLeft,
      scrollTop: tw.scrollTop,
    }));
    return {
      winY: typeof overrideWinY === 'number' ? overrideWinY : window.scrollY,
      winX: window.scrollX,
      previewTop: preview.scrollTop,
      previewLeft: preview.scrollLeft,
      contentTop: contentEl ? contentEl.scrollTop : 0,
      tableScrolls,
    };
  }

  function restoreAllPreviewScrollStates(snap) {
    if (!snap) return;
    const contentEl = document.querySelector('.content');
    if (contentEl && contentEl.scrollTop !== snap.contentTop) {
      contentEl.scrollTop = snap.contentTop;
    }
    if (preview.scrollTop !== snap.previewTop) preview.scrollTop = snap.previewTop;
    if (preview.scrollLeft !== snap.previewLeft) preview.scrollLeft = snap.previewLeft;
    const wraps = [...preview.querySelectorAll('.table-wrap')];
    wraps.forEach((tw, idx) => {
      const ts = snap.tableScrolls?.[idx];
      if (ts) {
        if (tw.scrollLeft !== ts.scrollLeft) tw.scrollLeft = ts.scrollLeft;
        if (tw.scrollTop !== ts.scrollTop) tw.scrollTop = ts.scrollTop;
      }
    });
    if (window.scrollY !== snap.winY || window.scrollX !== snap.winX) {
      window.scrollTo(snap.winX, snap.winY);
    }
  }

  async function renderDraftPreview(text, _unusedPreScroll = null) {
    const textClean = cleanLineEndings(text);
    const diffSig = `${textClean}\n===B===\n${cleanLineEndings(view.baseline)}\n===R===\n${cleanLineEndings(view.realText)}\n===U===\n${cleanLineEndings(view.userDraftText ?? '')}`;

    if (cleanLineEndings(view.lastRenderedPreviewText || '') === textClean && preview.innerHTML.trim()) {
      if (view.lastRenderedDiffSig === diffSig) {
        return;
      }
      const scrollSnap = captureAllPreviewScrollStates();
      const prevMinH = preview.style.minHeight;
      preview.style.minHeight = `${preview.offsetHeight}px`;
      try {
        const diff = diffApi();
        const hunks = diff ? annotateThreeWayHunks(diff.diffLines(String(view.baseline || ''), text), String(view.baseline || ''), text) : [];
        view.hunks = hunks;
        view.lastRenderedDiffSig = diffSig;
        renderPreviewDiff(hunks, text);
        updateStickyDiffBar(hunks);
        document.documentElement.dataset.mdPendingHunks = String(hunks.length);
        restoreAllPreviewScrollStates(scrollSnap);
      } finally {
        preview.style.minHeight = prevMinH;
      }
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
    // Capture scroll state AFTER network await, immediately before synchronous DOM patch!
    const scrollSnap = captureAllPreviewScrollStates();
    const prevMinH = preview.style.minHeight;
    preview.style.minHeight = `${preview.offsetHeight}px`;
    let needsMermaidRefresh = false;
    try {
      needsMermaidRefresh = patchPreviewDomIncrementally(preview, article);
      const diff = diffApi();
      const hunks = diff ? annotateThreeWayHunks(diff.diffLines(String(view.baseline || ''), text), String(view.baseline || ''), text) : [];
      view.hunks = hunks;
      view.lastRenderedPreviewText = text;
      view.lastRenderedDiffSig = diffSig;
      renderPreviewDiff(hunks, text);
      updateStickyDiffBar(hunks);
      document.documentElement.dataset.mdPendingHunks = String(hunks.length);
      restoreAllPreviewScrollStates(scrollSnap);
    } finally {
      preview.style.minHeight = prevMinH;
    }
    if (needsMermaidRefresh) {
      await globalThis.__lanternMarkdownPreview?.refresh?.(preview);
    }
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
      view.realVersion = state.realVersion || state.currentVersion;
      view.baseline = state.saved.content;
      view.realText = state.realContent ?? state.work?.realContent ?? state.saved.content;
      view.userDraftText = state.userDraft?.content ?? null;
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
      view.realVersion = workState.realVersion || workState.currentVersion;
      view.baseline = baselineDoc.content;
      view.realText = workState.realContent ?? serverWork?.realContent ?? baselineDoc.content;
      view.userDraftText = workState.userDraft?.content ?? null;
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
        kind === 'source' ? '' :
        view.roundtripSafe ? '' :
        '',
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
    if (view.saving) return;
    pushUndoSnapshot();
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
      if (view.active) {
        await applyWorkingText(baseline, null, { backed: true });
        view.instance?.focus?.();
      } else {
        await renderDraftPreview(baseline);
      }
      renderDraftDiff();
      status('Reverted pending changes.', 'info');
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
    const fastWindowScrollToEl = (el) => {
      const startY = window.scrollY;
      const rect = el.getBoundingClientRect();
      const targetY = Math.max(0, startY + rect.top - Math.round(window.innerHeight * 0.32));
      const dist = targetY - startY;
      if (Math.abs(dist) < 4) { window.scrollTo(0, targetY); return; }
      const dur = Math.min(140, Math.max(70, Math.abs(dist) * 0.07));
      const t0 = performance.now();
      const step = (now) => {
        const p = Math.min(1, (now - t0) / dur);
        const ease = 1 - Math.pow(1 - p, 3);
        window.scrollTo(0, Math.round(startY + dist * ease));
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    };
    if (view.mode === 'source' && view.instance?.restoreBookmark) {
      view.instance.restoreBookmark({ line: lineNo, column: 0 });
    } else if (view.mode === 'visual' && view.instance?.sourceBlockAtLine) {
      const blk = view.instance.sourceBlockAtLine(lineNo);
      if (blk) {
        fastWindowScrollToEl(blk);
        flashFocusSyncTarget(blk, lineNo);
      }
    } else {
      const node = preview.querySelector(`[data-diff-hunk-index="${view.currentHunkIdx}"]`)
        || preview.querySelector(`[data-l="${lineNo}"]`);
      if (node) {
        fastWindowScrollToEl(node);
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
      splitRenderTimer = setTimeout(async () => {
        await renderDraftPreview(text);
        if (splitMode === 'S-P' && view.mode === 'source' && view.instance?.sourceBookmark) {
          const bm = view.instance.sourceBookmark();
          if (bm?.line > 0 && bm.line !== view.lastAutoScrolledPreviewLine) {
            view.lastAutoScrolledPreviewLine = bm.line;
            scrollPreviewContainerToLine(preview, bm.line, bm.selectedText || '');
          }
        }
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
          if (typeof globalThis.toggleTerminal === 'function') {
            globalThis.toggleTerminal();
          }
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
      b.dataset.action = 'split-' + id;
      b.dataset.splitMode = id;
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
    versionWrap.append(versionBtn);
    document.body.appendChild(versionMenu);
    const positionFixedPopover = (btnEl, popEl) => {
      const r = btnEl.getBoundingClientRect();
      popEl.style.position = 'fixed';
      popEl.style.top = `${Math.round(r.bottom + 5)}px`;
      popEl.style.left = `${Math.max(8, Math.min(window.innerWidth - 300, Math.round(r.left)))}px`;
      popEl.style.right = 'auto';
      popEl.style.zIndex = '9999';
    };

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
      ensureShellStyle();
      const willOpen = versionMenu.hidden;
      auditPopover.hidden = true;
      versionMenu.hidden = !willOpen;
      if (willOpen) {
        positionFixedPopover(versionBtn, versionMenu);
        void loadAndRenderVersionMenu();
      }
    });

    // --- v8.0: Missing / Unreferenced Image Audit Button + Move to old/ ---
    const auditWrap = document.createElement('div');
    auditWrap.className = 'md-image-audit-wrap';
    const auditBtn = document.createElement('button');
    auditBtn.type = 'button';
    auditBtn.id = 'mdImageAuditBadge';
    auditBtn.className = 'btn md-image-audit-btn is-ok';
    auditBtn.textContent = 'Images (0)';
    const auditPopover = document.createElement('div');
    auditPopover.id = 'mdImageAuditPopover';
    auditPopover.className = 'md-image-audit-popover';
    auditPopover.hidden = true;
    auditWrap.append(auditBtn);
    document.body.appendChild(auditPopover);

    auditBtn.addEventListener('click', ev => {
      ev.stopPropagation();
      ensureShellStyle();
      const willOpen = auditPopover.hidden;
      versionMenu.hidden = true;
      auditPopover.hidden = !willOpen;
      if (willOpen) {
        positionFixedPopover(auditBtn, auditPopover);
        void refreshImageAudit();
      }
    });

    // --- v8.2: Package .md + assets into <name>.zip in current folder (connected to Lantern archive mode) ---
    const zipWrap = document.createElement('div');
    zipWrap.className = 'md-image-audit-wrap';
    const zipBtn = document.createElement('button');
    zipBtn.type = 'button';
    zipBtn.id = 'mdArchiveZipBtn';
    zipBtn.className = 'btn md-archive-zip-btn';
    zipBtn.textContent = '🗜️ Zip';
    zipBtn.title = 'Package this .md and its assets into <name>.zip in the current folder';
    const zipPopover = document.createElement('div');
    zipPopover.id = 'mdArchiveConflictPopover';
    zipPopover.className = 'md-image-audit-popover';
    zipPopover.hidden = true;
    zipWrap.append(zipBtn);
    document.body.appendChild(zipPopover);

    const runMdArchiveZip = async (conflictMode = 'ask') => {
      ensureShellStyle();
      zipBtn.disabled = true;
      const origLabel = '🗜️ Zip';
      zipBtn.textContent = '⏳ Zip…';
      try {
        if (view.active && view.instance) {
          await saveDraft().catch(() => {});
        }
        const res = await api('/api/archive', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mdPath: path, conflict: conflictMode }),
        });
        if (res.conflict) {
          zipBtn.disabled = false;
          zipBtn.textContent = origLabel;
          versionMenu.hidden = true;
          auditPopover.hidden = true;
          zipPopover.textContent = '';
          const titleDiv = document.createElement('div');
          titleDiv.className = 'md-image-audit-title';
          titleDiv.style.color = '#fcd34d';
          titleDiv.textContent = `⚠️ File "${res.existingName}" đã tồn tại trong thư mục này:`;
          const btnRow = document.createElement('div');
          btnRow.style.display = 'flex';
          btnRow.style.flexWrap = 'wrap';
          btnRow.style.gap = '6px';
          btnRow.style.marginTop = '8px';

          const overwriteBtn = document.createElement('button');
          overwriteBtn.type = 'button';
          overwriteBtn.className = 'md-hunk-button';
          overwriteBtn.style.background = '#7c2d12';
          overwriteBtn.style.borderColor = '#fb923c';
          overwriteBtn.textContent = `📝 Ghi đè (${res.existingName})`;
          overwriteBtn.addEventListener('click', ev => {
            ev.stopPropagation();
            zipPopover.hidden = true;
            void runMdArchiveZip('overwrite');
          });

          const copyBtn = document.createElement('button');
          copyBtn.type = 'button';
          copyBtn.className = 'md-hunk-button';
          copyBtn.style.background = '#1f4934';
          copyBtn.style.borderColor = '#55ce7a';
          copyBtn.textContent = `📄 Copy (${res.copyName})`;
          copyBtn.addEventListener('click', ev => {
            ev.stopPropagation();
            zipPopover.hidden = true;
            void runMdArchiveZip('copy');
          });

          const cancelBtn = document.createElement('button');
          cancelBtn.type = 'button';
          cancelBtn.className = 'md-hunk-button';
          cancelBtn.textContent = '✕ Huỷ';
          cancelBtn.addEventListener('click', ev => {
            ev.stopPropagation();
            zipPopover.hidden = true;
          });

          btnRow.append(overwriteBtn, copyBtn, cancelBtn);
          zipPopover.append(titleDiv, btnRow);
          zipPopover.hidden = false;
          positionFixedPopover(zipBtn, zipPopover);
          return;
        }
        zipPopover.hidden = true;
        zipBtn.disabled = false;
        zipBtn.textContent = `✓ ${res.name}`;
        status(`📦 Đã đóng gói .md và assets thành ${res.name}`, 'info');
        setTimeout(() => { zipBtn.textContent = origLabel; }, 2500);
      } catch (err) {
        zipBtn.disabled = false;
        zipBtn.textContent = origLabel;
        status('Lỗi đóng gói zip: ' + err.message, 'error');
      }
    };

    zipBtn.addEventListener('click', ev => {
      ev.stopPropagation();
      void runMdArchiveZip('ask');
    });

    document.addEventListener('click', ev => {
      if (!versionWrap.contains(ev.target) && !versionMenu.contains(ev.target)) versionMenu.hidden = true;
      if (!auditWrap.contains(ev.target) && !auditPopover.contains(ev.target)) auditPopover.hidden = true;
      if (!zipWrap.contains(ev.target) && !zipPopover.contains(ev.target)) zipPopover.hidden = true;
    });

    wrap.append(splitGroup, swapBtn, wrapBtn, versionWrap, auditWrap, zipWrap);
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
        const items = Array.isArray(d.items) ? d.items : [];
        const refCount = Number(d.referencedCount || 0);
        const totalBadgeCount = refCount + unused.length;
        ensureShellStyle();
        badge.hidden = false;
        const hasIssue = missing.length > 0 || unused.length > 0;
        badge.classList.toggle('is-warn', hasIssue);
        badge.classList.toggle('is-ok', !hasIssue);
        badge.textContent = `Images (${refCount || totalBadgeCount})`;
        badge.title = hasIssue
          ? `Images (${refCount} referenced, ${missing.length} missing, ${unused.length} unused in assets/)`
          : `All ${refCount} image(s) OK — click to preview thumbnails & jump to image`;

        const jumpToImageItem = (it) => {
          pop.hidden = true;
          const targetLine = Math.max(1, Number(it.line || 1));
          view.lastActiveLine = targetLine;
          if (view.mode === 'source' && view.instance?.restoreBookmark) {
            view.instance.restoreBookmark({ line: targetLine, column: 0 });
            return;
          }
          const searchRoot = (view.mode === 'visual' && view.host) ? view.host : preview;
          const allImgs = [...searchRoot.querySelectorAll('img')];
          const baseName = String(it.name || it.ref || '').split('/').pop();
          const matchedImg = allImgs.find(img => {
            const src = decodeURIComponent(img.getAttribute('src') || '');
            return (it.ref && src.includes(it.ref)) || (baseName && src.endsWith(baseName));
          });
          const targetNode = matchedImg || searchRoot.querySelector(`[data-l="${targetLine}"]`);
          if (targetNode) {
            targetNode.scrollIntoView({ behavior: 'smooth', block: 'center' });
            flashFocusSyncTarget(targetNode, targetLine);
          }
        };

        pop.textContent = '';
        const headSummary = document.createElement('div');
        headSummary.className = 'md-image-audit-title';
        headSummary.style.color = hasIssue ? '#fcd34d' : '#86efac';
        headSummary.textContent = hasIssue
          ? `⚠️ ${refCount} in .md · ${missing.length} missing · ${unused.length} unused`
          : `✓ ${refCount} image(s) in .md (click any image to jump)`;
        pop.appendChild(headSummary);

        if (!items.length) {
          const emptyMsg = document.createElement('div');
          emptyMsg.style.fontSize = '11.5px';
          emptyMsg.style.color = '#94a3b8';
          emptyMsg.style.padding = '6px 2px';
          emptyMsg.textContent = 'No images in this document.';
          pop.appendChild(emptyMsg);
        } else {
          const listWrap = document.createElement('div');
          listWrap.className = 'md-image-gallery-list';
          items.forEach(it => {
            const row = document.createElement('button');
            row.type = 'button';
            row.className = `md-image-gallery-item is-${it.status || 'ok'}`;
            row.title = it.line ? `Click to jump to ${it.ref} (Line ${it.line})` : it.ref;
            if (it.url && it.status !== 'missing') {
              const thumb = document.createElement('img');
              thumb.className = 'md-image-gallery-thumb';
              thumb.src = it.url;
              thumb.alt = it.name || '';
              thumb.loading = 'lazy';
              row.appendChild(thumb);
            } else {
              const ph = document.createElement('div');
              ph.className = 'md-image-gallery-thumb is-missing';
              ph.textContent = '✕';
              row.appendChild(ph);
            }
            const info = document.createElement('div');
            info.className = 'md-image-gallery-info';
            const nameEl = document.createElement('div');
            nameEl.className = 'md-image-gallery-name';
            nameEl.textContent = it.name || it.ref;
            const metaEl = document.createElement('div');
            metaEl.className = 'md-image-gallery-meta';
            metaEl.textContent = `${it.line ? 'L' + it.line + ' · ' : ''}${it.ref}`;
            info.append(nameEl, metaEl);

            const stBadge = document.createElement('span');
            stBadge.className = `md-image-gallery-badge is-${it.status || 'ok'}`;
            stBadge.textContent = it.status === 'missing' ? 'Missing' : (it.status === 'unused' ? 'Unused' : 'OK');
            row.append(info, stBadge);
            row.addEventListener('click', ev => {
              ev.stopPropagation();
              jumpToImageItem(it);
            });
            listWrap.appendChild(row);
          });
          pop.appendChild(listWrap);
        }

        if (unused.length > 0) {
          const moveBtn = document.createElement('button');
          moveBtn.type = 'button';
          moveBtn.className = 'md-image-audit-move-btn';
          moveBtn.textContent = `📦 Move ${unused.length} unused to old/`;
          moveBtn.title = 'Move unreferenced images into assets/old/';
          moveBtn.addEventListener('click', async ev => {
            ev.stopPropagation();
            moveBtn.disabled = true;
            moveBtn.textContent = 'Moving to assets/old/…';
            try {
              const mvRes = await api('/api/md/image-audit/move-to-old', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path, files: unused }),
              });
              status(`Moved ${mvRes.movedCount || 0} unreferenced image(s) to assets/old/.`, 'info');
              await refreshImageAudit();
            } catch (err) {
              moveBtn.disabled = false;
              moveBtn.textContent = `📦 Move ${unused.length} unused to old/`;
              status('Move to assets/old/ failed: ' + err.message, 'error');
            }
          });
          pop.appendChild(moveBtn);
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


  // Unified Clipboard Image Extractor & Uploader (Preview + Edit visually + Source + Table Cells)
  async function uploadImageBlobToAssets(blobOrFile, rawHintName = '') {
    const extMap = { 'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp', 'image/gif': 'gif', 'image/bmp': 'bmp', 'image/svg+xml': 'svg' };
    const mime = blobOrFile.type || 'image/png';
    const ext = extMap[mime] || 'png';
    const dir = path.includes('/') ? path.split('/').slice(0, -1).join('/') : '';
    const randId = 'pasted-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
    const relTarget = 'assets/' + randId + '.' + ext;
    const upRes = await fetch('/api/upload?path=' + encodeURIComponent(dir) + '&name=' + encodeURIComponent(relTarget) + '&conflict=rename', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': mime },
      body: blobOrFile,
    });
    const upData = await upRes.json().catch(() => ({}));
    if (!upRes.ok || upData.error || !upData.file) throw new Error(upData.error || ('HTTP ' + upRes.status));
    const serverPath = decodeURIComponent(String(upData.file).replace(/^\/+/, ''));
    const prefix = dir ? dir + '/' : '';
    const finalRel = serverPath.startsWith(prefix) ? serverPath.slice(prefix.length) : serverPath;
    const fileStem = finalRel.split('/').pop().replace(/\.[^.]+$/, '');
    const rawName = String(rawHintName || blobOrFile.name || '').replace(/\.[^.]+$/, '').trim().replace(/\s+/g, '_');
    const altName = (!rawName || /^(image|clipboard|pasted|blob)$/i.test(rawName)) ? fileStem : rawName;
    return `![${altName}](${finalRel})`;
  }

  function dataUriToBlob(dataUri) {
    const m = String(dataUri || '').match(/^data:([^;,]+)(?:;base64)?,(.*)$/i);
    if (!m) return null;
    const mime = m[1] || 'image/png';
    const b64 = m[2] || '';
    const bin = atob(b64);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    return new Blob([arr], { type: mime });
  }

  async function extractOrUploadClipboardImages(ev) {
    if (document.querySelector('dialog.lantern-crop-dialog[open], .lantern-crop-dialog')) return null;
    const cb = ev.clipboardData;
    const items = [...(cb?.items || [])];
    const imgFiles = items
      .filter(it => it.type && it.type.startsWith('image/'))
      .map(it => it.getAsFile?.())
      .filter(Boolean);
    const htmlData = cb?.getData?.('text/html') || '';
    const plainData = (cb?.getData?.('text/plain') || '').trim();

    // 1. Check if clipboard has plain Markdown image syntax ![alt](assets/...) or copied image token
    if (!imgFiles.length && /^!\[[^\]]*\]\([^)\r\n]+\)$/.test(plainData) && !plainData.includes('data:image/')) {
      ev.preventDefault();
      ev.stopPropagation();
      return [plainData];
    }

    // 2. Check if clipboard HTML has <img src="..."> (either local asset URL or data:image/...;base64)
    if (!imgFiles.length && /<img\b[^>]*\bsrc\s*=/i.test(htmlData)) {
      const holder = document.createElement('div');
      holder.innerHTML = htmlData;
      const imgs = [...holder.querySelectorAll('img')];
      if (imgs.length) {
        ev.preventDefault();
        ev.stopPropagation();
        const tokens = [];
        for (const el of imgs) {
          const rawSrc = (el.getAttribute('src') || '').trim();
          const alt = (el.getAttribute('alt') || 'image').trim();
          if (rawSrc.startsWith('data:image/')) {
            const blob = dataUriToBlob(rawSrc);
            if (blob) {
              status('Uploading pasted base64 image to assets/…', 'info');
              tokens.push(await uploadImageBlobToAssets(blob, alt));
            }
          } else if (rawSrc) {
            const dataMd = el.getAttribute('data-md-src');
            if (dataMd) {
              tokens.push(`![${alt}](${dataMd})`);
            } else {
              try {
                const u = new URL(rawSrc, location.origin);
                const cleanPath = decodeURIComponent(u.pathname.replace(/^\/+/, '')).split('?')[0];
                const docDir = path.includes('/') ? path.split('/').slice(0, -1).join('/') + '/' : '';
                const rel = (docDir && cleanPath.startsWith(docDir)) ? cleanPath.slice(docDir.length) : cleanPath;
                tokens.push(`![${alt}](${rel})`);
              } catch {
                tokens.push(`![${alt}](${rawSrc.split('?')[0]})`);
              }
            }
          }
        }
        if (tokens.length) return tokens;
      }
    }

    // 3. Binary image file(s) in clipboardData
    if (imgFiles.length) {
      // If user just copied an existing local image via Lantern's Copy Image button within the last 60s
      // and only 1 file is in clipboard, reuse its clean relative asset path if desired, or upload fresh to assets/
      ev.preventDefault();
      ev.stopPropagation();
      status(`Uploading ${imgFiles.length} pasted image(s) to assets/…`, 'info');
      const mdTokens = [];
      for (const file of imgFiles) {
        mdTokens.push(await uploadImageBlobToAssets(file, file.name));
      }
      return mdTokens;
    }

    // 4. Fallback: if user copied an image via Lantern toolbar/Ctrl+C and clipboardData had no text/files (e.g. headless/synthetic paste)
    if (!plainData && !htmlData && window.__lanternCopiedImage?.md && (Date.now() - (window.__lanternCopiedImage.at || 0) < 600000)) {
      ev.preventDefault();
      ev.stopPropagation();
      return [window.__lanternCopiedImage.md];
    }

    return null;
  }

  let lastClickedTableCellContext = null;

  function resolveTableCellCoordinates(cellEl, mdText) {
    if (!cellEl) return null;
    const table = cellEl.closest('table');
    const tr = cellEl.closest('tr');
    if (!table || !tr || cellEl.closest('.md-table-tr-del')) return null;
    const lines = String(mdText || '').replace(/\r\n?/g, '\n').split('\n');
    const trAttrLine = Number(tr.getAttribute('data-l') || 0);
    const tableAttrLine = Math.max(1, Number(table.getAttribute('data-l') || table.closest('[data-l]')?.getAttribute('data-l') || 1));
    let tableStartIdx = Math.min(lines.length - 1, tableAttrLine - 1);
    while (tableStartIdx > 0 && String(lines[tableStartIdx - 1] || '').trim().startsWith('|')) tableStartIdx--;
    while (tableStartIdx < lines.length && !String(lines[tableStartIdx] || '').trim().startsWith('|')) tableStartIdx++;
    const isHeader = Boolean(tr.parentElement?.tagName === 'THEAD');
    const tbodyRows = [...(table.tBodies[0]?.rows || [])].filter(r => !r.classList.contains('md-table-tr-del'));
    const bodyIdx = tbodyRows.indexOf(tr);
    const targetLineIdx = trAttrLine > 0
      ? (trAttrLine - 1)
      : (isHeader ? tableStartIdx : (tableStartIdx + 2 + Math.max(0, bodyIdx)));
    const realCells = [...tr.cells].filter(c => !c.classList.contains('md-table-td-del-col'));
    const colIdx = realCells.indexOf(cellEl);
    if (targetLineIdx < 0 || targetLineIdx >= lines.length || colIdx < 0) return null;
    return { targetLineIdx, colIdx, tableStartIdx };
  }

  function mountPreviewImageToolbar() {
    const toolbar = document.createElement('div');
    toolbar.className = 'md-image-crop-toolbar md-preview-image-toolbar md-docx-img-toolbar';
    toolbar.hidden = true;
    const undoBtn = document.createElement('button');
    undoBtn.type = 'button';
    undoBtn.className = 'btn md-img-undo-btn';
    undoBtn.setAttribute('data-img-cmd', 'undo');
    undoBtn.textContent = '↶ Undo';
    undoBtn.hidden = true;
    const copyImgBtn = document.createElement('button');
    copyImgBtn.type = 'button';
    copyImgBtn.className = 'btn md-img-copy-btn';
    copyImgBtn.setAttribute('data-img-cmd', 'copy');
    copyImgBtn.textContent = 'Copy';
    copyImgBtn.title = 'Copy image (Ctrl+C) to paste in any mode or table cell';
    const cropBtn = document.createElement('button');
    cropBtn.type = 'button';
    cropBtn.className = 'btn';
    cropBtn.setAttribute('data-img-cmd', 'crop');
    cropBtn.textContent = 'Crop';
    const dupBtn = document.createElement('button');
    dupBtn.type = 'button';
    dupBtn.className = 'btn';
    dupBtn.setAttribute('data-img-cmd', 'duplicate');
    dupBtn.textContent = 'Duplicate';
    dupBtn.title = 'Duplicate image to line below';
    const delBtn = document.createElement('button');
    delBtn.type = 'button';
    delBtn.className = 'btn danger';
    delBtn.setAttribute('data-img-cmd', 'delete');
    delBtn.textContent = 'Delete';
    toolbar.append(undoBtn, copyImgBtn, cropBtn, dupBtn, delBtn);
    document.body.appendChild(toolbar);

    let selectedImg = null;
    let busy = false;
    const backupMap = new Map();

    const clearSelection = () => {
      if (selectedImg) selectedImg.classList.remove('md-preview-img-selected');
      selectedImg = null;
      toolbar.hidden = true;
    };

    const resolveRelAssetPath = (imgEl) => {
      const dataMd = imgEl.getAttribute('data-md-src');
      if (dataMd && !dataMd.startsWith('data:')) return dataMd.trim();
      const rawAttr = imgEl.getAttribute('src') || '';
      const cleanPath = decodeURIComponent(rawAttr.split('?')[0].split('#')[0]).replace(/^\/+/, '');
      const docDir = path.includes('/') ? path.split('/').slice(0, -1).join('/') + '/' : '';
      if (docDir && cleanPath.startsWith(docDir)) {
        return cleanPath.slice(docDir.length);
      }
      return cleanPath;
    };

    const copySelectedImageToClipboard = async (imgEl, ev = null) => {
      if (!imgEl) return false;
      const relAsset = resolveRelAssetPath(imgEl);
      const alt = (imgEl.getAttribute('alt') || relAsset.split('/').pop()?.replace(/\.[^.]+$/, '') || 'image').trim();
      const mdToken = `![${alt}](${relAsset})`;
      const fullSrc = imgEl.currentSrc || imgEl.src || '';
      window.__lanternCopiedImage = { md: mdToken, src: fullSrc, rel: relAsset, alt, at: Date.now() };
      try { localStorage.setItem('lantern-copied-image', JSON.stringify(window.__lanternCopiedImage)); } catch (_) {}
      if (ev?.clipboardData) {
        try {
          ev.clipboardData.setData('text/plain', mdToken);
          ev.clipboardData.setData('text/html', `<img src="${fullSrc}" alt="${alt}" data-md-src="${relAsset}">`);
          ev.preventDefault();
        } catch (_) {}
      }
      if (navigator.clipboard) {
        try {
          if (navigator.clipboard.write && typeof ClipboardItem !== 'undefined' && fullSrc) {
            const resp = await fetch(fullSrc, { credentials: 'same-origin' });
            const blob = await resp.blob();
            if (blob.type === 'image/png') {
              await navigator.clipboard.write([
                new ClipboardItem({
                  'image/png': blob,
                  'text/plain': new Blob([mdToken], { type: 'text/plain' }),
                }),
              ]);
            } else {
              await navigator.clipboard.writeText(mdToken);
            }
          } else if (navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(mdToken);
          }
        } catch (_) {
          try { await navigator.clipboard.writeText?.(mdToken); } catch {}
        }
      }
      status(`Copied image ${relAsset} (press Ctrl+V to paste in any mode or table cell).`, 'info');
      return true;
    };

    const replaceOrRemoveImageInMarkdown = (mdContent, imgEl, replacementSrc = null) => {
      const relAsset = resolveRelAssetPath(imgEl);
      const rawSrcAttr = (imgEl.getAttribute('src') || '').split('?')[0];
      const baseName = relAsset.split('/').pop() || '';
      const surfaceRoot = imgEl.closest('article.md-preview') || preview;
      const allActiveImgs = [...surfaceRoot.querySelectorAll('img')].filter(el => !el.closest('.md-preview-deletion'));
      const imgOrdinal = allActiveImgs.indexOf(imgEl);
      const trEl = imgEl.closest('tr[data-l]');
      const blockEl = trEl || imgEl.closest('[data-l]');
      const approxLine = blockEl ? Math.max(1, Number(blockEl.getAttribute('data-l')) || 1) : 1;
      const hasCrLf = String(mdContent || '').includes('\r\n');
      const eol = hasCrLf ? '\r\n' : '\n';
      const lines = String(mdContent || '').replace(/\r\n?/g, '\n').split('\n');

      // Locate all image tokens across lines with their global ordinal
      const tokenMatches = [];
      const imgTokenRe = /!\[[^\]]*\]\([^)\r\n]+\)|<img\b[^>]*>/gi;
      lines.forEach((line, lineIdx) => {
        let m;
        imgTokenRe.lastIndex = 0;
        while ((m = imgTokenRe.exec(line)) !== null) {
          const tok = m[0];
          const matchesAsset = (relAsset && tok.includes(relAsset))
            || (rawSrcAttr && tok.includes(rawSrcAttr))
            || (baseName && tok.includes(baseName));
          tokenMatches.push({
            lineIdx,
            startCol: m.index,
            endCol: m.index + tok.length,
            token: tok,
            matchesAsset,
            globalOrd: tokenMatches.length,
          });
        }
      });

      const candidates = tokenMatches.filter(t => t.matchesAsset);
      if (!candidates.length) return null;
      candidates.sort((a, b) => {
        if (imgOrdinal >= 0) {
          const dOrdA = Math.abs(a.globalOrd - imgOrdinal);
          const dOrdB = Math.abs(b.globalOrd - imgOrdinal);
          if (dOrdA !== dOrdB) return dOrdA - dOrdB;
        }
        return Math.abs((a.lineIdx + 1) - approxLine) - Math.abs((b.lineIdx + 1) - approxLine);
      });

      const chosen = candidates[0];
      const targetIdx = chosen.lineIdx;
      const origLine = lines[targetIdx];
      const isTableRow = origLine.trim().startsWith('|') && origLine.trim().endsWith('|');

      if (replacementSrc === null) {
        const beforeSlice = origLine.slice(0, chosen.startCol);
        const afterSlice = origLine.slice(chosen.endCol);
        const updatedLine = (beforeSlice + afterSlice).replace(/[ \t]{2,}/g, ' ').trim();
        if (!isTableRow && !updatedLine) {
          lines.splice(targetIdx, 1);
          // Clean up double blank lines left behind by removing a standalone image block
          if (targetIdx < lines.length && targetIdx > 0 && !lines[targetIdx].trim() && !lines[targetIdx - 1].trim()) {
            lines.splice(targetIdx, 1);
          }
        } else {
          lines[targetIdx] = isTableRow ? (beforeSlice + afterSlice) : updatedLine;
        }
      } else {
        const replacedTok = chosen.token.startsWith('![')
          ? chosen.token.replace(/(!\[[^\]]*\]\(\s*)(?:<[^>]+>|[^\s)]+)(\s*(?:["'][^"']*["'])?\s*\))/, `$1${replacementSrc}$2`)
          : chosen.token.replace(/(<img\b[^>]*?\bsrc\s*=\s*["'])([^"']+)(["'])/i, `$1${replacementSrc}$3`);
        lines[targetIdx] = origLine.slice(0, chosen.startCol) + replacedTok + origLine.slice(chosen.endCol);
      }
      return lines.join(eol);
    };

    const applyPreviewMarkdownEdit = async (nextMd, statusMsg) => {
      pushUndoSnapshot();
      const state = await fetchWorkState().catch(() => null);
      if (state?.saved) {
        view.version = state.saved.version;
        view.baseline = state.saved.content;
        view.realText = state.realContent ?? state.work?.realContent ?? state.saved.content;
        view.realVersion = state.realVersion || state.work?.realHash || state.currentVersion;
      }
      const baseVer = state?.saved?.version || view.version;
      const expHash = state?.work?.hash || view.workHash || null;
      view.userDraftText = nextMd;

      const res = await api('/api/work/write', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path,
          content: nextMd,
          expectHash: expHash,
          baseVersion: baseVer,
          allowConcurrent: true,
          userDraft: true,
        }),
      });
      const renderedMd = typeof res.mergedContent === 'string' ? res.mergedContent : nextMd;
      view.workHash = res.hash || null;
      view.currentVersion = res.currentVersion;
      view.realVersion = res.realVersion || view.realVersion || res.currentVersion;
      view.workState = res.state;
      view.ackedText = renderedMd;
      view.lastSaved = renderedMd;
      view.dirty = cleanLineEndings(renderedMd) !== cleanLineEndings(view.baseline);
      restoreButtons();

      if (view.active && view.instance) {
        await applyWorkingText(renderedMd, view.workHash, { backed: true });
      } else {
        await renderDraftPreview(renderedMd);
      }
      void refreshImageAudit();
      status(statusMsg, 'info');
    };

    document.addEventListener('click', ev => {
      const t = ev.target;
      if (!(t instanceof Element)) return;
      const clickedCell = t.closest('article.md-preview td, article.md-preview th');
      if (clickedCell && !clickedCell.closest('.md-table-tr-del')) {
        lastClickedTableCellContext = {
          cellEl: clickedCell,
          mode: view.mode,
          at: Date.now(),
        };
      } else if (!t.closest('.md-image-crop-toolbar')) {
        lastClickedTableCellContext = null;
      }
      if (toolbar.contains(t)) return;
      const img = t.closest('article.md-preview img');
      const surfaceEl = img?.closest('article.md-preview');
      if (!img || !surfaceEl || surfaceEl.hidden || img.closest('.md-preview-deletion')) {
        if (!busy) clearSelection();
        return;
      }
      ensureShellStyle();
      if (selectedImg && selectedImg !== img) selectedImg.classList.remove('md-preview-img-selected');
      selectedImg = img;
      selectedImg.classList.add('md-preview-img-selected');
      const lNode = img.closest('[data-l]');
      if (lNode) {
        const lNo = Number(lNode.getAttribute('data-l'));
        if (lNo > 0) view.lastActiveLine = lNo;
      }
      const rect = img.getBoundingClientRect();
      toolbar.style.top = `${Math.max(52, Math.round(rect.top + 8))}px`;
      toolbar.style.left = `${Math.max(12, Math.min(window.innerWidth - 290, Math.round(rect.right - 260)))}px`;
      toolbar.style.right = 'auto';
      const resolveWsImgPath = (el) => {
        try {
          const u = new URL(el.currentSrc || el.src, location.origin);
          return decodeURIComponent(u.pathname.replace(/^\/+/, ''));
        } catch {
          return (el.getAttribute('src') || '').split('?')[0].replace(/^\/+/, '');
        }
      };
      const wsImgPath = resolveWsImgPath(img);
      const cleanUrl = (img.getAttribute('src') || '').split('?')[0];
      undoBtn.hidden = !(backupMap.has(wsImgPath) || backupMap.has(cleanUrl));
      toolbar.hidden = false;
      if (wsImgPath && /\.(png|jpe?g|webp)$/i.test(wsImgPath) && !backupMap.has(wsImgPath)) {
        fetch('/api/image/version?p=' + encodeURIComponent(wsImgPath), { cache: 'no-store', credentials: 'same-origin' })
          .then(r => r.ok ? r.json() : null)
          .then(d => {
            if (d?.hasBackup && selectedImg === img) {
              backupMap.set(wsImgPath, { kind: 'overwrite', relPath: wsImgPath });
              undoBtn.hidden = false;
            }
          })
          .catch(() => {});
      }
    });

    copyImgBtn.addEventListener('click', async () => {
      if (!selectedImg || busy) return;
      await copySelectedImageToClipboard(selectedImg);
    });

    // Keyboard support for selected image in both Preview and Edit visually:
    // - Delete / Backspace removes the selected image smoothly
    // - Ctrl+C / Cmd+C copies the selected image smoothly
    document.addEventListener('keydown', ev => {
      if (!selectedImg || busy) return;
      if (document.querySelector('dialog.lantern-crop-dialog[open], .lantern-crop-dialog')) return;
      const activeEl = document.activeElement;
      if (activeEl && activeEl.closest?.('input, textarea, .cm-editor, #lanternChatDrawer, #termDrawer, [contenteditable="true"]')) {
        return;
      }
      if (ev.key === 'Delete' || ev.key === 'Backspace') {
        ev.preventDefault();
        ev.stopPropagation();
        delBtn.click();
      } else if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'c') {
        const sel = window.getSelection?.();
        if (sel && !sel.isCollapsed && String(sel.toString() || '').trim()) return;
        void copySelectedImageToClipboard(selectedImg);
      }
    }, true);

    document.addEventListener('copy', ev => {
      if (!selectedImg || busy) return;
      const sel = window.getSelection?.();
      if (sel && !sel.isCollapsed && String(sel.toString() || '').trim()) return;
      void copySelectedImageToClipboard(selectedImg, ev);
    }, true);

    dupBtn.addEventListener('click', async () => {
      if (!selectedImg || busy) return;
      busy = true;
      try {
        const curMd = view.active ? getEditorText() : getWorkingPreviewMarkdown();
        const relAsset = resolveRelAssetPath(selectedImg);
        const alt = (selectedImg.getAttribute('alt') || relAsset.split('/').pop()?.replace(/\.[^.]+$/, '') || 'image').trim();
        const matchToken = `![${alt}](${relAsset})`;
        const blockEl = selectedImg.closest('tr[data-l], [data-l]');
        const approxLine = blockEl ? Math.max(1, Number(blockEl.getAttribute('data-l')) || 1) : 1;
        const lines = String(curMd || '').replace(/\r\n?/g, '\n').split('\n');
        const targetIdx = Math.max(0, Math.min(lines.length - 1, approxLine - 1));
        if (lines[targetIdx] && lines[targetIdx].trim().startsWith('|')) {
          const cellEl = selectedImg.closest('td, th');
          const coord = resolveTableCellCoordinates(cellEl, curMd);
          if (coord) {
            const cells = splitGfmRowCells(lines[coord.targetLineIdx]);
            cells[coord.colIdx] = (cells[coord.colIdx] ? cells[coord.colIdx] + ' ' : '') + matchToken;
            lines[coord.targetLineIdx] = '| ' + cells.join(' | ') + ' |';
          } else {
            lines.splice(targetIdx + 1, 0, matchToken);
          }
        } else {
          lines.splice(targetIdx + 1, 0, '', matchToken);
        }
        const nextMd = lines.join('\n');
        clearSelection();
        await applyPreviewMarkdownEdit(nextMd, 'Image duplicated.');
      } catch (err) {
        status('Duplicate image failed: ' + err.message, 'error');
      } finally {
        busy = false;
      }
    });

    delBtn.addEventListener('click', async () => {
      if (!selectedImg || busy) return;
      busy = true;
      try {
        const curMd = view.active ? getEditorText() : getWorkingPreviewMarkdown();
        const nextMd = replaceOrRemoveImageInMarkdown(curMd, selectedImg, null);
        if (nextMd === null || cleanLineEndings(nextMd) === cleanLineEndings(curMd)) {
          status('Could not locate image reference in Markdown.', 'warn');
          return;
        }
        clearSelection();
        await applyPreviewMarkdownEdit(nextMd, 'Image removed from Markdown.');
      } catch (err) {
        status('Delete image failed: ' + err.message, 'error');
      } finally {
        busy = false;
      }
    });

    const resolveWsPathForImg = (el) => {
      try {
        const u = new URL(el.currentSrc || el.src, location.origin);
        return decodeURIComponent(u.pathname.replace(/^\/+/, ''));
      } catch {
        return (el.getAttribute('src') || '').split('?')[0].replace(/^\/+/, '');
      }
    };

    cropBtn.addEventListener('click', async () => {
      if (!selectedImg || busy) return;
      const targetImg = selectedImg;
      busy = true;
      cropBtn.disabled = true;
      delBtn.disabled = true;
      try {
        const wsPath = resolveWsPathForImg(targetImg);
        let imgVersion = '';
        let canOverwrite = false;
        if (wsPath && /\.(png|jpe?g|webp)$/i.test(wsPath)) {
          try {
            const vRes = await fetch('/api/image/version?p=' + encodeURIComponent(wsPath), {
              cache: 'no-store',
              credentials: 'same-origin',
            });
            if (vRes.ok) {
              const vData = await vRes.json();
              if (vData?.version) {
                imgVersion = vData.version;
                canOverwrite = true;
              }
            }
          } catch (_) {}
        }
        const { openCrop } = await loadCropBundle();
        const res = await openCrop({
          src: targetImg.currentSrc || targetImg.src,
          name: targetImg.getAttribute('alt') || 'Image',
          allowOverwrite: canOverwrite,
          preferredAction: canOverwrite ? 'overwrite' : 'copy',
        });
        if (!res) return;
        const cleanSrc = (targetImg.getAttribute('src') || '').split('?')[0];
        if (res.action === 'overwrite' && canOverwrite && imgVersion) {
          const ovRes = await fetch('/api/image/overwrite?p=' + encodeURIComponent(wsPath), {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
              'Content-Type': res.blob.type,
              'If-Match': imgVersion,
            },
            body: res.blob,
          });
          const ovData = await ovRes.json().catch(() => ({}));
          if (!ovRes.ok || ovData.error) throw new Error(ovData.error || ('HTTP ' + ovRes.status));
          backupMap.set(wsPath, { kind: 'overwrite', relPath: wsPath });
          backupMap.set(cleanSrc, { kind: 'overwrite', relPath: wsPath });
          const bustUrl = '/' + wsPath.split('/').map(encodeURIComponent).join('/') + '?v=' + Date.now();
          targetImg.src = bustUrl;
          document.querySelectorAll('article.md-preview img').forEach(other => {
            if (resolveWsPathForImg(other) === wsPath) other.src = bustUrl;
          });
          undoBtn.hidden = false;
          void refreshImageAudit();
          status('Image cropped in place (click image → ↶ Undo to restore).', 'info');
        } else {
          const dir = path.includes('/') ? path.split('/').slice(0, -1).join('/') : '';
          const fname = 'assets/cropped-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8) + '.' + (res.extension || 'png');
          const upRes = await fetch('/api/upload?path=' + encodeURIComponent(dir) + '&name=' + encodeURIComponent(fname) + '&conflict=rename', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': res.blob.type },
            body: res.blob,
          });
          const upData = await upRes.json().catch(() => ({}));
          if (!upRes.ok || upData.error || !upData.file) throw new Error(upData.error || 'Upload failed');
          const serverPath = decodeURIComponent(String(upData.file).replace(/^\/+/, ''));
          const prefix = dir ? dir + '/' : '';
          const newRel = serverPath.startsWith(prefix) ? serverPath.slice(prefix.length) : serverPath;
          const curMd = view.active ? getEditorText() : getWorkingPreviewMarkdown();
          const nextMd = replaceOrRemoveImageInMarkdown(curMd, targetImg, newRel);
          if (nextMd && nextMd !== curMd) {
            backupMap.set(serverPath, { kind: 'copy', prevMd: curMd });
            backupMap.set(newRel, { kind: 'copy', prevMd: curMd });
            clearSelection();
            await applyPreviewMarkdownEdit(nextMd, 'Cropped image saved as ' + newRel);
          }
        }
      } catch (err) {
        status('Crop failed: ' + err.message, 'error');
      } finally {
        busy = false;
        cropBtn.disabled = false;
        delBtn.disabled = false;
      }
    });

    undoBtn.addEventListener('click', async () => {
      if (!selectedImg || busy) return;
      const wsPath = resolveWsPathForImg(selectedImg);
      const cleanSrc = (selectedImg.getAttribute('src') || '').split('?')[0];
      const entry = backupMap.get(wsPath) || backupMap.get(cleanSrc);
      busy = true;
      try {
        if (entry && entry.kind === 'copy' && entry.prevMd) {
          backupMap.delete(wsPath);
          backupMap.delete(cleanSrc);
          undoBtn.hidden = true;
          clearSelection();
          await applyPreviewMarkdownEdit(entry.prevMd, 'Reverted image to previous file.');
          return;
        }
        const targetRel = entry?.relPath || wsPath || cleanSrc.replace(/^\/+/, '');
        const uRes = await fetch('/api/image/undo?p=' + encodeURIComponent(targetRel), {
          method: 'POST',
          credentials: 'same-origin',
        });
        const uData = await uRes.json().catch(() => ({}));
        if (!uRes.ok || uData.error) throw new Error(uData.error || ('HTTP ' + uRes.status));
        backupMap.delete(wsPath);
        backupMap.delete(cleanSrc);
        undoBtn.hidden = true;
        const bustUrl = '/' + targetRel.split('/').map(encodeURIComponent).join('/') + '?v=' + Date.now();
        selectedImg.src = bustUrl;
        document.querySelectorAll('article.md-preview img').forEach(other => {
          if (resolveWsPathForImg(other) === targetRel) other.src = bustUrl;
        });
        status('Restored original image before crop.', 'info');
      } catch (err) {
        status('Undo crop failed: ' + err.message, 'error');
      } finally {
        busy = false;
      }
    });
  }


  // --- v9.0 Mode 1: Pure Docx-Style 1-Click Inline Editing in Preview (Zero Boxes, Zero Extra Lines, Live Diff) ---
  let activeLiveEditorCleanup = null;

  function getWorkingPreviewMarkdown() {
    if (view.active && view.instance) return getEditorText();
    if (typeof view.lastRenderedPreviewText === 'string' && view.lastRenderedPreviewText.length > 0) {
      return view.lastRenderedPreviewText;
    }
    if (view.ackedText) return String(view.ackedText);
    if (view.userDraftText !== null && view.userDraftText !== undefined) return String(view.userDraftText);
    return String(view.realText || view.baseline || '');
  }

  async function commitPreviewLiveMarkdown(rawNextMd, statusMsg = 'Updated draft in Preview (Ctrl+S to save).', _unusedPreScroll = null, skipDomRebuild = false) {
    const currentMd = getWorkingPreviewMarkdown();
    if (cleanLineEndings(rawNextMd) === cleanLineEndings(currentMd)) return false;
    const refEolSource = String(view.baseline || view.realText || currentMd || '');
    const docEol = refEolSource.includes('\r\n') ? '\r\n' : '\n';
    const nextMd = String(rawNextMd ?? '').replace(/\r\n?/g, '\n').split('\n').join(docEol);
    pushUndoSnapshot(currentMd);
    if (!view.version) {
      const st = await fetchWorkState().catch(() => null);
      if (st?.saved) {
        view.version = st.saved.version;
        view.currentVersion = st.currentVersion;
        view.realVersion = st.realVersion || st.currentVersion;
        view.baseline = st.saved.content;
        view.realText = st.realContent ?? st.work?.realContent ?? st.saved.content;
        view.workHash = st.work?.hash || null;
      }
    }
    view.userDraftText = nextMd;
    view.ackedText = nextMd;
    view.dirty = cleanLineEndings(nextMd) !== cleanLineEndings(view.baseline);
    restoreButtons();

    if (skipDomRebuild) {
      const syncSnap = captureAllPreviewScrollStates();
      const prevMinH = preview.style.minHeight;
      preview.style.minHeight = `${preview.offsetHeight}px`;
      try {
        view.lastRenderedPreviewText = nextMd;
        const diff = diffApi();
        const hunks = diff ? annotateThreeWayHunks(diff.diffLines(String(view.baseline || ''), nextMd), String(view.baseline || ''), nextMd) : [];
        view.hunks = hunks;
        const textClean = cleanLineEndings(nextMd);
        view.lastRenderedDiffSig = `${textClean}\n===B===\n${cleanLineEndings(view.baseline)}\n===R===\n${cleanLineEndings(view.realText)}\n===U===\n${cleanLineEndings(view.userDraftText ?? '')}`;
        renderPreviewDiff(hunks, nextMd);
        updateStickyDiffBar(hunks);
        document.documentElement.dataset.mdPendingHunks = String(hunks.length);
        restoreAllPreviewScrollStates(syncSnap);
      } finally {
        preview.style.minHeight = prevMinH;
      }
    }

    const res = await api('/api/work/write', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        path,
        content: nextMd,
        expectHash: view.workHash || null,
        baseVersion: view.version,
        allowConcurrent: true,
        userDraft: true,
      }),
    });
    const renderedMd = typeof res.mergedContent === 'string' ? res.mergedContent : nextMd;
    view.workHash = res.hash || null;
    view.currentVersion = res.currentVersion;
    view.realVersion = res.realVersion || view.realVersion || res.currentVersion;
    view.workState = res.state;
    view.ackedText = renderedMd;
    view.lastSaved = renderedMd;
    view.dirty = cleanLineEndings(renderedMd) !== cleanLineEndings(view.baseline);
    restoreButtons();
    if (!skipDomRebuild || cleanLineEndings(renderedMd) !== cleanLineEndings(nextMd)) {
      await renderDraftPreview(renderedMd);
    }
    status(statusMsg, 'info');
    return true;
  }

  function serializeInlineEditableNode(rootEl, { allowNewlines = false } = {}) {
    if (!rootEl) return '';
    const newBadges = rootEl.querySelectorAll?.('.md-table-cell-diff > .md-table-cell-new');
    const effectiveRoot = (newBadges && newBadges.length > 0) ? newBadges[newBadges.length - 1] : rootEl;

    const walk = (node) => {
      if (!node) return '';
      if (node.nodeType === Node.TEXT_NODE) {
        return String(node.nodeValue || '').replace(/\u00a0/g, ' ');
      }
      if (node.nodeType !== Node.ELEMENT_NODE) return '';
      const el = node;
      if (
        el.getAttribute('contenteditable') === 'false' ||
        el.hasAttribute('data-md-diff-ghost') ||
        el.classList.contains('md-diff-word-del') ||
        el.classList.contains('md-table-cell-old') ||
        el.classList.contains('md-table-row-actions') ||
        el.classList.contains('md-hunk-floating-pill') ||
        el.classList.contains('md-hunk-actions') ||
        el.tagName === 'INPUT' ||
        el.tagName === 'BUTTON'
      ) {
        return '';
      }
      const tag = el.tagName.toUpperCase();
      if (tag === 'IMG') {
        const alt = el.getAttribute('alt') || 'image';
        const dataMd = el.getAttribute('data-md-src');
        if (dataMd && !dataMd.startsWith('data:')) {
          return `![${alt}](${dataMd})`;
        }
        const rawSrc = (el.getAttribute('src') || '').split('?')[0];
        const dir = path.includes('/') ? path.split('/').slice(0, -1).join('/') + '/' : '';
        const cleanSrc = decodeURIComponent(rawSrc.replace(/^\/+/, ''));
        const relSrc = (dir && cleanSrc.startsWith(dir)) ? cleanSrc.slice(dir.length) : cleanSrc;
        return `![${alt}](${relSrc || rawSrc})`;
      }
      if (tag === 'BR') {
        return allowNewlines ? '\n' : ' ';
      }
      const childrenMd = [...el.childNodes].map(walk).join('');
      if (allowNewlines && (tag === 'DIV' || tag === 'P')) {
        return (el.previousSibling ? '\n' : '') + childrenMd;
      }
      if (tag === 'CODE') return '`' + childrenMd + '`';
      if (tag === 'STRONG' || tag === 'B') return '**' + childrenMd + '**';
      if (tag === 'EM' || tag === 'I') return '*' + childrenMd + '*';
      if (tag === 'DEL' || tag === 'S') return '~~' + childrenMd + '~~';
      if (tag === 'A') {
        const href = el.getAttribute('href') || '';
        return href ? `[${childrenMd}](${href})` : childrenMd;
      }
      return childrenMd;
    };
    const rawOut = [...effectiveRoot.childNodes].map(walk).join('');
    if (allowNewlines) {
      return rawOut
        .replace(/\r\n?/g, '\n')
        .replace(/[ \t]+\n/g, '\n')
        .replace(/\n+$/, '')
        .trim();
    }
    return rawOut.replace(/\r?\n/g, ' ').trim();
  }

  function stripMarkdownLineSyntaxForMatch(rawLine) {
    return String(rawLine || '')
      .replace(/^(?:\s*[-*+]\s+(?:\[[ xX]\]\s+)?|\s*\d+[.)]\s+|#{1,6}\s+|>\s?)/, '')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/\*\*([^*]+)\*\*/g, '$1')
      .replace(/~~([^~]+)~~/g, '$1')
      .replace(/\*([^*]+)\*/g, '$1')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function findBestMatchingLineIndex(lines, hintLineIdx, origPlainText) {
    const cleanTarget = String(origPlainText || '').replace(/\s+/g, ' ').trim();
    const safeHint = Math.max(0, Math.min(lines.length - 1, hintLineIdx));
    if (!cleanTarget) return safeHint;
    if (stripMarkdownLineSyntaxForMatch(lines[safeHint]) === cleanTarget) {
      return safeHint;
    }
    for (let delta = 1; delta <= 25; delta++) {
      for (const cand of [safeHint - delta, safeHint + delta]) {
        if (cand >= 0 && cand < lines.length) {
          if (stripMarkdownLineSyntaxForMatch(lines[cand]) === cleanTarget) {
            return cand;
          }
        }
      }
    }
    for (let delta = 0; delta <= 15; delta++) {
      for (const cand of [safeHint - delta, safeHint + delta]) {
        if (cand >= 0 && cand < lines.length) {
          const stripped = stripMarkdownLineSyntaxForMatch(lines[cand]);
          if (stripped && (stripped.includes(cleanTarget) || cleanTarget.includes(stripped))) {
            return cand;
          }
        }
      }
    }
    return safeHint;
  }

  function computeParagraphSpanEnd(lines, startIdx) {
    let i = startIdx + 1;
    while (i < lines.length) {
      const l = String(lines[i] || '');
      const st = l.trim();
      if (!st) break;
      if (/^ {0,3}([`~])\1{2,}/.test(l)) break;
      if (/^(#{1,6})\s+/.test(st)) break;
      if (/^(-{3,}|\*{3,}|_{3,})$/.test(st)) break;
      if (/^>\s?/.test(l)) break;
      if (/^\s*[-+*]\s+/.test(l) || /^\s*\d+[.)]\s+/.test(l)) break;
      if (i + 1 < lines.length && l.includes('|') && isTableDividerRow(splitPipeRow(lines[i + 1]))) break;
      i++;
    }
    return i;
  }

  function mountPreviewLiveEditor() {
    if (!preview || preview.dataset.livePreviewMounted === 'true') return;
    preview.dataset.livePreviewMounted = 'true';

    preview.addEventListener('change', ev => {
      const cb = ev.target;
      if (!(cb instanceof HTMLInputElement) || cb.type !== 'checkbox') return;
      const li = cb.closest('[data-l]');
      if (!li) return;
      const lineIdx = Math.max(0, (Number(li.getAttribute('data-l')) || 1) - 1);
      const md = getWorkingPreviewMarkdown();
      const lines = md.replace(/\r\n?/g, '\n').split('\n');
      if (lineIdx < lines.length && /^(\s*(?:[-*+]|\d+[.)])\s+\[)[ xX](\])/.test(lines[lineIdx])) {
        lines[lineIdx] = lines[lineIdx].replace(/^(\s*(?:[-*+]|\d+[.)])\s+\[)[ xX](\])/, `$1${cb.checked ? 'x' : ' '}$2`);
        void commitPreviewLiveMarkdown(lines.join('\n'), 'Updated task item in Preview draft.');
      }
    });

    // v9.24 Unified Ctrl+V Image Paste for BOTH Preview mode AND Edit visually mode (including inside Table Cells!)
    document.addEventListener('paste', async ev => {
      if (document.querySelector('dialog.lantern-crop-dialog[open], .lantern-crop-dialog')) return;
      if (view.mode !== 'preview' && view.mode !== 'visual') return;
      const t = ev.target;
      if (t instanceof Element && t.closest('#lanternChatDrawer, #termDrawer, input, textarea, .cm-editor')) return;

      // Capture active table cell BEFORE closing any inline contenteditable editor
      const activeEditCell = (t instanceof Element ? t.closest('article.md-preview td, article.md-preview th') : null)
        || document.querySelector('article.md-preview td[contenteditable="true"], article.md-preview th[contenteditable="true"], article.md-preview td .md-docx-inline-editing, article.md-preview th .md-docx-inline-editing')?.closest('td, th')
        || ((lastClickedTableCellContext && (Date.now() - lastClickedTableCellContext.at < 30000)) ? lastClickedTableCellContext.cellEl : null);

      const mdTokens = await extractOrUploadClipboardImages(ev);
      if (!mdTokens || !mdTokens.length) return;

      const scrollSnap = captureAllPreviewScrollStates();
      if (activeLiveEditorCleanup) {
        // Cancel inline editor without firing a competing save request
        activeLiveEditorCleanup(false);
      }

      try {
        const curMd = (view.mode === 'visual' && view.instance ? getEditorText() : getWorkingPreviewMarkdown()).replace(/\r\n?/g, '\n');
        const lines = curMd.split('\n');
        const cellCoord = activeEditCell ? resolveTableCellCoordinates(activeEditCell, curMd) : null;

        if (cellCoord && cellCoord.targetLineIdx >= 0 && cellCoord.targetLineIdx < lines.length) {
          // Paste image(s) directly inside the active table cell on 1 single line!
          const rowCells = splitGfmRowCells(lines[cellCoord.targetLineIdx]);
          while (rowCells.length <= cellCoord.colIdx) rowCells.push('');
          const curCellVal = String(rowCells[cellCoord.colIdx] || '').trim();
          const joinedTokens = mdTokens.join(' ');
          rowCells[cellCoord.colIdx] = curCellVal ? `${curCellVal} ${joinedTokens}` : joinedTokens;
          lines[cellCoord.targetLineIdx] = '| ' + rowCells.join(' | ') + ' |';
          view.lastActiveLine = cellCoord.targetLineIdx + 1;
        } else {
          // Paste image(s) at the active line as clean 1-line image block(s)
          const insertAfterLine = view.lastActiveLine
            ? Math.max(0, Math.min(lines.length, Number(view.lastActiveLine)))
            : lines.length;
          const insertionLines = ['', ...mdTokens, ''];
          lines.splice(insertAfterLine, 0, ...insertionLines);
          view.lastActiveLine = insertAfterLine + mdTokens.length;
        }

        const nextMd = lines.join('\n');
        if (view.mode === 'visual' && view.instance) {
          await applyWorkingText(nextMd, view.workHash, { backed: false });
          await flushWorkingCopy(nextMd);
          status(`Pasted ${mdTokens.length} image(s) in Visual Editor.`, 'info');
        } else {
          await commitPreviewLiveMarkdown(nextMd, `Pasted ${mdTokens.length} image(s) into Preview.`, scrollSnap, false);
        }
        void refreshImageAudit();
      } catch (err) {
        status('Image paste failed: ' + err.message, 'error');
      }
    }, true);

    // 1-Click Direct In-Place Docx-Style Editing on Table Cells (td, th), Code Blocks (pre.md-code), & Markdown Blocks (li, p, h1..h6)
    preview.addEventListener('click', ev => {
      if (view.mode !== 'preview' || preview.hidden) return;
      const sel = window.getSelection?.();
      if (sel && !sel.isCollapsed && String(sel.toString() || '').trim().length > 0) return;

      const target = ev.target instanceof Element ? ev.target : null;
      if (!target) return;
      if (target.closest('a, button, input, textarea, .md-hunk-actions, .md-hunk-floating-pill, .md-table-row-actions, .md-two-tier-diff, .md-preview-deletion, .mermaid-diagram, img')) {
        return;
      }

      // Case A: Table Cell (td / th) Direct 1-Click In-Place ContentEditable (Zero Height Collapse, Zero Flash)
      const cell = target.closest('td, th');
      const table = cell?.closest('table');
      if (cell && table && preview.contains(table) && !cell.closest('.md-table-tr-del')) {
        if (cell.getAttribute('contenteditable') === 'true' || cell.querySelector('[contenteditable="true"]')) return;
        if (activeLiveEditorCleanup) activeLiveEditorCleanup(true);

        const md = getWorkingPreviewMarkdown().replace(/\r\n?/g, '\n');
        const lines = md.split('\n');
        const tr = cell.closest('tr');
        const trAttrLine = Number(tr?.getAttribute('data-l') || 0);
        const tableAttrLine = Math.max(1, Number(table.getAttribute('data-l') || table.closest('[data-l]')?.getAttribute('data-l') || 1));
        let tableStartIdx = Math.min(lines.length - 1, tableAttrLine - 1);
        while (tableStartIdx > 0 && String(lines[tableStartIdx - 1] || '').trim().startsWith('|')) tableStartIdx--;
        while (tableStartIdx < lines.length && !String(lines[tableStartIdx] || '').trim().startsWith('|')) tableStartIdx++;

        const isHeader = Boolean(tr && tr.parentElement?.tagName === 'THEAD');
        const tbodyRows = [...(table.tBodies[0]?.rows || [])].filter(r => !r.classList.contains('md-table-tr-del'));
        const bodyIdx = tbodyRows.indexOf(tr);
        const targetLineIdx = trAttrLine > 0
          ? (trAttrLine - 1)
          : (isHeader ? tableStartIdx : (tableStartIdx + 2 + Math.max(0, bodyIdx)));
        if (targetLineIdx < 0 || targetLineIdx >= lines.length) return;

        const rowCells = splitGfmRowCells(lines[targetLineIdx]);
        const allCellsInRow = [...tr.cells];
        const colIdx = allCellsInRow.indexOf(cell);
        if (colIdx < 0) return;
        const origCellMd = (rowCells[colIdx] ?? serializeInlineEditableNode(cell, { allowNewlines: false })).trim();

        // Edit the active .md-table-cell-new badge directly in-place if the cell already has .md-table-cell-diff,
        // so the Red/Green comparison badges stay visible and the row height NEVER jumps or flashes!
        const newBadges = cell.querySelectorAll('.md-table-cell-diff > .md-table-cell-new');
        const editTargetEl = newBadges.length > 0 ? newBadges[newBadges.length - 1] : cell;
        const savedTargetHtml = editTargetEl.innerHTML;
        if (newBadges.length > 0) {
          editTargetEl.innerHTML = formatInlineMarkdownHtml(origCellMd);
        } else {
          cell.querySelectorAll('.md-hunk-floating-pill, .md-hunk-actions').forEach(el => {
            el.setAttribute('contenteditable', 'false');
          });
        }

        editTargetEl.setAttribute('contenteditable', 'true');
        editTargetEl.setAttribute('spellcheck', 'false');
        editTargetEl.classList.add('md-docx-inline-editing');
        editTargetEl.focus({ preventScroll: true });

        let finished = false;

        const buildUpdatedTableMd = () => {
          const curVal = serializeInlineEditableNode(editTargetEl, { allowNewlines: false }).replace(/\|/g, '\\|').trim();
          if (curVal === origCellMd) return null;
          const freshLines = getWorkingPreviewMarkdown().replace(/\r\n?/g, '\n').split('\n');
          if (targetLineIdx >= freshLines.length) return null;
          const freshCells = splitGfmRowCells(freshLines[targetLineIdx]);
          while (freshCells.length <= colIdx) freshCells.push('');
          freshCells[colIdx] = curVal;
          freshLines[targetLineIdx] = '| ' + freshCells.join(' | ') + ' |';
          return freshLines.join('\n');
        };

        const finishCell = (commit, moveDelta = 0) => {
          if (finished) return;
          finished = true;
          activeLiveEditorCleanup = null;
          const scrollSnap = captureAllPreviewScrollStates();
          editTargetEl.removeAttribute('contenteditable');
          editTargetEl.classList.remove('md-docx-inline-editing');
          restoreAllPreviewScrollStates(scrollSnap);
          if (!commit) {
            editTargetEl.innerHTML = savedTargetHtml;
            restoreAllPreviewScrollStates(scrollSnap);
            return;
          }
          const curValNow = serializeInlineEditableNode(editTargetEl, { allowNewlines: false }).replace(/\|/g, '\\|').trim();
          const nextMd = buildUpdatedTableMd();
          if (!nextMd) {
            editTargetEl.innerHTML = savedTargetHtml;
            restoreAllPreviewScrollStates(scrollSnap);
            return;
          }
          const cleanCellHtml = formatInlineMarkdownHtml(curValNow);
          cell.setAttribute('data-orig-html', cleanCellHtml);
          // Skip full /api/md/render DOM rebuild since the cell is already inside the rendered <table>!
          void commitPreviewLiveMarkdown(nextMd, `Updated table cell (L${targetLineIdx + 1}).`, scrollSnap, true).then(() => {
            if (moveDelta !== 0) {
              const updatedTables = [...preview.querySelectorAll('table')];
              const nextTable = updatedTables.find(t => Number(t.getAttribute('data-l')) === tableAttrLine) || updatedTables[0];
              if (nextTable) {
                const editableCells = [...nextTable.querySelectorAll('th, td')].filter(c => !c.closest('.md-table-tr-del'));
                const curFlatIdx = editableCells.findIndex(c => c.closest('tr')?.rowIndex === tr.rowIndex && c.cellIndex === colIdx);
                const nextCell = editableCells[curFlatIdx + moveDelta];
                if (nextCell) nextCell.click();
              }
            }
          });
        };
        activeLiveEditorCleanup = finishCell;

        const onKeyDown = kev => {
          if (kev.key === 'Escape') {
            kev.preventDefault();
            finishCell(false, 0);
          } else if (kev.key === 'Enter' && !kev.shiftKey) {
            kev.preventDefault();
            finishCell(true, 0);
          } else if (kev.key === 'Tab') {
            kev.preventDefault();
            finishCell(true, kev.shiftKey ? -1 : 1);
          } else if (kev.key.toLowerCase() === 's' && (kev.ctrlKey || kev.metaKey)) {
            kev.preventDefault();
            finishCell(true, 0);
            setTimeout(() => { void save(true); }, 60);
          }
        };
        const onBlur = () => {
          editTargetEl.removeEventListener('keydown', onKeyDown);
          editTargetEl.removeEventListener('blur', onBlur);
          finishCell(true, 0);
        };
        editTargetEl.addEventListener('keydown', onKeyDown);
        editTargetEl.addEventListener('blur', onBlur);
        return;
      }

      // Case A2: Fenced Code Block (pre.md-code[data-l]) Direct 1-Click In-Place Editing
      const preNode = target.closest('pre.md-code[data-l]');
      if (preNode && preview.contains(preNode)) {
        const codeEl = preNode.querySelector('code') || preNode;
        if (codeEl.getAttribute('contenteditable') === 'true') return;
        if (activeLiveEditorCleanup) activeLiveEditorCleanup(true);

        const md = getWorkingPreviewMarkdown().replace(/\r\n?/g, '\n');
        const lines = md.split('\n');
        const hintLineIdx = Math.max(0, (Number(preNode.getAttribute('data-l')) || 1) - 1);
        let fenceStartIdx = hintLineIdx;
        while (fenceStartIdx >= 0 && !/^\s*(`{3,}|~{3,})/.test(String(lines[fenceStartIdx] || ''))) {
          fenceStartIdx--;
        }
        if (fenceStartIdx < 0) {
          fenceStartIdx = hintLineIdx;
          while (fenceStartIdx < lines.length && !/^\s*(`{3,}|~{3,})/.test(String(lines[fenceStartIdx] || ''))) {
            fenceStartIdx++;
          }
        }
        if (fenceStartIdx < 0 || fenceStartIdx >= lines.length) return;
        const fenceMatch = String(lines[fenceStartIdx] || '').match(/^\s*(`{3,}|~{3,})/);
        const fenceToken = fenceMatch ? fenceMatch[1] : '```';
        let fenceEndIdx = fenceStartIdx + 1;
        while (fenceEndIdx < lines.length && !String(lines[fenceEndIdx] || '').trim().startsWith(fenceToken)) {
          fenceEndIdx++;
        }
        const origCodeBody = lines.slice(fenceStartIdx + 1, fenceEndIdx).join('\n');
        const savedCodeHtml = codeEl.innerHTML;

        preNode.querySelectorAll('.md-hunk-floating-pill, .md-hunk-actions').forEach(el => {
          el.setAttribute('contenteditable', 'false');
        });
        codeEl.textContent = origCodeBody;
        codeEl.setAttribute('contenteditable', 'true');
        codeEl.setAttribute('spellcheck', 'false');
        preNode.classList.add('md-docx-inline-editing');
        codeEl.classList.add('md-docx-inline-editing');
        codeEl.focus({ preventScroll: true });

        let codeClosed = false;
        const finishCodeBlock = (commit) => {
          if (codeClosed) return;
          codeClosed = true;
          activeLiveEditorCleanup = null;
          const scrollSnap = captureAllPreviewScrollStates();
          codeEl.removeAttribute('contenteditable');
          preNode.classList.remove('md-docx-inline-editing');
          codeEl.classList.remove('md-docx-inline-editing');
          restoreAllPreviewScrollStates(scrollSnap);
          if (!commit) {
            codeEl.innerHTML = savedCodeHtml;
            restoreAllPreviewScrollStates(scrollSnap);
            return;
          }
          const nextCodeBody = String(codeEl.innerText ?? codeEl.textContent ?? '').replace(/\r\n?/g, '\n').replace(/\n$/, '');
          if (nextCodeBody === origCodeBody) {
            codeEl.innerHTML = savedCodeHtml;
            restoreAllPreviewScrollStates(scrollSnap);
            return;
          }
          const escCode = nextCodeBody.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
          codeEl.innerHTML = escCode;
          codeEl.setAttribute('data-orig-inline-html', escCode);
          const freshLines = getWorkingPreviewMarkdown().replace(/\r\n?/g, '\n').split('\n');
          const bodyCount = Math.max(0, fenceEndIdx - (fenceStartIdx + 1));
          freshLines.splice(fenceStartIdx + 1, bodyCount, ...nextCodeBody.split('\n'));
          void commitPreviewLiveMarkdown(freshLines.join('\n'), `Updated code block (L${fenceStartIdx + 1}).`, scrollSnap, true);
        };
        activeLiveEditorCleanup = finishCodeBlock;

        const onCodeKeyDown = kev => {
          if (kev.key === 'Escape') {
            kev.preventDefault();
            finishCodeBlock(false);
          } else if (kev.key === 'Enter' && (kev.ctrlKey || kev.metaKey)) {
            kev.preventDefault();
            finishCodeBlock(true);
          } else if (kev.key === 'Tab') {
            kev.preventDefault();
            if (typeof document.execCommand === 'function') {
              document.execCommand('insertText', false, '  ');
            }
          } else if (kev.key.toLowerCase() === 's' && (kev.ctrlKey || kev.metaKey)) {
            kev.preventDefault();
            finishCodeBlock(true);
            setTimeout(() => { void save(true); }, 60);
          }
        };
        const onCodeBlur = () => {
          codeEl.removeEventListener('keydown', onCodeKeyDown);
          codeEl.removeEventListener('blur', onCodeBlur);
          finishCodeBlock(true);
        };
        codeEl.addEventListener('keydown', onCodeKeyDown);
        codeEl.addEventListener('blur', onCodeBlur);
        return;
      }

      // Case B: Block-level (li, p, h1..h6) Direct 1-Click In-Place ContentEditable (Docx-style, zero extra boxes/lines)
      const blockNode = target.closest('li[data-l], p[data-l], h1[data-l], h2[data-l], h3[data-l], h4[data-l], h5[data-l], h6[data-l]');
      if (!blockNode || !preview.contains(blockNode)) return;
      if (blockNode.getAttribute('contenteditable') === 'true') return;
      if (activeLiveEditorCleanup) activeLiveEditorCleanup(true);

      const isHeadingBlock = /^H[1-6]$/.test(blockNode.tagName);
      const allowBlockNewlines = !isHeadingBlock;

      const md = getWorkingPreviewMarkdown().replace(/\r\n?/g, '\n');
      const lines = md.split('\n');
      const hintLineIdx = Math.max(0, (Number(blockNode.getAttribute('data-l')) || 1) - 1);

      // Hide deleted word ghosts inside this block while editing so caret placement is natural
      const hiddenGhosts = [...blockNode.querySelectorAll('.md-diff-word-del, [data-md-diff-ghost]')];
      hiddenGhosts.forEach(g => { g.hidden = true; });
      blockNode.querySelectorAll('.md-hunk-floating-pill, .md-hunk-actions, input[type="checkbox"]').forEach(el => {
        el.setAttribute('contenteditable', 'false');
      });

      const initialSerialized = serializeInlineEditableNode(blockNode, { allowNewlines: allowBlockNewlines });
      const origPlainText = stripMarkdownLineSyntaxForMatch(initialSerialized);
      const targetLineIdx = findBestMatchingLineIndex(lines, hintLineIdx, origPlainText);
      const spanEndIdx = blockNode.tagName === 'P' ? computeParagraphSpanEnd(lines, targetLineIdx) : (targetLineIdx + 1);
      const spanCount = Math.max(1, spanEndIdx - targetLineIdx);
      const origRawLine = String(lines[targetLineIdx] ?? '');
      const prefixMatch = origRawLine.match(/^(\s*(?:[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+|#{1,6}\s+|>\s?))/);
      const linePrefix = prefixMatch ? prefixMatch[1] : '';

      const savedBlockHtml = blockNode.innerHTML;
      const origBlockMd = spanCount > 1
        ? lines.slice(targetLineIdx, spanEndIdx).join('\n')
        : initialSerialized;
      if (spanCount > 1) {
        blockNode.innerHTML = lines.slice(targetLineIdx, spanEndIdx).map(formatInlineMarkdownHtml).join('<br>');
      }

      blockNode.setAttribute('contenteditable', 'true');
      blockNode.setAttribute('spellcheck', 'false');
      blockNode.classList.add('md-docx-inline-editing');
      blockNode.focus({ preventScroll: true });

      let closed = false;
      const finishBlock = (commit) => {
        if (closed) return;
        closed = true;
        activeLiveEditorCleanup = null;
        const scrollSnap = captureAllPreviewScrollStates();
        blockNode.removeAttribute('contenteditable');
        blockNode.classList.remove('md-docx-inline-editing');
        hiddenGhosts.forEach(g => { g.hidden = false; });
        restoreAllPreviewScrollStates(scrollSnap);
        if (!commit) {
          blockNode.innerHTML = savedBlockHtml;
          restoreAllPreviewScrollStates(scrollSnap);
          return;
        }
        const nextInlineMd = serializeInlineEditableNode(blockNode, { allowNewlines: allowBlockNewlines });
        if (nextInlineMd === origBlockMd) {
          blockNode.innerHTML = savedBlockHtml;
          restoreAllPreviewScrollStates(scrollSnap);
          return;
        }
        const freshLines = getWorkingPreviewMarkdown().replace(/\r\n?/g, '\n').split('\n');
        const resolvedIdx = spanCount > 1 ? targetLineIdx : findBestMatchingLineIndex(freshLines, targetLineIdx, origPlainText);
        if (resolvedIdx < 0 || resolvedIdx >= freshLines.length) return;
        const replacementLines = nextInlineMd.split('\n').map((l, idx) => (idx === 0 ? linePrefix + l : l));
        const canPatchInPlace = replacementLines.length === spanCount;
        if (canPatchInPlace) {
          const existingCb = blockNode.querySelector('input[type="checkbox"]');
          const cbClone = existingCb ? existingCb.cloneNode(true) : null;
          const cleanInlineHtml = nextInlineMd.split('\n').map(formatInlineMarkdownHtml).join('<br>');
          blockNode.innerHTML = cleanInlineHtml;
          if (cbClone) blockNode.prepend(cbClone);
          blockNode.setAttribute('data-orig-inline-html', blockNode.innerHTML);
        }
        freshLines.splice(resolvedIdx, spanCount, ...replacementLines);
        void commitPreviewLiveMarkdown(freshLines.join('\n'), `Updated L${resolvedIdx + 1}.`, scrollSnap, canPatchInPlace);
      };
      activeLiveEditorCleanup = finishBlock;

      const onKeyDown = kev => {
        if (kev.key === 'Escape') {
          kev.preventDefault();
          finishBlock(false);
        } else if (kev.key === 'Enter') {
          if (isHeadingBlock && !kev.shiftKey) {
            kev.preventDefault();
            finishBlock(true);
          } else if (kev.ctrlKey || kev.metaKey) {
            kev.preventDefault();
            finishBlock(true);
          } else {
            // Issue 4 fix: Allow Enter / Shift+Enter to insert a newline inside paragraphs/blocks without collapsing!
            kev.preventDefault();
            if (typeof document.execCommand === 'function') {
              document.execCommand('insertLineBreak');
            }
          }
        } else if (kev.key.toLowerCase() === 's' && (kev.ctrlKey || kev.metaKey)) {
          kev.preventDefault();
          finishBlock(true);
          setTimeout(() => { void save(true); }, 60);
        }
      };
      const onBlur = () => {
        blockNode.removeEventListener('keydown', onKeyDown);
        blockNode.removeEventListener('blur', onBlur);
        finishBlock(true);
      };
      blockNode.addEventListener('keydown', onKeyDown);
      blockNode.addEventListener('blur', onBlur);
    });
  }

  bindSplitScrollSync();
  mountMarkdownExtraToolbar();
  mountPreviewImageToolbar();
  mountPreviewLiveEditor();
  // Pre-warm Source bundle on idle for lag-free mode switching (v9.0 Zero-Milkdown)
  setTimeout(() => {
    if (!document.hidden) {
      void loadSourceBundle().catch(() => {});
    }
  }, 350);

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
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'z') {
      const inFormInput = e.target instanceof Element && Boolean(e.target.closest('input, textarea, #lanternChatDrawer'));
      if (inFormInput) return;
      const inCm = e.target instanceof Element && Boolean(e.target.closest('.cm-editor'));
      const inPm = e.target instanceof Element && Boolean(e.target.closest('.ProseMirror'));
      if (view.mode === 'source' && typeof view.instance?.undo === 'function') {
        // If focus is NOT inside CodeMirror, call view.instance.undo(); if focus IS inside CodeMirror,
        // let CodeMirror undo if it has local history, or fall through to cross-mode undoHistoryStack if none!
        if (!inCm && view.instance.undo()) {
          e.preventDefault();
          view.instance.focus?.();
          return;
        }
        if (inCm && view.instance?.hasPendingPatches?.()) {
          return;
        }
      }
      if (view.mode === 'visual' && inPm && typeof view.instance?.isCleanFromMount === 'function' && !view.instance.isCleanFromMount()) {
        return;
      }
      if (!inCm || !view.instance?.hasPendingPatches?.()) {
        const curNow = cleanLineEndings(view.active ? getEditorText() : (view.ackedText || view.baseline || ''));
        let prevSnap = null;
        while (view.undoHistoryStack.length > 0) {
          const cand = view.undoHistoryStack.pop();
          if (cand && typeof cand.text === 'string' && cleanLineEndings(cand.text) !== curNow) {
            prevSnap = cand;
            break;
          }
        }
        if (!prevSnap && view.baseline && cleanLineEndings(view.baseline) !== curNow) {
          prevSnap = { text: view.baseline, at: Date.now() };
        }
        if (prevSnap) {
          e.preventDefault();
          void (async () => {
            if (view.active && view.instance) {
              await applyWorkingText(prevSnap.text, view.workHash, { backed: false });
              await flushWorkingCopy(prevSnap.text);
            } else {
              const state = await fetchWorkState().catch(() => null);
              if (state?.saved) {
                view.version = state.saved.version;
                view.baseline = state.saved.content;
                view.realText = state.realContent ?? state.work?.realContent ?? state.saved.content;
                view.realVersion = state.realVersion || state.work?.realHash || state.currentVersion;
              }
              const baseVer = state?.saved?.version || view.version;
              const expHash = state?.work?.hash || view.workHash || null;
              view.userDraftText = prevSnap.text;
              const res = await api('/api/work/write', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  path,
                  content: prevSnap.text,
                  expectHash: expHash,
                  baseVersion: baseVer,
                  allowConcurrent: true,
                  userDraft: true,
                }),
              });
              const renderedMd = typeof res.mergedContent === 'string' ? res.mergedContent : prevSnap.text;
              view.workHash = res.hash || null;
              view.currentVersion = res.currentVersion;
              view.realVersion = res.realVersion || view.realVersion || res.currentVersion;
              view.workState = res.state;
              if (res.state === 'clean') view.userDraftText = null;
              view.ackedText = renderedMd;
              view.lastSaved = renderedMd;
              view.dirty = cleanLineEndings(renderedMd) !== cleanLineEndings(view.baseline);
              restoreButtons();
              await renderDraftPreview(renderedMd);
            }
            status('Restored previous edit state (Ctrl+Z).', 'info');
          })();
          return;
        }
        if (view.mode === 'preview') {
          e.preventDefault();
          void (async () => {
            try {
              const vData = await api('/api/md/versions?p=' + encodeURIComponent(path));
              const allItems = [];
              (vData.groups || []).forEach(g => (g.items || []).forEach(it => allItems.push(it)));
              const prevVer = allItems.find(it => !it.isCurrent && it.version !== view.currentVersion) || allItems[1];
              if (prevVer) {
                const res = await api('/api/md/versions/restore', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ path, versionId: prevVer.id, version: prevVer.version }),
                });
                const nextText = res.work?.content ?? res.saved?.content ?? '';
                if (res.saved) {
                  view.version = res.saved.version;
                  view.baseline = res.saved.content;
                }
                view.currentVersion = res.currentVersion || prevVer.version;
                view.workHash = res.work?.hash || null;
                view.workState = res.state || (view.workHash ? 'pending' : 'clean');
                view.ackedText = nextText;
                view.lastSaved = nextText;
                view.dirty = Boolean(res.work);
                await renderDraftPreview(nextText);
                status('Restored previous saved version (Ctrl+Z).', 'info');
              }
            } catch (_) {}
          })();
          return;
        }
      }
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
  document.body?.setAttribute('data-md-shell-ready', '1');
  window.__lanternMdVisual = { get state() { return view; }, open: start,
    show: start, save: () => save(true), preview: close, flushNow: saveDraft,
    beginBotTurn, cancelBotTurn, touchBotTurn, onWorkLocked, onWorkChanged, undoLastBotTurn, jumpToDiffHunk,
    reconcileVisualMarkdown, syncSplitScrollFrom, refreshImageAudit };
})();
