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
    if (previous?.table === table) { previous.updatePan?.(); return; }
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
    const getScroller = () => port.matches('.table-wrap')
      ? port : (port.querySelector('.table-wrapper') || port);
    const context = {port, table, getScroller, overlay, style:null, widths:null,
      controller:new AbortController(), observer:null, observedScroller:null, updatePan:null, handleScrollGuard:null};
    contexts.set(port, context);
    const updatePan = () => {
      const scroller = getScroller();
      drag.hidden = scroller.scrollWidth <= scroller.clientWidth + 3;
      if (context.observer && context.observedScroller !== scroller) {
        if (context.observedScroller && context.observedScroller !== port && context.observedScroller !== table)
          context.observer.unobserve(context.observedScroller);
        if (scroller !== port) context.observer.observe(scroller);
        context.observedScroller = scroller;
      }
    };
    context.updatePan = updatePan;
    if (typeof ResizeObserver !== 'undefined') {
      context.observer = new ResizeObserver(updatePan);
      context.observer.observe(table);
      context.observer.observe(port);
    }
    // Milkdown table operations select rows/columns before mutating them.
    // ProseMirror scrolls that selection into view, which resets the inner
    // horizontal scroller to zero on wide tables and sends the menu off-screen.
    // Capture before the native handler and restore again after its click.
    const protectHandleScroll = guard => {
      if (!guard) return;
      let frames = 30;
      const restore = () => {
        // Milkdown can replace the entire table block after add/delete. Resolve
        // the logical table again from the still-mounted editor host + index.
        let currentPort = port.isConnected ? port : null;
        if (!currentPort && guard.host?.isConnected) {
          currentPort = guard.host.querySelectorAll('.milkdown-table-block')[guard.index] || null;
        }
        if (currentPort) {
          const scroller = currentPort.matches('.table-wrap')
            ? currentPort : (currentPort.querySelector('.table-wrapper') || currentPort);
          if (scroller?.isConnected) {
            const maxLeft = Math.max(0, scroller.scrollWidth - scroller.clientWidth);
            const maxTop = Math.max(0, scroller.scrollHeight - scroller.clientHeight);
            scroller.scrollLeft = guard.stickRight ? maxLeft : Math.min(guard.left, maxLeft);
            scroller.scrollTop = Math.min(guard.top, maxTop);
          }
        }
        if (--frames > 0) requestAnimationFrame(restore);
      };
      requestAnimationFrame(restore);
    };
    port.addEventListener('pointerdown', event => {
      if (!event.target.closest?.('.milkdown-table-block .handle')) return;
      const scroller = getScroller();
      if (scroller === port) return;
      const host = port.closest('.md-visual-host');
      const peers = host ? [...host.querySelectorAll('.milkdown-table-block')] : [];
      const maxLeft = Math.max(0, scroller.scrollWidth - scroller.clientWidth);
      context.handleScrollGuard = {
        left:scroller.scrollLeft, top:scroller.scrollTop, host,
        stickRight:maxLeft - scroller.scrollLeft <= 6,
        index:Math.max(0, peers.indexOf(port)),
      };
      // Native table commands run on pointerdown/click and can replace DOM.
      // Start restoration after the current event has completed.
      protectHandleScroll(context.handleScrollGuard);
    }, {capture:true,signal:context.controller.signal});
    port.addEventListener('click', event => {
      if (!event.target.closest?.('.milkdown-table-block .handle')) return;
      protectHandleScroll(context.handleScrollGuard);
    }, {signal:context.controller.signal});
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
      const scroller = getScroller();
      panning = {x: event.clientX, scroll: scroller.scrollLeft, scroller};
      drag.setPointerCapture(event.pointerId);
      drag.classList.add('lantern-panning');
      event.preventDefault();event.stopPropagation();
    }, {signal:context.controller.signal});
    drag.addEventListener('pointermove', event => {
      if (!panning) return;
      panning.scroller.scrollLeft = panning.scroll - (event.clientX - panning.x);
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
