// Self-contained browser editor. No CDN, remote fonts, telemetry or AI providers.
import { Crepe } from '@milkdown/crepe';
import { commandsCtx, editorViewCtx, parserCtx, remarkCtx } from '@milkdown/kit/core';
import {
  addColAfterCommand, addRowAfterCommand, deleteSelectedCellsCommand,
  selectColCommand, selectRowCommand,
} from '@milkdown/kit/preset/gfm';
import { $prose, $remark } from '@milkdown/kit/utils';
import { Plugin, PluginKey } from '@milkdown/kit/prose/state';
import { Decoration, DecorationSet } from '@milkdown/kit/prose/view';
import { imageInlineComponent, inlineImageConfig } from '@milkdown/kit/component/image-inline';
import { uploadConfig } from '@milkdown/kit/plugin/upload';
import '@milkdown/crepe/theme/common/style.css';
import '@milkdown/crepe/theme/nord-dark.css';

// Image URLs in Markdown are relative to the .md file, not /api/plugin/preview.
// Only the rendered URL is resolved: the Markdown node keeps its original src.
function previewImageURL(src, documentPath) {
  const text = typeof src === 'string' ? src.trim() : '';
  if (!text || !documentPath || /[\u0000-\u001f\u007f\\]/.test(text) || text.startsWith('//') || text.startsWith('#')) return '';
  try {
    const parent = new URL('/' + documentPath.split('/').map(encodeURIComponent).join('/'), location.origin);
    const resolved = new URL(text, parent);
    if (resolved.origin !== location.origin || !/^https?:$/.test(resolved.protocol)) return '';
    return resolved.pathname + resolved.search + resolved.hash;
  } catch { return ''; }
}

// Milkdown 7.22.2 image schemas require a string title, while CommonMark
// represents an omitted image title as null. Normalize only this optional AST
// field before ProseMirror parsing so ordinary ![alt](path) images survive.
const preserveUntitledImages = $remark('lantern-untitled-image-compat', () => () => tree => {
  const visit = node => {
    if ((node.type === 'image' || node.type === 'image-block') && node.title == null) node.title = '';
    if (Array.isArray(node.children)) node.children.forEach(visit);
  };
  visit(tree);
});

const DIFF_IGNORED_MDAST = new Set(['definition', 'footnoteDefinition']);

function makePendingDiffPlugin() {
  const key = new PluginKey('lantern-pending-diff');
  const milkdown = $prose(() => new Plugin({
    key,
    state: {
      init: () => DecorationSet.empty,
      apply(tr, current) {
        const meta = tr.getMeta(key);
        if (meta?.replace) return DecorationSet.create(tr.doc, meta.decorations || []);
        if (meta?.clear) return DecorationSet.empty;
        return current.map(tr.mapping, tr.doc);
      },
    },
    props: {
      decorations(state) {
        return key.getState(state) || DecorationSet.empty;
      },
    },
  }));
  return { key, milkdown };
}

function currentEditorPieces(crepe) {
  return crepe.editor.action(ctx => ({
    view: ctx.get(editorViewCtx),
    parser: ctx.get(parserCtx),
    remark: ctx.get(remarkCtx),
  }));
}

function sameSerializedBlock(parsedNode, currentNode) {
  if (parsedNode.eq(currentNode)) return true;
  if (parsedNode.type === currentNode.type && currentNode.type.name === 'heading') {
    try {
      const normalized = currentNode.type.create(
        { ...currentNode.attrs, id: parsedNode.attrs.id || '' },
        currentNode.content,
        currentNode.marks,
      );
      return parsedNode.eq(normalized);
    } catch {
      return false;
    }
  }
  return false;
}

function buildVerifiedBlockMap(crepe, markdown) {
  if (markdown !== crepe.getMarkdown()) {
    return { mapped: false, reason: 'stale', units: [] };
  }

  let pieces;
  let tree;
  try {
    pieces = currentEditorPieces(crepe);
    tree = pieces.remark.runSync(pieces.remark.parse(markdown));
  } catch (error) {
    return { mapped: false, reason: 'parse:' + error.message, units: [] };
  }

  const mdBlocks = (Array.isArray(tree?.children) ? tree.children : [])
    .filter(node => !DIFF_IGNORED_MDAST.has(node?.type));
  const pmBlocks = [];
  pieces.view.state.doc.forEach((node, offset, index) => {
    pmBlocks.push({ node, offset, index });
  });
  while (pmBlocks.length) {
    const last = pmBlocks[pmBlocks.length - 1];
    if (!last.node?.isTextblock || last.node.content.size !== 0) break;
    pmBlocks.pop();
  }

  if (mdBlocks.length !== pmBlocks.length) {
    return {
      mapped: false,
      reason: 'block-count:' + mdBlocks.length + '/' + pmBlocks.length,
      units: [],
    };
  }

  const units = [];
  for (let index = 0; index < mdBlocks.length; index++) {
    const md = mdBlocks[index];
    const pm = pmBlocks[index];
    const startOffset = Number(md?.position?.start?.offset);
    const endOffset = Number(md?.position?.end?.offset);
    const startLine = Number(md?.position?.start?.line);
    const endLine = Number(md?.position?.end?.line);
    if (![startOffset, endOffset, startLine, endLine].every(Number.isFinite)) {
      return { mapped: false, reason: 'missing-position:' + index, units: [] };
    }

    let parsed;
    try {
      parsed = pieces.parser(markdown.slice(startOffset, endOffset));
    } catch (error) {
      return { mapped: false, reason: 'slice-parse:' + index + ':' + error.message, units: [] };
    }
    if (parsed.childCount !== 1 || !sameSerializedBlock(parsed.child(0), pm.node)) {
      return { mapped: false, reason: 'block-proof:' + index, units: [] };
    }
    units.push({
      index,
      type: pm.node.type.name,
      from: pm.offset,
      to: pm.offset + pm.node.nodeSize,
      lineStart: Math.max(0, startLine - 1),
      lineEnd: Math.max(startLine, endLine),
    });
  }

  return { mapped: true, reason: '', units, view: pieces.view };
}

function diffGhost(text) {
  const ghost = document.createElement('div');
  ghost.className = 'md-visual-deletion';
  ghost.dataset.mdDiffGhost = 'true';
  ghost.contentEditable = 'false';
  ghost.textContent = text;
  return ghost;
}

function buildPendingDecorations(units, hunks, docSize) {
  const kinds = new Map();
  const widgets = [];
  let unanchored = 0;

  for (const hunk of Array.isArray(hunks) ? hunks : []) {
    if ((hunk.kind === 'add' || hunk.kind === 'mod') && hunk.draftEnd > hunk.draftStart) {
      const touched = units.filter(unit =>
        unit.lineStart < hunk.draftEnd && unit.lineEnd > hunk.draftStart);
      if (!touched.length) {
        unanchored++;
      } else {
        for (const unit of touched) {
          const prior = kinds.get(unit.index);
          kinds.set(unit.index, prior === 'mod' || hunk.kind === 'mod' ? 'mod' : 'add');
        }
      }
    }

    if (Array.isArray(hunk.baseText) && hunk.baseText.length) {
      const anchor = units.find(unit => unit.lineStart >= hunk.draftStart);
      const pos = anchor ? anchor.from : docSize;
      const key = [
        'del', hunk.baseStart, hunk.baseEnd, hunk.draftStart,
        hunk.baseText.join('\n'),
      ].join(':');
      widgets.push(Decoration.widget(
        pos,
        () => diffGhost(hunk.baseText.join('\n')),
        { side: -1, key, ignoreSelection: true },
      ));
    }
  }

  const decorations = widgets.slice();
  for (const unit of units) {
    const kind = kinds.get(unit.index);
    if (!kind) continue;
    decorations.push(Decoration.node(unit.from, unit.to, {
      class: kind === 'mod' ? 'md-visual-diff-mod' : 'md-visual-diff-add',
      'data-md-visual-diff-kind': kind,
    }));
  }
  return { decorations, unanchored };
}

function makePendingDiffController(crepe, key) {
  let debug = [];
  const clear = () => {
    const { view } = currentEditorPieces(crepe);
    view.dispatch(
      view.state.tr
        .setMeta(key, { clear: true })
        .setMeta('addToHistory', false)
    );
    debug = [];
  };

  const set = (markdown, hunks) => {
    const proof = buildVerifiedBlockMap(crepe, markdown);
    if (!proof.mapped) {
      clear();
      return { mapped: false, reason: proof.reason, unanchored: hunks?.length || 0 };
    }
    const built = buildPendingDecorations(
      proof.units,
      hunks,
      proof.view.state.doc.content.size,
    );
    proof.view.dispatch(
      proof.view.state.tr
        .setMeta(key, { replace: true, decorations: built.decorations })
        .setMeta('addToHistory', false)
    );
    debug = proof.units.map(unit => ({ ...unit }));
    return {
      mapped: true,
      reason: '',
      unanchored: built.unanchored,
      units: debug.length,
    };
  };

  return {
    setPendingDiff: set,
    clearPendingDiff: clear,
    debugBlockMap: () => debug.map(unit => ({ ...unit })),
  };
}

// One verified PM block -> source line lookup per navigation, not an ordinal
// text search against the hidden, potentially stale Preview DOM.
function sourceLineLocator(crepe) {
  const proof = buildVerifiedBlockMap(crepe, crepe.getMarkdown());
  if (!proof.mapped) return null;
  return element => {
    if (!element || !proof.view.dom.contains(element)) return null;
    try {
      const pos = proof.view.posAtDOM(element, 0);
      const block = proof.units.find(unit => pos > unit.from && pos < unit.to);
      return block ? block.lineStart + 1 : null;
    } catch {
      return null;
    }
  };
}

function sourceBlockAtLine(crepe, line) {
  const proof = buildVerifiedBlockMap(crepe, crepe.getMarkdown());
  if (!proof.mapped) return null;
  const requested = Math.trunc(Number(line)) - 1;
  const unit = proof.units.find(item =>
    requested >= item.lineStart && requested < item.lineEnd);
  if (!unit) return null;
  const element = proof.view.nodeDOM(unit.from);
  return element instanceof Element && proof.view.dom.contains(element) ? element : null;
}

// Paste/drop or the image toolbar must write a real file before inserting a
// Markdown image node. Reuse Lantern's existing root-confined upload
// endpoint; never persist data: or blob: URLs into the document.
const imageTypes = {
  'image/png': 'png',
  'image/jpeg': 'jpg',
  'image/webp': 'webp',
  'image/gif': 'gif',
  'image/bmp': 'bmp',
};
async function uploadImage(file, documentPath, onStatus, namePrefix = 'pasted') {
  const suffix = imageTypes[file?.type];
  if (!suffix) throw new Error('Clipboard image must be PNG, JPEG, WebP, GIF, or BMP.');
  if (!file.size || file.size > 20 * 1024 * 1024) throw new Error('Image must be 1 B–20 MiB.');
  const directory = documentPath.split('/').slice(0, -1).join('/');
  const name = namePrefix + '-' + Date.now() + '-' + Math.random().toString(36).slice(2, 10) + '.' + suffix;
  const relative = 'assets/' + name;
  const url = '/api/upload?path=' + encodeURIComponent(directory) +
    '&name=' + encodeURIComponent(relative) + '&conflict=rename';
  onStatus?.(namePrefix === 'cropped' ? 'Uploading cropped image…' : 'Uploading pasted image…', 'info');
  const response = await fetch(url, {
    method: 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: { 'Content-Type': file.type }, body: file,
  });
  let result;
  try { result = await response.json(); } catch { throw new Error('Image upload: invalid server response'); }
  if (!response.ok || result.error || !result.file) {
    throw new Error('Image upload: ' + (result.error || ('HTTP ' + response.status)));
  }
  // The server can rename on collision. Trust its final path, not our guess.
  const serverPath = decodeURIComponent(String(result.file).replace(/^\//, ''));
  const expectedPrefix = directory ? directory + '/assets/' : 'assets/';
  if (!serverPath.startsWith(expectedPrefix)) throw new Error('Image upload returned an unexpected file path');
  return { src: 'assets/' + serverPath.slice(expectedPrefix.length), alt: file.name || 'Pasted image' };
}

// Milkdown owns node identity and its versioned Markdown save. The editor never
// owns the crop UI/geometry/encoder; that is lazy-loaded for both consumers.
function mountImageCrop(root, crepe, documentPath, onStatus) {
  const toolbar=document.createElement('div');
  toolbar.className='md-image-crop-toolbar';
  toolbar.hidden=true;
  const cropButton=document.createElement('button');
  cropButton.type='button';cropButton.className='btn';cropButton.textContent='Crop image';
  const removeButton=document.createElement('button');
  removeButton.type='button';removeButton.className='btn';removeButton.textContent='Delete image';
  toolbar.append(cropButton,removeButton);root.prepend(toolbar);
  let selected=null,disposed=false,busy=false,operation=null;
  const view=()=>crepe.editor.action(ctx=>ctx.get(editorViewCtx));
  const hide=()=>{toolbar.hidden=true;selected=null;};
  const check=target=>{
    if(disposed)throw Error('Visual editor was closed.');
    const editor=view(),node=editor.state.doc.nodeAt(target.pos);
    if(!node||!node.eq(target.node))throw Error('Selected image changed. Select it again.');
    return {editor,node};
  };
  const select=img=>{
    let editor,pos,node;
    try{
      editor=view();pos=editor.posAtDOM(img.parentElement,0);node=editor.state.doc.nodeAt(pos);
      if(node?.type.name!=='image'){
        const choice=editor.state.selection;
        if(choice.node?.type.name!=='image')return null;
        pos=choice.from;node=choice.node;
      }
      return {img,pos,node};
    }catch{return null;}
  };
  const onClick=e=>{
    if(toolbar.contains(e.target))return;
    const img=e.target.closest?.('.milkdown-image-inline img');
    if(!img||!root.contains(img)){if(!busy)hide();return;}
    requestAnimationFrame(()=>{
      if(disposed||busy)return;
      try{
        const url=new URL(img.currentSrc);
        selected=url.origin===location.origin&&img.complete&&img.naturalWidth
          && /\.(png|jpe?g|webp|bmp)$/i.test(url.pathname)?select(img):null;
      }catch{selected=null;}
      toolbar.hidden=!selected;
    });
  };
  root.addEventListener('click',onClick);
  removeButton.addEventListener('click',()=>{
    if(!selected||busy)return;
    try{
      const {editor,node}=check(selected);
      editor.dispatch(editor.state.tr.delete(selected.pos,selected.pos+node.nodeSize));
      hide();onStatus?.('Image reference removed. Original asset preserved.','info');
    }catch(error){onStatus?.(error.message,'error');}
  });
  cropButton.addEventListener('click',async()=>{
    if(!selected||busy)return;
    const target=selected;
    busy=true;cropButton.disabled=true;removeButton.disabled=true;
    operation=new AbortController();
    try{
      check(target);
      // Dynamic import survives esbuild's IIFE bundling; no Milkdown code
      // is pulled into the stand-alone viewer's crop module.
      const cropURL='/static/vendor/lantern-image-crop.min.js';
      const {openCrop}=await import(cropURL);
      if(disposed||operation.signal.aborted)return;
      const result=await openCrop({
        src:target.img.currentSrc,
        name:target.node.attrs.alt||'Image',
        signal:operation.signal,
      });
      if(!result||disposed||operation.signal.aborted)return;
      // Do not upload a file for a selection that changed while the dialog
      // was open. A paged editor can replace the entire Milkdown instance.
      check(target);
      const file=new File([result.blob],'cropped.'+result.extension,{type:result.blob.type});
      const uploaded=await uploadImage(file,documentPath,onStatus,'cropped');
      // Upload is already durable. Never silently update a different node.
      try {
        const {editor,node}=check(target);
        editor.dispatch(editor.state.tr.setNodeMarkup(target.pos,undefined,{
          ...node.attrs,src:uploaded.src,
        }));
        onStatus?.('New image: '+uploaded.src+'. Saving Markdown…','info');
      }catch(error){
        onStatus?.('Image saved as '+uploaded.src+' but document changed: '+error.message,'error');
      }
    }catch(error){
      if(!disposed&&!operation?.signal.aborted)onStatus?.('Crop failed: '+error.message,'error');
    }finally{
      busy=false;cropButton.disabled=false;removeButton.disabled=false;operation=null;hide();
    }
  });
  return ()=>{
    disposed=true;operation?.abort();root.removeEventListener('click',onClick);
    toolbar.remove();
  };
}

function mountTableToolbar(root, crepe, onStatus) {
  const toolbar=document.createElement('div');
  toolbar.className='md-table-tools';
  toolbar.hidden=true;
  const label=document.createElement('span');label.className='md-table-tools-label';label.textContent='Table';
  const make=(text,title,kind,danger=false)=>{
    const b=document.createElement('button');b.type='button';b.textContent=text;b.title=title;
    b.className='btn'+(danger?' danger':'');b.dataset.tableAction=kind;toolbar.append(b);return b;
  };
  toolbar.append(label);
  make('+ Row','Add row after selected row','add-row');
  make('− Row','Delete selected row','delete-row',true);
  make('+ Col','Add column after selected column','add-col');
  make('− Col','Delete selected column','delete-col',true);
  root.append(toolbar);

  let selected=null,disposed=false;
  const view=()=>crepe.editor.action(ctx=>ctx.get(editorViewCtx));
  const hide=()=>{toolbar.hidden=true;selected=null;};
  const locate=cell=>{
    if(!cell||disposed)return null;
    const table=cell.closest('table.children'),row=cell.closest('tr');
    if(!table||!row||!root.contains(table))return null;
    const rowIndex=[...table.rows].indexOf(row);
    const colIndex=[...row.cells].indexOf(cell);
    if(rowIndex<0||colIndex<0)return null;
    const editor=view();
    let pos;
    try{pos=editor.posAtDOM(cell,0);}catch{return null;}
    if(!Number.isInteger(pos))return null;
    const $pos=editor.state.doc.resolve(pos);
    let tableDepth=-1;
    for(let depth=$pos.depth;depth>0;depth--){
      if($pos.node(depth).type.name==='table'){tableDepth=depth;break;}
    }
    if(tableDepth<0)return null;
    return {rowIndex,colIndex,tablePos:$pos.before(tableDepth)+1};
  };
  const choose=event=>{
    if(toolbar.contains(event.target))return;
    const cell=event.target.closest?.('.milkdown-table-block th,.milkdown-table-block td');
    const next=locate(cell);
    if(!next){hide();return;}
    selected=next;toolbar.hidden=false;
  };
  root.addEventListener('click',choose);

  const run=kind=>{
    const target=selected;if(!target||disposed)return;
    try{
      const result=crepe.editor.action(ctx=>{
        const commands=ctx.get(commandsCtx);
        if(kind==='add-row'||kind==='delete-row'){
          commands.call(selectRowCommand.key,{pos:target.tablePos,index:target.rowIndex});
          return kind==='add-row'
            ? commands.call(addRowAfterCommand.key)
            : commands.call(deleteSelectedCellsCommand.key);
        }
        commands.call(selectColCommand.key,{pos:target.tablePos,index:target.colIndex});
        return kind==='add-col'
          ? commands.call(addColAfterCommand.key)
          : commands.call(deleteSelectedCellsCommand.key);
      });
      if(result===false)throw Error('Table command was not applicable.');
      onStatus?.(
        kind==='add-row'?'Row added.':
        kind==='delete-row'?'Row deleted.':
        kind==='add-col'?'Column added.':'Column deleted.','info');
      if(kind.startsWith('delete-'))hide();
    }catch(error){onStatus?.('Table action failed: '+error.message,'error');}
  };
  toolbar.addEventListener('click',event=>{
    const button=event.target.closest?.('[data-table-action]');
    if(!button)return;
    event.preventDefault();event.stopPropagation();run(button.dataset.tableAction);
  });
  return ()=>{disposed=true;root.removeEventListener('click',choose);toolbar.remove();};
}

async function createVisualMarkdown(root, content, onChange, documentPath, onUploadStatus) {
  const pendingDiff = makePendingDiffPlugin();
  const crepe = new Crepe({
    root,
    defaultValue: content,
    features: {
      [Crepe.Feature.Latex]: false,
      // Block images rewrite ordinary alt text into a numeric aspect ratio.
      // Retain CommonMark image nodes and their exact alt/title semantics.
      [Crepe.Feature.ImageBlock]: false,
    },
  });
  crepe.editor.config(ctx => {
    ctx.update(inlineImageConfig.key, previous => ({
      ...previous,
      proxyDomURL: src => previewImageURL(src, documentPath),
      onUpload: async file => {
        try { return (await uploadImage(file, documentPath, onUploadStatus)).src; }
        catch (error) {
          onUploadStatus?.('Image upload failed: ' + error.message, 'error');
          throw error;
        }
      },
    }));
    ctx.update(uploadConfig.key, previous => ({
      ...previous,
      // Copied images from Paint or browsers may also have a text/html flavor.
      // Honor the attached file rather than ignoring the whole paste.
      enableHtmlFileUploader: true,
      uploader: async (files, schema) => {
        const allFiles = Array.from(files);
        const images = allFiles.filter(file => imageTypes[file.type]);
        if (!images.length) {
          if (allFiles.some(file => file.type.startsWith('image/'))) {
            onUploadStatus?.('Unsupported clipboard image. Use PNG, JPEG, WebP, GIF or BMP.', 'warn');
          }
          return [];
        }
        const image = schema.nodes.image;
        if (!image) throw new Error('Markdown image schema is unavailable');
        const nodes = [];
        for (const file of images) {
          try {
            const { src, alt } = await uploadImage(file, documentPath, onUploadStatus);
            const node = image.createAndFill({ src, alt, title: '' });
            if (!node) throw new Error('Cannot insert Markdown image');
            nodes.push(node);
          } catch (error) {
            onUploadStatus?.('Image paste failed: ' + error.message, 'error');
            throw error;
          }
        }
        onUploadStatus?.('Image pasted. Saving Markdown…', 'info');
        return nodes;
      },
    }));
  });
  crepe.editor.use(imageInlineComponent);
  crepe.editor.use(preserveUntitledImages);
  crepe.editor.use(pendingDiff.milkdown);
  crepe.on((listener) => {
    // Observe document mutations without serializing multi-megabyte Markdown on every keystroke.
    listener.updated((_ctx, nextDoc, previousDoc) => {
      if (!nextDoc?.eq || !nextDoc.eq(previousDoc)) onChange();
    });
  });
  await crepe.create();
  const pending = makePendingDiffController(crepe, pendingDiff.key);
  const unmountCrop = mountImageCrop(root, crepe, documentPath, onUploadStatus);
  const unmountTableToolbar = mountTableToolbar(root, crepe, onUploadStatus);
  return {
    getMarkdown() { return crepe.getMarkdown(); },
    setPendingDiff(markdown, hunks) { return pending.setPendingDiff(markdown, hunks); },
    clearPendingDiff() { return pending.clearPendingDiff(); },
    debugBlockMap() { return pending.debugBlockMap(); },
    sourceLineLocator() { return sourceLineLocator(crepe); },
    sourceBlockAtLine(line) { return sourceBlockAtLine(crepe, line); },
    destroy() { unmountTableToolbar(); unmountCrop(); return crepe.destroy(); },
    focus() { root.querySelector('[contenteditable="true"]')?.focus(); },
  };
}
window.LanternCrepe = { createVisualMarkdown };
