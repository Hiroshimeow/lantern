/* Lantern Markdown draft diff/merge (v4).
   Baseline and draft remain plain Markdown; this module describes line, word, and table cell changes. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.LanternMarkdownDiff = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const normalize = text => String(text ?? '').replace(/\r\n?/g, '\n');

  // Line comparison is EOL-insensitive, but source spans always point into the
  // original decoded JS string (UTF-16 code-unit offsets). This keeps logical
  // diffing separate from mutation and lets callers preserve exact CR/LF/CRLF.
  function sourceModel(text) {
    const source = String(text ?? '');
    const records = [];
    const eol = /\r\n|\r|\n/g;
    let tokenStart = 0;
    let contentStart = 0;
    let match;
    while ((match = eol.exec(source))) {
      records.push({
        text: source.slice(contentStart, match.index),
        tokenStart,
        contentStart,
        contentEnd: match.index,
      });
      tokenStart = match.index;
      contentStart = match.index + match[0].length;
    }
    records.push({
      text: source.slice(contentStart),
      tokenStart,
      contentStart,
      contentEnd: source.length,
    });
    for (let index = 0; index < records.length; index++) {
      records[index].tokenEnd = index + 1 < records.length
        ? records[index + 1].tokenStart
        : source.length;
    }
    return {source, lines: records};
  }

  const linesOf = text => sourceModel(text).lines.map(line => line.text);

  function myers(a, b, maxDistance = 2048) {
    const n = a.length, m = b.length;
    const limit = Math.min(n + m, maxDistance);
    let v = new Map([[1, 0]]);
    const trace = [];

    for (let d = 0; d <= limit; d++) {
      trace.push(new Map(v));
      const next = new Map();
      for (let k = -d; k <= d; k += 2) {
        const left = v.has(k - 1) ? v.get(k - 1) : Number.NEGATIVE_INFINITY;
        const down = v.has(k + 1) ? v.get(k + 1) : Number.NEGATIVE_INFINITY;
        let x;
        if (k === -d || (k !== d && left < down)) x = Number.isFinite(down) ? down : 0;
        else x = (Number.isFinite(left) ? left : 0) + 1;
        let y = x - k;
        while (x < n && y < m && a[x] === b[y]) { x++; y++; }
        next.set(k, x);
        if (x >= n && y >= m) return backtrack(trace, a, b);
      }
      v = next;
    }
    return null;
  }

  function backtrack(trace, a, b) {
    let x = a.length, y = b.length;
    const ops = [];
    for (let d = trace.length - 1; d >= 0; d--) {
      const v = trace[d];
      const k = x - y;
      const left = v.has(k - 1) ? v.get(k - 1) : Number.NEGATIVE_INFINITY;
      const down = v.has(k + 1) ? v.get(k + 1) : Number.NEGATIVE_INFINITY;
      const prevK = (k === -d || (k !== d && left < down)) ? k + 1 : k - 1;
      const prevXRaw = v.get(prevK);
      const prevX = Number.isFinite(prevXRaw) ? prevXRaw : 0;
      const prevY = prevX - prevK;

      while (x > prevX && y > prevY) {
        ops.push({type: 'equal', line: a[x - 1]});
        x--; y--;
      }
      if (d === 0) break;
      if (x === prevX) {
        ops.push({type: 'insert', line: b[y - 1]});
        y--;
      } else {
        ops.push({type: 'delete', line: a[x - 1]});
        x--;
      }
    }
    return ops.reverse();
  }

  /**
   * Word-level intra-line diff for highlighting exact changed words/tokens
   * inside modified paragraphs and table cells without strikethrough clutter.
   */
  function diffWords(oldStr, newStr) {
    const aText = String(oldStr ?? '');
    const bText = String(newStr ?? '');
    if (aText === bText) {
      return aText ? [{type: 'equal', text: aText}] : [];
    }
    const tokenize = s => s.match(/\s+|[\p{L}\p{N}_]+|[^\s\p{L}\p{N}_]+/gu) || [];
    const a = tokenize(aText);
    const b = tokenize(bText);
    if (!a.length) return b.length ? [{type: 'add', text: bText}] : [];
    if (!b.length) return a.length ? [{type: 'del', text: aText}] : [];

    const ops = myers(a, b, 512);
    if (!ops) {
      return [
        {type: 'del', text: aText},
        {type: 'add', text: bText},
      ];
    }
    const out = [];
    for (const op of ops) {
      const kind = op.type === 'equal' ? 'equal' : (op.type === 'delete' ? 'del' : 'add');
      const prev = out[out.length - 1];
      if (prev && prev.type === kind) {
        prev.text += op.line;
      } else {
        out.push({type: kind, text: op.line});
      }
    }
    return out;
  }

  /**
   * Parses a Markdown GFM pipe-table row into an array of trimmed cell strings.
   * Returns null if the line is not a pipe table data/header row or is a separator row.
   */
  function parseTableRowCells(line) {
    const raw = String(line ?? '').trim();
    if (!raw.startsWith('|') || !raw.endsWith('|') || raw.length < 3) return null;
    const inner = raw.slice(1, -1);
    const cells = [];
    let cur = '';
    for (let i = 0; i < inner.length; i++) {
      if (inner[i] === '\\' && i + 1 < inner.length && inner[i + 1] === '|') {
        cur += '|';
        i++;
      } else if (inner[i] === '|') {
        cells.push(cur.trim());
        cur = '';
      } else {
        cur += inner[i];
      }
    }
    cells.push(cur.trim());
    // Reject table separator rows like | --- | :---: | ---: |
    const isSeparator = cells.every(c => /^:?-{2,}:?$/.test(c));
    if (isSeparator) return null;
    return cells;
  }

  function contentSpan(model, start, end) {
    if (start === end) {
      const at = start < model.lines.length
        ? model.lines[start].contentStart
        : model.source.length;
      return {start: at, end: at, text: ''};
    }
    const first = model.lines[start];
    const last = model.lines[end - 1];
    const from = first.contentStart;
    const to = last.contentEnd;
    return {start: from, end: to, text: model.source.slice(from, to)};
  }

  function addSpan(model, start, end, targetLineCount) {
    if (end === model.lines.length && start === targetLineCount) {
      const from = model.lines[start]?.tokenStart ?? model.source.length;
      return {start: from, end: model.source.length, text: model.source.slice(from)};
    }
    const from = model.lines[start]?.contentStart ?? model.source.length;
    const to = end < model.lines.length
      ? model.lines[end].contentStart
      : model.source.length;
    return {start: from, end: to, text: model.source.slice(from, to)};
  }

  function deleteSpan(model, start, end) {
    if (start === 0) {
      const to = end < model.lines.length
        ? model.lines[end].contentStart
        : model.source.length;
      return {start: 0, end: to, text: model.source.slice(0, to)};
    }
    if (end === model.lines.length) {
      const from = model.lines[start].tokenStart;
      return {start: from, end: model.source.length, text: model.source.slice(from)};
    }
    const from = model.lines[start].contentStart;
    const to = model.lines[end].contentStart;
    return {start: from, end: to, text: model.source.slice(from, to)};
  }

  function emptySpan(model, line) {
    let at;
    if (line === 0) at = 0;
    else if (line >= model.lines.length) at = model.source.length;
    else at = model.lines[line].contentStart;
    return {start: at, end: at, text: ''};
  }

  function decorateHunk(hunk, baseModel, draftModel) {
    const baseCount = hunk.baseEnd - hunk.baseStart;
    const draftCount = hunk.draftEnd - hunk.draftStart;
    let baseSpan;
    let draftSpan;

    if (baseCount && draftCount) {
      baseSpan = contentSpan(baseModel, hunk.baseStart, hunk.baseEnd);
      draftSpan = contentSpan(draftModel, hunk.draftStart, hunk.draftEnd);
    } else if (!baseCount && draftCount) {
      baseSpan = emptySpan(baseModel, hunk.baseStart);
      draftSpan = addSpan(
        draftModel,
        hunk.draftStart,
        hunk.draftEnd,
        baseModel.lines.length,
      );
    } else if (baseCount && !draftCount) {
      baseSpan = deleteSpan(baseModel, hunk.baseStart, hunk.baseEnd);
      draftSpan = emptySpan(draftModel, hunk.draftStart);
    } else {
      baseSpan = emptySpan(baseModel, hunk.baseStart);
      draftSpan = emptySpan(draftModel, hunk.draftStart);
    }

    hunk.offsetUnit = 'utf16-code-unit';
    hunk.baseSpan = baseSpan;
    hunk.draftSpan = draftSpan;
    hunk.replacement = draftSpan.text;
    return hunk;
  }

  function diffLines(baseline, draft, options = {}) {
    const baseModel = sourceModel(baseline);
    const draftModel = sourceModel(draft);
    const base = baseModel.lines.map(line => line.text);
    const next = draftModel.lines.map(line => line.text);
    let prefix = 0;
    while (prefix < base.length && prefix < next.length && base[prefix] === next[prefix]) prefix++;
    let suffix = 0;
    while (suffix < base.length - prefix && suffix < next.length - prefix &&
           base[base.length - 1 - suffix] === next[next.length - 1 - suffix]) suffix++;

    const a = base.slice(prefix, base.length - suffix);
    const b = next.slice(prefix, next.length - suffix);
    if (!a.length && !b.length) return [];
    if (!a.length) return [decorateHunk({
      kind: 'add', baseStart: prefix, baseEnd: prefix,
      draftStart: prefix, draftEnd: prefix + b.length,
      baseText: [], draftText: b.slice(),
    }, baseModel, draftModel)];
    if (!b.length) return [decorateHunk({
      kind: 'del', baseStart: prefix, baseEnd: prefix + a.length,
      draftStart: prefix, draftEnd: prefix,
      baseText: a.slice(), draftText: [],
    }, baseModel, draftModel)];

    const ops = myers(a, b, options.maxDistance ?? 2048);
    if (!ops) return [decorateHunk({
      kind: 'mod',
      baseStart: prefix, baseEnd: prefix + a.length,
      draftStart: prefix, draftEnd: prefix + b.length,
      baseText: a.slice(), draftText: b.slice(),
      fallback: true,
    }, baseModel, draftModel)];

    let basePos = prefix, draftPos = prefix, current = null;
    const hunks = [];
    const flush = () => {
      if (!current) return;
      current.baseEnd = basePos;
      current.draftEnd = draftPos;
      current.kind = current.baseStart === current.baseEnd ? 'add'
        : current.draftStart === current.draftEnd ? 'del' : 'mod';
      hunks.push(decorateHunk(current, baseModel, draftModel));
      current = null;
    };

    for (const op of ops) {
      if (op.type === 'equal') {
        flush();
        basePos++; draftPos++;
        continue;
      }
      if (!current) current = {
        kind: 'mod',
        baseStart: basePos, baseEnd: basePos,
        draftStart: draftPos, draftEnd: draftPos,
        baseText: [], draftText: [],
      };
      if (op.type === 'delete') {
        current.baseText.push(op.line);
        basePos++;
      } else {
        current.draftText.push(op.line);
        draftPos++;
      }
    }
    flush();
    return hunks;
  }

  function applyHunk(text, hunk, direction = 'forward') {
    const source = String(text ?? '');
    const reverse = direction === 'reverse';
    if (direction !== 'forward' && !reverse) throw new Error('invalid hunk direction');
    const from = reverse ? hunk?.draftSpan : hunk?.baseSpan;
    const to = reverse ? hunk?.baseSpan : hunk?.draftSpan;
    const fromLines = reverse ? hunk?.draftText : hunk?.baseText;
    const toLines = reverse ? hunk?.baseText : hunk?.draftText;
    const startLine = reverse ? hunk?.draftStart : hunk?.baseStart;
    if (!from || !to || !Number.isInteger(from.start) || !Number.isInteger(from.end))
      throw new Error('hunk exact source span is unavailable');

    if (Array.isArray(fromLines) && Array.isArray(toLines) &&
        fromLines.length > 0 && fromLines.length === toLines.length) {
      const model = sourceModel(source);
      for (let index = 0; index < fromLines.length; index++) {
        if (model.lines[startLine + index]?.text !== fromLines[index])
          throw new Error('hunk source line no longer matches current text');
      }
      let result = source;
      for (let index = fromLines.length - 1; index >= 0; index--) {
        const line = model.lines[startLine + index];
        result = result.slice(0, line.contentStart) +
          String(toLines[index] ?? '') +
          result.slice(line.contentEnd);
      }
      return result;
    }

    if (source.slice(from.start, from.end) !== String(from.text ?? ''))
      throw new Error('hunk source span no longer matches current text');
    return source.slice(0, from.start) + String(to.text ?? '') + source.slice(from.end);
  }

  function hunkReplacement(hunk) {
    return Array.isArray(hunk.draftText) ? hunk.draftText : [];
  }

  function overlaps(a, b) {
    const aEmpty = a.baseStart === a.baseEnd;
    const bEmpty = b.baseStart === b.baseEnd;
    if (aEmpty && bEmpty) return a.baseStart === b.baseStart;
    if (aEmpty) return a.baseStart >= b.baseStart && a.baseStart < b.baseEnd;
    if (bEmpty) return b.baseStart >= a.baseStart && b.baseStart < a.baseEnd;
    return Math.max(a.baseStart, b.baseStart) < Math.min(a.baseEnd, b.baseEnd);
  }

  function equivalent(a, b) {
    return a.baseStart === b.baseStart && a.baseEnd === b.baseEnd &&
      hunkReplacement(a).join('\n') === hunkReplacement(b).join('\n');
  }

  function merge3(baseText, oursText, theirsText) {
    const base = String(baseText ?? '');
    const ours = diffLines(base, oursText);
    const theirs = diffLines(base, theirsText);
    const acceptedTheirs = [];
    const conflicts = [];

    for (const their of theirs) {
      const touching = ours.filter(our => overlaps(our, their));
      if (!touching.length) {
        acceptedTheirs.push(their);
        continue;
      }
      if (touching.length === 1 && equivalent(touching[0], their)) continue;
      const ourLines = touching.flatMap(o => o.draftText || []);
      conflicts.push({
        baseStart: their.baseStart,
        baseEnd: their.baseEnd,
        draftStart: their.draftStart,
        draftEnd: their.draftEnd,
        oursText: ourLines,
        piText: their.draftText.slice(),
        baseText: their.baseText.slice(),
      });
    }

    const edits = ours.concat(acceptedTheirs).sort((a, b) =>
      b.baseSpan.start - a.baseSpan.start ||
      b.baseSpan.end - a.baseSpan.end);
    let merged = base;
    for (const edit of edits) merged = applyHunk(merged, edit, 'forward');
    return {
      text: merged,
      conflicts,
      appliedPiHunks: acceptedTheirs.length,
      oursHunks: ours,
      theirsHunks: theirs,
    };
  }

  return {
    normalize,
    linesOf,
    sourceModel,
    diffLines,
    diffWords,
    parseTableRowCells,
    applyHunk,
    merge3,
    overlaps,
    equivalent,
  };
});
