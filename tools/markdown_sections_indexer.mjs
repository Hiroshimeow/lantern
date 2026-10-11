// Proven Markdown-it block parser provides safe page boundaries. Every slice
// corresponds exactly to an untouched region of the original Markdown string.
// This worker deliberately does not serialize Markdown or build an editor DOM.
import MarkdownIt from 'markdown-it';

const parser = new MarkdownIt({html: false, linkify: false, typographer: false});
export const TARGET_CHARS = 12 * 1024;
export const MAX_RICH_CHARS = 48 * 1024;

export function indexMarkdown(source, targetChars = TARGET_CHARS) {
  if (typeof source !== 'string') throw new TypeError('Markdown must be a string');
  const lines = [0];
  let at = 0;
  while ((at = source.indexOf('\n', at)) !== -1) {
    at += 1;
    lines.push(at);
  }
  lines.push(source.length);
  const tokens = [];
  // Block-only parsing is sufficient for safe boundaries: avoid building huge
  // inline token trees. Outer tokens preserve fenced code, lists and tables.
  parser.block.parse(source, parser, {}, tokens);
  const spans = [];
  const headings = [];
  for (let i = 0; i < tokens.length; i += 1) {
    const t = tokens[i];
    if (t.level !== 0 || !Array.isArray(t.map) || t.map[1] <= t.map[0]) continue;
    const start = lines[Math.max(0, Math.min(t.map[0], lines.length - 1))];
    const end = lines[Math.max(0, Math.min(t.map[1], lines.length - 1))];
    if (!(end > start)) continue;
    if (spans.length && start < spans[spans.length - 1].end) continue;
    spans.push({start, end, type:t.type});
    if (t.type === 'heading_open') {
      const value = (tokens[i + 1]?.content || '').trim();
      if (value) headings.push({at:start, level:Number(t.tag.slice(1)) || 1, title:value.slice(0,110)});
    }
  }
  // Exact token boundaries are retained for page partitioning.
  const pages = [];
  let sectionStart = 0;
  let lastBoundary = 0;
  const threshold = Math.max(1024, Math.min(32 * 1024, Number(targetChars) || TARGET_CHARS));
  function push(end) {
    if (end <= sectionStart) return;
    pages.push({start:sectionStart, end, oversized:end-sectionStart > MAX_RICH_CHARS});
    sectionStart = end;
  }
  for (const span of spans) {
    if (span.start > sectionStart && span.end - sectionStart > threshold) {
      push(span.start); // never bisect a Markdown block token
    }
    lastBoundary = Math.max(lastBoundary, span.end);
  }
  if (sectionStart < source.length || !pages.length) push(source.length);
  if (!pages.length) pages.push({start:0, end:0, oversized:false});
  // Heading position -> owning page; binary search allows thousands of pages.
  for (const h of headings) {
    let left = 0, right = pages.length - 1;
    while (left < right) {
      const mid = (left + right) >>> 1;
      if (pages[mid].end <= h.at) left = mid + 1;
      else right = mid;
    }
    h.page = left;
  }
  return {
    pages, headings, chars:source.length, maxPageChars:Math.max(...pages.map(p=>p.end-p.start)),
    oversized:pages.filter(p=>p.oversized).length, blocks:spans.length,
  };
}

if (typeof self !== 'undefined' && typeof self.postMessage === 'function' &&
    typeof self.document === 'undefined') {
  self.onmessage = event => {
    const {id, source, targetChars} = event.data || {};
    try { self.postMessage({id, ok:true, result:indexMarkdown(source, targetChars)}); }
    catch (error) { self.postMessage({id, ok:false, error:String(error?.message || error)}); }
  };
}
