/* Drag wide Markdown tables horizontally; drag near a header's right edge
   to resize columns. Widths are visual only: GFM cannot serialize them. */
(() => {
  'use strict';
  const PORTS = '.md-preview .table-wrap, .md-visual-host .milkdown-table-block';
  const contexts = new Map();
  let counter = 0, scheduled = false;
  function attach(port) {
    const table = port.matches('.table-wrap') ? port.querySelector('table') : port.querySelector('table.children');
    const previous = contexts.get(port);
    if (previous?.table === table) return;
    if (previous) { previous.observer?.disconnect(); previous.controller.abort(); previous.style?.remove(); previous.overlay.remove(); contexts.delete(port); }
    if (!table) return;
    const id = 'lantern-table-' + ++counter;
    port.classList.add('lantern-table-interactive', id);
    const overlay = document.createElement('div');
    overlay.className = 'lantern-table-overlay';
    const drag = document.createElement('button');
    drag.type = 'button';drag.className = 'lantern-table-pan';
    drag.textContent = '↔ Kéo bảng';
    drag.title = 'Kéo để cuộn ngang bảng; kéo sát mép phải tiêu đề cột để đổi độ rộng';
    drag.setAttribute('aria-label', 'Kéo bảng sang trái hoặc phải');
    overlay.append(drag);
    port.prepend(overlay);
    const marker = document.createElement('div');
    marker.className = 'lantern-table-resize-marker';marker.hidden = true;
    overlay.append(marker);
    const context = {port, table, overlay, style:null, widths:null, controller:new AbortController(), observer:null, updatePan:null};
    contexts.set(port, context);
    const updatePan = () => { drag.hidden = port.scrollWidth <= port.clientWidth + 3; };
    context.updatePan = updatePan;
    if (typeof ResizeObserver !== 'undefined') {
      context.observer = new ResizeObserver(updatePan);
      context.observer.observe(table);
      context.observer.observe(port);
    }
    const headerCells = () => [...(table.rows[0]?.cells || [])];
    const minimum = 90, maximum = 900;
    // Rules live outside contenteditable; resizing must never mutate document
    // nodes, trigger Milkdown saves, or add unsupported Markdown width syntax.
    const applyWidths = () => {
      if (!context.style) {
        context.style = document.createElement('style');
        document.head.append(context.style);
      }
      const total = context.widths.reduce((sum, w) => sum + w, 0);
      context.style.textContent = `.${id} table{table-layout:fixed!important;width:${total}px!important;min-width:${total}px!important}` +
        context.widths.map((w, i) => `.${id} table tr>:nth-child(${i + 1}){width:${w}px!important;min-width:${w}px!important;max-width:${w}px!important}`).join('');
      updatePan();
    };
    const nearEdge = event => {
      const cell = event.target.closest?.('th');
      if (!cell || !table.contains(cell) || !headerCells().includes(cell)) return null;
      return Math.abs(cell.getBoundingClientRect().right - event.clientX) <= 10 ? cell : null;
    };
    let resizing = null;
    port.addEventListener('pointermove', event => {
      if (resizing) {
        const next = Math.max(minimum, Math.min(maximum, resizing.width + event.clientX - resizing.x));
        context.widths[resizing.index] = Math.round(next);
        applyWidths();
        event.preventDefault();return;
      }
      if (event.buttons) return;
      const cell = nearEdge(event);
      port.classList.toggle('lantern-table-near-edge', !!cell);
      marker.hidden = !cell;
      if (cell) {
        // Place the marker at the right edge in the scroll container's space.
        marker.style.left = cell.getBoundingClientRect().right - port.getBoundingClientRect().left + 'px';
        marker.style.top = cell.getBoundingClientRect().top - port.getBoundingClientRect().top + 'px';
        marker.style.height = cell.getBoundingClientRect().height + 'px';
      }
    }, {signal:context.controller.signal});
    port.addEventListener('pointerdown', event => {
      if (event.button !== 0 || event.target.closest?.('.lantern-table-overlay')) return;
      const cell = nearEdge(event);
      if (!cell) return;
      const headers = headerCells();
      if (!headers.length || headers.some(h => h.colSpan !== 1)) return;
      const index = headers.indexOf(cell);
      context.widths ||= headers.map(h => Math.max(minimum, Math.round(h.getBoundingClientRect().width)));
      resizing = {index, x:event.clientX, width:context.widths[index]};
      marker.hidden = true;
      port.setPointerCapture(event.pointerId);
      event.preventDefault();event.stopPropagation();
    }, {capture:true,signal:context.controller.signal});
    const endResize = event => {
      if (!resizing) return;
      resizing = null;
      port.classList.remove('lantern-table-near-edge');
      if (port.hasPointerCapture(event.pointerId)) port.releasePointerCapture(event.pointerId);
      updatePan();
    };
    port.addEventListener('pointerup', endResize, {signal:context.controller.signal});
    port.addEventListener('pointercancel', endResize, {signal:context.controller.signal});
    port.addEventListener('pointerleave', () => { if (!resizing) marker.hidden = true; }, {signal:context.controller.signal});
    let panning = null;
    drag.addEventListener('pointerdown', event => {
      if (event.button !== 0 || drag.hidden) return;
      panning = {x: event.clientX, scroll: port.scrollLeft};
      drag.setPointerCapture(event.pointerId);
      drag.classList.add('lantern-panning');
      event.preventDefault();event.stopPropagation();
    }, {signal:context.controller.signal});
    drag.addEventListener('pointermove', event => {
      if (!panning) return;
      port.scrollLeft = panning.scroll - (event.clientX - panning.x);
      event.preventDefault();
    }, {signal:context.controller.signal});
    function endPan(event) {
      if (!panning) return;
      panning = null;drag.classList.remove('lantern-panning');
      if (drag.hasPointerCapture(event.pointerId)) drag.releasePointerCapture(event.pointerId);
    }
    drag.addEventListener('pointerup', endPan, {signal:context.controller.signal});
    drag.addEventListener('pointercancel', endPan, {signal:context.controller.signal});
    port.addEventListener('pointerenter', updatePan, {signal:context.controller.signal});
    requestAnimationFrame(updatePan);
  }
  function scan() {
    scheduled = false;
    for (const [port, context] of contexts) {
      if (port.isConnected) continue;
      context.observer?.disconnect();context.controller.abort();context.style?.remove();contexts.delete(port);
    }
    document.querySelectorAll(PORTS).forEach(attach);
  }
  function schedule() {
    if (scheduled) return;
    scheduled = true;requestAnimationFrame(scan);
  }
  function init() {
    scan();
    const content = document.querySelector('.content');
    if (!content) return;
    // Milkdown may populate or replace a table within an existing wrapper.
    // Coalesce every subtree insertion/removal into one animation-frame scan.
    new MutationObserver(schedule).observe(content, {childList: true, subtree: true});
    window.addEventListener('resize', () => {
      for (const context of contexts.values()) context.updatePan();
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
