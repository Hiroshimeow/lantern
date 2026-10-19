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
    policy: {},
    usage: {},
    attachmentDismissed: new Set(),
    selectedPaths: new Set(),
    contextTimer: null,
    logTimer: null,
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

  function displayUserText(raw) {
    const text = String(raw || '');
    const match = text.match(/<user_request>\s*\n([\s\S]*?)\n<\/user_request>\s*$/);
    return match ? match[1] : text;
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
    drawer.setAttribute('aria-label', 'LanternBot');

    const head = create('div', 'lantern-chat-head');
    const title = create('div', 'lantern-chat-title', 'LanternBot');
    const path = create('div', 'lantern-chat-path', 'Current location');
    path.id = 'lanternChatPath';
    path.title = 'Current Lantern context';

    const provider = create('select', 'lantern-chat-provider');
    provider.id = 'lanternChatProvider';
    provider.title = 'Provider';
    provider.disabled = true;

    const model = create('select', 'lantern-chat-model');
    model.id = 'lanternChatModel';
    model.title = 'Model';
    model.disabled = true;

    const fresh = create('button', 'lantern-chat-iconbtn', 'New chat');
    fresh.id = 'lanternChatNew';
    fresh.type = 'button';
    fresh.title = 'Start a new LanternBot conversation';

    const close = create('button', 'lantern-chat-iconbtn lantern-chat-close', '×');
    close.type = 'button';
    close.setAttribute('aria-label', 'Close chat');

    head.append(title, path, provider, model, fresh, close);

    const status = create('div', 'lantern-chat-status', 'Chat is idle');
    status.id = 'lanternChatStatus';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');

    const messages = create('div', 'lantern-chat-messages');
    messages.id = 'lanternChatMessages';

    const compose = create('div', 'lantern-chat-compose');
    const attachments = create('div', 'lantern-chat-attachments');
    attachments.id = 'lanternChatAttachments';
    attachments.hidden = true;
    const input = create('textarea', 'lantern-chat-input');
    input.id = 'lanternChatInput';
    input.rows = 3;
    input.placeholder = 'Ask LanternBot about the current Lantern location…';
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
    compose.append(attachments, input, row);

    drawer.append(head, status, messages, compose);
    document.body.append(drawer);

    close.addEventListener('click', () => setOpen(false));
    send.addEventListener('click', sendPrompt);
    stop.addEventListener('click', abortTurn);
    fresh.addEventListener('click', newChat);
    provider.addEventListener('change', changeProvider);
    model.addEventListener('change', changeModel);
    input.addEventListener('keydown', event => {
      if (event.key !== 'Enter' || event.isComposing) return;
      if (event.shiftKey || event.ctrlKey || event.metaKey || event.altKey) return;
      event.preventDefault();
      sendPrompt();
    });
  }

  function injectLaunch() {
    if (q('.lantern-chat-launch')) return;
    const button = create('button', 'lantern-chat-launch', '✦ Chat');
    button.type = 'button';
    button.title = 'Open LanternBot';
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
    const provider = q('#lanternChatProvider');
    const model = q('#lanternChatModel');
    if (input) input.disabled = !S.connected || !S.authenticated;
    if (provider) provider.disabled = !S.connected || !S.authenticated ||
      !S.models.length || Boolean(S.policy?.lockProvider);
    if (model) model.disabled = !S.connected || !S.authenticated ||
      !S.models.length || Boolean(S.policy?.lockModel);
    setStreaming(S.streaming);
    if (!S.authenticated) {
      setStatus('Terminal is locked. Unlock Terminal first; Chat uses the same access state.', 'warn');
    }
  }

  // Browser-session event log: tool invocations are ephemeral in Pi's text
  // transcript, but must survive F5 in this tab, including their order.
  const logKey = sessionId => 'lanternbot-view:' + location.origin + ':' + sessionId;
  function persistChatLog() {
    clearTimeout(S.logTimer);
    S.logTimer = setTimeout(() => {
      const list = q('#lanternChatMessages');
      const sessionId = String(S.state?.sessionId || '');
      if (!sessionId || !list) return;
      try {
        const nodes = [...list.children].slice(-500).map(el => ({
          kind:el.classList.contains('lantern-chat-tool') ? 'tool' : 'message',
          role:el.dataset.role || 'system',
          text:el.textContent || '',
          id:el.dataset.toolCallId || '',
          error:el.dataset.error || '',
        }));
        const lastUser = [...nodes].reverse().find(x => x.role === 'user')?.text || '';
        const raw = JSON.stringify({at:Date.now(),lastUser,nodes});
        if (raw.length < 1500000) sessionStorage.setItem(logKey(sessionId),raw);
      } catch { /* Private mode or quota limits: continue without local replay. */ }
    },180);
  }
  function restoreChatLog(messages) {
    const id = String(S.state?.sessionId || '');
    if (!id) return false;
    let snapshot;
    try { snapshot = JSON.parse(sessionStorage.getItem(logKey(id)) || 'null'); }
    catch { return false; }
    if (!snapshot || Date.now() - snapshot.at > 7*86400000 ||
        !Array.isArray(snapshot.nodes) || !snapshot.nodes.length) return false;
    const lastUser = [...(Array.isArray(messages) ? messages : [])].reverse()
      .find(m => m?.role === 'user');
    if ((lastUser ? displayUserText(textContentOf(lastUser.content)) : '') !== snapshot.lastUser)
      return false;
    const list = q('#lanternChatMessages');
    if (!list) return false;
    list.textContent = '';
    S.toolRows.clear();
    S.assistant = null;
    for (const item of snapshot.nodes) {
      if (item.kind === 'tool') {
        const node = create('div', 'lantern-chat-tool', String(item.text || ''));
        node.dataset.toolCallId = String(item.id || '');
        if (item.error) node.dataset.error = item.error;
        list.append(node);
        if (item.id) S.toolRows.set(item.id, node);
      } else {
        appendMessage(item.role || 'system', String(item.text || ''));
      }
    }
    list.scrollTop = list.scrollHeight;
    return true;
  }

  function appendMessage(role, text, options = {}) {
    const list = q('#lanternChatMessages');
    if (!list) return null;
    const node = create('div', 'lantern-chat-msg', text || '');
    node.dataset.role = role;
    if (options.streaming) node.classList.add('is-streaming');
    list.append(node);
    list.scrollTop = list.scrollHeight;
    persistChatLog();
    return node;
  }

  function appendSystem(text, kind = '') {
    const node = appendMessage('system', text);
    if (kind) node.dataset.kind = kind;
    return node;
  }

  function renderHistory(messages, greeting = '') {
    const list = q('#lanternChatMessages');
    if (!list) return;
    list.textContent = '';
    S.assistant = null;
    S.toolRows.clear();
    let visible = 0;
    for (const message of Array.isArray(messages) ? messages : []) {
      const role = roleOf(message);
      if (role === 'system') continue;
      const raw = textContentOf(message.content);
      const text = role === 'user' ? displayUserText(raw) : raw;
      if (text) {
        appendMessage(role, text);
        visible += 1;
      }
    }
    if (!visible && greeting) appendMessage('assistant', greeting);
  }

  function modelsForProvider(provider) {
    return S.models.filter(item => String(item.provider || '') === provider);
  }

  function renderModelOptions(provider, wantedId = '') {
    const select = q('#lanternChatModel');
    if (!select) return;
    const items = modelsForProvider(provider);
    select.textContent = '';
    for (const item of items) {
      const opt = document.createElement('option');
      opt.value = String(item.id || '');
      opt.textContent = String(item.name || item.id || '');
      if (opt.value === wantedId) opt.selected = true;
      select.append(opt);
    }
    if (wantedId && !items.some(item => String(item.id || '') === wantedId) && items.length) {
      select.value = String(items[0].id || '');
    }
    select.disabled = !S.connected || S.authenticated === false ||
      !items.length || Boolean(S.policy?.lockModel);
  }

  function renderModels(models, state, summary = null) {
    S.models = Array.isArray(models) ? models : [];
    if (summary?.policy) S.policy = summary.policy;
    if (summary?.usage) S.usage = summary.usage;
    const active = state?.model || S.state?.model || {};
    const activeProvider = String(active.provider || '');
    const activeId = String(active.id || '');
    const provider = q('#lanternChatProvider');
    if (!provider) return;
    const providers = [...new Set(S.models.map(item => String(item.provider || '')).filter(Boolean))];
    provider.textContent = '';
    for (const value of providers) {
      const opt = document.createElement('option');
      opt.value = value;
      opt.textContent = value;
      if (value === activeProvider) opt.selected = true;
      provider.append(opt);
    }
    if (activeProvider && providers.includes(activeProvider)) provider.value = activeProvider;
    else if (providers.length) provider.value = providers[0];
    provider.disabled = !S.connected || S.authenticated === false ||
      !providers.length || Boolean(S.policy?.lockProvider);
    renderModelOptions(provider.value, provider.value === activeProvider ? activeId : '');
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
      setStatus('Loading LanternBot…');
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
      const provider = q('#lanternChatProvider');
      const model = q('#lanternChatModel');
      if (provider) provider.disabled = true;
      if (model) model.disabled = true;
      setStatus('Chat disconnected. Reconnecting…', 'warn');
      if (S.open) {
        S.reconnect = setTimeout(connect, S.reconnectDelay);
        S.reconnectDelay = Math.min(5000, Math.round(S.reconnectDelay * 1.6));
      }
    };
  }

  function selectedFilePaths() {
    let selected = [];
    try { selected = globalThis.selectedArray?.() || []; } catch {}
    const current = new Set(selected.map(String));
    for (const old of [...S.selectedPaths]) {
      if (!current.has(old)) S.attachmentDismissed.delete(old);
    }
    S.selectedPaths = current;
    return [...current].filter(path => {
      const card = document.querySelector(`.card[data-rel="${CSS.escape(path)}"]`);
      return !card || card.dataset.isdir !== '1';
    });
  }

  function attachmentPaths() {
    return selectedFilePaths().filter(path => !S.attachmentDismissed.has(path));
  }

  function refreshAttachments() {
    const holder = q('#lanternChatAttachments');
    if (!holder) return;
    const paths = attachmentPaths();
    holder.textContent = '';
    holder.hidden = paths.length === 0;
    for (const path of paths) {
      const chip = create('span', 'lantern-chat-attachment');
      const label = create('span', 'lantern-chat-attachment-label', path);
      label.title = path;
      const remove = create('button', 'lantern-chat-attachment-remove', '×');
      remove.type = 'button';
      remove.title = 'Detach from next LanternBot message';
      remove.addEventListener('click', () => {
        S.attachmentDismissed.add(path);
        refreshAttachments();
      });
      chip.append(label, remove);
      holder.append(chip);
    }
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
    refreshAttachments();
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
    persistChatLog();
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
    S.assistant = null; // subsequent assistant response must appear after tool calls
    persistChatLog();
  }

  function renderToolEnd(event) {
    const id = String(event.toolCallId || event.id || '');
    const row = S.toolRows.get(id);
    if (!row) return;
    const failed = Boolean(event.isError || event.error);
    row.dataset.error = failed ? 'true' : 'false';
    const suffix = create('span', '', failed ? 'failed' : 'done');
    row.append(suffix);
    persistChatLog();
  }

  function onBotEvent(event) {
    const typ = String(event?.type || '');
    if (typ === 'agent_start' || typ === 'turn_start') {
      setStreaming(true);
      setStatus('LanternBot is working…');
      return;
    }
    if (typ === 'message_start' && event.message?.role === 'assistant') {
      // No placeholder before the tool events: render a reply only once
      // there is real text to place on the timeline.
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
      persistChatLog();
      const error = event.message.errorMessage;
      if (error && !node.textContent) node.textContent = 'LanternBot error: ' + error;
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
      setStatus('LanternBot is retrying: ' + String(event.errorMessage || ''), 'warn');
      return;
    }
    if (typ === 'agent_settled') {
      setStreaming(false);
      setStatus(event.aborted ? 'LanternBot stopped' : 'Ready');
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
      S.policy = message.summary?.policy || {};
      S.usage = message.summary?.usage || {};
      renderModels(message.models || [], S.state, message.summary || {});
      renderHistory(message.messages || [], String(S.policy?.greeting || ''));
      restoreChatLog(message.messages || []);
      setStreaming(Boolean(message.summary?.streaming));
      setAccess(S.authenticated !== false);
      setStatus('Ready');
      refreshContextLabel();
      return;
    }
    if (typ === 'chat_bot_event') {
      onBotEvent(message.event || {});
      return;
    }
    if (typ === 'chat_work_changed') {
      const editor = globalThis.__lanternMdVisual;
      if (!editor?.onWorkChanged) {
        setStatus('Markdown working-copy controller is unavailable for LanternBot updates.', 'error');
        return;
      }
      void Promise.resolve(editor.onWorkChanged(
        String(message.path || ''),
        message.hash || null,
        Boolean(message.final),
      )).then(() => {
        setStatus(message.final
          ? 'LanternBot updated the real .md; Ctrl+S accepts the diff.'
          : 'LanternBot changed the real .md.');
        refreshContextLabel();
      }).catch(error => {
        setStatus('LanternBot working-copy merge failed: ' + String(error?.message || error), 'error');
        appendSystem('LanternBot working-copy merge failed: ' + String(error?.message || error), 'error');
      });
      return;
    }
    if (typ === 'chat_work_error') {
      globalThis.__lanternMdVisual?.cancelBotTurn?.();
      setStatus(String(message.error || 'LanternBot working-copy update failed'), 'error');
      appendSystem('LanternBot working-copy error: ' + String(message.error || 'unknown error'), 'error');
      return;
    }
    if (typ === 'chat_real_file_touched') {
      globalThis.__lanternMdVisual?.cancelBotTurn?.();
      setStatus('Saved Markdown changed outside the pending working copy. Save is blocked until you reconcile.', 'error');
      appendSystem('Saved Markdown changed while LanternBot was working. The working copy was kept; reconcile before Save.', 'error');
      return;
    }
    if (typ === 'chat_prompt_accepted') {
      setStreaming(true);
      setStatus('LanternBot is working…');
      return;
    }
    if (typ === 'chat_model_changed') {
      S.state = message.state || S.state;
      renderModels(S.models, S.state, message.summary || null);
      setStatus('Provider/model changed');
      return;
    }
    if (typ === 'chat_session_changed') {
      S.state = message.state || {};
      return;
    }
    if (typ === 'chat_aborted') {
      setStatus('Stopping LanternBot…', 'warn');
      return;
    }
    if (typ === 'chat_process_exit') {
      setStreaming(false);
      setStatus('LanternBot runtime exited. Reopen chat to restart it.', 'error');
      return;
    }
    if (typ === 'chat_error') {
      globalThis.__lanternMdVisual?.cancelBotTurn?.();
      setStreaming(false);
      const locked = message.code === 'terminal_auth_required';
      if (locked) setAccess(false);
      else setStatus(String(message.error || 'Chat error'), 'error');
      if (!locked) appendSystem('Chat error: ' + String(message.error || 'unknown error'), 'error');
    }
  }

  async function prepareMarkdownTurn(context) {
    if (context?.kind !== 'markdown') return null;
    const editor = globalThis.__lanternMdVisual;
    if (!editor?.beginBotTurn) throw new Error('Markdown working-copy controller is unavailable');
    return await editor.beginBotTurn();
  }

  async function sendPrompt() {
    const input = q('#lanternChatInput');
    if (!input || input.disabled || S.streaming) return;
    const message = input.value.trim();
    if (!message) return;
    try {
      input.disabled = true;
      const context = captureContext();
      const attachments = attachmentPaths();
      if (attachments.length) context.attachments = attachments;
      const promptId = 'chat-' + Date.now().toString(36);
      const workHash = await prepareMarkdownTurn(context);
      refreshContextLabel();
      appendMessage('user', message);
      sendRaw({
        type: 'chat_prompt',
        reqId: promptId,
        message,
        context,
        workHash,
      });
      input.value = '';
      S.assistant = null;
      setStreaming(true);
      setStatus('Sending to LanternBot…');
    } catch (error) {
      globalThis.__lanternMdVisual?.cancelBotTurn?.();
      setStreaming(false);
      appendSystem(String(error?.message || error), 'error');
      setStatus(String(error?.message || error), 'error');
    } finally {
      input.disabled = !S.connected || S.authenticated === false;
    }
  }

  function abortTurn() {
    if (!S.connected || !S.streaming) return;
    try { sendRaw({type: 'chat_abort'}); setStatus('Stopping LanternBot…', 'warn'); }
    catch (error) { setStatus(String(error?.message || error), 'error'); }
  }

  function newChat() {
    if (!S.connected || S.streaming || S.authenticated === false) return;
    try {
      sendRaw({type: 'chat_new'});
      renderHistory([], String(S.policy?.greeting || ''));
      setStatus('Starting a new LanternBot conversation…');
    } catch (error) {
      setStatus(String(error?.message || error), 'error');
    }
  }

  function selectedProviderModel() {
    return {
      provider: String(q('#lanternChatProvider')?.value || ''),
      modelId: String(q('#lanternChatModel')?.value || ''),
    };
  }

  function changeProvider() {
    const provider = q('#lanternChatProvider');
    if (!provider || !provider.value || S.streaming) return;
    renderModelOptions(provider.value, '');
    changeModel();
  }

  function changeModel() {
    if (S.streaming) return;
    const selected = selectedProviderModel();
    if (!selected.provider || !selected.modelId) return;
    try {
      sendRaw({
        type: 'chat_set_model',
        provider: selected.provider,
        modelId: selected.modelId,
      });
      setStatus('Changing provider/model…');
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
      prepareMarkdownTurn,
      refreshContext: refreshContextLabel,
    };
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
