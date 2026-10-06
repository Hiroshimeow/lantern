# T5 — Mermaid 11.17.2 dependency/advisory/license gate

Date: 2026-10-06
Status: **PASS for the Markdown implementation lane**. No product asset has been vendored yet.

## Deliberate pin

- Package: `mermaid@11.17.2`.
- npm integrity: `sha512-V6K3C8EBdEsPFZXSKMJe6ppQOENxuHARr9GvHX4hh47lAbhMRD9qf4oEK7LoaRQxULMa80/qt5gHO73aCleBBg==`.
- License: MIT.
- Candidate standalone browser bundle: `package/dist/mermaid.min.js`.
- Bundle size: 3,572,661 bytes.
- Bundle SHA-256: `581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8`.
- No literal dynamic `import(` was found in the candidate bundle.
- The source map shows the bundle is self-contained with bundled dependency sources; T7's blocked-network run remains the binding proof that no runtime fetch occurs.

The current npm latest checked during this review is `mermaid@12.1.0`. Its standalone `mermaid.min.js` is 5,493,176 bytes and its clean production audit still reports the same two low KaTeX-chain findings. Therefore 11.17.2 is an intentional smaller-bundle pin, not a claim that it is latest or vulnerability-free.

## Advisory result

A clean `mermaid@11.17.2` production tree reports:

- critical: 0
- high: 0
- moderate: 0
- low: 2

Both lows are one dependency chain:

- `mermaid -> katex@0.16.47`
- GHSA-238p-pmpm-9mq7 — existing prototype pollution can bypass KaTeX trust restrictions.
- npm affected range: `>=0.11.0 <0.18.2`.

Decision: **accepted as documented residual risk for this local preview lane**, under the reviewed nonce-only CSP, Mermaid `securityLevel:"strict"`, no `unsafe-eval`, and no KaTeX trust option. Re-audit when an applicable Mermaid release ships KaTeX >=0.18.2. This is not represented as “no vulnerability”.

## Review-called dependency reachability

Resolved 11.17.2 production tree and bundle source map were inspected.

### lodash-es

- `dagre-d3-es@7.0.14 -> lodash-es@4.18.1`.
- The selected `mermaid.min.js.map` contains **240** `lodash-es@4.18.1` source entries.
- Conclusion: lodash-es is runtime-reachable/present in the selected bundle.
- `npm audit` reported no advisory for the resolved `lodash-es@4.18.1`.

### Chevrotain

- `@mermaid-js/parser@1.2.1 -> @chevrotain/types@11.1.2`.
- No runtime `chevrotain` package is installed in the resolved production tree.
- The selected bundle source map contains **0** entries for `chevrotain`, `@chevrotain/types`, or `@mermaid-js/parser`.
- Conclusion: the reviewed Chevrotain concern is not runtime-reachable in this selected all-in-one bundle; only the type-only package exists in the npm dependency graph.

## License-notice gate

The production dependency tree contains 113 package/version rows. License metadata/files were enumerated. Three packages need manual normalization when generating the retained third-party notice:

- `khroma@2.1.0`: package.json omits `license`, but bundled `license` file is MIT.
- `fastdom@1.0.12`: package metadata says MIT; installed package has no top-level license file.
- `strictdom@1.0.1`: package metadata says MIT; installed package has no top-level license file.

Before committing the vendor asset, generate `static/vendor/mermaid-11.17.2.LICENSES.txt` from this resolved tree and include Mermaid's own MIT license.

## Runtime/offline gate

Static inspection finds one standalone browser bundle and no literal dynamic import. T7 must still run with Lantern reachable while every non-Lantern origin is blocked and must record zero extra/non-Lantern requests for the required seven-diagram matrix.

## Gate result

**T5: PASS.** T6 may begin only after T3/T4 are green, exactly as specified.

No Mermaid asset was added to the Lantern repository by this research step.
