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
const artifactPaths = [out, out.replace(/\.js$/, '.css'), out + '.LEGAL.txt'];
const artifacts = {};
for (const file of artifactPaths) {
  if (fs.existsSync(file)) {
    const buffer = fs.readFileSync(file);
    artifacts[path.basename(file)] = { bytes: buffer.length, sha256: crypto.createHash('sha256').update(buffer).digest('hex') };
  }
}
fs.writeFileSync(path.join(vendor, 'lantern-crepe.manifest.json'), JSON.stringify({
  dependencies: {'@milkdown/crepe':'7.22.2', esbuild:'0.28.2'},
  artifacts,
}, null, 2) + '\n');
console.log('Lantern Crepe offline bundle:', artifacts);
