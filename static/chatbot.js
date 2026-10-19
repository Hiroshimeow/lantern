(() => {
  'use strict';

  const S = {
    ws: null,
    open: false,
    connected: false,
    authenticated: null,
    reconnect: null,
    reconnectDelay: 500,
    sessions: [],
    active: null,
    role: null,
    ownershipEpoch: null,
    term: null,
    fit: null,
    host: null,
    ro: null,
    resizeTimer: null,
    contextTimer: null,
    creating: false,
    expanded: false,
  };

  const q = (sel, root = document) => root.querySelector(sel);
  const activeKey = () => 'lantern-pi-active:' + location.origin;

  function create(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function currentMarkdownContext(path) {
    const mode = String(globalThis.__lanternMdVisual?.state?.mode || 'preview');
    let bookmark = null;
    try { bookmark = globalThis.LanternAnchorBridge?.capture?.(mode) || null; } catch {}
    if (!bookmark && mode === 'source') {
      const area = q('textarea.md-source-area');
      if (area) {
        const before = area.value.slice(0, area.selectionStart);
        bookmark = {
          line: before.split('\n').length,
          selectedText: area.value.slice(area.selectionStart, area.selectionEnd),
        };
      }
    }
    const clean = String(path || '').replace(/^\/+/, '');
    const slash = clean.lastIndexOf('/');
    const context = {
      kind: 'markdown',
      path: clean,
      folder: slash >= 0 ? clean.slice(0, slash) : '',
      markdownMode: mode === 'paged' ? 'visual' : mode,
    };
    if (bookmark?.line) context.line = Number(bookmark.line);
    if (bookmark?.selectedText) context.selectedText = String(bookmark.selectedText);
    return context;
  }

  function currentBrowserContext() {
    if (globalThis.LanternChatContext?.capture) {
      try {
        const custom = globalThis.LanternChatContext.capture();
        if (custom && typeof custom === 'object') return custom;
      } catch {}
    }
    const folder = String(
      globalThis.currentPath?.() ?? globalThis.APP?.currentPath ?? ''
    ).replace(/^\/+/, '');
    let selected = [];
    try { selected = globalThis.selectedArray?.() || []; } catch {}
    const context = selected.length === 1
      ? {kind: 'file', path: String(selected[0]), folder}
      : {kind: 'folder', folder};
    if (selected.length > 1) context.attachments = selected.map(String);
    return context;
  }

  function captureContext() {
    const body = document.body;
    const kind = body?.dataset?.lanternChatKind;
    const path = body?.dataset?.lanternChatPath;
    return kind === 'markdown' && path
      ? currentMarkdownContext(path)
      : currentBrowserContext();
  }

  function contextLabel(context) {
    const path = context?.path || context?.folder || '/';
    const line = context?.line ? ':' + context.line : '';
    const mode = context?.markdownMode ? ' · ' + context.markdownMode : '';
    return String(path || '/') + line + mode;
  }

  function refreshContextLabel() {
    const node = q('#lanternChatPath');
    if (!node) return;
    const label = contextLabel(captureContext());
    node.textContent = label;
    node.title = label;
  }

  function setStatus(text, kind = '') {
    const node = q('#lanternChatStatus');
    if (!node) return;
    node.textContent = text;
    if (kind) node.dataset.kind = kind;
    else delete node.dataset.kind;
  }

  function send(payload) {
    if (!S.ws || S.ws.readyState !== WebSocket.OPEN) return false;
    S.ws.send(JSON.stringify(payload));
    return true;
  }

  function activeSession() {
    return S.sessions.find(item => item.sessionId === S.active) || null;
  }

  function updateControls() {
    const session = activeSession();
    const select = q('#lanternPiSessions');
    const fresh = q('#lanternPiNew');
    const takeover = q('#lanternPiTakeover');
    const stop = q('#lanternPiStop');
    if (select) select.disabled = !S.connected || S.authenticated === false;
    if (fresh) fresh.disabled = !S.connected || S.authenticated === false || S.creating;
    if (takeover) {
      takeover.hidden = S.role !== 'viewer';
      takeover.disabled = !session?.running || !S.connected;
    }
    if (stop) stop.disabled = !session?.running || S.role !== 'writer' || !S.connected;
    const role = q('#lanternPiRole');
    if (role) role.textContent = session
      ? (session.running ? (S.role === 'writer' ? '● Writer' : '○ Viewer') : 'Exited')
      : 'No session';
  }

  function renderSessions() {
    const select = q('#lanternPiSessions');
    if (!select) return;
    select.textContent = '';
    for (const session of S.sessions) {
      const opt = document.createElement('option');
      opt.value = session.sessionId;
      const ctx = session.contextRef || {};
      const label = ctx.path || ctx.folder || session.cwd || session.sessionId.slice(0, 8);
      opt.textContent = (session.running ? '● ' : '○ ') + label;
      select.append(opt);
    }
    if (S.active && S.sessions.some(item => item.sessionId === S.active)) {
      select.value = S.active;
    }
    updateControls();
  }

  function ensureTerminal() {
    if (S.term) return;
    if (!globalThis.Terminal || !globalThis.FitAddon?.FitAddon) {
      setStatus('xterm.js assets are unavailable.', 'error');
      return;
    }
    const host = q('#lanternPiHost');
    if (!host) return;
    const term = new Terminal({
      cursorBlink: true,
      scrollback: 8000,
      fontSize: 13,
      fontFamily: '"Cascadia Mono","JetBrains Mono",Consolas,ui-monospace,monospace',
      theme: {
        background: '#050709',
        foreground: '#e6edf3',
        cursor: '#73d18a',
        selectionBackground: '#315c44',
      },
    });
    const fit = new FitAddon.FitAddon();
    term.loadAddon(fit);
    term.open(host);
    term.onData(data => {
      const session = activeSession();
      if (!session?.running || S.role !== 'writer' || !Number.isInteger(S.ownershipEpoch)) return;
      send({
        type: 'pi_session_input',
        sessionId: session.sessionId,
        generation: session.generation,
        ownershipEpoch: S.ownershipEpoch,
        data,
      });
    });
    const ro = new ResizeObserver(() => scheduleFit(false));
    ro.observe(host);
    S.term = term;
    S.fit = fit;
    S.host = host;
    S.ro = ro;
    setTimeout(() => scheduleFit(false), 20);
  }

  function scheduleFit(focus = false) {
    if (!S.term || !S.fit || !S.host || S.host.offsetWidth <= 0 || S.host.offsetHeight <= 0) return;
    requestAnimationFrame(() => {
      try {
        S.fit.fit();
        if (focus) S.term.focus();
      } catch { return; }
      const session = activeSession();
      if (!session?.running || S.role !== 'writer' || !Number.isInteger(S.ownershipEpoch)) return;
      clearTimeout(S.resizeTimer);
      S.resizeTimer = setTimeout(() => {
        send({
          type: 'pi_session_resize',
          sessionId: session.sessionId,
          generation: session.generation,
          ownershipEpoch: S.ownershipEpoch,
          cols: S.term.cols || 80,
          rows: S.term.rows || 24,
        });
      }, 80);
    });
  }

  function attachSession(sessionId) {
    const session = S.sessions.find(item => item.sessionId === sessionId);
    if (!session?.running) {
      if (session) setStatus('Selected Pi session has exited.', 'warn');
      return;
    }
    if (S.active && S.active !== sessionId) {
      send({type: 'pi_session_detach', sessionId: S.active});
    }
    S.active = sessionId;
    S.role = null;
    S.ownershipEpoch = null;
    try { sessionStorage.setItem(activeKey(), sessionId); } catch {}
    renderSessions();
    setStatus('Attaching Pi session…');
    send({
      type: 'pi_session_attach',
      sessionId: session.sessionId,
      generation: session.generation,
    });
  }

  function createSession() {
    if (!S.connected || S.authenticated === false || S.creating) return;
    ensureTerminal();
    if (!S.term) return;
    S.creating = true;
    updateControls();
    const context = captureContext();
    const label = context.path || context.folder || '/';
    setStatus('Starting native Pi…');
    send({
      type: 'pi_session_create',
      context,
      title: 'Pi · ' + label,
      cols: S.term.cols || 100,
      rows: S.term.rows || 32,
    });
  }

  function stopSession() {
    const session = activeSession();
    if (!session?.running || S.role !== 'writer') return;
    send({
      type: 'pi_session_stop',
      sessionId: session.sessionId,
      generation: session.generation,
    });
    setStatus('Stopping Pi…', 'warn');
  }

  function takeover() {
    const session = activeSession();
    if (!session?.running || S.role !== 'viewer') return;
    send({
      type: 'pi_session_takeover',
      sessionId: session.sessionId,
      generation: session.generation,
    });
    setStatus('Taking control…');
  }

  function sendKey(key, modifiers = {}) {
    const session = activeSession();
    if (!session?.running || S.role !== 'writer' || !Number.isInteger(S.ownershipEpoch)) return;
    send({
      type: 'pi_session_key',
      sessionId: session.sessionId,
      generation: session.generation,
      ownershipEpoch: S.ownershipEpoch,
      key,
      modifiers,
    });
    S.term?.focus();
  }

  function onMessage(message) {
    const type = String(message?.type || '');
    if (type === 'terminal_auth') {
      S.authenticated = Boolean(message.authenticated);
      if (!S.authenticated) setStatus('Terminal is locked. Unlock Terminal first.', 'warn');
      updateControls();
      return;
    }
    if (type === 'pi_session_state') {
      S.sessions = Array.isArray(message.sessions) ? message.sessions : [];
      let wanted = '';
      try { wanted = sessionStorage.getItem(activeKey()) || ''; } catch {}
      const candidate = S.sessions.find(item => item.sessionId === wanted && item.running)
        || S.sessions.find(item => item.running);
      renderSessions();
      if (candidate) attachSession(candidate.sessionId);
      else if (S.open && S.authenticated !== false) createSession();
      return;
    }
    if (type === 'pi_session_created') {
      S.creating = false;
      const session = message.session || {};
      S.sessions = [...S.sessions.filter(item => item.sessionId !== session.sessionId), session];
      renderSessions();
      attachSession(session.sessionId);
      return;
    }
    if (type === 'pi_session_replay') {
      if (message.sessionId !== S.active) return;
      S.role = String(message.role || 'viewer');
      S.ownershipEpoch = Number(message.ownershipEpoch);
      ensureTerminal();
      if (S.term) {
        S.term.reset();
        if (message.truncated) S.term.write('\x1b[90m[Earlier Pi history omitted from display; preserved on server]\x1b[0m\r\n');
        S.term.write(String(message.output || ''), () => scheduleFit(true));
      }
      setStatus(S.role === 'writer' ? 'Native Pi · Writer' : 'Native Pi · Viewer');
      updateControls();
      return;
    }
    if (type === 'pi_session_output') {
      if (message.sessionId === S.active) S.term?.write(String(message.data || ''));
      return;
    }
    if (type === 'pi_session_ownership') {
      if (message.sessionId !== S.active) return;
      S.role = String(message.role || 'viewer');
      S.ownershipEpoch = Number(message.ownershipEpoch);
      setStatus(S.role === 'writer' ? 'Native Pi · Writer' : 'Native Pi · Viewer');
      updateControls();
      if (S.role === 'writer') scheduleFit(true);
      return;
    }
    if (type === 'pi_session_exit') {
      const session = S.sessions.find(item => item.sessionId === message.sessionId);
      if (session) {
        session.running = false;
        session.exitCode = message.exitCode;
      }
      if (message.sessionId === S.active) {
        S.term?.write('\r\n\x1b[90m[Pi exited' + (message.exitCode == null ? '' : ' with code ' + message.exitCode) + ']\x1b[0m\r\n');
        setStatus('Pi exited.', 'warn');
      }
      renderSessions();
      return;
    }
    if (type === 'pi_session_stopped') {
      const stopped = message.session || {};
      S.sessions = S.sessions.map(item => item.sessionId === stopped.sessionId ? stopped : item);
      renderSessions();
      setStatus('Pi stopped.', 'warn');
      return;
    }
    if (type === 'pi_session_error') {
      S.creating = false;
      if (message.code === 'terminal_auth_required') {
        S.authenticated = false;
        setStatus('Terminal is locked. Unlock Terminal first.', 'warn');
      } else {
        setStatus(String(message.error || 'Pi session error'), 'error');
      }
      updateControls();
    }
  }

  function connect() {
    if (S.ws && [WebSocket.OPEN, WebSocket.CONNECTING].includes(S.ws.readyState)) return;
    clearTimeout(S.reconnect);
    const scheme = location.protocol === 'https:' ? 'wss://' : 'ws://';
    const ws = new WebSocket(scheme + location.host + '/ws?v=2');
    S.ws = ws;
    setStatus('Connecting…');
    ws.onopen = () => {
      if (S.ws !== ws) return;
      S.connected = true;
      S.reconnectDelay = 500;
      send({type: 'terminal_client_v2'});
      send({type: 'pi_session_sync'});
      updateControls();
    };
    ws.onmessage = event => {
      let message;
      try { message = JSON.parse(event.data); } catch { return; }
      onMessage(message);
    };
    ws.onerror = () => { try { ws.close(); } catch {} };
    ws.onclose = () => {
      if (S.ws !== ws) return;
      S.connected = false;
      S.ws = null;
      S.role = null;
      S.ownershipEpoch = null;
      updateControls();
      if (S.open) {
        setStatus('Disconnected. Reconnecting…', 'warn');
        S.reconnect = setTimeout(connect, S.reconnectDelay);
        S.reconnectDelay = Math.min(5000, Math.round(S.reconnectDelay * 1.6));
      }
    };
  }

  function disconnect() {
    clearTimeout(S.reconnect);
    S.reconnect = null;
    if (S.active) send({type: 'pi_session_detach', sessionId: S.active});
    const ws = S.ws;
    S.ws = null;
    S.connected = false;
    if (ws) try { ws.close(); } catch {}
    S.role = null;
    S.ownershipEpoch = null;
    updateControls();
  }

  function setExpanded(value) {
    S.expanded = Boolean(value);
    const drawer = q('#lanternChatDrawer');
    if (drawer) drawer.dataset.expanded = S.expanded ? 'true' : 'false';
    q('#lanternPiExpand').textContent = S.expanded ? 'Dock' : 'Expand';
    setTimeout(() => scheduleFit(true), 30);
  }

  function setOpen(value) {
    buildUi();
    S.open = Boolean(value);
    const drawer = q('#lanternChatDrawer');
    if (drawer) drawer.dataset.open = S.open ? 'true' : 'false';
    document.body.classList.toggle('lantern-chat-open', S.open);
    if (S.open) {
      ensureTerminal();
      refreshContextLabel();
      connect();
      clearInterval(S.contextTimer);
      S.contextTimer = setInterval(refreshContextLabel, 800);
      setTimeout(() => scheduleFit(true), 40);
    } else {
      clearInterval(S.contextTimer);
      S.contextTimer = null;
      disconnect();
    }
  }

  function buildUi() {
    if (q('#lanternChatDrawer')) return;
    const drawer = create('aside', 'lantern-chat-drawer');
    drawer.id = 'lanternChatDrawer';
    drawer.dataset.open = 'false';
    drawer.dataset.expanded = 'false';
    drawer.setAttribute('aria-label', 'LanternBot Native Pi');

    const head = create('div', 'lantern-chat-head');
    const title = create('div', 'lantern-chat-title', 'LanternBot · Pi');
    const path = create('div', 'lantern-chat-path', '/');
    path.id = 'lanternChatPath';

    const select = create('select', 'lantern-pi-sessions');
    select.id = 'lanternPiSessions';
    select.title = 'Attach or switch Pi session';
    select.addEventListener('change', () => attachSession(select.value));

    const fresh = create('button', 'lantern-chat-iconbtn', 'New Pi');
    fresh.id = 'lanternPiNew';
    fresh.type = 'button';
    fresh.addEventListener('click', createSession);

    const takeover = create('button', 'lantern-chat-iconbtn', 'Take over');
    takeover.id = 'lanternPiTakeover';
    takeover.type = 'button';
    takeover.hidden = true;
    takeover.addEventListener('click', takeover);

    const stop = create('button', 'lantern-chat-iconbtn danger', 'Stop');
    stop.id = 'lanternPiStop';
    stop.type = 'button';
    stop.addEventListener('click', stopSession);

    const expand = create('button', 'lantern-chat-iconbtn', 'Expand');
    expand.id = 'lanternPiExpand';
    expand.type = 'button';
    expand.addEventListener('click', () => setExpanded(!S.expanded));

    const close = create('button', 'lantern-chat-iconbtn lantern-chat-close', '×');
    close.type = 'button';
    close.setAttribute('aria-label', 'Close Pi');
    close.addEventListener('click', () => setOpen(false));

    head.append(title, path, select, fresh, takeover, stop, expand, close);

    const statusRow = create('div', 'lantern-chat-status');
    const status = create('span', '', 'Native Pi idle');
    status.id = 'lanternChatStatus';
    const role = create('span', 'lantern-pi-role', 'No session');
    role.id = 'lanternPiRole';
    statusRow.append(status, role);

    const host = create('div', 'lantern-pi-host');
    host.id = 'lanternPiHost';

    const keys = create('div', 'lantern-pi-mobile-keys');
    for (const [label, key, mods] of [
      ['Esc', 'Escape', {}], ['Tab', 'Tab', {}], ['↑', 'ArrowUp', {}],
      ['↓', 'ArrowDown', {}], ['←', 'ArrowLeft', {}], ['→', 'ArrowRight', {}],
      ['Ctrl+C', 'c', {ctrl: true}], ['Ctrl+P', 'p', {ctrl: true}],
    ]) {
      const button = create('button', '', label);
      button.type = 'button';
      button.addEventListener('click', () => sendKey(key, mods));
      keys.append(button);
    }

    drawer.append(head, statusRow, host, keys);
    document.body.append(drawer);
  }

  function injectLaunch() {
    if (q('.lantern-chat-launch')) return;
    const button = create('button', 'lantern-chat-launch', '✦ Pi');
    button.type = 'button';
    button.title = 'Open native Pi';
    button.addEventListener('click', () => setOpen(!S.open));
    const actions = q('.top .actions');
    if (actions) {
      button.classList.add('btn');
      actions.append(button);
      return;
    }
    const bar = q('.md-bar .bar-top');
    if (bar) {
      button.classList.add('btn');
      const grow = q('.grow', bar);
      if (grow?.nextSibling) bar.insertBefore(button, grow.nextSibling);
      else bar.append(button);
      return;
    }
    button.classList.add('lantern-chat-float');
    button.textContent = 'Pi';
    document.body.append(button);
  }

  function init() {
    buildUi();
    injectLaunch();
    globalThis.LanternChat = {
      open: () => setOpen(true),
      close: () => setOpen(false),
      captureContext,
      refreshContext: refreshContextLabel,
    };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, {once: true});
  } else {
    init();
  }
})();
