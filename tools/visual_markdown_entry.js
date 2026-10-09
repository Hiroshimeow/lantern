// Self-contained browser editor. No CDN, remote fonts, telemetry or AI providers.
import { Crepe } from '@milkdown/crepe';
import '@milkdown/crepe/theme/common/style.css';
import '@milkdown/crepe/theme/nord-dark.css';

async function createVisualMarkdown(root, content, onChange) {
  const crepe = new Crepe({
    root,
    defaultValue: content,
    features: {
      [Crepe.Feature.Latex]: false,
      [Crepe.Feature.ImageBlock]: false,
    },
  });
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
