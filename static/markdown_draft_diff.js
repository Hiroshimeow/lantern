/* Lantern Markdown draft diff/merge.
   Baseline and draft remain plain Markdown; this module only describes changes. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.LanternMarkdownDiff = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const normalize = text => String(text ?? '').replace(/\r\n?/g, '\n');
  const linesOf = text => normalize(text).split('\n');

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

  function diffLines(baseline, draft, options = {}) {
    const base = linesOf(baseline);
    const next = linesOf(draft);
    let prefix = 0;
    while (prefix < base.length && prefix < next.length && base[prefix] === next[prefix]) prefix++;
    let suffix = 0;
    while (suffix < base.length - prefix && suffix < next.length - prefix &&
           base[base.length - 1 - suffix] === next[next.length - 1 - suffix]) suffix++;

    const a = base.slice(prefix, base.length - suffix);
    const b = next.slice(prefix, next.length - suffix);
    if (!a.length && !b.length) return [];
    if (!a.length) return [{
      kind: 'add', baseStart: prefix, baseEnd: prefix,
      draftStart: prefix, draftEnd: prefix + b.length,
      baseText: [], draftText: b.slice(),
    }];
    if (!b.length) return [{
      kind: 'del', baseStart: prefix, baseEnd: prefix + a.length,
      draftStart: prefix, draftEnd: prefix,
      baseText: a.slice(), draftText: [],
    }];

    const ops = myers(a, b, options.maxDistance ?? 2048);
    if (!ops) return [{
      kind: 'mod',
      baseStart: prefix, baseEnd: prefix + a.length,
      draftStart: prefix, draftEnd: prefix + b.length,
      baseText: a.slice(), draftText: b.slice(),
      fallback: true,
    }];

    let basePos = prefix, draftPos = prefix, current = null;
    const hunks = [];
    const flush = () => {
      if (!current) return;
      current.baseEnd = basePos;
      current.draftEnd = draftPos;
      current.kind = current.baseStart === current.baseEnd ? 'add'
        : current.draftStart === current.draftEnd ? 'del' : 'mod';
      hunks.push(current);
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
    const base = linesOf(baseText);
    const ours = diffLines(baseText, oursText);
    const theirs = diffLines(baseText, theirsText);
    const acceptedTheirs = [];
    const conflicts = [];

    for (const their of theirs) {
      const touching = ours.filter(our => overlaps(our, their));
      if (!touching.length) {
        acceptedTheirs.push(their);
        continue;
      }
      if (touching.length === 1 && equivalent(touching[0], their)) continue;
      conflicts.push({
        baseStart: their.baseStart,
        baseEnd: their.baseEnd,
        draftStart: their.draftStart,
        draftEnd: their.draftEnd,
        piText: their.draftText.slice(),
        baseText: their.baseText.slice(),
      });
    }

    const edits = ours.concat(acceptedTheirs).sort((a, b) =>
      b.baseStart - a.baseStart || b.baseEnd - a.baseEnd);
    const merged = base.slice();
    for (const edit of edits) {
      merged.splice(edit.baseStart, edit.baseEnd - edit.baseStart, ...hunkReplacement(edit));
    }
    return {
      text: merged.join('\n'),
      conflicts,
      appliedPiHunks: acceptedTheirs.length,
      oursHunks: ours,
      theirsHunks: theirs,
    };
  }

  return {normalize, linesOf, diffLines, merge3, overlaps, equivalent};
});
