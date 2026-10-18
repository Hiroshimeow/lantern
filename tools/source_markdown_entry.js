// Lantern Source editor: CodeMirror owns editing/viewport/history while
// LanternMarkdownDiff remains the only hunk/merge truth.
import {EditorState, StateEffect, StateField} from '@codemirror/state';
import {
  Decoration,
  EditorView,
  GutterMarker,
  WidgetType,
  gutter,
} from '@codemirror/view';
import {basicSetup} from 'codemirror';
import {oneDark} from '@codemirror/theme-one-dark';

const setHunksEffect = StateEffect.define();

class DiffGutterMarker extends GutterMarker {
  constructor(kind) {
    super();
    this.kind = kind;
  }
  eq(other) { return other.kind === this.kind; }
  toDOM() {
    const node = document.createElement('span');
    node.className = 'cm-lantern-gutter-marker cm-lantern-gutter-' + this.kind;
    node.setAttribute('aria-hidden', 'true');
    node.textContent = '●';
    return node;
  }
}

class DeletionWidget extends WidgetType {
  constructor(index, hunk, action) {
    super();
    this.index = index;
    this.text = Array.isArray(hunk.baseText) ? hunk.baseText.join(' ↵ ') : '';
    this.action = action;
  }
  eq(other) {
    return other.index === this.index && other.text === this.text &&
      other.action === this.action;
  }
  toDOM() {
    const row = document.createElement('div');
    row.className = 'cm-lantern-deletion';
    row.dataset.hunkIndex = String(this.index);
    const text = document.createElement('span');
    text.className = 'cm-lantern-deletion-text';
    text.textContent = this.text ? '− ' + this.text : 'Deleted content';
    const actions = document.createElement('span');
    actions.className = 'md-hunk-actions';
    for (const [action, label] of [['accept', 'Accept'], ['undo', 'Undo']]) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'md-hunk-button';
      button.textContent = label;
      button.setAttribute('aria-label', label);
      button.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        this.action?.(this.index, action);
      });
      actions.append(button);
    }
    row.append(text, actions);
    return row;
  }
  ignoreEvent() { return true; }
}

function prepareDecorations(state, payload) {
  const ranges = [];
  const hunks = Array.isArray(payload?.hunks) ? payload.hunks : [];
  for (const [index, hunk] of hunks.entries()) {
    if ((hunk.kind === 'add' || hunk.kind === 'mod') &&
        hunk.draftEnd > hunk.draftStart) {
      const from = Math.max(0, hunk.draftStart);
      const to = Math.min(state.doc.lines, hunk.draftEnd);
      for (let lineNo = from; lineNo < to; lineNo++) {
        const line = state.doc.line(lineNo + 1);
        ranges.push(
          Decoration.line({
            attributes: {
              class: 'cm-lantern-diff-line cm-lantern-diff-' + hunk.kind,
              'data-hunk-index': String(index),
            },
          }).range(line.from)
        );
      }
    }
    if (Array.isArray(hunk.baseText) && hunk.baseText.length) {
      const lineNo = Math.max(1, Math.min(state.doc.lines, hunk.draftStart + 1));
      const at = state.doc.line(lineNo).from;
      ranges.push(
        Decoration.widget({
          widget: new DeletionWidget(index, hunk, payload?.action),
          block: true,
          side: -1,
        }).range(at)
      );
    }
  }
  return Decoration.set(ranges, true);
}

const hunkField = StateField.define({
  create() {
    return {hunks: [], action: null, decorations: Decoration.none};
  },
  update(value, transaction) {
    let payload = null;
    for (const effect of transaction.effects) {
      if (effect.is(setHunksEffect)) payload = effect.value;
    }
    if (payload) {
      return {
        hunks: Array.isArray(payload.hunks) ? payload.hunks : [],
        action: payload.action || null,
        decorations: prepareDecorations(transaction.state, payload),
      };
    }
    if (!transaction.docChanged) return value;
    return {
      ...value,
      decorations: value.decorations.map(transaction.changes),
    };
  },
  provide(field) {
    return EditorView.decorations.from(field, value => value.decorations);
  },
});

const markerCache = new Map();
function marker(kind) {
  if (!markerCache.has(kind)) markerCache.set(kind, new DiffGutterMarker(kind));
  return markerCache.get(kind);
}

const diffGutter = gutter({
  class: 'cm-lantern-diff-gutter',
  lineMarker(view, line) {
    const lineIndex = view.state.doc.lineAt(line.from).number - 1;
    const payload = view.state.field(hunkField);
    for (const hunk of payload.hunks) {
      if (hunk.draftEnd > hunk.draftStart &&
          lineIndex >= hunk.draftStart && lineIndex < hunk.draftEnd)
        return marker(hunk.kind === 'add' ? 'add' : 'mod');
      if (Array.isArray(hunk.baseText) && hunk.baseText.length &&
          lineIndex === Math.min(view.state.doc.lines - 1, hunk.draftStart))
        return marker('del');
    }
    return null;
  },
});

const sourceTheme = EditorView.theme({
  '&': {height: 'min(74vh, 1000px)', minHeight: '340px'},
  '.cm-scroller': {overflow: 'auto'},
  '.cm-content': {
    fontFamily: 'ui-monospace,SFMono-Regular,Consolas,monospace',
    fontSize: '13px',
    lineHeight: '1.6',
    caretColor: '#dce7f5',
  },
});

function normalizedText(text) {
  return String(text ?? '').replace(/\r\n?/g, '\n');
}

function minimalChange(current, next) {
  if (current === next) return null;
  let start = 0;
  const common = Math.min(current.length, next.length);
  while (start < common && current.charCodeAt(start) === next.charCodeAt(start)) start++;
  let oldEnd = current.length;
  let newEnd = next.length;
  while (oldEnd > start && newEnd > start &&
         current.charCodeAt(oldEnd - 1) === next.charCodeAt(newEnd - 1)) {
    oldEnd--;
    newEnd--;
  }
  return {from: start, to: oldEnd, insert: next.slice(start, newEnd)};
}

function createSourceMarkdown(parent, content, onChange, onAction) {
  let suppressChange = false;
  const state = EditorState.create({
    doc: normalizedText(content),
    extensions: [
      basicSetup,
      oneDark,
      sourceTheme,
      hunkField,
      diffGutter,
      EditorView.contentAttributes.of({
        'aria-label': 'Markdown source',
        'aria-multiline': 'true',
        'data-lantern-source-content': 'true',
        spellcheck: 'false',
      }),
      EditorView.updateListener.of(update => {
        if (update.docChanged && !suppressChange) onChange?.(update);
      }),
    ],
  });
  const view = new EditorView({state, parent});
  view.dom.classList.add('md-source-editor');

  const api = {
    kind: 'codemirror-source',
    getMarkdown() {
      return view.state.doc.toString();
    },
    focus() {
      view.focus();
    },
    destroy() {
      view.destroy();
    },
    setHunks(hunks) {
      view.dispatch({
        effects: setHunksEffect.of({hunks: Array.isArray(hunks) ? hunks : [], action: onAction}),
      });
    },
    replaceExternalText(text) {
      const next = normalizedText(text);
      const change = minimalChange(view.state.doc.toString(), next);
      if (!change) return false;
      suppressChange = true;
      try {
        view.dispatch({changes: change});
      } finally {
        suppressChange = false;
      }
      return true;
    },
    sourceBookmark() {
      const main = view.state.selection.main;
      const line = view.state.doc.lineAt(main.head);
      const bookmark = {
        line: line.number,
        column: main.head - line.from,
      };
      if (main.from !== main.to) {
        const selected = view.state.doc.sliceString(main.from, main.to);
        if (selected.length <= 512 && !selected.includes('\n'))
          bookmark.selectedText = selected;
      }
      return bookmark;
    },
    restoreBookmark(bookmark) {
      const wanted = Math.max(1, Math.min(view.state.doc.lines, Number(bookmark?.line) || 1));
      const line = view.state.doc.line(wanted);
      const column = Math.max(0, Math.min(line.length, Number(bookmark?.column) || 0));
      let anchor = line.from + column;
      let head = anchor;
      const selected = bookmark?.selectedText;
      if (selected && selected.length <= 512 && !selected.includes('\n')) {
        const text = line.text;
        const first = text.indexOf(selected);
        if (first >= 0 && text.indexOf(selected, first + selected.length) < 0) {
          anchor = line.from + first;
          head = anchor + selected.length;
        }
      }
      view.dispatch({
        selection: {anchor, head},
        effects: EditorView.scrollIntoView(anchor, {y: 'start', yMargin: 80}),
      });
      view.focus();
      return true;
    },
    selectionOffsets() {
      const main = view.state.selection.main;
      return {from: main.from, to: main.to, anchor: main.anchor, head: main.head};
    },
    debugMetrics() {
      const viewport = view.viewport;
      return {
        docLines: view.state.doc.lines,
        renderedLines: view.contentDOM.querySelectorAll('.cm-line').length,
        domNodes: view.dom.querySelectorAll('*').length,
        viewportFrom: viewport.from,
        viewportTo: viewport.to,
        focused: view.hasFocus,
        selection: api.selectionOffsets(),
      };
    },
  };

  return api;
}

window.LanternSourceEditor = {createSourceMarkdown};
