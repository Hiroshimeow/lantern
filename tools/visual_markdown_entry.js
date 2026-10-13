// Self-contained browser editor. No CDN, remote fonts, telemetry or AI providers.
import { Crepe } from '@milkdown/crepe';
import { editorViewCtx } from '@milkdown/kit/core';
import { $remark } from '@milkdown/kit/utils';
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

async function createVisualMarkdown(root, content, onChange, documentPath, onUploadStatus) {
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
  crepe.on((listener) => {
    // Observe document mutations without serializing multi-megabyte Markdown on every keystroke.
    listener.updated((_ctx, nextDoc, previousDoc) => {
      if (!nextDoc?.eq || !nextDoc.eq(previousDoc)) onChange();
    });
  });
  await crepe.create();
  const unmountCrop = mountImageCrop(root, crepe, documentPath, onUploadStatus);
  return {
    getMarkdown() { return crepe.getMarkdown(); },
    destroy() { unmountCrop(); return crepe.destroy(); },
    focus() { root.querySelector('[contenteditable="true"]')?.focus(); },
  };
}
window.LanternCrepe = { createVisualMarkdown };
