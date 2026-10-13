# Image Crop — implementation and verification (2026-10-13)

## Implementation
- One offline, lazy-loaded module: `tools/image_crop_entry.js`, built to `static/vendor/lantern-image-crop.min.js` with pinned Cropper.js 2.3.0.
- Used by Markdown Edit Visually and the full image viewer. Opening an image viewer does **not** load the Milkdown bundle.
- Four rectangular corner handles, movable selection, zoom/pan, reset, keyboard 1-pixel adjustment (Shift: 10 source pixels); enlarged touch targets on coarse pointers.
- The crop module owns only image UI, source pixels and encoding. The callers own persistence: Markdown creates a sibling `assets/` file and updates its versioned document; the image viewer saves a new sibling file and refreshes its listing. No source asset is overwritten or deleted.
- `/api/upload`: same-directory temporary file; flush and fsync; atomic no-clobber publication using `os.link` for ask/skip/rename, `os.replace` only for explicitly requested overwrite. On an unsupported filesystem, no-clobber uploads fail instead of falling back to overwrite. Incomplete temporary names are hidden and refused by HTTP.
- On Markdown 409, the new image may remain as an unused asset (no automatic deletion, as requested); original Markdown and concurrent edits remain intact.

## Tested acceptance (FJP, isolated loopback Edge, no live port 9999 interference)
- 23 Markdown Edge E2E: PASS (three modes, Mermaid, 4.9 MiB paged editor, image Crop and conflict).
- Shared viewer/format/upload targeted tests: PASS (EXIF 1–8, PNG alpha, WebP lossy/lossless/alpha, BMP, animated formats rejected, >20 MiB rejected, 409, 12 simultaneous same-name uploads, interrupted and incomplete uploads, temporary HTTP denial).
- Visual zoom/pan crop compared **byte-for-byte** to an expected 90x70 PNG pixel region: PASS.
- Twenty open/cancel cycles: no leftover crop modal DOM; simulated mobile 2x-DPR corner touch drag: PASS.
- Python-wide suite before last guarded follow-ups: 138 tests, PASS, 55 skipped; `npm ci` then offline build: PASS.

## Preliminary performance sample (FJP Edge, simple synthetic JPEG, one run)
| Input | Open crop (s) | Apply/Save As (s) | p95 animation frame (ms) | Slowest recorded frame (ms) |
| --- | ---: | ---: | ---: | ---: |
| 3840x2160 | 1.453 | 0.266 | 16.8 | 17.0 |
| 7680x4320 | 1.047 | 0.734 | 16.9 | 101.4 |
| 10000x5000 (50 MP) | 0.969 | 0.828 | 16.9 | 169.5 |

The benchmark is reproducible via `LANTERN_E2E=1 LANTERN_CROP_PERF=1` with `tests/test_image_crop_performance_e2e.py` (optional Pillow/Playwright). Numbers are indicative, not performance guarantees. Samples are highly compressible and don't represent noisy photographs. JS heap readings exclude native decoded-image, GPU and process working-set memory; **peak real memory and repeat-cycle native/GPU retention are not measured**.

## Limits
- Canvas re-encodes pixels and does not promise preservation of EXIF/ICC metadata, JPEG losslessness, or exact Display-P3 color fidelity.
- Static JPEG→JPEG, PNG→PNG, non-alpha WebP→WebP when supported, alpha WebP/BMP→PNG. Animated GIF/PNG/WebP, SVG and cross-origin sources are unsupported. Output is limited to 20 MiB; crop export up to 60 MP of pixel area.
- Mobile touch was checked in Chromium emulation; physical mobile browsers and Safari remain unverified. Some network filesystems cannot provide the required atomic no-clobber hard-link operation.
