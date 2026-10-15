const assert = require('node:assert/strict');
const m = require('../static/markdown_anchor_bridge.js');
const md = '# Intro\n\nFirst paragraph.\n\nFirst paragraph.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\nEnd.\n';
assert.deepEqual(m.sourceSelection(md, {line:3, selectedText:'paragraph'}),
  {start:15, end:24});
assert.deepEqual(m.sourceSelection(md, {line:5, selectedText:'paragraph'}),
  {start:33, end:42});
assert.equal(m.sourceSelection(md, {line:3, selectedText:'First paragraph.'}).start, 9);
assert.equal(m.sourceSelection(md, {line:3, selectedText:'missing'}), null);
assert.equal(m.sourceSelection(md, {line:3, selectedText:'a'}), null); // matches repeatedly within the line, fail closed
assert.equal(m.closestLine([1,3,5,9,11], 8),5);
assert.equal(m.closestLine([1,3,5,9,11], 9),9);
assert.equal(m.closestLine([1,3,5], 0),1);
assert.equal(m.normalizedText('  Hi  \n there   '), 'Hi there');
console.log('MARKDOWN_LOCATION_NODE_TEST_OK');
