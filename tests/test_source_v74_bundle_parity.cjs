// Optional artifact check (no parser/tool installation): use the build's esbuild
// to reparse and canonicalize both bundles identically, including identifier
// minification, literal escaping, whitespace and manual-patch formatting.
// Run: node tests/test_source_v74_bundle_parity.cjs <original> <rebuilt>
const assert = require('node:assert/strict');
const fs = require('node:fs');
const crypto = require('node:crypto');
const {transformSync} = require('esbuild');
const [original, rebuilt] = process.argv.slice(2);
assert.ok(original && rebuilt, 'provide original and rebuilt source bundles');
function canonical(file) {
  return transformSync(fs.readFileSync(file, 'utf8'), {
    loader: 'js', minify: true, target: ['chrome114', 'firefox115', 'safari16'],
    legalComments: 'none',
  }).code;
}
const a = canonical(original), b = canonical(rebuilt);
if (a !== b) {
  let at = 0;
  while (at < Math.min(a.length, b.length) && a[at] === b[at]) at++;
  console.error({originalLength: a.length, rebuiltLength: b.length, firstDifference: at,
    original: a.slice(Math.max(0, at - 70), at + 120),
    rebuilt: b.slice(Math.max(0, at - 70), at + 120)});
}
assert.equal(a === b, true, 'entire canonical source bundles must match, not just patched excerpts');
console.log(JSON.stringify({canonicalBytes: Buffer.byteLength(a),
  sha256: crypto.createHash('sha256').update(a).digest('hex'),
  parity: 'entire parsed/minified token stream identical'}, null, 2));
