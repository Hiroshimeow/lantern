/* Lantern v9.25 — Smooth Lightbox Media Viewer (Zoom/Pan/Rotate/Preload/Video Controls) & Side Preview */
(() => {
  'use strict';

  const MEDIA_KINDS = new Set(['image', 'video', 'audio']);
  const mediaState = {
    kind: null,
    items: [],
    index: -1,
    current: null,
    busy: false,
    cropActive: false,
    zoom: 1,
    rotate: 0,
    panX: 0,
    panY: 0,
    preloaded: new Set(),
    returnFocusEl: null,
  };

  function qSel(s) { return document.querySelector(s); }
  function isMediaKind(kind) { return MEDIA_KINDS.has(kind); }
  function mediaLabel(kind) { return window.LanternI18n?.t(kind, kind) || 'Media'; }

  function encPath(s) { return encodeURIComponent(String(s || '')).replace(/%2F/g, '/'); }
  function fileUrl(rel) { return '/' + encPath(rel); }
  function previewUrl(rel) { return '/api/plugin/preview?p=' + encodeURIComponent(rel); }
  function mediaUrl(it) { return it?.url || fileUrl(it?.rel || ''); }

  function getLoadedItems() {
    return (window.LanternAppState && Array.isArray(window.LanternAppState.items)) ? window.LanternAppState.items : [];
  }

  function findLoadedItem(rel) {
    return getLoadedItems().find(it => !it.special && it.rel === rel) || null;
  }

  function normalizeMediaItem(src, kind, url, name, rel) {
    const r = src?.rel || rel || '';
    return {
      rel: r,
      kind: src?.kind || kind || 'image',
      url: src?.url || url || fileUrl(r),
      name: src?.name || name || r.split('/').pop() || 'Media',
      size_text: src?.sizeText || src?.size_text || '',
      mtime_text: src?.mtimeText || src?.mtime_text || '',
    };
  }

  function collectMediaItems(kind, fallback) {
    const list = getLoadedItems()
      .filter(it => !it.special && it.kind === kind)
      .map(it => normalizeMediaItem(it, kind));
    if (fallback && !list.some(it => it.rel === fallback.rel)) list.unshift(fallback);
    return list;
  }

  function fmtTime(seconds) {
    seconds = Number(seconds || 0);
    if (!seconds) return '';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return (h ? String(h).padStart(2, '0') + ':' : '') + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
  }

  function computeFitScale(img) {
    const body = qSel('#modalBody');
    if (!img || !body || !img.naturalWidth || !img.naturalHeight) return 1;
    const bw = Math.max(100, body.clientWidth - 24);
    const bh = Math.max(100, body.clientHeight - 24);
    const rotated = (Math.abs(mediaState.rotate) % 180) === 90;
    const iw = rotated ? img.naturalHeight : img.naturalWidth;
    const ih = rotated ? img.naturalWidth : img.naturalHeight;
    return Math.min(1, bw / iw, bh / ih);
  }

  function applyImageTransform() {
    const img = qSel('#modalBody img.lightbox-img');
    const lbl = qSel('#modalZoomLabel');
    if (lbl) {
      lbl.textContent = mediaState.zoomMode === 'fit' ? 'Fit' : (Math.round(mediaState.zoom * 100) + '%');
    }
    if (!img) return;
    if (mediaState.zoomMode === 'fit') {
      const rotated = (Math.abs(mediaState.rotate) % 180) === 90;
      const body = qSel('#modalBody');
      if (rotated && body && body.clientWidth && body.clientHeight) {
        img.style.maxWidth = Math.max(80, body.clientHeight - 24) + 'px';
        img.style.maxHeight = Math.max(80, body.clientWidth - 24) + 'px';
      } else {
        img.style.maxWidth = '100%';
        img.style.maxHeight = '100%';
      }
      img.style.transform = `translate3d(0px, 0px, 0) scale(1) rotate(${mediaState.rotate}deg)`;
      return;
    }
    img.style.maxWidth = '100%';
    img.style.maxHeight = '100%';
    img.style.transform = `translate3d(${mediaState.panX}px, ${mediaState.panY}px, 0) scale(${mediaState.zoom}) rotate(${mediaState.rotate}deg)`;
  }

  function resetZoom() {
    mediaState.zoomMode = 'fit';
    mediaState.zoom = 1;
    mediaState.rotate = 0;
    mediaState.panX = 0;
    mediaState.panY = 0;
    applyImageTransform();
  }

  function setActualSize() {
    if (mediaState.kind !== 'image') return;
    const img = qSel('#modalBody img.lightbox-img');
    const fitScale = computeFitScale(img);
    mediaState.zoomMode = 'custom';
    mediaState.zoom = fitScale > 0 ? Number((1 / fitScale).toFixed(2)) : 1;
    mediaState.panX = 0;
    mediaState.panY = 0;
    applyImageTransform();
  }

  function zoomBy(delta) {
    if (mediaState.kind !== 'image') return;
    mediaState.zoomMode = 'custom';
    mediaState.zoom = Math.max(0.25, Math.min(6, Number((mediaState.zoom + delta).toFixed(2))));
    if (mediaState.zoom <= 1) { mediaState.panX = 0; mediaState.panY = 0; }
    applyImageTransform();
  }

  function rotateBy(deg) {
    if (mediaState.kind !== 'image') return;
    mediaState.rotate = (mediaState.rotate + deg) % 360;
    applyImageTransform();
  }

  function setVideoSpeed(val) {
    const v = qSel('#modalBody video');
    const rate = Math.max(0.25, Math.min(4, Number(val) || 1));
    if (v) v.playbackRate = rate;
  }

  function toggleFullscreen() {
    const box = qSel('#modal .modal-box');
    if (!box) return;
    if (document.fullscreenElement) {
      document.exitFullscreen?.().catch(() => {});
    } else {
      box.requestFullscreen?.().catch(() => {});
    }
  }

  function setModalNavState() {
    const multi = mediaState.items.length > 1;
    const prevDis = !multi && mediaState.index <= 0;
    const nextDis = !multi && !window.LanternAppState?.hasMore;
    ['#modalPrevBtn', '#modalPrevFloat'].forEach(sel => { const el = qSel(sel); if (el) el.disabled = prevDis; });
    ['#modalNextBtn', '#modalNextFloat'].forEach(sel => { const el = qSel(sel); if (el) el.disabled = nextDis; });
    const isImg = mediaState.kind === 'image';
    const isVid = mediaState.kind === 'video';
    qSel('#modalImageTools')?.classList.toggle('hidden', !isImg);
    qSel('#modalVideoSpeed')?.classList.toggle('hidden', !isVid);
    qSel('#modalCropBtn')?.classList.toggle('hidden', !isImg);
    qSel('#modalCropOverwriteBtn')?.classList.toggle('hidden', !isImg);
  }

  function prefetchAround() {
    if (mediaState.kind !== 'image' || !mediaState.items.length) return;
    for (const offset of [1, -1, 2, -2]) {
      const idx = mediaState.index + offset;
      if (idx < 0 || idx >= mediaState.items.length) continue;
      const url = mediaUrl(mediaState.items[idx]);
      if (url && !mediaState.preloaded.has(url)) {
        mediaState.preloaded.add(url);
        const im = new Image();
        im.decoding = 'async';
        im.src = url;
      }
    }
  }

  function addVideoPanelItem(panel, label, value) {
    if (value === undefined || value === null || value === '') return;
    const div = document.createElement('div');
    const b = document.createElement('b');
    b.textContent = label + ': ';
    div.append(b, document.createTextNode(String(value)));
    panel.appendChild(div);
  }

  async function loadVideoInfo(it, video, panel) {
    try {
      const r = await fetch('/api/video_info?p=' + encodeURIComponent(it.rel), { cache: 'no-store' });
      const info = await r.json();
      if (!r.ok || info.error || mediaState.current?.rel !== it.rel) return;
      panel.textContent = '';
      if (info.width && info.height) addVideoPanelItem(panel, window.LanternI18n?.t('resolution', 'Resolution'), `${info.width}×${info.height}`);
      if (info.duration) addVideoPanelItem(panel, window.LanternI18n?.t('duration', 'Duration'), fmtTime(info.duration));
      if (info.video_codec) addVideoPanelItem(panel, 'Video', info.video_codec + (info.fps ? ` · ${info.fps} fps` : ''));
      if (info.audio_codec) addVideoPanelItem(panel, 'Audio', info.audio_codec);
      if (info.bitrate_text) addVideoPanelItem(panel, 'Bitrate', info.bitrate_text);
      if (Array.isArray(info.subtitles) && info.subtitles.length) {
        info.subtitles.forEach((sub, idx) => {
          const track = document.createElement('track');
          track.kind = 'subtitles';
          track.label = sub.name || `Sub ${idx + 1}`;
          track.src = sub.url;
          if (idx === 0) track.default = true;
          video.appendChild(track);
        });
        addVideoPanelItem(panel, window.LanternI18n?.t('subtitles', 'Subtitles'), info.subtitles.map(s => s.name).join(', '));
      }
    } catch (_) {}
  }

  function wireImageZoomPan(img, container) {
    let dragging = false;
    let startX = 0, startY = 0, origPanX = 0, origPanY = 0;

    container.onwheel = (ev) => {
      if (mediaState.kind !== 'image') return;
      ev.preventDefault();
      zoomBy(ev.deltaY < 0 ? 0.2 : -0.2);
    };
    img.ondblclick = () => {
      if (mediaState.zoom > 1.05) resetZoom();
      else { mediaState.zoom = 2; applyImageTransform(); }
    };
    img.onpointerdown = (ev) => {
      if (mediaState.zoom <= 1 || ev.button !== 0) return;
      ev.preventDefault();
      dragging = true;
      startX = ev.clientX; startY = ev.clientY;
      origPanX = mediaState.panX; origPanY = mediaState.panY;
      img.classList.add('dragging');
      img.setPointerCapture?.(ev.pointerId);
    };
    img.onpointermove = (ev) => {
      if (!dragging) return;
      mediaState.panX = origPanX + (ev.clientX - startX);
      mediaState.panY = origPanY + (ev.clientY - startY);
      applyImageTransform();
    };
    img.onpointerup = () => {
      dragging = false;
      img.classList.remove('dragging');
    };
  }

  function renderMediaItem(it, index) {
    const modal = qSel('#modal');
    const titleEl = qSel('#modalTitle');
    const metaEl = qSel('#modalMeta');
    const body = qSel('#modalBody');
    if (!modal || !body) return;

    mediaState.current = it;
    mediaState.index = index;
    resetZoom();

    modal.classList.remove('media-image', 'media-video', 'media-audio');
    modal.classList.add('show', 'media-' + it.kind);

    if (titleEl) titleEl.textContent = it.name;
    const totalStr = mediaState.items.length ? `${index + 1}/${mediaState.items.length}` : '1/1';
    const metaParts = [mediaLabel(it.kind), totalStr, it.size_text, it.mtime_text].filter(Boolean);
    if (metaEl) metaEl.textContent = metaParts.join(' · ');

    body.textContent = '';
    const url = mediaUrl(it);

    if (it.kind === 'image') {
      const img = document.createElement('img');
      img.className = 'lightbox-img';
      img.alt = it.name;
      img.decoding = 'async';
      img.src = url;
      img.onload = () => {
        if (mediaState.current?.rel === it.rel && metaEl && img.naturalWidth) {
          const parts = [mediaLabel(it.kind), totalStr, `${img.naturalWidth}×${img.naturalHeight}`, it.size_text, it.mtime_text].filter(Boolean);
          metaEl.textContent = parts.join(' · ');
        }
      };
      img.onerror = () => {
        if (mediaState.current?.rel !== it.rel) return;
        body.textContent = '';
        const box = document.createElement('div');
        box.className = 'lightbox-broken';
        const ic = document.createElement('div');
        ic.style.fontSize = '38px';
        ic.textContent = '🖼️';
        const msg = document.createElement('b');
        msg.textContent = window.LanternI18n?.t('brokenImage', 'This image could not be displayed.');
        const sub = document.createElement('div');
        sub.className = 'sub';
        sub.textContent = it.name || it.rel;
        const dl = document.createElement('a');
        dl.className = 'btn small';
        dl.href = url + (url.includes('?') ? '&' : '?') + 'download=1';
        dl.textContent = '⬇️ ' + (window.LanternI18n?.t('download', 'Download'));
        box.append(ic, msg, sub, dl);
        body.appendChild(box);
      };
      body.appendChild(img);
      wireImageZoomPan(img, body);
      prefetchAround();
    } else if (it.kind === 'video') {
      const wrap = document.createElement('div');
      wrap.className = 'video-wrap';
      const video = document.createElement('video');
      video.src = url;
      video.controls = true;
      video.autoplay = true;
      video.playsInline = true;
      video.preload = 'metadata';
      const speedSel = qSel('#modalVideoSpeed');
      if (speedSel) speedSel.value = '1';
      const panel = document.createElement('div');
      panel.className = 'video-panel';
      wrap.append(video, panel);
      body.appendChild(wrap);
      void loadVideoInfo(it, video, panel);
    } else if (it.kind === 'audio') {
      const audio = document.createElement('audio');
      audio.src = url;
      audio.controls = true;
      audio.autoplay = true;
      audio.style.width = 'min(720px, 90%)';
      body.appendChild(audio);
    }
    setModalNavState();
  }

  function openPreview(kind, url, name, rel = '') {
    const m = qSel('#modal');
    if (m && !m.classList.contains('show')) {
      mediaState.returnFocusEl = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    }
    const found = findLoadedItem(rel);
    const fallback = normalizeMediaItem(found, kind, url, name, rel);
    mediaState.kind = fallback.kind;
    mediaState.items = collectMediaItems(fallback.kind, fallback);
    const idx = Math.max(0, mediaState.items.findIndex(x => x.rel === fallback.rel));
    renderMediaItem(mediaState.items[idx] || fallback, idx);
    qSel('#modalCloseBtn')?.focus?.();
  }

  async function stepMedia(delta, ev) {
    if (ev) { ev.preventDefault(); ev.stopPropagation(); }
    if (!mediaState.kind || mediaState.busy || mediaState.cropActive) return;
    mediaState.busy = true;
    try {
      let nextIdx = mediaState.index + delta;
      if (nextIdx >= mediaState.items.length && window.LanternAppState?.hasMore && typeof window.loadMore === 'function') {
        await window.loadMore(false);
        mediaState.items = collectMediaItems(mediaState.kind, mediaState.current);
      }
      if (!mediaState.items.length) return;
      nextIdx = (nextIdx + mediaState.items.length) % mediaState.items.length;
      renderMediaItem(mediaState.items[nextIdx], nextIdx);
    } finally {
      mediaState.busy = false;
    }
  }

  function closeModal() {
    if (mediaState.cropActive) return;
    const m = qSel('#modal');
    if (!m) return;
    const body = qSel('#modalBody');
    if (body) { body.onwheel = null; body.textContent = ''; }
    m.classList.remove('show', 'media-image', 'media-video', 'media-audio');
    mediaState.kind = null;
    mediaState.current = null;
    mediaState.items = [];
    mediaState.index = -1;
    mediaState.busy = false;
    const ret = mediaState.returnFocusEl;
    mediaState.returnFocusEl = null;
    try { ret?.focus?.(); } catch (_) {}
  }

  async function cropViewedImage(overwriteOriginal = false) {
    const original = mediaState.current;
    if (mediaState.cropActive || original?.kind !== 'image' || !original.rel) return;
    mediaState.cropActive = true;
    try {
      const cropURL = '/static/vendor/lantern-image-crop.min.js';
      const mod = await import(cropURL);
      const openCrop = mod?.openCrop || mod?.default?.openCrop || mod?.default;
      if (typeof openCrop !== 'function') throw new Error('Crop module unavailable');

      const originalExt = (original.rel.match(/\.([^.]+)$/) || [])[1]?.toLowerCase();
      const validType = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp' }[originalExt];
      const canOverwrite = Boolean(validType);
      let originalVersion = null;
      if (canOverwrite) {
        const check = await fetch('/api/image/version?p=' + encodeURIComponent(original.rel), { cache: 'no-store' });
        const st = await check.json().catch(() => ({}));
        if (!check.ok || !st.version) throw new Error(st.error || 'Cannot inspect original image');
        originalVersion = st.version;
      }

      const result = await openCrop({
        src: mediaUrl(original),
        name: original.name || 'Image',
        allowOverwrite: canOverwrite,
        preferredAction: overwriteOriginal ? 'overwrite' : 'copy',
      });
      if (!result) return;

      const persistOverwrite = result.action === 'overwrite' || (!result.action && overwriteOriginal);
      if (persistOverwrite) {
        if (!validType || validType !== result.blob.type) {
          throw new Error('Crop output format differs from original; use Crop (Save As)');
        }
        if (!confirm(window.LanternI18n?.t('cropConfirmOver', 'Overwrite original image? All files using this image will change. This cannot be undone. EXIF/ICC metadata may be lost.'))) {
          return;
        }
        const response = await fetch('/api/image/overwrite?p=' + encodeURIComponent(original.rel), {
          method: 'POST',
          credentials: 'same-origin',
          cache: 'no-store',
          headers: { 'Content-Type': result.blob.type, 'If-Match': originalVersion },
          body: result.blob,
        });
        const update = await response.json().catch(() => ({}));
        if (!response.ok || update.error) throw new Error(update.error || ('Overwrite HTTP ' + response.status));
        if (typeof window.toast === 'function') window.toast(window.LanternI18n?.t('cropSavedOver', 'Original image overwritten'));
        if (typeof window.clearFolderCache === 'function') window.clearFolderCache();
        if (typeof window.softRefresh === 'function') await window.softRefresh().catch(() => {});
        mediaState.cropActive = false;
        const refreshedUrl = fileUrl(original.rel) + '?v=' + encodeURIComponent(update.version || String(Date.now()));
        openPreview('image', refreshedUrl, original.name, original.rel);
        const updated = mediaState.items[mediaState.index];
        if (updated?.rel === original.rel) {
          updated.url = refreshedUrl;
          renderMediaItem(updated, mediaState.index);
        }
        return;
      }

      const pieces = original.rel.split('/');
      const originalName = pieces.pop() || 'image';
      const directory = pieces.join('/');
      const stem = originalName.replace(/\.[^.]+$/, '');
      const ext = result.extension || originalExt || 'png';
      const name = `${stem}-cropped-${Date.now()}-${Math.random().toString(36).slice(2, 8)}.${ext}`;
      if (typeof window.toast === 'function') window.toast('Saving cropped copy…');
      const response = await fetch('/api/upload?path=' + encodeURIComponent(directory) + '&name=' + encodeURIComponent(name) + '&conflict=rename', {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: { 'Content-Type': result.blob.type },
        body: result.blob,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.error || !data.file) throw new Error(data.error || ('Upload HTTP ' + response.status));
      const newRel = decodeURIComponent(String(data.file).replace(/^\//, ''));
      if (typeof window.toast === 'function') window.toast('New image created: ' + newRel);
      if (typeof window.clearFolderCache === 'function') window.clearFolderCache();
      if (typeof window.softRefresh === 'function') await window.softRefresh().catch(() => {});
      mediaState.cropActive = false;
      openPreview('image', fileUrl(newRel), newRel.split('/').pop(), newRel);
    } catch (err) {
      if (err && err.message !== 'cancelled' && typeof window.toast === 'function') {
        window.toast('Crop failed: ' + err.message);
      }
    } finally {
      mediaState.cropActive = false;
    }
  }

  function handleModalKeydown(e) {
    const modal = qSel('#modal');
    if (!modal || !modal.classList.contains('show') || mediaState.cropActive) return false;
    if (e.key === 'Escape') { e.preventDefault(); closeModal(); return true; }
    if (e.key === 'Tab') {
      const focusables = Array.from(modal.querySelectorAll('button:not([disabled]):not(.hidden), select:not([disabled]):not(.hidden), a[href], video, audio'))
        .filter(el => el.offsetParent !== null);
      if (focusables.length) {
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); return true; }
        if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); return true; }
      }
      return false;
    }
    if (e.key === 'ArrowLeft' && !e.shiftKey) { e.preventDefault(); void stepMedia(-1); return true; }
    if (e.key === 'ArrowRight' && !e.shiftKey) { e.preventDefault(); void stepMedia(1); return true; }
    if (e.key === 'f' || e.key === 'F') { e.preventDefault(); toggleFullscreen(); return true; }
    if (mediaState.kind === 'image') {
      if (e.key === '+' || e.key === '=') { e.preventDefault(); zoomBy(0.25); return true; }
      if (e.key === '-') { e.preventDefault(); zoomBy(-0.25); return true; }
      if (e.key === '0') { e.preventDefault(); resetZoom(); return true; }
      if (e.key === '1') { e.preventDefault(); setActualSize(); return true; }
      if (e.key === 'r' || e.key === 'R') { e.preventDefault(); rotateBy(90); return true; }
    } else if (mediaState.kind === 'video') {
      const v = qSel('#modalBody video');
      if (v) {
        if (e.key === ' ' || e.key === 'k' || e.key === 'K') { e.preventDefault(); if (v.paused) v.play(); else v.pause(); return true; }
        if (e.key === 'j' || e.key === 'J' || (e.shiftKey && e.key === 'ArrowLeft')) { e.preventDefault(); v.currentTime = Math.max(0, v.currentTime - 10); return true; }
        if (e.key === 'l' || e.key === 'L' || (e.shiftKey && e.key === 'ArrowRight')) { e.preventDefault(); v.currentTime = Math.min(v.duration || 0, v.currentTime + 10); return true; }
        if (e.key === 'm' || e.key === 'M') { e.preventDefault(); v.muted = !v.muted; return true; }
      }
    }
    return false;
  }

  window.LanternMedia = {
    state: mediaState,
    isMediaKind,
    openPreview,
    closeModal,
    stepMedia,
    cropViewedImage,
    zoomBy,
    resetZoom,
    setActualSize,
    rotateBy,
    setVideoSpeed,
    toggleFullscreen,
    handleModalKeydown,
    fileUrl,
    previewUrl,
  };

  window.openPreview = openPreview;
  window.closeModal = closeModal;
  window.stepMedia = stepMedia;
  window.cropViewedImage = cropViewedImage;
})();
