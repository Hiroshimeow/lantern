import { build } from 'esbuild';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import crypto from 'node:crypto';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const vendor = path.join(root, 'static', 'vendor');
const out = path.join(vendor, 'lantern-crepe.min.js');
fs.mkdirSync(vendor, { recursive: true });
await build({
  entryPoints: [path.join(root, 'tools', 'visual_markdown_entry.js')],
  outfile: out,
  bundle: true,
  platform: 'browser',
  format: 'iife',
  target: ['chrome114', 'firefox115', 'safari16'],
  minify: true,
  // KaTeX is disabled in the editor. Do not vendor or inline its font binaries.
  external: ['*.woff', '*.woff2', '*.ttf'],
  legalComments: 'external',
  sourcemap: false,
  logLevel: 'info',
});
// Shared Cropper UI is an independent ES module loaded only when a user crops.
// The media viewer must never load the 2.7 MB Milkdown editor.
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
const codeBlockOut=path.join(vendor,'lantern-large-block.min.js');
await build({
  entryPoints:[path.join(root,'tools','oversized_code_editor_entry.js')],
  outfile:codeBlockOut,
  bundle:true,
  platform:'browser',
  format:'iife',
  target:['chrome114','firefox115','safari16'],
  minify:true,
  legalComments:'external',
  sourcemap:false,
  logLevel:'info',
});
const artifactPaths = [out, out.replace(/\.js$/, '.css'), out + '.LEGAL.txt',
  imageCropOut, imageCropOut + '.LEGAL.txt',
  worker, worker + '.LEGAL.txt', codeBlockOut, codeBlockOut+'.LEGAL.txt'];
const artifacts = {};
for (const file of artifactPaths) {
  if (fs.existsSync(file)) {
    const buffer = fs.readFileSync(file);
    artifacts[path.basename(file)] = { bytes: buffer.length, sha256: crypto.createHash('sha256').update(buffer).digest('hex') };
  }
}
fs.writeFileSync(path.join(vendor, 'lantern-crepe.manifest.json'), JSON.stringify({
  dependencies: {'@milkdown/crepe':'7.22.2', esbuild:'0.28.2', 'markdown-it':'14.3.1',cropperjs:'2.3.0'},
  artifacts,
}, null, 2) + '\n');
console.log('Lantern Crepe offline bundle:', artifacts);
