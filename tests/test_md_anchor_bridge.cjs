const assert=require('node:assert/strict');
const m=require('../static/markdown_anchor_bridge.js');
const source='# Intro\r\n\r\nParagraph _word_.\r\n\r\n<!-- comment -->\r\n\r\n| C1 | C2 |\r\n|---|---|\r\n| 1 | 2 |\r\n';
for (const line of [1,2,3,4,5,6,7,8,9]) {
 const offset=m.offsetForLine(source,line);
 assert.equal(m.lineForOffset(source,offset),line);
}
assert.equal(m.sourceOffsetToPage(source,9,{pages:[{start:0,end:30},{start:30,end:source.length}]}),1);
assert.equal(m.offsetForLine(source,10000),source.length);
const fake={
 getAttribute(key){return key==='data-l'?'9':null},
 tagName:'TR',textContent:'1 2',
 closest(selector){return selector==='[data-l]'?this:selector==='article.md-preview'?parent:null}
};
const parent={querySelectorAll(){return [fake]}};
assert.deepEqual(m.anchorFromElement(fake),{line:9,blockTag:'TR',text:'1 2',ordinal:0});
console.log('ANCHOR_BRIDGE_NODE_TEST_OK');
