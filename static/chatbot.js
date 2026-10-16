(() => {
  'use strict';

  const S = {
    ws: null,
    open: false,
    connected: false,
    authenticated: null,
    streaming: false,
    reconnect: null,
    reconnectDelay: 500,
    assistant: null,
    toolRows: new Map(),
    state: null,
    models: [],
    contextTimer: null,
  };

  const q = (sel, root = document) => root.querySelector(sel);

  function textContentOf(content) {
    if (typeof content === 'string') return content;
    if (!Array.isArray(content)) return '';
    return content.map(part => {
      if (typeof part === 'string') return part;
      if (!part || typeof part !== 'object') return '';
      if (part.type === 'text' && typeof part.text === 'string') return part.text;
      if (typeof part.content === 'string') return part.content;
      return '';
    }).filter(Boolean).join('');
  }

  function roleOf(message) {
    const role = String(message?.role || '');
    return role === 'assistant' || role === 'user' ? role : 'system';
  }

  function create(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function buildUi() {
    if (q('#lanternChatDrawer')) return;
    const drawer = create('aside', 'lantern-chat-drawer');
    drawer.id = 'lanternChatDrawer';
    drawer.dataset.open = 'false';
    drawer.setAttribute('aria-label', 'Lantern Pi chatbot');

    const head = create('div', 'lantern-chat-head');
    const title = create('div', 'lantern-chat-title', 'Pi Chat');
    const path = create('div', 'lantern-chat-path', 'Current location');
    path.id = 'lanternChatPath';
    path.title = 'Current Lantern context';

    const model = create('select', 'lantern-chat-model');
    model.id = 'lanternChatModel';
    model.title = 'Pi model';
    model.disabled = true;

    const fresh = create('button', 'lantern-chat-iconbtn', 'New chat');
    fresh.id = 'lanternChatNew';
    fresh.type = 'button';
    fresh.title = 'Start a new Pi session';

    const close = create('button', 'lantern-chat-iconbtn lantern-chat-close', '×');
    close.type = 'button';
    close.setAttribute('aria-label', 'Close chat');

    head.append(title, path, model, fresh, close);

    const status = create('div', 'lantern-chat-status', 'Chat is idle');
    status.id = 'lanternChatStatus';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');

    const messages = create('div', 'lantern-chat-messages');
    messages.id = 'lanternChatMessages';

    const compose = create('div', 'lantern-chat-compose');
    const input = create('textarea', 'lantern-chat-input');
    input.id = 'lanternChatInput';
    input.rows = 3;
    input.placeholder = 'Ask Pi about the current Lantern location…';
    input.disabled = true;

    const row = create('div', 'lantern-chat-compose-row');
    const hint = create('div', 'lantern-chat-hint', 'Ctrl/⌘ + Enter to send');
    const stop = create('button', 'lantern-chat-stop', 'Stop');
    stop.id = 'lanternChatStop';
    stop.type = 'button';
    stop.hidden = true;
    const send = create('button', 'lantern-chat-send', 'Send');
    send.id = 'lanternChatSend';
    send.type = 'button';
    send.disabled = true;
    row.append(hint, stop, send);
    compose.append(input, row);

    drawer.append(head, status, messages, compose);
    document.body.append(drawer);

    close.addEventListener('click', () => setOpen(false));
    send.addEventListener('click', sendPrompt);
    stop.addEventListener('click', abortTurn);
    fresh.addEventListener('click', newChat);
    model.addEventListener('change', changeModel);
    input.addEventListener('keydown', event => {
      if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
        event.preventDefault();
        sendPrompt();
      }
    });
  }

  function injectLaunch() {
    if (q('.lantern-chat-launch')) return;
    const button = create('button', 'lantern-chat-launch', '✦ Chat');
    button.type = 'button';
    button.title = 'Open Lantern Pi chatbot';
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
    button.textContent = '✦';
    document.body.append(button);
  }

  function setStatus(text, kind = '') {
    const node = q('#lanternChatStatus');
    if (!node) return;
    node.textContent = text;
    if (kind) node.dataset.kind = kind;
    else delete node.dataset.kind;
  }

  function setStreaming(value) {
    S.streaming = Boolean(value);
    const stop = q('#lanternChatStop');
    const send = q('#lanternChatSend');
    const fresh = q('#lanternChatNew');
    const launch = q('.lantern-chat-launch');
    if (stop) stop.hidden = !S.streaming;
    if (send) send.disabled = S.streaming || !S.connected || S.authenticated === false;
    if (fresh) fresh.disabled = S.streaming || !S.connected || S.authenticated === false;
    if (launch) launch.dataset.chatState = S.streaming ? 'busy' : 'idle';
    if (!S.streaming && S.assistant) {
      S.assistant.classList.remove('is-streaming');
      S.assistant = null;
    }
  }

  function setAccess(authenticated) {
    S.authenticated = Boolean(authenticated);
    const input = q('#lanternChatInput');
    const model = q('#lanternChatModel');
    if (input) input.disabled = !S.connected || !S.authenticated;
    if (model) model.disabled = !S.connected || !S.authenticated || !S.models.length;
    setStreaming(S.streaming);
    if (!S.authenticated) {
      setStatus('Terminal is locked. Unlock Terminal first; Chat uses the same access state.', 'warn');
    }
  }

  function appendMessage(role, text, options = {}) {
    const list = q('#lanternChatMessages');
    if (!list) return null;
    const node = create('div', 'lantern-chat-msg', text || '');
    node.dataset.role = role;
    if (options.streaming) node.classList.add('is-streaming');
    list.append(node);
    list.scrollTop = list.scrollHeight;
    return node;
  }

  function appendSystem(text, kind = '') {
    const node = appendMessage('system', text);
    if (kind) node.dataset.kind = kind;
    return node;
  }

  function renderHistory(messages) {
    const list = q('#lanternChatMessages');
    if (!list) return;
    list.textContent = '';
    S.assistant = null;
    S.toolRows.clear();
    for (const message of Array.isArray(messages) ? messages : []) {
      const role = roleOf(message);
      if (role === 'system') continue;
      const text = textContentOf(message.content);
      if (text) appendMessage(role, text);
    }
  }

  function renderModels(models, state) {
    S.models = Array.isArray(models) ? models : [];
    const select = q('#lanternChatModel');
    if (!select) return;
    const active = state?.model || S.state?.model || {};
    const wanted = String(active.provider || '') + '/' + String(active.id || '');
    select.textContent = '';
    for (const item of S.models) {
      const opt = document.createElement('option');
      opt.value = String(item.provider || '') + '/' + String(item.id || '');
      opt.textContent = String(item.name || item.id || opt.value);
      if (opt.value === wanted) opt.selected = true;
      select.append(opt);
    }
    select.disabled = !S.connected || S.authenticated === false || !S.models.length;
  }

  function sendRaw(payload) {
    if (!S.ws || S.ws.readyState !== WebSocket.OPEN) throw new Error('Chat WebSocket is not connected');
    S.ws.send(JSON.stringify(payload));
  }

  function connect() {
    if (S.ws && (S.ws.readyState === WebSocket.OPEN || S.ws.readyState === WebSocket.CONNECTING)) return;
    clearTimeout(S.reconnect);
    setStatus('Connecting to Lantern…');
    const scheme = location.protocol === 'https:' ? 'wss://' : 'ws://';
    const ws = new WebSocket(scheme + location.host + '/ws?v=2');
    S.ws = ws;
    ws.onopen = () => {
      if (S.ws !== ws) return;
      S.connected = true;
      S.reconnectDelay = 500;
      sendRaw({type: 'terminal_client_v2'});
      sendRaw({type: 'chat_sync'});
      setStatus('Loading Pi session…');
      const input = q('#lanternChatInput');
      if (input) input.disabled = S.authenticated === false;
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
      const input = q('#lanternChatInput');
      if (input) input.disabled = true;
      const model = q('#lanternChatModel');
      if (model) model.disabled = true;
      setStatus('Chat disconnected. Reconnecting…', 'warn');
      if (S.open) {
        S.reconnect = setTimeout(connect, S.reconnectDelay);
        S.reconnectDelay = Math.min(5000, Math.round(S.reconnectDelay * 1.6));
      }
    };
  }

  function currentMarkdownContext(path) {
    const mode = String(globalThis.__lanternMdVisual?.state?.mode || 'preview');
    let bookmark = null;
    try {
      bookmark = globalThis.LanternAnchorBridge?.capture?.(mode) || null;
    } catch {}
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
    const folder = String(globalThis.currentPath?.() ?? globalThis.APP?.currentPath ?? '').replace(/^\/+/, '');
    let selected = [];
    try { selected = globalThis.selectedArray?.() || []; } catch {}
    if (selected.length === 1) return {kind: 'file', path: String(selected[0]), folder};
    return {kind: 'folder', folder};
  }

  function captureContext() {
    const body = document.body;
    const kind = body?.dataset?.lanternChatKind;
    const path = body?.dataset?.lanternChatPath;
    return kind === 'markdown' && path ? currentMarkdownContext(path) : currentBrowserContext();
  }

  function contextLabel(context) {
    const path = context?.path || context?.folder || '/';
    const mode = context?.markdownMode ? ' · ' + context.markdownMode : '';
    const line = context?.line ? ':' + context.line : '';
    return String(path || '/') + line + mode;
  }

  function refreshContextLabel() {
    const path = q('#lanternChatPath');
    if (!path) return;
    const context = captureContext();
    const label = contextLabel(context);
    path.textContent = label;
    path.title = label;
  }

  function setOpen(value) {
    buildUi();
    S.open = Boolean(value);
    const drawer = q('#lanternChatDrawer');
    if (drawer) drawer.dataset.open = S.open ? 'true' : 'false';
    document.body.classList.toggle('lantern-chat-open', S.open);
    if (S.open) {
      refreshContextLabel();
      connect();
      clearInterval(S.contextTimer);
      S.contextTimer = setInterval(refreshContextLabel, 700);
      setTimeout(() => q('#lanternChatInput')?.focus(), 80);
    } else {
      clearInterval(S.contextTimer);
      S.contextTimer = null;
    }
  }

  function ensureAssistant() {
    if (S.assistant?.isConnected) return S.assistant;
    S.assistant = appendMessage('assistant', '', {streaming: true});
    return S.assistant;
  }

  function appendAssistantDelta(delta) {
    if (!delta) return;
    const node = ensureAssistant();
    node.textContent += delta;
    const list = q('#lanternChatMessages');
    if (list) list.scrollTop = list.scrollHeight;
  }

  function assistantDelta(event) {
    if (typeof event?.delta === 'string') return event.delta;
    const inner = event?.assistantMessageEvent || event?.event;
    if (inner && inner.type === 'text_delta') {
      if (typeof inner.delta === 'string') return inner.delta;
      if (typeof inner.text === 'string') return inner.text;
    }
    return '';
  }

  function renderToolStart(event) {
    const list = q('#lanternChatMessages');
    if (!list) return;
    const id = String(event.toolCallId || event.id || Math.random());
    const row = create('div', 'lantern-chat-tool');
    const name = create('span', 'lantern-chat-tool-name', '↳ ' + String(event.toolName || 'tool'));
    const args = event.args && typeof event.args === 'object'
      ? JSON.stringify(event.args).slice(0, 260) : '';
    const detail = create('span', '', args);
    row.append(name, detail);
    row.dataset.toolCallId = id;
    list.append(row);
    list.scrollTop = list.scrollHeight;
    S.toolRows.set(id, row);
  }

  function renderToolEnd(event) {
    const id = String(event.toolCallId || event.id || '');
    const row = S.toolRows.get(id);
    if (!row) return;
    const failed = Boolean(event.isError || event.error);
    row.dataset.error = failed ? 'true' : 'false';
    const suffix = create('span', '', failed ? 'failed' : 'done');
    row.append(suffix);
  }

  function onPiEvent(event) {
    const typ = String(event?.type || '');
    if (typ === 'agent_start' || typ === 'turn_start') {
      setStreaming(true);
      setStatus('Pi is working…');
      return;
    }
    if (typ === 'message_start' && event.message?.role === 'assistant') {
      ensureAssistant();
      return;
    }
    if (typ === 'message_update') {
      setStreaming(true);
      appendAssistantDelta(assistantDelta(event));
      return;
    }
    if (typ === 'message_end' && event.message?.role === 'assistant') {
      const text = textContentOf(event.message.content);
      const node = ensureAssistant();
      if (!node.textContent && text) node.textContent = text;
      const error = event.message.errorMessage;
      if (error && !node.textContent) node.textContent = 'Pi error: ' + error;
      return;
    }
    if (typ === 'tool_execution_start') {
      renderToolStart(event);
      return;
    }
    if (typ === 'tool_execution_end') {
      renderToolEnd(event);
      return;
    }
    if (typ === 'auto_retry_start') {
      setStatus('Pi is retrying: ' + String(event.errorMessage || ''), 'warn');
      return;
    }
    if (typ === 'agent_settled') {
      setStreaming(false);
      setStatus(event.aborted ? 'Pi stopped' : 'Ready');
    }
  }

  function onMessage(message) {
    const typ = String(message?.type || '');
    if (typ === 'terminal_auth') {
      setAccess(Boolean(message.authenticated));
      return;
    }
    if (typ === 'chat_state') {
      S.state = message.state || {};
      renderModels(message.models || [], S.state);
      renderHistory(message.messages || []);
      setStreaming(Boolean(message.summary?.streaming));
      setAccess(S.authenticated !== false);
      setStatus('Ready');
      refreshContextLabel();
      return;
    }
    if (typ === 'chat_pi_event') {
      onPiEvent(message.event || {});
      return;
    }
    if (typ === 'chat_prompt_accepted') {
      setStreaming(true);
      setStatus('Pi is working…');
      return;
    }
    if (typ === 'chat_model_changed') {
      S.state = message.state || S.state;
      renderModels(S.models, S.state);
      setStatus('Model changed');
      return;
    }
    if (typ === 'chat_session_changed') {
      S.state = message.state || {};
      return;
    }
    if (typ === 'chat_aborted') {
      setStatus('Stopping Pi…', 'warn');
      return;
    }
    if (typ === 'chat_process_exit') {
      setStreaming(false);
      setStatus('Pi process exited. Reopen chat to restart it.', 'error');
      return;
    }
    if (typ === 'chat_error') {
      setStreaming(false);
      const locked = message.code === 'terminal_auth_required';
      if (locked) setAccess(false);
      else setStatus(String(message.error || 'Chat error'), 'error');
      if (!locked) appendSystem('Chat error: ' + String(message.error || 'unknown error'), 'error');
    }
  }

  function sendPrompt() {
    const input = q('#lanternChatInput');
    if (!input || input.disabled || S.streaming) return;
    const message = input.value.trim();
    if (!message) return;
    const context = captureContext();
    refreshContextLabel();
    try {
      appendMessage('user', message);
      sendRaw({
        type: 'chat_prompt',
        reqId: 'chat-' + Date.now().toString(36),
        message,
        context,
      });
      input.value = '';
      S.assistant = null;
      setStreaming(true);
      setStatus('Sending to Pi…');
    } catch (error) {
      setStreaming(false);
      appendSystem(String(error?.message || error), 'error');
    }
  }

  function abortTurn() {
    if (!S.connected || !S.streaming) return;
    try { sendRaw({type: 'chat_abort'}); setStatus('Stopping Pi…', 'warn'); }
    catch (error) { setStatus(String(error?.message || error), 'error'); }
  }

  function newChat() {
    if (!S.connected || S.streaming || S.authenticated === false) return;
    try {
      sendRaw({type: 'chat_new'});
      renderHistory([]);
      setStatus('Starting a new Pi session…');
    } catch (error) {
      setStatus(String(error?.message || error), 'error');
    }
  }

  function changeModel() {
    const select = q('#lanternChatModel');
    if (!select || !select.value || S.streaming) return;
    const slash = select.value.indexOf('/');
    if (slash < 1) return;
    try {
      sendRaw({
        type: 'chat_set_model',
        provider: select.value.slice(0, slash),
        modelId: select.value.slice(slash + 1),
      });
      setStatus('Changing model…');
    } catch (error) {
      setStatus(String(error?.message || error), 'error');
    }
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

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
