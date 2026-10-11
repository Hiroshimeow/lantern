import assert from 'node:assert/strict';
import {indexMarkdown, TARGET_CHARS, MAX_RICH_CHARS} from '../tools/markdown_sections_indexer.mjs';

function assertPartition(source, targetChars) {
  const index = indexMarkdown(source, targetChars);
  assert(index.pages.length > 0);
  assert.equal(index.chars, source.length);
  assert.equal(index.pages[0].start, 0);
  assert.equal(index.pages.at(-1).end, source.length);
  let at=0;
  for(const p of index.pages) {
    assert.equal(p.start, at);
    assert(p.end >= p.start);
    at=p.end;
    assert.equal(p.oversized, p.end-p.start > MAX_RICH_CHARS);
  }
  assert.equal(index.pages.map(p=>source.slice(p.start,p.end)).join(''), source);
  for(const h of index.headings) {
    const p=index.pages[h.page];
    assert(p && p.start <= h.at && h.at < p.end, 'heading maps to its page');
  }
  return index;
}
{
  const src = '# Intro\n\nParagraph.\n\n'+('## Part\n\nHello **world**!\n\n'.repeat(2000));
  const {pages, headings, oversized}=assertPartition(src);
  assert(pages.length > 2);
  assert(headings.length > 1000);
  assert.equal(oversized,0);
}
{
  const src = '# Chinese & emoji 🐈\n\n'+
    '~~~mermaid\nflowchart LR\n'+' A --> B\n'.repeat(420)+ '~~~\n\n'+
    '|A|B|\n|---|---|\n'+ '|x|y|\n'.repeat(500)+ '\n'+
    '> Quote\n> with continuation\n\n' +
    '1. list\n   - nested\n\n   continuation\n\n' +
    '# End\n';
  const {pages,headings}=assertPartition(src,2600);
  // Large fenced Mermaid and tables remain indivisible blocks.
  // Exact token boundaries are retained for page partitioning.
  assert(pages.length>1);
  for(const p of pages.slice(0,-1)) {
    assert(!src.slice(p.start,p.end).endsWith('~~~mermaid\n'));
  }
  assert(headings.some(h=>h.title==='End'));
}
{
  const src='## Header\r\n\r\n'+'### Section\r\n\r\nText with emoji 👩‍💻\r\n\r\n'.repeat(800);
  assertPartition(src);
}
{
  const big = '# Long\n\n'+('Some inline text, **bold**, [links](#ref), and Unicode tiếng Việt.\n\n'.repeat(75000));
  const start=performance.now();
  const x=assertPartition(big);
  const elapsed=performance.now()-start;
  console.log('BENCH_LEXER_5MB='+JSON.stringify({chars:big.length,pages:x.pages.length,oversized:x.oversized,ms:Math.round(elapsed)}));
  assert(x.pages.length>100);
}
console.log('SEGMENT_INDEX_TESTS_OK');
