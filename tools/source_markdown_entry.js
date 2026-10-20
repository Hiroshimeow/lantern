// Lantern Source editor: CodeMirror owns editing/viewport/history while
// LanternMarkdownDiff remains the only hunk/merge truth.
import {ChangeSet, EditorState, StateEffect, StateField, Text} from '@codemirror/state';
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
  constructor(index, hunk, action, subIdx = 0) {
    super();
    this.index = index;
    this.subIdx = subIdx;
    const arr = Array.isArray(hunk?.baseText) ? hunk.baseText : [];
    this.text = arr.map(line => '− ' + line).join('\n');
    this.action = action;
  }
  eq(other) {
    return other.index === this.index && other.subIdx === this.subIdx &&
      other.text === this.text &&
      other.action === this.action;
  }
  toDOM() {
    const row = document.createElement('div');
    row.className = 'cm-lantern-deletion';
    row.dataset.hunkIndex = String(this.index);
    const text = document.createElement('div');
    text.className = 'cm-lantern-deletion-text';
    text.textContent = this.text || '− (Deleted empty line)';
    const actions = document.createElement('span');
    actions.className = 'md-hunk-actions';
    for (const [action, label] of [['accept', '✓ Accept'], ['undo', '↶ Undo']]) {
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
    row.append(actions, text);
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
      if (hunk.kind === 'mod' && Array.isArray(hunk.draftText) &&
          hunk.baseText.length === hunk.draftText.length && hunk.baseText.length > 1) {
        for (let k = 0; k < hunk.baseText.length; k++) {
          if (hunk.baseText[k] !== hunk.draftText[k]) {
            const lineNo = Math.max(1, Math.min(state.doc.lines, hunk.draftStart + k + 1));
            const at = state.doc.line(lineNo).from;
            ranges.push(
              Decoration.widget({
                widget: new DeletionWidget(index, {baseText: [hunk.baseText[k]]}, payload?.action, k),
                block: true,
                side: -1,
              }).range(at)
            );
          }
        }
      } else {
        const lineNo = Math.max(1, Math.min(state.doc.lines, hunk.draftStart + 1));
        const at = state.doc.line(lineNo).from;
        ranges.push(
          Decoration.widget({
            widget: new DeletionWidget(index, hunk, payload?.action, 0),
            block: true,
            side: -1,
          }).range(at)
        );
      }
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
  '&': {height: '100%', minHeight: '78vh', display: 'flex', flexDirection: 'column', flex: '1'},
  '.cm-scroller': {overflow: 'auto', flex: '1', height: '100%'},
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

function pointFor(doc, position) {
  const line = doc.lineAt(position);
  return {line: line.number, column: position - line.from};
}

function patchesFor(baseDoc, changes) {
  const patches = [];
  changes.iterChanges((fromA, toA, _fromB, _toB, inserted) => {
    patches.push({
      from: pointFor(baseDoc, fromA),
      to: pointFor(baseDoc, toA),
      insert: inserted.toString(),
      expected: baseDoc.sliceString(fromA, toA),
    });
  });
  return patches;
}

function createSourceMarkdown(parent, content, onChange, onAction, options = {}) {
  const initialText = normalizedText(content);
  const acknowledgedText = normalizedText(
    options.acknowledgedText === undefined ? content : options.acknowledgedText
  );
  let acknowledgedDoc = Text.of(acknowledgedText.split('\n'));
  const initialChange = minimalChange(acknowledgedText, initialText);
  let pendingChanges = initialChange
    ? ChangeSet.of(initialChange, acknowledgedDoc.length)
    : ChangeSet.empty(acknowledgedDoc.length);
  let inflight = null;
  let batchId = 0;
  let suppressCallback = false;
  let suppressPending = false;

  const state = EditorState.create({
    doc: initialText,
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
        if (!update.docChanged) return;
        if (!suppressPending) {
          // Browser automation, paste, accessibility tools and some IMEs may
          // surface a full-document CM transaction for a local edit. Refine
          // each transaction to its actual changed prefix/suffix before
          // composing it into the durable patch queue; otherwise a textarea-
          // style whole replacement would normalize untouched mixed EOLs.
          const refined = minimalChange(
            update.startState.doc.toString(),
            update.state.doc.toString(),
          );
          const changes = refined
            ? ChangeSet.of(refined, update.startState.doc.length)
            : ChangeSet.empty(update.startState.doc.length);
          pendingChanges = pendingChanges.compose(changes);
        }
        if (!suppressCallback) onChange?.(update);
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
    hasPendingPatches() {
      return !!inflight || !pendingChanges.empty;
    },
    takePendingPatches() {
      if (inflight) throw new Error('Source patch batch already in flight');
      if (pendingChanges.empty) return null;
      const changes = pendingChanges;
      const before = acknowledgedDoc;
      const after = changes.apply(before);
      const patches = patchesFor(before, changes);
      if (!patches.length) return null;
      const batch = {
        id: ++batchId,
        patches,
        before,
        after,
        changes,
      };
      inflight = batch;
      pendingChanges = ChangeSet.empty(after.length);
      return batch;
    },
    acknowledgePatches(batch) {
      if (!inflight || inflight.id !== batch?.id)
        throw new Error('Source patch acknowledgement is stale');
      acknowledgedDoc = inflight.after;
      inflight = null;
      return true;
    },
    rejectPatches(batch) {
      if (!inflight || inflight.id !== batch?.id) return false;
      pendingChanges = inflight.changes.compose(pendingChanges);
      inflight = null;
      return true;
    },
    replaceExternalText(text, {acknowledge = true} = {}) {
      if (inflight) throw new Error('Cannot replace Source while a patch is in flight');
      const next = normalizedText(text);
      const change = minimalChange(view.state.doc.toString(), next);
      if (change) {
        suppressCallback = true;
        suppressPending = acknowledge;
        try {
          view.dispatch({changes: change});
        } finally {
          suppressPending = false;
          suppressCallback = false;
        }
      }
      if (acknowledge) {
        acknowledgedDoc = view.state.doc;
        pendingChanges = ChangeSet.empty(acknowledgedDoc.length);
      }
      return !!change;
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
      // CodeMirror's scroll effect is applied during measure. For immediate
      // cross-mode restoration also seed the editor scroller from its own
      // virtual line block; this keeps the target visible without page reload.
      try {
        const block = view.lineBlockAt(anchor);
        view.scrollDOM.scrollTop = Math.max(0, block.top - 80);
      } catch (_) {}
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
        pendingPatchCount: inflight?.patches?.length || (
          pendingChanges.empty ? 0 : patchesFor(acknowledgedDoc, pendingChanges).length
        ),
      };
    },
  };

  return api;
}

window.LanternSourceEditor = {createSourceMarkdown};
