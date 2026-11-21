import { build } from 'esbuild';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import crypto from 'node:crypto';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const vendor = path.join(root, 'static', 'vendor');
fs.mkdirSync(vendor, { recursive: true });

// Shared Cropper UI is an independent ES module loaded only when a user crops.
const imageCropOut = path.join(vendor, 'lantern-image-crop.min.js');
await build({
  entryPoints: [path.join(root, 'tools', 'image_crop_entry.js')],
  outfile: imageCropOut,
  bundle: true,
  platform: 'browser',
  format: 'esm',
  target: ['chrome114', 'firefox115', 'safari16'],
  minify: true,
  legalComments: 'external',
  sourcemap: false,
  logLevel: 'info',
});

// The block lexer runs off-thread so loading a 5 MiB document never blocks typing.
const worker = path.join(vendor, 'lantern-md-segment-worker.min.js');
await build({
  entryPoints: [path.join(root, 'tools', 'markdown_sections_indexer.mjs')],
  outfile: worker,
  bundle: true,
  platform: 'browser',
  format: 'iife',
  target: ['chrome114', 'firefox115', 'safari16'],
  minify: true,
  legalComments: 'external',
  sourcemap: false,
  logLevel: 'info',
});

const codeBlockOut = path.join(vendor, 'lantern-large-block.min.js');
await build({
  entryPoints: [path.join(root, 'tools', 'oversized_code_editor_entry.js')],
  outfile: codeBlockOut,
  bundle: true,
  platform: 'browser',
  format: 'iife',
  target: ['chrome114', 'firefox115', 'safari16'],
  minify: true,
  legalComments: 'external',
  sourcemap: false,
  logLevel: 'info',
});

// Source is an independent CodeMirror 6 bundle.
const sourceOut = path.join(vendor, 'lantern-source-editor.min.js');
await build({
  entryPoints: [path.join(root, 'tools', 'source_markdown_entry.js')],
  outfile: sourceOut,
  bundle: true,
  platform: 'browser',
  format: 'iife',
  target: ['chrome114', 'firefox115', 'safari16'],
  minify: true,
  legalComments: 'external',
  sourcemap: false,
  logLevel: 'info',
});

const artifactPaths = [
  imageCropOut, imageCropOut + '.LEGAL.txt',
  worker, worker + '.LEGAL.txt',
  codeBlockOut, codeBlockOut + '.LEGAL.txt',
  sourceOut, sourceOut + '.LEGAL.txt',
];
const artifacts = {};
for (const file of artifactPaths) {
  if (fs.existsSync(file)) {
    const buffer = fs.readFileSync(file);
    artifacts[path.basename(file)] = {
      bytes: buffer.length,
      sha256: crypto.createHash('sha256').update(buffer).digest('hex'),
    };
  }
}
const manifestPath = path.join(vendor, 'lantern-bundles.manifest.json');
fs.writeFileSync(manifestPath, JSON.stringify({
  dependencies: {
    codemirror: '6.0.2',
    '@codemirror/theme-one-dark': '6.1.3',
    esbuild: '0.28.2',
    'markdown-it': '14.3.1',
    cropperjs: '2.3.0',
  },
  artifacts,
}, null, 2) + '\n');
