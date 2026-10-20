// Run: node --test tests/test_source_v74_characterization.cjs
// Optional oracle: LANTERN_SOURCE_V74_TARGET=<preserved or rebuilt bundle>.
// Extract real code without loading CodeMirror's browser runtime. The stubs only
// record DOM/decorations; widget, placement, equality and callbacks are unmodified.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {test} = require('node:test');

const root = path.resolve(__dirname, '..');
const target = process.env.LANTERN_SOURCE_V74_TARGET || path.join(root, 'tools/source_markdown_entry.js');
const source = fs.readFileSync(target, 'utf8');
function node(tagName) {
  return {
    tagName, dataset: {}, attributes: {}, children: [], listeners: {},
    setAttribute(key, value) { this.attributes[key] = value; },
    addEventListener(key, value) { this.listeners[key] = value; },
    append(...children) { this.children.push(...children); },
  };
}
const decoration = {
  line: spec => ({range: at => ({type: 'line', at, ...spec})}),
  widget: spec => ({range: at => ({type: 'widget', at, ...spec})}),
  set: (ranges, sort) => { assert.equal(sort, true); return ranges; },
};
let code, widgetName, prepareName, themeCode;
if (source.includes('class DeletionWidget')) {
  code = source.slice(source.indexOf('class DeletionWidget'), source.indexOf('const hunkField'));
  widgetName = 'DeletionWidget';
  prepareName = 'prepareDecorations';
  themeCode = source.slice(source.indexOf('const sourceTheme ='), source.indexOf('function normalizedText'));
  themeCode += '\nreturn sourceTheme;';
} else {
  const match = /([\w$]+)=class extends ([\w$]+)\{constructor\([^)]*\)\{super\(\),this\.index=/.exec(source);
  assert.ok(match, 'bundle widget boundary');
  widgetName = match[1];
  const start = match.index;
  const end = source.indexOf(';function ', start);
  assert.ok(end > start, 'bundle widget end');
  const functionStart = end + 1;
  prepareName = /^function ([\w$]+)/.exec(source.slice(functionStart))[1];
  const functionEnd = source.indexOf('var ', functionStart);
  code = 'const ' + source.slice(start, functionEnd);
  code = code.replace('extends ' + match[2], 'extends WidgetType');
  const decorationName = /return ([\w$]+)\.set\(/.exec(code)[1];
  code = code.replace(new RegExp('\\b' + decorationName + '\\.', 'g'), 'Decoration.');
  const theme = /[\w$]+=[\w$]+\.theme\((\{"&":\{height:"100%",minHeight:"78vh"[\s\S]*?)\);function/.exec(source);
  assert.ok(theme, 'bundle source theme boundary');
  themeCode = 'return ' + theme[1] + ';';
}
const api = new Function('WidgetType', 'Decoration', 'document',
  code + `\nreturn {Widget: ${widgetName}, prepare: ${prepareName}};`)(
    class {}, decoration, {createElement: node});
const theme = new Function('EditorView', themeCode)({theme: value => value});
const {Widget, prepare} = api;
const state = {doc: {lines: 4, line: n => {
  assert.ok(n >= 1 && n <= 4);
  return {from: (n - 1) * 10};
}}};
function widgets(hunk, action) {
  return prepare(state, {hunks: [hunk], action}).filter(range => range.type === 'widget');
}

test('deletion DOM is block text with a minus on every line, including empty lines', () => {
  const widget = new Widget(7, {baseText: ['old', '', 'last']});
  assert.equal(widget.text, '− old\n− \n− last');
  const row = widget.toDOM();
  assert.equal(row.tagName, 'div');
  assert.equal(row.className, 'cm-lantern-deletion');
  assert.equal(row.dataset.hunkIndex, '7');
  assert.equal(row.children[1].tagName, 'div');
  assert.equal(row.children[1].className, 'cm-lantern-deletion-text');
  assert.equal(row.children[1].textContent, widget.text);
  assert.equal(widget.ignoreEvent(), true);
});

test('missing/non-array base text uses original fallback; an empty line keeps its prefix', () => {
  for (const hunk of [undefined, {}, {baseText: null}, {baseText: 'old'}, {baseText: []}]) {
    assert.equal(new Widget(0, hunk).toDOM().children[1].textContent, '− (Deleted empty line)');
  }
  assert.equal(new Widget(0, {baseText: ['']}).toDOM().children[1].textContent, '− ');
});

test('widget equality includes hunk, sub-index, text and callback identity', () => {
  const action = () => {};
  const make = (index = 2, text = 'old', fn = action, sub = 0) => new Widget(index, {baseText: [text]}, fn, sub);
  const first = make();
  assert.equal(first.subIdx, 0);
  assert.equal(first.eq(make()), true);
  for (const other of [make(3), make(2, 'other'), make(2, 'old', () => {}), make(2, 'old', action, 1)]) {
    assert.equal(first.eq(other), false);
  }
});

test('action labels and aria labels preserve symbols; callbacks target whole hunk, not sub-index', () => {
  const calls = [];
  const widget = new Widget(8, {baseText: ['old']}, (...args) => calls.push(args), 3);
  const buttons = widget.toDOM().children[0].children;
  for (const [i, label] of ['✓ Accept', '↶ Undo'].entries()) {
    const button = buttons[i];
    assert.equal(button.type, 'button');
    assert.equal(button.className, 'md-hunk-button');
    assert.equal(button.textContent, label);
    assert.equal(button.attributes['aria-label'], label);
    let prevented = 0, stopped = 0;
    button.listeners.click({preventDefault() { prevented++; }, stopPropagation() { stopped++; }});
    assert.equal(prevented, 1);
    assert.equal(stopped, 1);
  }
  assert.deepEqual(calls, [[8, 'accept'], [8, 'undo']]);
  new Widget(8, {}).toDOM().children[0].children[0].listeners.click({preventDefault() {}, stopPropagation() {}});
});

test('equal-length multiline mods place old text only above each changed corresponding line', () => {
  const action = () => {};
  const hunk = {kind: 'mod', draftStart: 1, draftEnd: 4,
    baseText: ['old A', 'same', 'old C'], draftText: ['new A', 'same', 'new C']};
  const ranges = prepare(state, {hunks: [hunk], action});
  const lines = ranges.filter(r => r.type === 'line');
  assert.deepEqual(lines.map(r => r.at), [10, 20, 30]);
  for (const line of lines) {
    assert.equal(line.attributes.class, 'cm-lantern-diff-line cm-lantern-diff-mod');
    assert.equal(line.attributes['data-hunk-index'], '0');
  }
  const deleted = ranges.filter(r => r.type === 'widget');
  assert.deepEqual(deleted.map(r => [r.at, r.widget.text, r.widget.subIdx]), [[10, '− old A', 0], [30, '− old C', 2]]);
  for (const range of deleted) {
    assert.equal(range.block, true);
    assert.equal(range.side, -1);
    assert.equal(range.widget.index, 0);
    assert.equal(range.widget.action, action);
  }
  assert.equal(widgets({...hunk, draftText: hunk.baseText}).length, 0);
});

test('deletions, unequal-length mods, single-line mods and missing draftText retain whole-block placement', () => {
  for (const hunk of [
    {kind: 'del', baseText: ['a', 'b'], draftText: []},
    {kind: 'mod', baseText: ['a', 'b'], draftText: ['c']},
    {kind: 'mod', baseText: ['a'], draftText: ['b']},
    {kind: 'mod', baseText: ['a', 'b']},
  ]) {
    const deleted = widgets({...hunk, draftStart: 2, draftEnd: 2});
    assert.equal(deleted.length, 1);
    assert.equal(deleted[0].at, 20);
    assert.equal(deleted[0].widget.subIdx, 0);
    assert.equal(deleted[0].widget.text, hunk.baseText.map(line => '− ' + line).join('\n'));
  }
  assert.equal(widgets({kind: 'add', draftStart: 0, draftEnd: 1, baseText: []}).length, 0);
  assert.equal(prepare(state, null).length, 0);
});

test('both whole-block and per-line positions clamp to document bounds', () => {
  for (const [draftStart, expected] of [[-5, 0], [20, 30]]) {
    assert.equal(widgets({kind: 'del', draftStart, baseText: ['x']})[0].at, expected);
    assert.deepEqual(widgets({kind: 'mod', draftStart, baseText: ['x', 'y'], draftText: ['a', 'b']}).map(r => r.at), [expected, expected]);
  }
});

test('only outer editor has 78vh minimum; scroller retains overflow, flex and height', () => {
  assert.equal(theme['&'].minHeight, '78vh');
  assert.deepEqual(theme['.cm-scroller'], {overflow: 'auto', flex: '1', height: '100%'});
});
