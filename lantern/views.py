
from pathlib import Path

from .config import AppConfig
from .filesystem import FileService
from .media import MediaService

CSS = r"""
:root{color-scheme:dark;--bg:#090b10;--panel:#11141b;--panel2:#111827;--line:#374151;--text:#f8fafc;--muted:#cbd5e1;--accent:#68e37a;--accent2:#8db4ff;--danger:#ff5d5d;--warn:#ffbf63;--shadow:0 18px 48px rgba(0,0,0,.32)}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top left,#142017 0,#090b10 36%,#06070a 100%);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;overflow-x:hidden}a{color:inherit;text-decoration:none}button,input,textarea{font:inherit}.app{min-height:100vh;display:flex;flex-direction:column}.top{position:sticky;top:0;z-index:30;background:rgba(9,11,16,.82);backdrop-filter:blur(18px);border-bottom:1px solid rgba(255,255,255,.08)}.top-inner{display:grid;grid-template-columns:auto 1fr auto;gap:12px;align-items:center;padding:12px 14px}.brand{display:flex;align-items:center;gap:10px;min-width:0}.logo{width:36px;height:36px;border-radius:14px;background:linear-gradient(135deg,#61ff75,#8bb6ff);display:grid;place-items:center;color:#061007;font-weight:900;box-shadow:0 10px 30px rgba(104,227,122,.2)}.brand-title{font-weight:850;white-space:nowrap}.brand-sub{color:var(--muted);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:36vw}.search{min-width:140px}.search input{width:100%;height:40px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.05);color:var(--text);padding:0 14px;outline:none}.search input:focus{border-color:rgba(104,227,122,.75);box-shadow:0 0 0 4px rgba(104,227,122,.1)}.actions{display:flex;gap:8px;align-items:center;justify-content:flex-end;flex-wrap:wrap}.btn{height:38px;padding:0 13px;border:1px solid rgba(255,255,255,.1);border-radius:13px;background:var(--panel2);color:var(--text);cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:7px;font-weight:750;transition:.12s}.btn:hover{transform:translateY(-1px);border-color:rgba(255,255,255,.2);background:#1b2230}.btn:active{transform:translateY(0)}.btn.primary{background:linear-gradient(135deg,#54ee69,#7eaaff);color:#061007;border:0}.btn.danger{background:#28171a;color:#ffd6d6;border-color:#653238}.btn.warn{background:#2a2111;color:#ffe2b3;border-color:#604819}.btn.ghost{background:transparent}.btn.small{height:31px;padding:0 10px;border-radius:10px;font-size:12px}.select{height:31px;border:1px solid rgba(255,255,255,.18);border-radius:10px;background:#111827;color:#f8fafc;padding:0 10px;font-weight:700;outline:none;color-scheme:dark}.select.compact{max-width:105px}.checkline{height:31px;display:inline-flex;align-items:center;gap:6px;border:1px solid rgba(255,255,255,.1);border-radius:10px;background:var(--panel2);padding:0 10px;font-weight:700;font-size:12px;color:var(--text);user-select:none}.checkline input{accent-color:var(--accent)}.crumbs{display:flex;gap:7px;align-items:center;overflow:auto;padding:0 14px 12px;color:var(--muted);white-space:nowrap}.crumbs a{color:var(--text);background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);padding:5px 9px;border-radius:10px}.crumbs span{color:#596272}.notice{margin:14px 14px 0;padding:10px 12px;border:1px solid rgba(255,255,255,.08);border-radius:16px;background:rgba(255,255,255,.04);color:var(--muted);display:flex;justify-content:space-between;gap:10px;align-items:center}.notice b{color:var(--text)}.main{padding:14px;display:flex;flex-direction:column;gap:12px}.toolbar{display:flex;align-items:center;gap:9px;flex-wrap:wrap}.toolbar .grow{flex:1}.view-toggle{display:flex;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:3px}.view-toggle button{border:0;background:transparent;color:var(--muted);height:30px;padding:0 10px;border-radius:10px;cursor:pointer}.view-toggle button.active{background:#242b38;color:#fff}.dropzone{border:1px dashed rgba(255,255,255,.14);border-radius:20px;background:rgba(255,255,255,.035);min-height:55vh;padding:12px;transition:.12s}.dropzone.drag{border-color:var(--accent);background:rgba(104,227,122,.08)}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}.grid.list{display:flex;flex-direction:column}.card{position:relative;border:1px solid rgba(255,255,255,.08);border-radius:18px;background:rgba(17,20,27,.9);overflow:hidden;box-shadow:0 8px 24px rgba(0,0,0,.14);transition:.1s;min-width:0}.card:hover{transform:translateY(-2px);border-color:rgba(255,255,255,.18)}.card.selected{outline:2px solid var(--accent);outline-offset:0}.card-main{display:block;cursor:pointer}.grid:not(.list) .thumbwrap{height:128px;display:grid;place-items:center;background:#080a0e;position:relative}.thumb{width:100%;height:100%;object-fit:cover;display:block}.fileicon{font-size:42px;filter:drop-shadow(0 12px 24px rgba(0,0,0,.25))}.meta{padding:10px;min-width:0}.name{font-weight:760;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.sub{margin-top:4px;color:var(--muted);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.badge{position:absolute;top:8px;right:8px;background:rgba(0,0,0,.65);border:1px solid rgba(255,255,255,.12);color:#fff;border-radius:999px;font-size:11px;padding:3px 7px;font-weight:800}.check{position:absolute;top:8px;left:8px;width:28px;height:28px;border-radius:10px;border:1px solid rgba(255,255,255,.2);background:rgba(0,0,0,.45);z-index:4;display:grid;place-items:center;cursor:pointer}.selected .check{background:var(--accent);color:#061007;border-color:var(--accent)}.selected .check:after{content:'✓';font-weight:900}.grid.list .card{display:grid;grid-template-columns:44px 1fr auto;align-items:center;border-radius:14px}.grid.list .thumbwrap{height:44px;display:grid;place-items:center;background:#10141c}.grid.list .thumb{width:44px;height:44px}.grid.list .fileicon{font-size:24px}.grid.list .meta{padding:8px 10px}.grid.list .badge{position:static;margin-right:10px}.grid.list .check{top:8px;left:8px;width:24px;height:24px}.empty{height:45vh;display:grid;place-items:center;color:var(--muted);text-align:center}.loader{grid-column:1/-1;padding:18px;text-align:center;color:var(--muted)}.skeleton{height:190px;border-radius:18px;background:linear-gradient(90deg,rgba(255,255,255,.04),rgba(255,255,255,.08),rgba(255,255,255,.04));background-size:200% 100%;animation:shimmer 1.2s infinite}@keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}.modal{position:fixed;inset:0;background:rgba(0,0,0,.88);z-index:100;display:none;align-items:center;justify-content:center;padding:12px}.modal.show{display:flex}.modal-box{width:min(1200px,98vw);max-height:96vh;background:#0c0f15;border:1px solid rgba(255,255,255,.12);border-radius:22px;box-shadow:var(--shadow);overflow:hidden;display:flex;flex-direction:column}.modal-head{height:54px;display:flex;align-items:center;gap:10px;justify-content:space-between;padding:0 12px;border-bottom:1px solid rgba(255,255,255,.08)}.modal-title{font-weight:800;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.modal-body{display:grid;place-items:center;min-height:40vh;overflow:auto;background:#050608}.modal-body img,.modal-body video{max-width:100%;max-height:calc(96vh - 56px);background:#000}.modal-body audio{width:min(760px,92vw)}.editor{min-height:calc(100vh - 1px);display:flex;flex-direction:column}.editorbar{position:sticky;top:0;z-index:10;display:flex;gap:8px;align-items:center;padding:10px;background:#0c0f15;border-bottom:1px solid rgba(255,255,255,.08)}.editorbar .title{font-weight:800;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.editorbar .grow{flex:1}.editarea{flex:1;width:100%;min-height:70vh;background:#07090d;color:#f5f7fb;border:0;outline:0;padding:16px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:14px;line-height:1.55;resize:none}.toast{position:fixed;right:14px;bottom:14px;z-index:200;display:flex;flex-direction:column;gap:8px}.toast div{background:#111823;border:1px solid rgba(255,255,255,.12);border-radius:14px;padding:10px 12px;box-shadow:var(--shadow);color:#fff}.progress{height:8px;background:rgba(255,255,255,.08);border-radius:999px;overflow:hidden;min-width:160px}.progress span{display:block;height:100%;width:0;background:linear-gradient(90deg,#61ff75,#8bb6ff)}.hidden{display:none!important}@media(max-width:760px){.top-inner{grid-template-columns:1fr;gap:7px;padding:8px 10px}.brand{gap:8px}.logo{width:32px;height:32px;border-radius:11px}.brand-sub{max-width:72vw;font-size:11px}.search input{height:36px;border-radius:11px}.top-inner>.actions{justify-content:flex-start;flex-wrap:nowrap;overflow-x:auto;padding-bottom:2px;scrollbar-width:none}.top-inner>.actions::-webkit-scrollbar{display:none}.top-inner>.actions>.btn{flex:0 0 auto;height:34px;padding:0 10px;border-radius:10px}.main{padding:8px;gap:8px}.toolbar{gap:6px;flex-wrap:nowrap;overflow-x:auto;padding-bottom:2px;scrollbar-width:none}.toolbar::-webkit-scrollbar{display:none}.toolbar>*{flex:0 0 auto}.toolbar .grow{display:none}.grid{grid-template-columns:repeat(auto-fill,minmax(120px,1fr))}.grid:not(.list) .thumbwrap{height:108px}.btn .label{display:none}}




/* --- GPU/VRAM Telemetry Pill & Grid Icon Aspect Fix + Performance --- */
.sys-telemetry-pill{height:34px;padding:0 11px;border:1px solid rgba(104,227,122,.28);border-radius:11px;background:rgba(13,20,30,.92);color:#e2f1ff;font-size:11.5px;font-weight:750;display:inline-flex;align-items:center;gap:7px;cursor:pointer;user-select:none;white-space:nowrap;box-shadow:inset 0 1px 0 rgba(255,255,255,.06)}
.sys-telemetry-pill:hover{border-color:rgba(104,227,122,.6);background:#152234}
.sys-vram-bar{width:38px;height:6px;border-radius:999px;background:rgba(255,255,255,.12);overflow:hidden;display:inline-block;vertical-align:middle}
.sys-vram-fill{display:block;height:100%;background:linear-gradient(90deg,#54ee69,#7eaaff);transition:width .25s ease}
.sys-vram-fill.warn{background:linear-gradient(90deg,#fbbf24,#f59e0b)}
.sys-vram-fill.danger{background:linear-gradient(90deg,#f87171,#ef4444)}
.grid{align-items:start!important;grid-template-columns:repeat(auto-fill,minmax(140px,1fr))!important}
.grid:not(.list) .card{min-height:0!important;height:auto!important;align-self:start!important;content-visibility:auto;contain-intrinsic-size:158px}
.grid:not(.list) .card-main{height:auto!important;display:flex;flex-direction:column}
.grid:not(.list) .thumbwrap{height:98px!important;flex:0 0 98px!important;max-height:98px!important}
.grid:not(.list) .fileicon{font-size:32px!important;line-height:1!important;display:inline-flex;align-items:center;justify-content:center;width:40px;height:40px}
.grid:not(.list) .name{display:-webkit-box!important;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden!important;max-height:2.45em;line-height:1.22!important;word-break:break-word}

/* --- recursive search selector --- */
.search{display:flex;align-items:center;min-width:220px}
.search-depth{height:40px;max-width:86px;border:1px solid var(--line);border-right:0;border-radius:14px 0 0 14px;background:#111827;color:#f8fafc;padding:0 8px;outline:none;font-weight:800;cursor:pointer;color-scheme:dark}
.search input{border-radius:0 14px 14px 0!important}
.search-depth option,.select option{background:#111827;color:#f8fafc}
.search-depth:focus,.search input:focus{border-color:rgba(104,227,122,.75);box-shadow:0 0 0 4px rgba(104,227,122,.1)}
@media(max-width:760px){.search{min-width:0}.search-depth{max-width:78px;padding:0 6px}}
/* --- media viewer / video player mode --- */
.modal.media-video .modal-box{width:min(1320px,98vw)}
.modal.media-video .modal-body{background:#000}
.modal-stage{position:relative;min-height:40vh;background:#050608}.modal-body{position:relative;touch-action:pan-y;overscroll-behavior:contain}
.modal-title-wrap{min-width:0;display:flex;flex-direction:column;gap:2px}.modal-meta{color:var(--muted);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.modal-head .actions{flex-wrap:nowrap}.modal-head .btn:disabled,.modal-nav:disabled{opacity:.35;cursor:default;transform:none}.modal-nav{position:absolute;top:50%;transform:translateY(-50%);z-index:3;width:46px;height:70px;border:1px solid rgba(255,255,255,.16);border-radius:16px;background:rgba(0,0,0,.45);color:#fff;font-size:34px;font-weight:900;display:grid;place-items:center;cursor:pointer;backdrop-filter:blur(8px)}.modal-nav:hover:not(:disabled){background:rgba(255,255,255,.12)}.modal-prev{left:12px}.modal-next{right:12px}.modal-body img{user-select:none;-webkit-user-drag:none}.modal-body video{width:min(1280px,100%);height:auto}.media-hint{position:absolute;left:50%;bottom:12px;transform:translateX(-50%);background:rgba(0,0,0,.55);border:1px solid rgba(255,255,255,.12);border-radius:999px;padding:5px 10px;color:var(--muted);font-size:12px;pointer-events:none}.modal.media-video .media-hint{display:none}@media(max-width:760px){.modal{padding:0}.modal-box{width:100vw;height:100dvh;max-height:none;border-radius:0;border-left:0;border-right:0}.modal-head{height:auto;min-height:54px}.modal-body{min-height:calc(100dvh - 54px)}.modal-body img,.modal-body video{max-height:calc(100dvh - 56px)}.modal-nav{display:none}.modal-meta{font-size:11px}.modal-head .btn.small{height:30px;padding:0 9px}}

.video-wrap{width:100%;display:flex;flex-direction:column;align-items:center;background:#000}.video-wrap video{width:100%;max-height:calc(96vh - 150px);background:#000}.video-panel{width:100%;padding:10px 12px;background:#080b10;border-top:1px solid rgba(255,255,255,.08);color:var(--muted);font-size:12px;display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:7px}.video-panel b{color:var(--text)}.video-panel .wide{grid-column:1/-1}.video-panel .video-actions{display:flex;gap:7px;flex-wrap:wrap}.video-panel .chip{display:inline-flex;align-items:center;min-height:26px;padding:4px 8px;border:1px solid rgba(255,255,255,.12);border-radius:999px;background:#111827;color:#f8fafc;text-decoration:none;font-weight:750}

/* --- vNext stability patch: thumbnail/folder/upload styles --- */
body.thumb-contain .thumb,
body.thumb-contain .folder-mosaic img{object-fit:contain;background:#000}
body.thumb-cover .thumb,
body.thumb-cover .folder-mosaic img{object-fit:cover;background:#000}
.thumbwrap{overflow:hidden}
.grid:not(.list) .card{min-height:190px}
.grid:not(.list) .card-main{height:100%;display:flex;flex-direction:column}
.grid:not(.list) .thumbwrap{flex:0 0 128px}
.grid:not(.list) .meta{background:rgba(17,20,27,.92);border-top:1px solid rgba(255,255,255,.04)}
.folder-mosaic{width:100%;height:100%;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:repeat(2,minmax(0,1fr));gap:1px;background:#050608;overflow:hidden}
.folder-mosaic.empty{display:grid;grid-template-columns:1fr;grid-template-rows:1fr;place-items:center;background:#080a0e}
.folder-mosaic.empty .fileicon{font-size:46px;opacity:.95}
.folder-mosaic .cell{min-width:0;min-height:0;display:grid;place-items:center;background:#000;overflow:hidden;transform:translateZ(0)}
.folder-mosaic .cell img{width:100%;height:100%;display:block;object-fit:contain;background:#000;will-change:opacity,transform}
.folder-mosaic.none .cell img{animation:none}
.folder-mosaic.fade .cell img{animation:fpFade .22s ease-out both}
.folder-mosaic.slide .cell img{animation:fpSlide .24s ease-out both}
.folder-mosaic.flip .cell img{animation:fpFlip .26s ease-out both;backface-visibility:hidden}
@keyframes fpFade{from{opacity:.35}to{opacity:1}}
@keyframes fpSlide{from{opacity:.55;transform:translateY(6px)}to{opacity:1;transform:none}}
@keyframes fpFlip{from{opacity:.4;transform:rotateY(80deg)}to{opacity:1;transform:rotateY(0)}}
@media (prefers-reduced-motion:reduce){.folder-mosaic .cell img,.btn,.card,.skeleton{animation:none!important;transition:none!important}}
.upload-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.72);z-index:110;display:none;align-items:center;justify-content:center;padding:14px;backdrop-filter:blur(8px)}
.upload-backdrop.show{display:flex}
.upload-box{width:min(900px,96vw);max-height:92vh;background:#0d1118;border:1px solid rgba(255,255,255,.12);border-radius:22px;box-shadow:var(--shadow);display:flex;flex-direction:column;overflow:hidden}
.upload-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:14px;border-bottom:1px solid rgba(255,255,255,.08)}
.upload-title{font-weight:850;font-size:16px}.upload-body{padding:14px;overflow:auto;display:flex;flex-direction:column;gap:12px}.upload-drop{min-height:190px;border:2px dashed rgba(255,255,255,.16);border-radius:20px;background:rgba(255,255,255,.035);display:grid;place-items:center;text-align:center;color:var(--muted);cursor:pointer;transition:.12s}.upload-drop:hover,.upload-drop.drag{border-color:var(--accent);background:rgba(104,227,122,.08);color:var(--text)}.upload-plus{font-size:52px;line-height:1;color:var(--accent);font-weight:900}.upload-options{display:flex;gap:9px;align-items:center;flex-wrap:wrap}.upload-queue{border:1px solid rgba(255,255,255,.08);border-radius:16px;overflow:auto;max-height:260px;background:#080b10}.upload-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center;padding:8px 10px;border-bottom:1px solid rgba(255,255,255,.055);font-size:12px}.upload-row:last-child{border-bottom:0}.upload-path{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.upload-state{color:var(--muted);white-space:nowrap}.upload-state.ok{color:var(--accent)}.upload-state.err{color:var(--danger)}.upload-foot{display:flex;gap:10px;align-items:center;padding:12px 14px;border-top:1px solid rgba(255,255,255,.08);flex-wrap:wrap}.upload-summary{color:var(--muted);font-size:12px;min-width:160px}.upload-progress{height:8px;background:rgba(255,255,255,.08);border-radius:999px;overflow:hidden;flex:1;min-width:180px}.upload-progress span{display:block;height:100%;width:0;background:linear-gradient(90deg,#61ff75,#8bb6ff)}
.grid.list .folder-mosaic{width:44px;height:44px}.grid.list .folder-mosaic.empty .fileicon{font-size:24px}.grid.list .card-main{display:contents}.grid.list .meta{border-top:0;background:transparent}
.ctx-menu{position:fixed;z-index:230;min-width:190px;padding:6px;border:1px solid rgba(255,255,255,.14);border-radius:14px;background:#0d121b;box-shadow:0 18px 54px rgba(0,0,0,.5);display:flex;flex-direction:column;gap:2px}.ctx-menu.hidden{display:none}.ctx-menu button{height:32px;border:0;border-radius:9px;background:transparent;color:var(--text);display:flex;align-items:center;gap:8px;padding:0 10px;text-align:left;cursor:pointer;font-weight:720}.ctx-menu button:hover{background:#1a2230}.ctx-menu button.danger{color:#ffd2d2}.ctx-menu button.hidden{display:none}

/* compact grid + Windows-like details list with preview pane */
.browser-area{display:block}.side-preview{display:none}.grid{grid-template-columns:repeat(auto-fill,minmax(126px,1fr));gap:10px}.dropzone{padding:10px;border-radius:18px}.list-head{display:none}.list-size,.list-mtime,.list-kind{display:none}.grid:not(.list) .card{border-radius:15px;min-height:176px}.grid:not(.list) .thumbwrap{height:112px;flex:0 0 112px}.grid:not(.list) .meta{padding:8px 9px}.grid:not(.list) .fileicon{font-size:36px}.grid:not(.list) .name{font-size:13px;white-space:normal;word-break:break-word;overflow:visible;text-overflow:clip;line-height:1.2}.grid:not(.list) .sub{font-size:11px}.grid:not(.list) .check{width:25px;height:25px;border-radius:9px;top:7px;left:7px}.grid:not(.list) .badge{top:7px;right:7px;font-size:10px;padding:2px 6px}
.view-list .browser-area{display:grid;grid-template-columns:minmax(420px,1fr) minmax(340px,.9fr);gap:12px;align-items:start}.view-list .side-preview{display:flex;position:sticky;top:118px;min-height:55vh;max-height:calc(100vh - 132px);border:1px solid rgba(255,255,255,.1);border-radius:16px;background:#0b1018;overflow:hidden;flex-direction:column}.side-title{padding:11px 13px;border-bottom:1px solid rgba(255,255,255,.08);font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.side-body{flex:1;min-height:0;display:grid;place-items:center;overflow:auto;background:#05070b}.side-empty{margin:auto;color:var(--muted);text-align:center;padding:24px}.side-media{max-width:100%;max-height:100%;object-fit:contain}.side-audio{width:92%;align-self:center}.side-frame{width:100%;height:100%;border:0;background:#080a0f}.side-text{width:100%;height:100%;margin:0;padding:14px;white-space:pre-wrap;word-break:break-word;color:#e8eef8;font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.grid.list{gap:2px;border-radius:12px;background:#0d1118;border-style:solid}.grid.list .list-head{display:grid;grid-template-columns:30px 42px minmax(160px,1fr) 142px 82px 96px;gap:9px;align-items:center;min-height:34px;padding:0 10px;color:#b5c4d7;font-size:12px;border-bottom:1px solid rgba(255,255,255,.12);position:sticky;top:0;z-index:3;background:#10141b}.grid.list .list-head button{border:0;background:transparent;color:inherit;text-align:left;font:inherit;font-weight:700;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.grid.list .list-head button:hover{color:#fff}.grid.list .list-head button:nth-child(1){grid-column:3}.grid.list .list-head button:nth-child(2){grid-column:4}.grid.list .list-head button:nth-child(3){grid-column:5}.grid.list .list-head button:nth-child(4){grid-column:6;text-align:right}.grid.list .card{display:grid;grid-template-columns:30px 42px minmax(160px,1fr) 142px 82px 96px;gap:9px;align-items:center;min-height:46px;padding:3px 10px;border-radius:0;background:transparent;border-left:0;border-right:0;border-top:0;box-shadow:none;overflow:visible}.grid.list .card:hover{transform:none;background:rgba(255,255,255,.055);border-color:rgba(255,255,255,.12)}.grid.list .card.selected{outline:0;box-shadow:inset 3px 0 0 var(--accent);background:rgba(104,227,122,.08)}.grid.list .check{position:static;grid-column:1;grid-row:1;width:22px;height:22px;border-radius:7px;background:rgba(255,255,255,.045);justify-self:center}.grid.list .card-main{display:contents}.grid.list .thumbwrap{grid-column:2;grid-row:1;width:34px;height:34px;border-radius:8px;display:grid;place-items:center;background:#0b1018}.grid.list .thumb{width:34px;height:34px;border-radius:8px}.grid.list .folder-mosaic{grid-column:2;grid-row:1;width:34px;height:34px;border-radius:8px}.grid.list .folder-mosaic.empty .fileicon,.grid.list .fileicon{font-size:19px}.grid.list .meta{grid-column:3;grid-row:1;min-width:0;padding:0;background:transparent;border-top:0}.grid.list .name{font-size:13px;font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.grid.list .sub{display:none}.grid.list .list-size,.grid.list .list-mtime,.grid.list .list-kind{display:block;color:var(--muted);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.grid.list .list-mtime{grid-column:4;grid-row:1}.grid.list .list-kind{grid-column:5;grid-row:1}.grid.list .list-size{grid-column:6;grid-row:1;text-align:right}.grid.list .badge{display:none}.grid.list .skeleton{height:46px;border-radius:8px}.grid.list .loader{border-top:1px solid rgba(255,255,255,.08)}
@media(max-width:900px){.view-list .browser-area{grid-template-columns:1fr}.view-list .side-preview{position:static;min-height:280px;max-height:55vh}.grid.list .list-head,.grid.list .card{grid-template-columns:28px 38px minmax(0,1fr) 78px}.grid.list .list-head button:nth-child(1){grid-column:3}.grid.list .list-head button:nth-child(4){grid-column:4}.grid.list .list-head button:nth-child(2),.grid.list .list-head button:nth-child(3),.grid.list .list-mtime,.grid.list .list-kind{display:none}.grid.list .thumbwrap,.grid.list .thumb,.grid.list .folder-mosaic{width:34px;height:34px}.grid.list .list-size{grid-column:4}}
/* preview pane mode + final thumbnail/check overrides */
.view-list:not(.preview-pane) .browser-area{display:block}.view-list:not(.preview-pane) .side-preview{display:none}.preview-pane .browser-area{display:grid;grid-template-columns:minmax(420px,1fr) minmax(360px,.85fr);gap:12px;align-items:start}.preview-pane .side-preview{display:flex;position:sticky;top:118px;min-height:62vh;height:calc(100vh - 132px);max-height:calc(100vh - 132px);border:1px solid rgba(255,255,255,.1);border-radius:16px;background:#0b1018;overflow:hidden;flex-direction:column}.side-title{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center}.side-title-text{min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.side-nav{display:inline-flex;gap:5px}.side-nav button{width:28px;height:26px;border:1px solid rgba(255,255,255,.12);border-radius:8px;background:#151c28;color:#f8fafc;cursor:pointer;font-weight:900}.side-nav button:hover{background:#243044}.side-body{position:relative;overflow:hidden;display:block;background:#000}.side-content{width:100%;height:100%;display:grid;place-items:center;overflow:hidden}.side-media{width:auto!important;height:auto!important;max-width:100%!important;max-height:100%!important;object-fit:contain!important;background:#000}.side-frame{width:100%;height:100%;border:0;background:#080a0f}.side-frame,.side-text{overflow:auto}.side-text{display:block}.preview-pane .side-preview{height:calc(100dvh - 132px)!important;max-height:calc(100dvh - 132px)!important;overflow:hidden!important}.side-body{flex:1!important;min-height:0!important;position:relative!important;overflow:hidden!important;display:block!important}.side-content{position:absolute!important;inset:0!important;width:auto!important;height:auto!important;display:grid!important;place-items:center!important;overflow:hidden!important}.side-content.doc,.side-content.text{display:block!important;overflow:auto!important}.side-fit-bg{position:absolute!important;inset:0!important;background-color:#000!important;background-repeat:no-repeat!important;background-position:center center!important;background-size:contain!important}.side-video{width:100%!important;height:100%!important;max-width:100%!important;max-height:100%!important;object-fit:contain!important;display:block!important;background:#000}.side-frame{width:100%!important;height:100%!important}.side-text{min-height:100%;width:100%;height:auto}.side-arrow{position:absolute;top:50%;transform:translateY(-50%);z-index:5;width:42px;height:58px;border:1px solid rgba(255,255,255,.16);border-radius:14px;background:rgba(8,12,18,.58);color:#fff;font-size:34px;font-weight:900;cursor:pointer;opacity:0;transition:.12s}.side-body:hover .side-arrow{opacity:1}.side-arrow:hover{background:rgba(24,32,44,.88)}.side-prev{left:10px}.side-next{right:10px}.side-audio{width:92%;align-self:center}.grid:not(.list) .check{z-index:12;pointer-events:auto}.grid:not(.list) .check:hover,.grid.list .check:hover{border-color:var(--accent);box-shadow:0 0 0 3px rgba(104,227,122,.13)}.card.selected .check{background:var(--accent)!important;color:#061007!important;border-color:var(--accent)!important}.card.selected .check:after{content:'✓';font-weight:950}.btn.active,#previewPaneBtn.active{background:#243044;border-color:rgba(104,227,122,.45);color:#fff}body.thumb-contain .grid:not(.list) .thumb,body.thumb-contain .grid:not(.list) .folder-mosaic img{object-fit:contain!important;background:#000!important}body.thumb-cover .grid:not(.list) .thumb,body.thumb-cover .grid:not(.list) .folder-mosaic img{object-fit:cover!important;background:#000!important}@media(max-width:900px){.preview-pane .browser-area{grid-template-columns:1fr}.preview-pane .side-preview{position:static;height:55vh;min-height:300px;max-height:55vh}}

.download-choice-backdrop{position:fixed;inset:0;z-index:240;display:flex;align-items:center;justify-content:center;padding:16px;background:rgba(0,0,0,.72);backdrop-filter:blur(8px)}.download-choice-box{width:min(430px,94vw);background:#0d1118;border:1px solid rgba(255,255,255,.14);border-radius:20px;box-shadow:var(--shadow);padding:16px;display:flex;flex-direction:column;gap:12px}.download-choice-title{font-weight:850;font-size:16px}.download-choice-desc{color:var(--muted);line-height:1.45}.download-choice-actions{display:flex;gap:9px;justify-content:flex-end;flex-wrap:wrap}.side-video-fit{position:absolute!important;inset:0!important;display:grid!important;place-items:center!important;background:#000!important;overflow:hidden!important}.side-video-fit video,.side-video{width:100%!important;height:100%!important;max-width:100%!important;max-height:100%!important;object-fit:contain!important;object-position:center center!important;display:block!important;background:#000!important}


"""

JS = r"""
const $ = (s, r=document) => r.querySelector(s);
const $$ = (s, r=document) => Array.from(r.querySelectorAll(s));
const defaults = window.APP?.defaults || {};
const prefKey = k => 'lanDrive:' + k;
function pref(k, fallback){ const v = localStorage.getItem(prefKey(k)); return v === null ? fallback : v; }
const state = {
  selected:new Set(),
  view:pref('view', defaults.default_view || 'grid'),
  sort:pref('sort', defaults.default_sort || 'name-asc'),
  items:[], offset:0,
  limit:Number(pref('page_limit', defaults.page_limit || 220)),
  foldersFirst:String(pref('folders_first', defaults.folders_first === false ? 'false' : 'true')) !== 'false',
  recursiveDepth:pref('recursive_depth', '0'),
  thumbFit:pref('thumb_fit', defaults.thumb_fit || 'contain'),
  folderPreview:String(pref('folder_preview_enabled', defaults.folder_preview_enabled === false ? 'false' : 'true')) !== 'false',
  previewAnimation:pref('folder_preview_animation', defaults.folder_preview_animation || 'fade'),
  uploadConflict:pref('upload_conflict', defaults.upload_conflict || 'ask'),
  uploadParallel:Number(pref('upload_parallel', defaults.upload_parallel || 3)),
  uploadAutoStart:String(pref('upload_auto_start', defaults.upload_auto_start ? 'true' : 'false')) === 'true',
  pluginEnabled:!!(window.APP?.plugin?.enabled),
  previewPane:String(pref('preview_pane_enabled','true')) !== 'false',
  hasMore:true, loading:false, searchTimer:null,
  listPreview:null, dragSelecting:false, dragMode:null, dragCandidate:null, suppressClick:false, lastListClick:0
};
document.body.classList.add('thumb-'+(state.thumbFit==='cover'?'cover':'contain'));
const grid=$('#grid'), q=$('#q'), toastBox=$('#toast'), sidePreview=$('#sidePreview'), browserArea=$('#browserArea');
const emptyHTML='<div class="empty"><div><div style="font-size:42px">🫙</div><p>Không có mục phù hợp.</p><p>Kéo file/folder vào đây hoặc bấm Upload.</p></div></div>';
function toast(msg){ if(!toastBox){console.log(msg);return} const el=document.createElement('div');el.textContent=msg;toastBox.appendChild(el);setTimeout(()=>el.remove(),3200) }
function enc(s){return encodeURIComponent(s).replace(/%2F/g,'/')}
function currentPath(){return window.APP?.currentPath||''}
function selectedArray(){return Array.from(state.selected)}
function cachePrefix(){return 'lanDrive:list:'+location.pathname+':'}
function cacheKey(){return cachePrefix()+state.sort+':'+state.limit+':'+state.recursiveDepth+':'+String(state.foldersFirst)+':'+(q?.value||'')}
function scrollKey(){return 'lanDrive:scroll:'+location.pathname}
function clearFolderCache(){try{const p=cachePrefix(); Object.keys(sessionStorage).forEach(k=>{if(k.startsWith(p))sessionStorage.removeItem(k)})}catch(e){}}
let prefSaveTimer=null;
function savePrefs(patch){
  Object.entries(patch||{}).forEach(([k,v])=>localStorage.setItem(prefKey(k), String(v)));
  clearTimeout(prefSaveTimer);
  prefSaveTimer=setTimeout(()=>fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(patch)}).catch(()=>{}),180);
}
function applyView(){ if(!grid)return; const list=state.view==='list'; grid.classList.toggle('list',list); document.body.classList.toggle('view-list',list); document.body.classList.toggle('preview-pane',!!state.previewPane); $$('.view-toggle button').forEach(b=>b.classList.toggle('active',b.dataset.view===state.view)); const pb=$('#previewPaneBtn'); if(pb){pb.classList.toggle('active',!!state.previewPane); pb.textContent=state.previewPane?'👁 Preview on':'👁 Preview off'} localStorage.setItem(prefKey('view'),state.view); if(state.previewPane)ensureSidePreview(); else clearSidePreview(); }
function setView(v){state.view=v;applyView();savePrefs({default_view:v})}
function togglePreviewPane(){state.previewPane=!state.previewPane;localStorage.setItem(prefKey('preview_pane_enabled'),String(state.previewPane));applyView()}
function syncControls(){
  const s=$('#sortSelect'), l=$('#limitSelect'), f=$('#foldersFirst'), rd=$('#recursiveDepth'), tf=$('#thumbFit'), fp=$('#folderPreviewToggle'), anim=$('#previewAnim'), uc=$('#uploadConflict');
  if(s)s.value=state.sort; if(l)l.value=String(state.limit); if(f)f.checked=!!state.foldersFirst; if(rd)rd.value=state.recursiveDepth;
  if(tf)tf.value=state.thumbFit; if(fp)fp.checked=!!state.folderPreview; if(anim)anim.value=state.previewAnimation; if(uc)uc.value=state.uploadConflict;
}
function changeThumbFit(sel){state.thumbFit=sel.value==='cover'?'cover':'contain';document.body.classList.remove('thumb-cover','thumb-contain');document.body.classList.add('thumb-'+(state.thumbFit==='cover'?'cover':'contain'));savePrefs({thumb_fit:state.thumbFit,folder_preview_fit:state.thumbFit});render();toast(state.thumbFit==='cover'?'Thumbnail: crop':'Thumbnail: fit')}
function toggleFolderPreview(el){state.folderPreview=!!el.checked;savePrefs({folder_preview_enabled:state.folderPreview});refreshFolder()}
function changePreviewAnimation(sel){state.previewAnimation=sel.value||'fade';savePrefs({folder_preview_animation:state.previewAnimation});setupFolderPreviews()}
function changeUploadConflict(sel){state.uploadConflict=sel.value||'ask';savePrefs({upload_conflict:state.uploadConflict})}
function isArchiveCard(card){return !!(card&&card.dataset.isdir==='0'&&card.dataset.kind==='archive')}
function selectedCards(){return selectedArray().map(rel=>document.querySelector(`.card[data-rel="${CSS.escape(rel)}"]`)).filter(Boolean)}
function updateSelectionUI(){ if(!grid)return; $$('.card').forEach(c=>{const want=state.selected.has(c.dataset.rel);if(c.classList.contains('selected')!==want)c.classList.toggle('selected',want)}); const n=state.selected.size; const count=$('#selCount'); if(count)count.textContent=n?`${n} selected`:(state.loading?'Đang tải...':`${Math.max(0,state.items.filter(x=>!x.special).length)}${state.hasMore?'+':''} mục`); const one=n===1?document.querySelector(`.card[data-rel="${CSS.escape(selectedArray()[0]||'')}"]`):null; const oneFile=!!(one&&one.dataset.isdir==='0'); const canPreview=!!(oneFile&&one.dataset.preview==='1'); const canExtract=!!(one&&isArchiveCard(one)); $('#deleteBtn')?.classList.toggle('hidden',!n); $('#downloadBtn')?.classList.toggle('hidden',!n); $('#archiveBtn')?.classList.toggle('hidden',!n); $('#copyBtn')?.classList.toggle('hidden',!n); $('#moveBtn')?.classList.toggle('hidden',!n); $('#duplicateBtn')?.classList.toggle('hidden',!n); $('#batchRenameBtn')?.classList.toggle('hidden',n<2); $('#extractBtn')?.classList.toggle('hidden',!canExtract); $('#renameBtn')?.classList.toggle('hidden',n!==1); $('#shareBtn')?.classList.toggle('hidden',n!==1); $('#previewBtn')?.classList.toggle('hidden',!canPreview); }
function setPreviewSelection(rel,scroll=true){if(!rel)return;state.selected.clear();state.selected.add(rel);updateSelectionUI();if(scroll){requestAnimationFrame(()=>{const c=document.querySelector(`.card[data-rel="${CSS.escape(rel)}"]`);if(c)c.scrollIntoView({block:'nearest',inline:'nearest'})})}}
function toggleSelect(rel,ev){if(ev){ev.preventDefault();ev.stopPropagation()} closeContextMenu(); if(!rel)return; if(state.selected.has(rel))state.selected.delete(rel);else state.selected.add(rel);updateSelectionUI()}
function clearSel(){state.selected.clear();updateSelectionUI()}
function selectVisible(){$$('.card:not(.hidden)').forEach(c=>{if(c.dataset.rel)state.selected.add(c.dataset.rel)});updateSelectionUI()}
function applyDragSelect(card){if(!state.dragSelecting||!card?.dataset?.rel)return;if(state.dragMode==='add')state.selected.add(card.dataset.rel);else if(state.dragMode==='remove')state.selected.delete(card.dataset.rel);updateSelectionUI()}
function beginDragSelect(ev,card){if(!(ev.ctrlKey||ev.metaKey)||ev.button!==0||!card?.dataset?.rel)return false;ev.preventDefault();ev.stopPropagation();state.dragCandidate={rel:card.dataset.rel,x:ev.clientX,y:ev.clientY,mode:state.selected.has(card.dataset.rel)?'remove':'add'};return true}
function maybeStartDragSelect(ev){const d=state.dragCandidate;if(!d||state.dragSelecting)return;const dx=ev.clientX-d.x,dy=ev.clientY-d.y;if(Math.hypot(dx,dy)<5)return;state.dragSelecting=true;state.dragMode=d.mode;state.suppressClick=true;const c=document.querySelector(`.card[data-rel="${CSS.escape(d.rel)}"]`);applyDragSelect(c)}
function closeContextMenu(){const m=$('#ctxMenu'); if(m)m.classList.add('hidden')}
function ensureContextSelection(card){const rel=card?.dataset?.rel||''; if(!rel)return ''; if(!state.selected.has(rel)){state.selected.clear();state.selected.add(rel);updateSelectionUI()} return rel}
function openContextMenu(ev,card){
  ev.preventDefault();ev.stopPropagation();const rel=ensureContextSelection(card);if(!rel)return;
  const m=$('#ctxMenu'); if(!m)return; m.dataset.rel=rel;
  const arr=selectedArray(); const one=arr.length===1; const c=one?document.querySelector(`.card[data-rel="${CSS.escape(arr[0])}"]`):null;
  const oneFile=!!(c&&c.dataset.isdir==='0'), oneText=!!(oneFile&&c.dataset.kind==='text'), canPreview=!!(oneFile&&c.dataset.preview==='1'), canExtract=!!(one&&isArchiveCard(c));
  m.querySelector('[data-act="open"]')?.classList.toggle('hidden',!one);
  m.querySelector('[data-act="preview"]')?.classList.toggle('hidden',!canPreview);
  m.querySelector('[data-act="edit"]')?.classList.toggle('hidden',!oneText);
  m.querySelector('[data-act="rename"]')?.classList.toggle('hidden',!one);
  m.querySelector('[data-act="share"]')?.classList.toggle('hidden',!one);
  m.querySelector('[data-act="extract"]')?.classList.toggle('hidden',!canExtract);
  m.querySelector('[data-act="batch"]')?.classList.toggle('hidden',arr.length<2);
  const w=210,h=390; m.style.left=Math.max(8,Math.min(ev.clientX,innerWidth-w-8))+'px'; m.style.top=Math.max(8,Math.min(ev.clientY,innerHeight-h-8))+'px'; m.classList.remove('hidden');
}
function contextAction(action){
  closeContextMenu();
  if(action==='open'){const rel=selectedArray()[0];const c=rel&&document.querySelector(`.card[data-rel="${CSS.escape(rel)}"]`);if(c)openItem(c);return}
  if(action==='preview')return previewSelected();
  if(action==='edit'){const rel=selectedArray()[0];if(rel)location.href=fileUrl(rel)+'?edit=1';return}
  if(action==='rename')return renameOne();
  if(action==='share')return shareOne();
  if(action==='download')return downloadSelected();
  if(action==='archive')return archiveSelected();
  if(action==='extract')return extractSelected();
  if(action==='copy')return copySel();
  if(action==='move')return moveSel();
  if(action==='duplicate')return duplicateSel();
  if(action==='batch')return batchRenameSel();
  if(action==='delete')return deleteSel();
}
function cardHTML(it){
  if(it.special==='back')return `<div class="card" data-rel="" data-name=".." data-size="0" data-mtime="0" data-isdir="1" data-kind="folder" data-rawname=".."><a class="card-main" href="${it.href}"><div class="thumbwrap"><div class="fileicon">↩️</div></div><div class="meta"><div class="name">Back</div><div class="sub">Parent folder</div></div><div class="list-size">Folder</div><div class="list-mtime"></div><div class="list-kind">DIR</div></a></div>`;
  const detailKind=(it.is_dir?'DIR':(it.kind||'FILE')).toUpperCase();
  const badge=['video','audio','text','pdf'].includes(it.kind)?`<div class="badge">${detailKind}</div>`:'';
  let thumb='';
  if(it.kind==='folder' && state.folderPreview){
    thumb=`<div class="folder-mosaic empty ${state.previewAnimation}" data-folder-preview="${it.relEsc}" title="Folder preview"><div class="fileicon">📁</div></div>`;
  }else if(it.thumb){
    const thumbSrc=(state.thumbFit==='contain'&&it.kind==='image')?(it.url||fileUrl(it.rel)):it.thumb;
    thumb=`<img class="thumb" loading="lazy" decoding="async" src="${thumbSrc}" onerror="this.style.display='none';this.nextElementSibling.classList.remove('hidden')"><div class="fileicon hidden">${it.icon}</div>`;
  }else{ thumb=`<div class="fileicon">${it.icon}</div>`; }
  return `<div class="card" data-rel="${it.relEsc}" data-name="${it.nameLowerEsc}" data-size="${it.size}" data-mtime="${it.mtime}" data-isdir="${it.is_dir?'1':'0'}" data-kind="${it.kind}" data-preview="${it.preview?'1':'0'}" data-rawname="${it.nameEsc}" oncontextmenu="openContextMenu(event,this)" onmousedown="beginDragSelect(event,this)" onmouseenter="applyDragSelect(this)"><button class="check" onmousedown="event.stopPropagation()" onclick="toggleSelect(this.closest('.card').dataset.rel, event)" title="Select" aria-label="Select"></button>${badge}<div class="card-main" onclick="openItem(this.closest('.card'),event)"><div class="thumbwrap">${thumb}</div><div class="meta"><div class="name" title="${it.nameEsc}">${it.nameEsc}</div><div class="sub">${it.searchPathTextEsc?it.searchPathTextEsc+' · ':''}${it.sizeTextEsc} · ${it.mtimeTextEsc}</div></div><div class="list-size" title="${it.sizeTextEsc}">${it.sizeTextEsc}</div><div class="list-mtime" title="${it.mtimeTextEsc}">${it.mtimeTextEsc}</div><div class="list-kind">${detailKind}</div></div></div>`
}
function sortDirFor(key){const cur=state.sort||'name-asc';return cur.startsWith(key+'-')&&cur.endsWith('asc')?'desc':'asc'}
function sortByHeader(key){sortCards(key+'-'+sortDirFor(key))}
function sortArrow(key){const cur=state.sort||'';return cur.startsWith(key+'-')?(cur.endsWith('asc')?' ▲':' ▼'):''}
function listHeaderHTML(){return `<div class="list-head"><button onclick="sortByHeader('name')">Name${sortArrow('name')}</button><button onclick="sortByHeader('mtime')">Date modified${sortArrow('mtime')}</button><button onclick="sortByHeader('type')">Type${sortArrow('type')}</button><button onclick="sortByHeader('size')">Size${sortArrow('size')}</button></div>`}
function ensureListHeader(){if(grid&&!grid.querySelector('.list-head'))grid.insertAdjacentHTML('afterbegin',listHeaderHTML())}
function ensureLoader(){ const old=$('#loader'); if(old)old.remove(); if(state.hasMore)grid.insertAdjacentHTML('beforeend','<div id="loader" class="loader">Cuộn xuống để tải thêm...</div>'); observeLoader(); }
function render(){ if(!grid)return; const old=$('#loader'); if(old)old.remove(); if(!state.items.length&&!state.loading){grid.innerHTML=emptyHTML;return} if(grid.querySelector('.empty')||grid.querySelector('.skeleton'))grid.innerHTML=''; grid.innerHTML=listHeaderHTML()+state.items.map(cardHTML).join(''); ensureLoader(); applyView(); updateSelectionUI(); setupFolderPreviews() }
function appendRender(newItems){ if(!grid)return; const old=$('#loader'); if(old)old.remove(); if(grid.querySelector('.empty')||grid.querySelector('.skeleton'))grid.innerHTML=listHeaderHTML(); ensureListHeader(); if(newItems&&newItems.length)grid.insertAdjacentHTML('beforeend',newItems.map(cardHTML).join('')); ensureLoader(); applyView(); updateSelectionUI(); setupFolderPreviews() }
function saveListCache(){try{if(listDataKey!==listContextKey())return;sessionStorage.setItem(cacheKey(),JSON.stringify({items:state.items,offset:state.offset,hasMore:state.hasMore,scrollY:window.scrollY,ts:Date.now()}))}catch(e){}}
function hydrateCache(){try{const raw=sessionStorage.getItem(cacheKey()); if(!raw)return false; const c=JSON.parse(raw); if(!Array.isArray(c.items))return false; state.items=c.items; state.offset=c.offset??c.items.filter(it=>!it.special).length; state.hasMore=!!c.hasMore; listDataKey=listContextKey(); render(); requestAnimationFrame(()=>window.scrollTo(0,c.scrollY??Number(sessionStorage.getItem(scrollKey())||0))); return true}catch(e){return false}}
window.addEventListener('pagehide',()=>{if(grid){sessionStorage.setItem(scrollKey(),String(window.scrollY));saveListCache()}});
window.addEventListener('pageshow',e=>{if(grid&&e.persisted)setTimeout(()=>softRefresh().catch(()=>{}),0)});
// Existing scroll pagination is lazy. Refresh directory data on return/focus and
// with a slow fallback, not by rebuilding the grid every four seconds.
let lastListFetchAt=0;
function canLazyRefresh(){return !document.hidden&&grid&&!state.loading&&!state.selected.size&&!state.listPreview&&!$('#modal')?.classList.contains('show')&&!$('#uploadModal')?.classList.contains('show')&&!$('#termDrawer')?.classList.contains('show')}
function refreshWhenActive(minAgeMs=5000){if(canLazyRefresh()&&Date.now()-lastListFetchAt>=minAgeMs)softRefresh().catch(()=>{})}
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshWhenActive()});
window.addEventListener('focus',()=>refreshWhenActive());
let autoRefreshTimer=setInterval(()=>refreshWhenActive(30000),30000);
let listWork=null, pendingListUpdate=null, listRevision=0, listDataKey=null;
let listRetryRequired=false, appendRepairUsed=false;
function listQuery(){return {path:currentPath(),sort:state.sort,q:q?.value||'',recursive_depth:(q?.value||'').trim()?state.recursiveDepth:'0',folders_first:String(state.foldersFirst)}}
function listContextKey(){return JSON.stringify([listQuery(),state.limit])}
function captureListViewport(){
  const visible=[];
  for(const card of grid.querySelectorAll('.card[data-rel]')){
    const rect=card.getBoundingClientRect();
    if(card.dataset.rel&&rect.bottom>0&&rect.top<innerHeight)visible.push({rel:card.dataset.rel,top:rect.top});
  }
  return {y:window.scrollY,visible};
}
function restoreListViewport(viewport){
  // Use the next surviving visible card when the old anchor was deleted/renamed.
  for(const anchor of viewport.visible){
    const card=grid.querySelector(`.card[data-rel="${CSS.escape(anchor.rel)}"]`);
    if(card){window.scrollBy(0,card.getBoundingClientRect().top-anchor.top);return}
  }
  window.scrollTo(0,viewport.y);
}
async function performListUpdate(kind,revision){
  const query=listQuery(), key=listContextKey();
  const isCurrent=()=>revision===listRevision&&key===listContextKey();
  const reset=kind==='reset'||listDataKey!==key;
  const append=kind==='append'&&!reset;
  const target=append?0:Math.max(state.limit,reset?0:state.offset);
  let offset=append?state.offset:0, next=append?state.items.slice():[], more=true, total=null;
  const appended=[];
  try{
    do{
      // The server caps each response at 1000 real entries. Parent is not an entry.
      const limit=append?state.limit:Math.min(1000,Math.max(20,target-offset));
      const params=new URLSearchParams({...query,offset:String(offset),limit:String(limit)});
      const r=await fetch('/api/list?'+params.toString(),{cache:'no-store'});
      const j=await r.json();
      if(!isCurrent())return;
      if(!r.ok||j.error)throw new Error(j.error||r.statusText);
      if(!Array.isArray(j.items))throw new Error('Invalid listing response');
      const cursor=Number(j.nextOffset);
      if(!Number.isSafeInteger(cursor)||cursor<offset||(j.hasMore&&cursor===offset))throw new Error('Invalid listing cursor');
      if(total!==null&&j.total!==total)throw new Error('Directory changed during refresh; refresh again');
      total=j.total;
      next.push(...j.items); appended.push(...j.items);
      offset=cursor; more=!!j.hasMore;
    }while(!append&&more&&offset<target);
    if(!isCurrent())return;
    const real=next.filter(it=>!it.special), paths=new Set(real.map(it=>it.rel));
    if(paths.size!==real.length){
      // An insertion before our cursor shifted pagination. Repair once, not per frame.
      if(append&&!appendRepairUsed){appendRepairUsed=true;pendingListUpdate='refresh';return}
      throw new Error('Directory changed during refresh; refresh again');
    }
    const wasBlocked=listRetryRequired;
    listRetryRequired=false;
    if(append)appendRepairUsed=false;
    const changed=JSON.stringify(state.items)!==JSON.stringify(next), paginationChanged=state.hasMore!==more;
    // Capture at commit time: selection and scrolling may change while fetching.
    const viewport=!reset&&!append&&changed?captureListViewport():null;
    const selected=reset?[]:selectedArray();
    const previewBefore=state.listPreview && state.items.find(it=>it.rel===state.listPreview);
    state.items=next; state.offset=offset; state.hasMore=more; listDataKey=key;
    state.selected=new Set(selected.filter(rel=>paths.has(rel)));
    if(state.listPreview&&!paths.has(state.listPreview))clearSidePreview();
    if(changed||reset){
      if(append)appendRender(appended);
      else if(next.length)render();
      else{grid.innerHTML=emptyHTML;ensureLoader()}
    }else if(paginationChanged||wasBlocked)ensureLoader();
    // Paint can rewrite a file while the right-hand preview is open. Update
    // its image URL too, not just the thumbnail cards behind the pane.
    const previewAfter=state.listPreview && next.find(it=>it.rel===state.listPreview);
    if(previewAfter && previewBefore?.url!==previewAfter.url && state.previewPane){
      const card=[...grid.querySelectorAll('.card[data-rel]')]
        .find(el=>el.dataset.rel===state.listPreview);
      if(card)renderListPreview(card);
    }
    if(viewport)restoreListViewport(viewport);
    if(reset)window.scrollTo(0,0);
    lastListFetchAt=Date.now();
    // Manual refresh clears the cache before fetching, including unchanged data.
    saveListCache();
  }catch(e){
    if(isCurrent()){
      listRetryRequired=true;
      if(io)io.disconnect();
      const loader=$('#loader');
      if(loader)loader.innerHTML='<button type="button" class="btn small" onclick="refreshFolder()">Thử lại tải danh sách</button>';
      toast('Refresh lỗi: '+e.message);
    }
  }
}
function requestListUpdate(kind){
  if(!grid)return Promise.resolve();
  if(kind==='append'){
    if(listWork||!state.hasMore||listRetryRequired)return listWork||Promise.resolve();
  }else{listRevision++;appendRepairUsed=false}
  // Coalesce refreshes; a sort/search reset supersedes refresh and append.
  if(kind==='reset'||pendingListUpdate!=='reset')pendingListUpdate=kind;
  if(listWork)return listWork;
  state.loading=true;updateSelectionUI();
  listWork=(async()=>{
    try{
      while(pendingListUpdate){
        const action=pendingListUpdate;pendingListUpdate=null;
        await performListUpdate(action,listRevision);
      }
    }finally{state.loading=false;listWork=null;updateSelectionUI();if(!listRetryRequired)observeLoader()}
  })();
  return listWork;
}
function loadMore(reset=false){return requestListUpdate(reset?'reset':'append')}
let io=null; function observeLoader(){ if(!grid)return; if(io)io.disconnect(); const loader=$('#loader'); if(!loader)return; io=new IntersectionObserver(es=>{if(es.some(e=>e.isIntersecting))loadMore(false)},{rootMargin:'900px'}); io.observe(loader)}
function filterCards(){clearTimeout(state.searchTimer);state.searchTimer=setTimeout(()=>{clearFolderCache();loadMore(true)}, Number(defaults.search_debounce_ms||240))} q?.addEventListener('input',filterCards);
function sortCards(mode){if(mode)state.sort=mode; syncControls(); savePrefs({default_sort:state.sort}); clearFolderCache(); loadMore(true)}
function changeSort(sel){sortCards(sel.value)}
function changeLimit(sel){state.limit=Number(sel.value||220); savePrefs({page_limit:state.limit}); clearFolderCache(); loadMore(true)}
function changeFoldersFirst(el){state.foldersFirst=!!el.checked; savePrefs({folders_first:state.foldersFirst}); clearFolderCache(); loadMore(true)}
function changeRecursiveDepth(sel){state.recursiveDepth=String(sel.value||'0');localStorage.setItem(prefKey('recursive_depth'),state.recursiveDepth);clearFolderCache();loadMore(true)}
function softRefresh(){return requestListUpdate('refresh')}
function refreshFolder(){clearFolderCache();softRefresh()}
const MEDIA_KINDS = new Set(['image','video','audio']);
const mediaState = {kind:null,current:null,items:[],index:-1,busy:false,cropActive:false,touchX:0,touchY:0};
window.LanternChatContext={
  capture(){
    const folder=currentPath();
    const viewed=$('#modal')?.classList.contains('show')&&mediaState.current?.rel?String(mediaState.current.rel):'';
    if(viewed)return{kind:'file',path:viewed,folder};
    const chosen=selectedArray();
    if(chosen.length===1){
      const card=document.querySelector(`.card[data-rel="${CSS.escape(chosen[0])}"]`);
      return card?.dataset.isdir==='1'
        ?{kind:'folder',folder:String(chosen[0])}
        :{kind:'file',path:String(chosen[0]),folder};
    }
    return{kind:'folder',folder};
  }
};
function isTypingTarget(el){return el&&['INPUT','TEXTAREA','SELECT'].includes(el.tagName)}
function isMediaKind(kind){return MEDIA_KINDS.has(kind)}
function findLoadedItem(rel){return state.items.find(it=>!it.special&&it.rel===rel)||null}
function normalizeMediaItem(src,kind,url,name,rel){
  const item=src||{};
  return {kind:item.kind||kind,rel:item.rel||rel||'',url:item.url||url||fileUrl(item.rel||rel||''),name:item.name||name||item.nameEsc||''};
}
function collectMediaItems(kind,fallback){
  const items=state.items.filter(it=>!it.special&&it.kind===kind).map(it=>normalizeMediaItem(it));
  if(fallback){
    const exists=items.some(it=>(fallback.rel&&it.rel===fallback.rel)||(fallback.url&&it.url===fallback.url));
    if(!exists)items.push(fallback);
  }
  return items;
}
function mediaLabel(kind){return kind==='image'?'Ảnh':kind==='video'?'Video':kind==='audio'?'Audio':'Media'}
function mediaUrl(it){return it?.url||fileUrl(it?.rel||'')}
function setModalNavState(){
  const len=mediaState.items.length, idx=mediaState.index;
  const canStep=len>1||(mediaState.kind&&state.hasMore);
  const cropButton=$('#modalCropBtn');if(cropButton){cropButton.classList.toggle('hidden',mediaState.kind!=='image');cropButton.disabled=mediaState.cropActive;}
  const overwriteButton=$('#modalCropOverwriteBtn');if(overwriteButton){const supported=mediaState.kind==='image'&&/\.(?:png|jpe?g|webp)$/i.test(mediaState.current?.rel||'');overwriteButton.classList.toggle('hidden',!supported);overwriteButton.disabled=mediaState.cropActive;}
  ['#modalPrevBtn','#modalNextBtn','#modalPrevFloat','#modalNextFloat'].forEach(sel=>{const b=$(sel);if(b)b.disabled=!canStep||mediaState.busy||mediaState.cropActive});
  const meta=$('#modalMeta');
  if(meta){
    const pos=len?`${Math.max(0,idx)+1}/${len}${state.hasMore?'+':''}`:'0/0';
    meta.textContent=`${mediaLabel(mediaState.kind)} · ${pos}`;
  }
}
function prefetchMediaAround(){
  const len=mediaState.items.length;
  if(len<2)return;
  [1,-1].forEach(delta=>{
    const it=mediaState.items[(mediaState.index+delta+len)%len];
    if(!it)return;
    const url=mediaUrl(it);
    if(it.kind==='image'){const img=new Image();img.decoding='async';img.src=url;}
    else if(it.kind==='video'){const v=document.createElement('video');v.preload='metadata';v.src=url;}
  });
}
function fmtTime(seconds){seconds=Number(seconds||0);if(!seconds)return'';const h=Math.floor(seconds/3600),m=Math.floor((seconds%3600)/60),s=Math.floor(seconds%60);return(h?String(h).padStart(2,'0')+':':'')+String(m).padStart(2,'0')+':'+String(s).padStart(2,'0')}
function addVideoPanelItem(panel,label,value){if(value===undefined||value===null||value==='')return;const div=document.createElement('div');div.innerHTML='<b>'+label+':</b> ';div.append(document.createTextNode(String(value)));panel.appendChild(div)}
async function loadVideoInfo(it,video,panel){
  if(!it?.rel||!panel)return;
  panel.innerHTML='<div class="wide">Đang đọc metadata video...</div>';
  try{
    const r=await fetch('/api/video_info?p='+encodeURIComponent(it.rel));
    const j=await r.json();
    if(!r.ok||j.error)throw new Error(j.error||r.statusText);
    panel.innerHTML='';
    addVideoPanelItem(panel,'File',j.name);
    addVideoPanelItem(panel,'Dung lượng',j.sizeText);
    addVideoPanelItem(panel,'Duration',fmtTime(j.duration));
    addVideoPanelItem(panel,'Resolution',j.width&&j.height?`${j.width}×${j.height}`:'');
    addVideoPanelItem(panel,'Video',j.video_codec);
    addVideoPanelItem(panel,'Audio',j.audio_codec);
    addVideoPanelItem(panel,'FPS',j.fps);
    addVideoPanelItem(panel,'Bitrate',j.bitrateText);
    if(Array.isArray(j.subtitles)&&j.subtitles.length){
      const wrap=document.createElement('div');wrap.className='wide video-actions';
      const label=document.createElement('span');label.className='chip';label.textContent='Subtitles';wrap.appendChild(label);
      j.subtitles.forEach((s,idx)=>{
        const track=document.createElement('track');track.kind='subtitles';track.label=s.label||s.name||('Sub '+(idx+1));track.srclang=s.lang||('s'+idx);track.src=s.url;if(idx===0)track.default=true;video.appendChild(track);
        const a=document.createElement('a');a.className='chip';a.href=s.url;a.target='_blank';a.textContent=s.name||('Sub '+(idx+1));wrap.appendChild(a);
      });
      panel.appendChild(wrap);
    }
    if(!j.ffprobe){const note=document.createElement('div');note.className='wide';note.textContent='ffprobe không có, chỉ hiển thị stat cơ bản.';panel.appendChild(note)}
  }catch(e){panel.innerHTML='<div class="wide">Không đọc được metadata video: '+e.message+'</div>'}
}
function renderMediaItem(it,index,opts={}){
  const modal=$('#modal'),body=$('#modalBody'),title=$('#modalTitle');
  if(!modal||!body||!it||mediaState.cropActive)return;
  mediaState.current=it;mediaState.kind=it.kind;mediaState.index=index;
  title.textContent=it.name||'';
  body.innerHTML='';
  modal.classList.toggle('media-image',it.kind==='image');
  modal.classList.toggle('media-video',it.kind==='video');
  modal.classList.toggle('media-audio',it.kind==='audio');
  if(it.kind==='image'){
    const img=document.createElement('img');img.src=mediaUrl(it);img.alt=it.name||'';img.draggable=false;body.appendChild(img);
  }else if(it.kind==='video'){
    const wrap=document.createElement('div');wrap.className='video-wrap';
    const v=document.createElement('video');v.src=mediaUrl(it);v.controls=true;v.autoplay=opts.autoplay!==false;v.playsInline=true;v.preload='auto';
    v.addEventListener('ended',()=>{if(mediaState.items.length>1)stepMedia(1)});
    const panel=document.createElement('div');panel.className='video-panel';
    wrap.appendChild(v);wrap.appendChild(panel);body.appendChild(wrap);
    loadVideoInfo(it,v,panel);
  }else if(it.kind==='audio'){
    const a=document.createElement('audio');a.src=mediaUrl(it);a.controls=true;a.autoplay=opts.autoplay!==false;a.preload='metadata';body.appendChild(a);
  }
  setModalNavState();prefetchMediaAround();
}
function openPreview(kind,url,name,rel=''){
  if(!isMediaKind(kind)||mediaState.cropActive)return;
  const modal=$('#modal'); if(!modal)return;
  const loaded=findLoadedItem(rel);
  const fallback=normalizeMediaItem(loaded,kind,url,name,rel);
  mediaState.items=collectMediaItems(kind,fallback);
  const foundIndex=mediaState.items.findIndex(it=>(rel&&it.rel===rel)||it.url===url);
  mediaState.index=foundIndex>=0?foundIndex:mediaState.items.length-1;
  renderMediaItem(mediaState.items[mediaState.index]||fallback,mediaState.index,{autoplay:true});
  modal.classList.add('show');
}
async function cropViewedImage(overwriteOriginal=false){
  const original=mediaState.current;
  if(mediaState.cropActive||original?.kind!=='image'||!original.rel)return;
  mediaState.cropActive=true;setModalNavState();
  try{
    const cropURL='/static/vendor/lantern-image-crop.min.js';
    const {openCrop}=await import(cropURL);
    // Capture the original content hash BEFORE the dialog whenever overwrite
    // is available. The user can choose Save Copy or Overwrite inside Crop;
    // a concurrent change during the dialog must still be refused.
    const originalExt=(original.rel.match(/\.([^.]+)$/)||[])[1]?.toLowerCase();
    const validType={png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',webp:'image/webp'}[originalExt];
    const canOverwrite=!!validType;
    let originalVersion=null;
    if(canOverwrite){
      const check=await fetch('/api/image/version?p='+encodeURIComponent(original.rel),{cache:'no-store'});
      const state=await check.json();
      if(!check.ok||!state.version)throw Error(state.error||'Cannot inspect original image');
      originalVersion=state.version;
    }
    const result=await openCrop({
      src:mediaUrl(original),name:original.name||'Image',
      allowOverwrite:canOverwrite,preferredAction:overwriteOriginal?'overwrite':'copy'
    });
    if(!result)return;
    const persistOverwrite=result.action==='overwrite'||(!result.action&&overwriteOriginal);
    if(persistOverwrite){
      if(validType!==result.blob.type)throw Error('Crop output format differs from original; use Crop (Save As)');
      if(!confirm('Overwrite original image? All files using this image will change. This cannot be undone. EXIF/ICC metadata may be lost.'))return;
      const response=await fetch('/api/image/overwrite?p='+encodeURIComponent(original.rel),{
        method:'POST',credentials:'same-origin',cache:'no-store',
        headers:{'Content-Type':result.blob.type,'If-Match':originalVersion},body:result.blob,
      });
      const update=await response.json();
      if(!response.ok||update.error)throw Error(update.error||('Overwrite HTTP '+response.status));
      toast('Original image overwritten');
      clearFolderCache();
      await loadMore(true).catch(error=>toast('Refresh failed: '+error.message));
      mediaState.cropActive=false;
      const refreshedUrl=fileUrl(original.rel)+'?v='+encodeURIComponent(update.version);
      openPreview('image',refreshedUrl,original.name,original.rel);
      // openPreview normally prefers a loaded list item; ensure the new image
      // version wins even if the directory list/cache had the old URL.
      const updated=mediaState.items[mediaState.index];
      if(updated?.rel===original.rel){updated.url=refreshedUrl;renderMediaItem(updated,mediaState.index);}
      return;
    }
    // Existing Crop action remains Save As; no original bytes are changed.
    const pieces=original.rel.split('/');
    const originalName=pieces.pop()||'image';
    const directory=pieces.join('/');
    const stem=originalName.replace(/\.[^.]+$/,'');
    const name=stem+'-cropped-'+Date.now()+'-'+Math.random().toString(36).slice(2,8)+'.'+result.extension;
    toast('Saving cropped copy…');
    const response=await fetch('/api/upload?path='+encodeURIComponent(directory)+
      '&name='+encodeURIComponent(name)+'&conflict=rename',{
        method:'POST',credentials:'same-origin',cache:'no-store',
        headers:{'Content-Type':result.blob.type},body:result.blob,
      });
    const data=await response.json();
    if(!response.ok||data.error||!data.file)throw Error(data.error||('Upload HTTP '+response.status));
    const path=decodeURIComponent(String(data.file).replace(/^\//,''));
    toast('New image created: '+path);
    try{
      clearFolderCache();
      await loadMore(true);
    }catch(error){
      // A folder refresh error cannot undo the successful Save As.
      toast('Image saved, but folder refresh failed: '+error.message);
    }
    mediaState.cropActive=false;
    openPreview('image',fileUrl(path),path.split('/').pop(),path);
  }catch(error){toast('Crop failed: '+error.message);}
  finally{mediaState.cropActive=false;setModalNavState();}
}
async function stepMedia(delta,ev){
  if(ev&&ev.preventDefault){ev.preventDefault();ev.stopPropagation();}
  const modal=$('#modal');
  if(!modal?.classList.contains('show')||!mediaState.kind||mediaState.busy||mediaState.cropActive)return;
  let items=mediaState.items;
  if(!items.length)return;
  let currentIndex=items.findIndex(it=>(mediaState.current?.rel&&it.rel===mediaState.current.rel)||it.url===mediaState.current?.url);
  if(currentIndex>=0)mediaState.index=currentIndex;
  let next=mediaState.index+delta;
  if(delta>0&&next>=items.length&&state.hasMore&&!state.loading){
    mediaState.busy=true;setModalNavState();
    await loadMore(false);
    mediaState.items=collectMediaItems(mediaState.kind,mediaState.current);
    items=mediaState.items;
    currentIndex=items.findIndex(it=>(mediaState.current?.rel&&it.rel===mediaState.current.rel)||it.url===mediaState.current?.url);
    mediaState.index=currentIndex>=0?currentIndex:mediaState.index;
    next=mediaState.index+delta;
    mediaState.busy=false;setModalNavState();
  }
  if(!items.length)return;
  if(next<0)next=items.length-1;
  if(next>=items.length)next=0;
  if(next===mediaState.index&&items.length===1)return;
  renderMediaItem(items[next],next,{autoplay:true});
}
function closeModal(){if(mediaState.cropActive)return;const m=$('#modal'); if(!m)return; $('#modalBody').innerHTML='';m.classList.remove('show','media-image','media-video','media-audio');mediaState.kind=null;mediaState.current=null;mediaState.items=[];mediaState.index=-1;mediaState.busy=false}
function setupModalGestures(){
  const body=$('#modalBody'); if(!body||body.dataset.swipeReady)return; body.dataset.swipeReady='1';
  body.addEventListener('touchstart',e=>{const t=e.changedTouches[0];mediaState.touchX=t.clientX;mediaState.touchY=t.clientY},{passive:true});
  body.addEventListener('touchend',e=>{if(mediaState.cropActive)return;const t=e.changedTouches[0];const dx=t.clientX-mediaState.touchX,dy=t.clientY-mediaState.touchY;if(Math.abs(dx)>52&&Math.abs(dx)>Math.abs(dy)*1.35){e.preventDefault();stepMedia(dx<0?1:-1)}},{passive:false});
}
setupModalGestures();
document.addEventListener('keydown',e=>{
  const modalOpen=$('#modal')?.classList.contains('show');
  if(modalOpen){
    if(mediaState.cropActive)return;
    if(e.key==='Escape'){e.preventDefault();closeModal();return}
    if((e.key==='ArrowLeft'||e.key==='ArrowRight')&&!isTypingTarget(document.activeElement)){
      if(mediaState.kind==='image'||e.shiftKey){e.preventDefault();stepMedia(e.key==='ArrowRight'?1:-1);return}
    }
  }else if(e.key==='Escape'&&$('#uploadModal')?.classList.contains('show')){closeUploadDialog();return}
  else if(state.previewPane&&state.listPreview&&(e.key==='ArrowLeft'||e.key==='ArrowRight')&&!isTypingTarget(document.activeElement)){e.preventDefault();stepSidePreview(e.key==='ArrowRight'?1:-1);return}
  if(grid&&(e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='a'&&!isTypingTarget(document.activeElement)){e.preventDefault();selectVisible()}
});
document.addEventListener('click',e=>{if(!e.target.closest?.('#ctxMenu'))closeContextMenu()});
document.addEventListener('mousemove',maybeStartDragSelect);
document.addEventListener('mouseup',()=>{const wasDrag=state.dragSelecting;state.dragCandidate=null;state.dragSelecting=false;state.dragMode=null;if(wasDrag){state.suppressClick=true;setTimeout(()=>{state.suppressClick=false},0)}});
window.addEventListener('scroll',closeContextMenu,true);
async function api(path,data){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data||{})});const j=await r.json().catch(()=>({}));if(!r.ok||j.error)throw new Error(j.error||`HTTP ${r.status}`);return j}
async function mkdir(){const name=prompt('Tên thư mục mới:');if(!name)return;try{await api('/api/mkdir',{path:currentPath(),name});clearFolderCache();await softRefresh()}catch(e){toast('Lỗi tạo thư mục: '+e.message)}}
async function newFile(){const name=prompt('Tên file mới, ví dụ notes.txt:');if(!name)return;try{const r=await api('/api/newfile',{path:currentPath(),name});location.href=r.edit_url}catch(e){toast('Lỗi tạo file: '+e.message)}}
async function renameOne(){const rel=selectedArray()[0];if(!rel)return;const old=rel.split('/').pop();const name=prompt('Đổi tên thành:',old);if(!name||name===old)return;try{await api('/api/rename',{path:rel,name});clearFolderCache();await softRefresh()}catch(e){toast('Lỗi rename: '+e.message)}}
async function copySel(){const arr=selectedArray();if(!arr.length)return;const dest=prompt(`Copy ${arr.length} mục đến thư mục:`,currentPath());if(dest===null)return;try{const r=await api('/api/copy',{paths:arr,dest,conflict:'rename'});toast(`Đã copy ${r.copied?.length||0} mục`);clearFolderCache();await softRefresh()}catch(e){toast('Lỗi copy: '+e.message)}}
async function moveSel(){const arr=selectedArray();if(!arr.length)return;const dest=prompt(`Move ${arr.length} mục đến thư mục:`,currentPath());if(dest===null)return;if(!confirm(`Move ${arr.length} mục đến /${dest}?`))return;try{const r=await api('/api/move',{paths:arr,dest,conflict:'rename'});toast(`Đã move ${r.moved?.length||0} mục`);clearFolderCache();await softRefresh()}catch(e){toast('Lỗi move: '+e.message)}}
async function duplicateSel(){const arr=selectedArray();if(!arr.length)return;try{const r=await api('/api/duplicate',{paths:arr,conflict:'rename'});toast(`Đã duplicate ${r.duplicated?.length||0} mục`);clearFolderCache();await softRefresh()}catch(e){toast('Lỗi duplicate: '+e.message)}}
async function batchRenameSel(){const arr=selectedArray();if(arr.length<2){toast('Batch rename cần chọn ít nhất 2 mục');return}const cards=selectedCards();const hasFolder=cards.some(c=>c.dataset.isdir==='1'), hasFile=cards.some(c=>c.dataset.isdir==='0');if(hasFolder&&hasFile&&!confirm('Bạn đang chọn cả file và folder. Vẫn batch rename?'))return;const kinds=new Set(cards.map(c=>c.dataset.kind));if(kinds.size>1&&!confirm('Các mục không cùng loại. Vẫn batch rename theo tên?'))return;const find=prompt('Batch rename: tìm chuỗi trong tên:','');if(find===null)return;if(find===''){toast('Chuỗi tìm không được rỗng');return}const repl=prompt('Thay bằng:','');if(repl===null)return;const items=arr.map(path=>{const old=path.split('/').pop();return{path,name:old.split(find).join(repl)}}).filter(x=>x.name&&x.name!==x.path.split('/').pop());if(!items.length){toast('Không có tên nào thay đổi');return}try{const r=await api('/api/batch_rename',{items});toast(`Đã rename ${r.renamed?.length||0} mục`);state.selected.clear();await softRefresh()}catch(e){toast('Lỗi batch rename: '+e.message)}}
async function extractSelected(){const arr=selectedArray();const card=arr.length===1?document.querySelector(`.card[data-rel="${CSS.escape(arr[0])}"]`):null;if(!isArchiveCard(card)){toast('Chỉ extract file archive');return}const dest=prompt('Extract đến thư mục:',currentPath());if(dest===null)return;try{const r=await api('/api/extract',{path:arr[0],dest,conflict:'rename'});toast(`Extract xong: ${r.written||0} file`);await softRefresh()}catch(e){toast('Lỗi extract: '+e.message)}}
function submitArchive(paths,format='zip',compression='compress'){const arr=paths||selectedArray();if(!arr.length)return;const form=document.createElement('form');form.method='POST';form.action='/api/archive';const input=document.createElement('input');input.name='payload';input.value=JSON.stringify({paths:arr,format,compression});form.appendChild(input);document.body.appendChild(form);form.submit();form.remove()}
function downloadZip(paths){submitArchive(paths||selectedArray(),'zip','compress')}
function archiveSelected(){const arr=selectedArray();if(!arr.length)return;const rawFormat=prompt('Archive format: zip hoặc tar','zip');if(rawFormat===null)return;let format=(rawFormat||'zip').trim().toLowerCase();if(!['zip','tar'].includes(format)){toast('Format phải là zip hoặc tar');return}const rawCompression=prompt('Compression: compress hoặc store','compress');if(rawCompression===null)return;let compression=(rawCompression||'compress').trim().toLowerCase();if(!['compress','store'].includes(compression)){toast('Compression phải là compress hoặc store');return}submitArchive(arr,format,compression)}
function selectedHasFolder(){return selectedCards().some(c=>c.dataset.isdir==='1')}
function askDownloadMode(count){
  return new Promise(resolve=>{
    const backdrop=document.createElement('div');
    backdrop.className='download-choice-backdrop';
    const box=document.createElement('div');
    box.className='download-choice-box';
    const title=document.createElement('div');
    title.className='download-choice-title';
    title.textContent='Tải nhiều file';
    const desc=document.createElement('div');
    desc.className='download-choice-desc';
    desc.textContent=`Bạn đang chọn ${count} file. Chọn Zip để đóng gói như cũ, hoặc tải từng file đồng thời tối đa 5 file.`;
    const actions=document.createElement('div');
    actions.className='download-choice-actions';
    const rawBtn=document.createElement('button');
    rawBtn.className='btn primary';
    rawBtn.textContent='Tải từng file';
    const zipBtn=document.createElement('button');
    zipBtn.className='btn';
    zipBtn.textContent='Zip rồi tải';
    const cancelBtn=document.createElement('button');
    cancelBtn.className='btn ghost';
    cancelBtn.textContent='Huỷ';
    actions.append(rawBtn,zipBtn,cancelBtn);
    box.append(title,desc,actions);
    backdrop.appendChild(box);
    const close=choice=>{document.removeEventListener('keydown',onKey);backdrop.remove();resolve(choice)};
    const onKey=e=>{if(e.key==='Escape')close('cancel')};
    rawBtn.onclick=()=>close('files');
    zipBtn.onclick=()=>close('zip');
    cancelBtn.onclick=()=>close('cancel');
    backdrop.onclick=e=>{if(e.target===backdrop)close('cancel')};
    document.addEventListener('keydown',onKey);
    document.body.appendChild(backdrop);
    rawBtn.focus();
  });
}
function triggerDirectDownload(rel){
  const a=document.createElement('a');
  a.href='/'+enc(rel)+'?download=1';
  a.download=rel.split('/').pop()||'download';
  a.style.display='none';
  document.body.appendChild(a);
  a.click();
  a.remove();
}
function downloadFilesDirect(paths,maxParallel=5){
  const arr=paths||selectedArray();
  if(!arr.length)return;
  const limit=Math.max(1,Math.min(Number(maxParallel)||5,5,arr.length));
  let index=0;
  toast(`Đang mở tải ${arr.length} file, tối đa ${limit} file mỗi lượt...`);
  const launchWave=()=>{
    const batch=arr.slice(index,index+limit);
    index+=batch.length;
    batch.forEach(triggerDirectDownload);
    if(index<arr.length)setTimeout(launchWave,900);
    else setTimeout(()=>toast(`Đã mở tải ${arr.length} file`),250);
  };
  launchWave();
}
async function downloadSelected(){
  const arr=selectedArray();
  if(!arr.length)return;
  const cards=selectedCards();
  if(arr.length===1){
    const card=cards[0];
    if(card&&card.dataset.isdir==='0'){location.href='/'+enc(arr[0])+'?download=1';return}
    submitArchive(arr,'zip','compress');return;
  }
  if(cards.some(c=>c.dataset.isdir==='1')){toast('Selection có folder, sẽ tải dạng archive.');submitArchive(arr,'zip','compress');return}
  const choice=await askDownloadMode(arr.length);
  if(choice==='zip')submitArchive(arr,'zip','compress');
  else if(choice==='files')downloadFilesDirect(arr,5);
  else toast('Đã huỷ tải');
}
async function deleteSel(){const arr=selectedArray();if(!arr.length)return;if(!confirm(`Xoá vĩnh viễn ${arr.length} mục?`))return;try{await api('/api/delete',{paths:arr});clearFolderCache();state.selected.clear();await softRefresh()}catch(e){toast('Lỗi xoá: '+e.message)}}
async function shareOne(){const rel=selectedArray()[0];if(!rel)return;const url=new URL('/'+enc(rel),location.href).href;let ok=false;try{if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(url);ok=true}}catch(e){} if(!ok){try{const ta=document.createElement('textarea');ta.value=url;ta.style.position='fixed';ta.style.left='-9999px';document.body.appendChild(ta);ta.focus();ta.select();ok=document.execCommand('copy');ta.remove()}catch(e){}} if(ok)toast('Đã copy link'); else prompt('Không copy tự động được, copy link này:',url)}
function previewUrl(rel){return '/api/plugin/preview?p='+encodeURIComponent(rel)}
function previewSelected(){const rel=selectedArray()[0];if(!rel)return;window.open(previewUrl(rel),'_blank')}
async function addPreviewExtension(){const raw=prompt('Thêm đuôi/pattern đọc nhanh, ví dụ .env.local hoặc *.secret hoặc .foo:');if(!raw)return;try{const j=await api('/api/plugin/extensions',{add:raw});state.pluginEnabled=true;toast('Đã thêm: '+(j.custom_patterns||[]).join(', '));clearFolderCache();loadMore(true)}catch(e){toast('Lỗi plugin: '+e.message)}}
function fileUrl(rel){return '/'+enc(rel)}
function clearSidePreview(){if(sidePreview){sidePreview.innerHTML='<div class="side-empty">Preview off</div>';state.listPreview=null}}
function ensureSidePreview(){if(sidePreview&&state.previewPane&&!state.listPreview)sidePreview.innerHTML='<div class="side-empty">Chọn file để preview</div>'}
function listCanPreview(card){return !!card&&card.dataset.isdir==='0'&&(isMediaKind(card.dataset.kind)||card.dataset.preview==='1'||card.dataset.kind==='text'||card.dataset.kind==='pdf')}
function sidePreviewCards(){return $$('.card').filter(c=>c.dataset.rel&&listCanPreview(c))}
async function stepSidePreview(delta){let cards=sidePreviewCards();if(!cards.length)return;let i=cards.findIndex(c=>c.dataset.rel===state.listPreview);if(i>=0&&delta>0&&i>=cards.length-1&&state.hasMore&&!state.loading){await loadMore(false);cards=sidePreviewCards();i=cards.findIndex(c=>c.dataset.rel===state.listPreview)}else if(i>=0&&delta<0&&i===0&&state.hasMore&&!state.loading){await loadMore(false);cards=sidePreviewCards();i=cards.findIndex(c=>c.dataset.rel===state.listPreview)}if(i<0)i=0;else i=(i+delta+cards.length)%cards.length;renderListPreview(cards[i])}
function renderListPreview(card){
  if(!sidePreview||!card)return;
  const rel=card.dataset.rel,kind=card.dataset.kind,item=findLoadedItem(rel),name=item?.name||card.dataset.rawname||rel,url=item?.url||fileUrl(rel);
  state.listPreview=rel;
  setPreviewSelection(rel,true);
  sidePreview.innerHTML='<div class="side-title"><span class="side-title-text"></span><div class="side-nav top"><button onclick="togglePreviewPane()" title="Close preview">×</button></div></div><div class="side-body"><button class="side-arrow side-prev" onclick="stepSidePreview(-1)" title="Previous">‹</button><button class="side-arrow side-next" onclick="stepSidePreview(1)" title="Next">›</button><div class="side-content"></div></div>';
  sidePreview.querySelector('.side-title-text').textContent=name;
  const body=sidePreview.querySelector('.side-content');
  const mode=m=>{body.className='side-content '+m};
  if(kind==='image'){mode('media');body.innerHTML=`<div class="side-fit-bg" style="background-image:url('${url.replace(/'/g,"%27")}')"></div>`;
    const open=document.createElement('button');open.className='btn small';open.textContent='Open / Crop';
    open.addEventListener('click',()=>openPreview('image',url,name,rel));
    sidePreview.querySelector('.side-nav.top')?.prepend(open);
  }
  else if(kind==='video'){mode('media video');body.innerHTML=`<div class="side-video-fit"><video class="side-video" src="${url}" controls preload="metadata" playsinline></video></div>`}
  else if(kind==='audio'){mode('media audio');body.innerHTML=`<audio class="side-audio" src="${url}" controls preload="metadata"></audio>`}
  else if(card.dataset.preview==='1'){mode('doc');body.innerHTML=`<iframe class="side-frame" src="${previewUrl(rel)}"></iframe>`}
  else if(kind==='text'){mode('text');body.innerHTML='<pre class="side-text">Đang đọc...</pre>';fetch(url,{headers:{Range:'bytes=0-199999'}}).then(async r=>{if(!r.ok)throw new Error('HTTP '+r.status);if(r.status!==206&&Number(r.headers.get('content-length')||0)>200000)throw new Error('Range unsupported for large preview');const total=Number((r.headers.get('content-range')||'').split('/').pop());return {text:await r.text(),truncated:total>200000}}).then(x=>{if(state.listPreview!==rel)return;const pre=body.querySelector('pre');if(pre)pre.textContent=x.text+(x.truncated?'\n\n[Preview limited to 200 KB]':'')}).catch(e=>body.textContent='Không đọc được preview: '+e.message)}
  else{mode('empty');body.innerHTML='<div class="side-empty">Không hỗ trợ preview nhanh</div>'}
}
function openItem(card,ev){const rel=card.dataset.rel;if(state.suppressClick){if(ev){ev.preventDefault();ev.stopPropagation()}return}if(ev&&(ev.ctrlKey||ev.metaKey)){toggleSelect(rel,ev);return}closeContextMenu();const kind=card.dataset.kind,item=findLoadedItem(rel),name=item?.name||card.dataset.rawname,url=fileUrl(rel);saveListCache();if(state.previewPane&&listCanPreview(card)){renderListPreview(card);return}if(kind==='folder')location.href=url+'/';else if(isMediaKind(kind))openPreview(kind,url,name,rel);else if(card.dataset.preview==='1')location.href=previewUrl(rel);else if(kind==='text')location.href=url+'?edit=1';else toast('File này chưa hỗ trợ preview. Dùng nút Download để tải.')}

// ---------------- Folder preview mosaic ----------------
let folderPreviewIO=null, folderPreviewTimers=[];
const folderPreviewQueue=[];
let folderPreviewActive=0;
function clearFolderPreviewTimers(){folderPreviewTimers.forEach(t=>clearInterval(t));folderPreviewTimers=[]}
function renderFolderMosaic(el, items, start=0){
  if(!el||!Array.isArray(items)||!items.length)return;
  const anim=(state.previewAnimation||'fade');
  el.className='folder-mosaic '+anim;
  el.innerHTML='';
  for(let i=0;i<4;i++){
    const it=items[(start+i)%items.length];
    const cell=document.createElement('div');cell.className='cell';
    if(it){
      const img=document.createElement('img');img.loading='lazy';img.decoding='async';img.src=it.thumb||it.url;img.alt=it.name||'';
      img.onerror=()=>{ if(it.url && img.src.indexOf(it.url)===-1){ img.src=it.url; } else { cell.innerHTML='<span class="fileicon">📁</span>'; } };
      cell.appendChild(img);
    } else cell.innerHTML='<span class="fileicon">📁</span>';
    el.appendChild(cell);
  }
}
function startFolderRotate(el, items){
  if(!defaults.folder_preview_rotate || !state.folderPreview || !items || items.length<=4)return;
  let idx=0; const ms=Math.max(1800,Number(defaults.folder_preview_interval_ms||3500));
  const timer=setInterval(()=>{if(document.hidden||!document.body.contains(el))return; const r=el.getBoundingClientRect(); if(r.bottom<0||r.top>innerHeight)return; idx=(idx+4)%items.length; renderFolderMosaic(el,items,idx)},ms);
  folderPreviewTimers.push(timer);
}
function queueFolderPreview(el){
  if(!el||el.dataset.loaded||el.dataset.queued)return;
  el.dataset.queued='1'; folderPreviewQueue.push(el); pumpFolderPreviewQueue();
}
async function pumpFolderPreviewQueue(){
  const maxActive=2;
  while(folderPreviewActive<maxActive && folderPreviewQueue.length){
    const el=folderPreviewQueue.shift();
    if(!el||!document.body.contains(el)||el.dataset.loaded)continue;
    folderPreviewActive++;
    loadFolderPreview(el).finally(()=>{folderPreviewActive--; setTimeout(pumpFolderPreviewQueue,40);});
  }
}
async function loadFolderPreview(el){
  const rel=el.dataset.folderPreview;if(!rel||el.dataset.loaded)return;el.dataset.loaded='1';
  try{const r=await fetch('/api/folder_preview?p='+encodeURIComponent(rel),{cache:'no-store'});const j=await r.json(); if(!r.ok||j.error||!j.items||!j.items.length)return; renderFolderMosaic(el,j.items,0); startFolderRotate(el,j.items)}catch(e){}
}
function setupFolderPreviews(){
  clearFolderPreviewTimers(); if(folderPreviewIO)folderPreviewIO.disconnect(); folderPreviewQueue.length=0; folderPreviewActive=0;
  const els=$$('.folder-mosaic[data-folder-preview]'); if(!els.length||!state.folderPreview)return;
  folderPreviewIO=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting){queueFolderPreview(e.target);folderPreviewIO.unobserve(e.target)}})},{rootMargin:'350px'});
  els.forEach(el=>folderPreviewIO.observe(el));
}

function uploadQuery(item,relDir){
  const file=item.file||item;
  const relName=(item.relPath||file.webkitRelativePath||file.name).replace(/^\/+/, '');
  const target=relDir.replace(/^\/+|\/+$/g,'');
  return `path=${encodeURIComponent(target)}&name=${encodeURIComponent(relName)}`;
}
async function preflightUpload(item,relDir){
  const r=await fetch('/api/upload/check?'+uploadQuery(item,relDir),{cache:'no-store'});
  const data=await r.json();
  if(!r.ok)throw new Error(data.error||'Upload preflight failed');
  return !!data.exists;
}
async function uploadFile(item,relDir,progressCb,conflictMode){
  const file=item.file||item;
  const relName=(item.relPath||file.webkitRelativePath||file.name).replace(/^\/+/, '');
  const url=`/api/upload?${uploadQuery(item,relDir)}&conflict=${encodeURIComponent(conflictMode||state.uploadConflict||'ask')}`;
  return new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open('POST',url);xhr.setRequestHeader('Content-Type','application/octet-stream');xhr.upload.onprogress=e=>{if(e.lengthComputable&&progressCb)progressCb(e.loaded,e.total,relName)};xhr.onload=()=>{let data={};try{data=JSON.parse(xhr.responseText||'{}')}catch(e){};if(xhr.status>=200&&xhr.status<300)resolve(data);else{const err=new Error(data.error||xhr.responseText||xhr.statusText);err.status=xhr.status;reject(err)}};xhr.onerror=()=>reject(new Error('network error'));xhr.send(file)})
}
const uploadState={queue:[],running:false,done:0,failed:0,totalBytes:0,loadedBytes:0,active:new Map()};
function humanBytes(n){n=Number(n||0);for(const u of ['B','KB','MB','GB','TB']){if(n<1024||u==='TB')return (u==='B'?Math.round(n):n.toFixed(1))+' '+u;n/=1024}}
function openUploadDialog(){const m=$('#uploadModal'); if(!m)return; m.classList.add('show'); renderUploadQueue();}
function closeUploadDialog(){ if(uploadState.running&&!confirm('Upload đang chạy, vẫn đóng popup?'))return; $('#uploadModal')?.classList.remove('show') }
function chooseFiles(){openUploadDialog()} function chooseFolder(){openUploadDialog()}
function pickUploadFiles(){$('#fileInput')?.click()} function pickUploadFolder(){$('#folderInput')?.click()}
function normalizeUploadItem(it,targetPath){it.targetPath=targetPath==null?currentPath():targetPath;return it}
function enqueueUploadItems(items,targetPath,autoStart=state.uploadAutoStart){
  const arr=Array.from(items||[]).map(it=>normalizeUploadItem(it,targetPath));
  if(!arr.length)return 0;
  uploadState.queue.push(...arr); uploadState.totalBytes=uploadState.queue.reduce((a,x)=>a+(x.size||0),0); renderUploadQueue();
  if(autoStart)startUploadQueue();
  return arr.length;
}
function addUploadFiles(files,targetPath=currentPath()){const arr=Array.from(files||[]).map(f=>({file:f,relPath:f.webkitRelativePath||f.name,state:'ready',loaded:0,size:f.size||0,targetPath})); return enqueueUploadItems(arr,targetPath);}
async function traverseEntry(entry,path,out,targetPath=currentPath()){
  if(entry.isFile){await new Promise(res=>entry.file(f=>{out.push({file:f,relPath:(path+f.name).replace(/^\/+/,''),state:'ready',loaded:0,size:f.size||0,targetPath});res()},()=>res()))}
  else if(entry.isDirectory){const reader=entry.createReader();let batch=[];do{batch=await new Promise(res=>reader.readEntries(res,()=>res([])));for(const e of batch)await traverseEntry(e,path+entry.name+'/',out,targetPath)}while(batch.length)}
}
async function itemsFromDrop(e,targetPath=currentPath()){
  const out=[]; const dt=e.dataTransfer; const items=Array.from(dt?.items||[]);
  if(items.length&&items[0].webkitGetAsEntry){for(const it of items){const entry=it.webkitGetAsEntry();if(entry)await traverseEntry(entry,'',out,targetPath)}}
  if(out.length)return out;
  return Array.from(dt?.files||[]).map(f=>({file:f,relPath:f.webkitRelativePath||f.name,state:'ready',loaded:0,size:f.size||0,targetPath}));
}
async function handleUploadDrop(e){e.preventDefault();e.stopPropagation();const dz=$('#uploadDrop');dz?.classList.remove('drag');const targetPath=currentPath();const out=await itemsFromDrop(e,targetPath);enqueueUploadItems(out,targetPath);}
async function handleGridUploadDrop(e){
  e.preventDefault(); e.stopPropagation(); grid?.classList.remove('drag');
  if(uploadState.running){toast('Upload đang chạy, chưa thêm queue mới');return}
  const targetPath=currentPath(); openUploadDialog();
  const added=enqueueUploadItems(await itemsFromDrop(e,targetPath),targetPath,false);
  if(added)toast(`Đã thêm ${added} file vào queue upload`);
}
function renderUploadQueue(){
  const q=$('#uploadQueue'), sum=$('#uploadSummary'), bar=$('#uploadModalBar'); if(!q)return;
  const total=uploadState.queue.length; const bytes=uploadState.queue.reduce((a,x)=>a+(x.size||0),0);
  q.innerHTML=uploadState.queue.slice(0,500).map((it,i)=>`<div class="upload-row"><div class="upload-path" title="${it.relPath}">${it.relPath}</div><div class="upload-state ${it.state==='done'?'ok':it.state==='error'?'err':''}">${it.state||'ready'} ${it.size?humanBytes(it.size):''}</div></div>`).join('') || '<div class="upload-row"><div class="upload-path">Chưa có file nào trong queue.</div><div class="upload-state">ready</div></div>';
  if(total>500)q.insertAdjacentHTML('beforeend',`<div class="upload-row"><div class="upload-path">... còn ${total-500} file nữa</div><div></div></div>`);
  if(sum)sum.textContent=`${total} file · ${humanBytes(bytes)} · done ${uploadState.done} · lỗi ${uploadState.failed}`;
  const loaded=uploadState.queue.reduce((a,x)=>a+(x.loaded||0),0); if(bar)bar.style.width=bytes?Math.min(100,Math.round(loaded/bytes*100))+'%':'0%';
}
async function uploadOneQueued(it){
  it.state='uploading';it.loaded=0;renderUploadQueue();
  try{
    let mode=state.uploadConflict,res;
    const targetPath=it.targetPath==null?currentPath():it.targetPath;
    // Decide before sending the body. The server still checks conflicts to guard races.
    if((mode==='ask'||mode==='skip')&&await preflightUpload(it,targetPath)){
      if(mode==='skip'||!confirm(`File đã tồn tại:\n${it.relPath}\n\nGhi đè file này?`)){
        it.state='skipped';it.loaded=it.size;return;
      }
      mode='overwrite';
    }
    try{res=await uploadFile(it,targetPath,(loaded,total)=>{it.loaded=loaded;renderUploadQueue()},mode)}
    catch(e){
      if(e.status===409&&mode==='ask'){
        if(confirm(`File vừa được tạo:\n${it.relPath}\n\nGhi đè file này?`)){
          res=await uploadFile(it,targetPath,(loaded,total)=>{it.loaded=loaded;renderUploadQueue()},'overwrite');
        }else{it.state='skipped';it.loaded=it.size;return}
      }else throw e;
    }
    it.state=res?.skipped?'skipped':'done';it.loaded=it.size;uploadState.done++;
  }catch(e){it.state='error';it.error=e.message;uploadState.failed++}
  finally{renderUploadQueue()}
}
async function startUploadQueue(){
  if(uploadState.running)return; if(!uploadState.queue.length){toast('Queue trống');return} uploadState.running=true;uploadState.done=0;uploadState.failed=0;
  const workers=Array.from({length:Math.max(1,Math.min(Number(state.uploadParallel||3),8))},async()=>{while(true){const it=uploadState.queue.find(x=>x.state==='ready'); if(!it)break; await uploadOneQueued(it)}});
  await Promise.all(workers); uploadState.running=false; toast(uploadState.failed?`Upload xong, lỗi ${uploadState.failed}`:'Upload xong'); clearFolderCache(); await softRefresh();
}
function clearUploadQueue(){if(uploadState.running){toast('Đang upload, chưa xoá queue được');return} uploadState.queue=[];uploadState.done=0;uploadState.failed=0;renderUploadQueue()}
$('#fileInput')?.addEventListener('change',e=>{addUploadFiles(e.target.files);e.target.value=''});$('#folderInput')?.addEventListener('change',e=>{addUploadFiles(e.target.files);e.target.value=''});
const upDrop=$('#uploadDrop'); if(upDrop){['dragenter','dragover'].forEach(ev=>upDrop.addEventListener(ev,e=>{e.preventDefault();upDrop.classList.add('drag')}));['dragleave','drop'].forEach(ev=>upDrop.addEventListener(ev,e=>{e.preventDefault();upDrop.classList.remove('drag')}));upDrop.addEventListener('drop',handleUploadDrop);upDrop.addEventListener('click',pickUploadFiles)}
if(grid){
  ['dragenter','dragover'].forEach(ev=>grid.addEventListener(ev,e=>{if(uploadState.running)return;e.preventDefault();e.stopPropagation();grid.classList.add('drag')}));
  ['dragleave','dragend'].forEach(ev=>grid.addEventListener(ev,e=>{e.preventDefault();grid.classList.remove('drag')}));
  grid.addEventListener('drop',handleGridUploadDrop);
}
$('#uploadConflict')?.addEventListener('change',e=>changeUploadConflict(e.target));
if(grid){
  syncControls(); applyView();
  const usedCache=hydrateCache();
  if(usedCache){setTimeout(()=>softRefresh().catch(()=>{}),0)}
  else loadMore(true);
  updateSelectionUI();
}


async function refreshSysTelemetry(){
  const pill=document.getElementById('sysTelemetryPill');
  if(!pill||document.hidden)return;
  try{
    const r=await fetch('/api/sysstats',{cache:'no-store'});
    if(!r.ok)return;
    const d=await r.json();
    const g=d.gpu||{}, ram=d.ram||{}, cpu=d.cpu||{};
    const vramUsed=(Number(g.vramUsedMb||0)/1024).toFixed(1);
    const vramTot=(Number(g.vramTotalMb||0)/1024).toFixed(1);
    const pct=Number(g.vramPercent||0);
    const barCls=pct>=90?'sys-vram-fill danger':(pct>=72?'sys-vram-fill warn':'sys-vram-fill');
    const gpuLabel=g.available
      ? ('GPU '+(g.utilPercent||0)+'% · VRAM '+vramUsed+'/'+vramTot+'G')
      : ('VRAM '+vramUsed+'/'+vramTot+'G · CPU '+(cpu.loadPercent||0)+'%');
    pill.innerHTML='<span>🎮 '+gpuLabel+'</span><span class="sys-vram-bar"><span class="'+barCls+'" style="width:'+Math.min(100,Math.max(4,pct))+'%"></span></span><span>RAM '+(ram.percent||0)+'%</span>';
    pill.title=(g.name||'System')+'\nVRAM: '+(g.vramUsedMb||0)+' / '+(g.vramTotalMb||0)+' MB ('+pct+'%)'+(g.tempC!=null?' · '+g.tempC+'°C':'')+'\nRAM: '+(ram.usedMb||0)+' / '+(ram.totalMb||0)+' MB ('+(ram.percent||0)+'%)';
  }catch(_){}
}
setTimeout(refreshSysTelemetry, 120);
setInterval(refreshSysTelemetry, 5000);

// Terminal + SCM use xterm.js over the persistent WebSocket bridge in /static/terminal_scm.js.

"""



def breadcrumb(rel_path: str, files: FileService) -> str:
    rel_path = rel_path.strip("/")
    parts = [] if not rel_path else rel_path.split("/")
    out = [f'<a href="/">Root</a>']
    acc = []
    for p in parts:
        acc.append(p)
        out.append(f'<span>/</span><a href="/{files.quote_path("/".join(acc))}/">{files.html_escape(p)}</a>')
    return "".join(out)

def page_shell(title: str, body: str, current_path: str, *, config: AppConfig, files: FileService) -> bytes:
    static_root = (Path(__file__).resolve().parents[1] / "static").resolve()
    def asset_url(rel: str) -> str:
        path = (static_root / rel).resolve()
        try:
            path.relative_to(static_root)
            version = files.file_etag(path, path.stat())
        except (OSError, ValueError):
            return f"/static/{rel}"
        return f"/static/{rel}?v={version}"

    xterm_css = asset_url("vendor/xterm.css")
    terminal_css = asset_url("terminal_scm.css")
    xterm_js = asset_url("vendor/xterm.js")
    fit_js = asset_url("vendor/addon-fit.js")
    terminal_js = asset_url("terminal_scm.js")
    chat_css = asset_url("chatbot.css")
    chat_js = asset_url("chatbot.js")
    app = {
        "currentPath": current_path.strip("/"),
        "title": config.title,
        "plugin": {"enabled": files.plugin_enabled()},
        "defaults": {
            "default_sort": config.default_sort,
            "default_view": config.default_view,
            "page_limit": config.page_limit,
            "folders_first": config.folders_first,
            "search_debounce_ms": config.search_debounce_ms,
            "terminal_enabled": config.terminal_enabled,
            "terminal_max_buffer_chars": config.terminal_max_buffer_chars,
            "terminal_start_height_px": config.terminal_start_height_px,
            "terminal_mobile_extra_keys": config.terminal_mobile_extra_keys,
            "thumb_fit": config.thumb_fit,
            "folder_preview_enabled": config.folder_preview_enabled,
            "folder_preview_mode": config.folder_preview_mode,
            "folder_preview_fit": config.folder_preview_fit,
            "folder_preview_rotate": config.folder_preview_rotate,
            "folder_preview_animation": config.folder_preview_animation,
            "folder_preview_interval_ms": config.folder_preview_interval_ms,
            "folder_preview_scan_limit": config.folder_preview_scan_limit,
            "folder_preview_max_items": config.folder_preview_max_items,
            "folder_preview_include_video": config.folder_preview_include_video,
            "upload_auto_start": config.upload_auto_start,
            "upload_parallel": config.upload_parallel,
            "upload_conflict": config.upload_conflict,
        },
    }
    html_doc = f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<title>{files.html_escape(title)}</title>
<style>{CSS}</style>
<link rel="stylesheet" href="{xterm_css}">
<link rel="stylesheet" href="{terminal_css}">
<link rel="stylesheet" href="{chat_css}">
</head>
<body>
{body}
<script>window.APP={files.json_dumps(app)};</script>
<script>{JS}</script>
<script src="{xterm_js}"></script>
<script src="{fit_js}"></script>
<script src="{terminal_js}"></script>
<script src="{chat_js}"></script>
</body>
</html>"""
    return html_doc.encode("utf-8", "surrogateescape")

class ViewService:
    def __init__(self, config: AppConfig, files: FileService, media: MediaService):
        self.cfg = config
        self.files = files
        self.media = media

    def breadcrumb(self, rel_path: str) -> str:
        return breadcrumb(rel_path, self.files)

    def page_shell(self, title: str, body: str, current_path: str = "/") -> bytes:
        return page_shell(title, body, current_path, config=self.cfg, files=self.files)
