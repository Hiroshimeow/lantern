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

// Crop is a contextual image action inside Visual Edit, not a fourth document
// mode. Existing /api/upload and /api/md/save own file creation and versioning.
function mountImageCrop(root, crepe, documentPath, onStatus) {
  const toolbar = document.createElement('div');
  toolbar.className = 'md-image-crop-toolbar';
  toolbar.hidden = true;
  const cropButton = document.createElement('button');
  cropButton.type = 'button';
  cropButton.className = 'btn';
  cropButton.textContent = 'Crop image';
  toolbar.append(cropButton);
  root.prepend(toolbar);

  let selected = null;
  let dialog = null;
  let disposed = false;
  const editorView = () => crepe.editor.action(ctx => ctx.get(editorViewCtx));
  const supported = img => {
    try {
      const url = new URL(img.currentSrc);
      return img.complete && img.naturalWidth > 0 && img.naturalHeight > 0 &&
        url.origin === location.origin && /\.(png|jpe?g|webp|bmp)$/i.test(url.pathname);
    } catch { return false; }
  };
  const pickImage = img => {
    const view = editorView();
    let pos = view.posAtDOM(img.parentElement, 0);
    let node = view.state.doc.nodeAt(pos);
    if (node?.type.name !== 'image') {
      const {from, node: chosen} = view.state.selection;
      if (chosen?.type.name !== 'image') return null;
      pos = from;
      node = chosen;
    }
    return {pos, node, img};
  };
  const checkNode = target => {
    const view = editorView();
    const node = view.state.doc.nodeAt(target.pos);
    if (!node || !node.eq(target.node)) throw Error('Image changed; select it again.');
    return {view, node};
  };
  const hideToolbar = () => { toolbar.hidden = true; selected = null; };
  const onRootClick = event => {
    const img = event.target.closest?.('.milkdown-image-inline img');
    if (!img || !root.contains(img)) {
      if (!toolbar.contains(event.target)) hideToolbar();
      return;
    }
    requestAnimationFrame(() => {
      if (disposed) return;
      selected = supported(img) ? pickImage(img) : null;
      toolbar.hidden = !selected;
    });
  };
  root.addEventListener('click', onRootClick);

  async function openCrop(target) {
    checkNode(target);
    const img = target.img;
    if (!supported(img)) throw Error('Crop supports local PNG, JPEG, WebP and BMP images.');
    const modal = document.createElement('dialog');
    modal.className = 'md-image-crop-dialog';
    modal.setAttribute('aria-label', 'Crop image');
    const title = document.createElement('h2');
    title.textContent = 'Crop image';
    const hint = document.createElement('p');
    hint.textContent = 'Drag across the picture to select a crop. The original asset will not be changed.';
    const canvas = document.createElement('canvas');
    canvas.className = 'md-image-crop-canvas';
    canvas.setAttribute('aria-label', 'Drag to select crop');
    const scale = Math.min(840 / img.naturalWidth, 520 / img.naturalHeight,
      Math.max(1, 360 / Math.max(img.naturalWidth, img.naturalHeight)));
    canvas.width = Math.max(1, Math.round(img.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(img.naturalHeight * scale));
    const ctx = canvas.getContext('2d');
    if (!ctx) throw Error('Canvas is not available.');
    let bounds = {x: canvas.width * .1, y: canvas.height * .1,
      w: canvas.width * .8, h: canvas.height * .8};
    const paint = () => {
      const {x, y, w, h} = bounds;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      ctx.fillStyle = 'rgba(0,0,0,.5)';
      ctx.fillRect(0, 0, canvas.width, y);
      ctx.fillRect(0, y, x, h);
      ctx.fillRect(x + w, y, canvas.width - (x + w), h);
      ctx.fillRect(0, y + h, canvas.width, canvas.height - (y + h));
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 2;
      ctx.strokeRect(x + 1, y + 1, Math.max(0, w - 2), Math.max(0, h - 2));
    };
    paint();
    const point = e => {
      const box = canvas.getBoundingClientRect();
      return {
        x: Math.max(0, Math.min(canvas.width, (e.clientX - box.left) * canvas.width / box.width)),
        y: Math.max(0, Math.min(canvas.height, (e.clientY - box.top) * canvas.height / box.height)),
      };
    };
    let anchor = null;
    canvas.addEventListener('pointerdown', e => {
      if (e.button !== 0) return;
      anchor = point(e);
      canvas.setPointerCapture(e.pointerId);
      bounds = {x: anchor.x, y: anchor.y, w: 0, h: 0};
      paint();
    });
    canvas.addEventListener('pointermove', e => {
      if (!anchor) return;
      const end = point(e);
      bounds = {x: Math.min(anchor.x, end.x), y: Math.min(anchor.y, end.y),
        w: Math.abs(anchor.x - end.x), h: Math.abs(anchor.y - end.y)};
      paint();
    });
    canvas.addEventListener('pointerup', () => { anchor = null; });
    canvas.addEventListener('pointercancel', () => { anchor = null; });

    const actions = document.createElement('div');
    actions.className = 'md-image-crop-actions';
    const button = (label, className) => {
      const item = document.createElement('button');
      item.type = 'button'; item.textContent = label; item.className = className;
      actions.append(item);
      return item;
    };
    const cancel = button('Cancel', 'btn');
    const remove = button('Delete image', 'btn');
    const apply = button('Apply crop', 'btn primary');
    const finish = () => {
      if (dialog !== modal) return;
      modal.close(); modal.remove(); dialog = null; hideToolbar();
    };
    cancel.addEventListener('click', finish);
    modal.addEventListener('cancel', event => {
      event.preventDefault();
      if (!apply.disabled) finish();
    });
    remove.addEventListener('click', () => {
      try {
        const {view, node} = checkNode(target);
        view.dispatch(view.state.tr.delete(target.pos, target.pos + node.nodeSize));
        onStatus?.('Image removed from Markdown. Asset retained.', 'info');
        finish();
      } catch (error) { onStatus?.(error.message, 'error'); }
    });
    apply.addEventListener('click', async () => {
      if (bounds.w < 2 || bounds.h < 2) {
        onStatus?.('Select a larger crop area.', 'warn'); return;
      }
      apply.disabled = true;
      remove.disabled = true;
      cancel.disabled = true;
      try {
        checkNode(target);
        const x = Math.round(bounds.x * img.naturalWidth / canvas.width);
        const y = Math.round(bounds.y * img.naturalHeight / canvas.height);
        const w = Math.min(img.naturalWidth - x,
          Math.max(1, Math.round(bounds.w * img.naturalWidth / canvas.width)));
        const h = Math.min(img.naturalHeight - y,
          Math.max(1, Math.round(bounds.h * img.naturalHeight / canvas.height)));
        const output = document.createElement('canvas');
        output.width = w; output.height = h;
        output.getContext('2d').drawImage(img, x, y, w, h, 0, 0, w, h);
        const blob = await new Promise(resolve => output.toBlob(resolve, 'image/png'));
        if (!blob) throw Error('Unable to export cropped image.');
        const file = new File([blob], 'cropped.png', {type: 'image/png'});
        const image = await uploadImage(file, documentPath, onStatus, 'cropped');
        if (disposed) return;
        const {view, node} = checkNode(target);
        view.dispatch(view.state.tr.setNodeMarkup(target.pos, undefined, {
          ...node.attrs, src: image.src,
        }));
        finish();
        onStatus?.('Cropped image inserted. Saving Markdown…', 'info');
      } catch (error) {
        onStatus?.('Crop failed: ' + error.message, 'error');
      } finally {
        apply.disabled = false;
        remove.disabled = false;
        cancel.disabled = false;
      }
    });
    modal.append(title, hint, canvas, actions);
    document.body.append(modal);
    dialog = modal;
    modal.showModal();
  }

  cropButton.addEventListener('click', () => {
    if (!selected || dialog) return;
    void openCrop(selected).catch(error => onStatus?.('Crop unavailable: ' + error.message, 'error'));
  });
  return () => {
    disposed = true;
    root.removeEventListener('click', onRootClick);
    dialog?.close();
    dialog?.remove();
    dialog = null;
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
