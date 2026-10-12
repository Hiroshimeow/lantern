// Self-contained browser editor. No CDN, remote fonts, telemetry or AI providers.
import { Crepe } from '@milkdown/crepe';
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
async function uploadImage(file, documentPath, onStatus) {
  const suffix = imageTypes[file?.type];
  if (!suffix) throw new Error('Clipboard image must be PNG, JPEG, WebP, GIF, or BMP.');
  if (!file.size || file.size > 20 * 1024 * 1024) throw new Error('Image must be 1 B–20 MiB.');
  const directory = documentPath.split('/').slice(0, -1).join('/');
  const name = 'pasted-' + Date.now() + '-' + Math.random().toString(36).slice(2, 10) + '.' + suffix;
  const relative = 'assets/' + name;
  const url = '/api/upload?path=' + encodeURIComponent(directory) +
    '&name=' + encodeURIComponent(relative) + '&conflict=rename';
  onStatus?.('Uploading pasted image…', 'info');
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
  return {
    getMarkdown() { return crepe.getMarkdown(); },
    destroy() { return crepe.destroy(); },
    focus() { root.querySelector('[contenteditable="true"]')?.focus(); },
  };
}
window.LanternCrepe = { createVisualMarkdown };
