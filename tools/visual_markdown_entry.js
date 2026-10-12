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

async function createVisualMarkdown(root, content, onChange, documentPath) {
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
      // Object URLs are ephemeral and must never be saved as Markdown links.
      onUpload: async () => { throw new Error('Link to an image already in the Lantern root.'); },
    }));
    // Crepe's default paste/drop uploader creates transient blob: URLs when
    // ImageBlock is disabled. Refuse unsaved attachments until a durable file
    // upload flow exists, rather than corrupting Markdown with broken links.
    ctx.update(uploadConfig.key, previous => ({
      ...previous,
      uploader: async () => [],
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
