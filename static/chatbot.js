/**
 * Lantern Chatbot — Integrated Modular Web UI & Host Bridge (Port 9999, v7)
 * 100% compatible with Lantern v2 WebSocket (/ws?v=2) and HTTP contracts:
 * - Full chat_state & chat_bot_event streaming protocol with durable User + Assistant transcript persistence
 * - YAML-governed Backend Access Policy (no editable Tool/Extension/MCP flags in UI Settings)
 * - Paste (Ctrl+V) images/files + Drag-and-Drop OS files/images + Drag-and-Drop Lantern .card[data-rel]
 * - Unified Context Chips with image thumbnails & Layer-1 dirty-draft opt-out chip
 */
(() => {
  'use strict';
  if (window.self !== window.top && !window.APP?.standaloneChat) return;
  if (window.__lanternChatbotMounted) return;
  window.__lanternChatbotMounted = true;

  const UI_STORAGE_KEY = 'lantern-chatbot:ui-prefs:v2';
  const CLIENT_SESSION_KEY = 'lantern-chatbot:client-session-id:v74';
  const TAB_CACHE_PREFIX = 'lantern-chatbot:tab-cache:v74:';
  const ATTACHMENT_STORAGE_KEY = 'lanternChatAttachments';
  const LEGACY_OPEN_KEY = 'lanternChatOpen';
  const IMAGE_EXT_RE = /\.(png|jpe?g|gif|webp|bmp|svg|avif)$/i;

  const TAB_RUNTIME_ID = 'rt-' + Math.random().toString(36).slice(2, 9) + '-' + Date.now().toString(36).slice(-4);
  const WIN_NAME_CID_PREFIX = 'lantern_tab_cid:';

  function generateFreshTabSessionId() {
    return 'tab-' + Math.random().toString(36).slice(2, 9) + '-' + Date.now().toString(36).slice(-4);
  }

  function persistTabSessionId(cid) {
    try {
      sessionStorage.setItem(CLIENT_SESSION_KEY, cid);
      if (!window.APP?.standaloneChat && !String(window.name || '').startsWith('lanbot_')) {
        window.name = WIN_NAME_CID_PREFIX + cid;
      }
    } catch {}
    return cid;
  }

  function resolveClientSessionId() {
    try {
      const qs = new URLSearchParams(window.location.search || '');
      const fromUrl = (qs.get('client_session') || qs.get('chat_session') || qs.get('session') || '').trim();
      if (fromUrl) {
        return persistTabSessionId(fromUrl);
      }
      const fromBody = (document.body?.dataset?.lanternClientSession || window.APP?.clientSessionId || '').trim();
      if (fromBody) {
        return persistTabSessionId(fromBody);
      }
      const winName = String(window.name || '').trim();
      if (winName.startsWith(WIN_NAME_CID_PREFIX)) {
        const fromWin = winName.slice(WIN_NAME_CID_PREFIX.length).trim();
        if (fromWin) {
          return persistTabSessionId(fromWin);
        }
      }
      // If window.name does NOT carry WIN_NAME_CID_PREFIX, this is either a brand-new tab
      // or a tab opened via Ctrl+Click / Middle-Click (where the browser cloned sessionStorage
      // from the parent tab but reset window.name to ""). Always allocate a fresh tab ID!
      return persistTabSessionId(generateFreshTabSessionId());
    } catch {
      return 'tab-default';
    }
  }

  const INITIAL_CLIENT_SESSION_ID = resolveClientSessionId();
  const IS_STANDALONE_CHAT = Boolean(window.APP?.standaloneChat || document.body?.classList?.contains('lantern-chat-standalone'));
  let contextChannel = null;
  try {
    if (typeof BroadcastChannel !== 'undefined') {
      contextChannel = new BroadcastChannel('lantern_chat_context_v74');
    }
  } catch {}

  const DEFAULT_SLASH_COMMANDS = [
    { command: '/model', category: 'model', description: 'Open Model Selector or switch model (/model <id>)' },
    { command: '/new', category: 'session', description: 'Start a new Pi session' },
    { command: '/compact', category: 'session', description: 'Compact session context via Pi core to save tokens' },
    { command: '/fork', category: 'session', description: 'Fork current conversation into a new branch' },
    { command: '/session', category: 'session', description: 'Switch or manage saved conversations' },
    { command: '/thinking', category: 'config', description: 'Set Pi core thinking level (off|low|medium|high|xhigh)' },
    { command: '/skills', category: 'skill', description: 'List discovered workspace & global skills' },
    { command: '/harness', category: 'harness', description: 'Inspect Pi Core Harness status or scaffold starter skills (/harness init)' },
    { command: '/mcp', category: 'tools', description: 'Inspect MCP status or run an MCP task' },
    { command: '/settings', category: 'config', description: 'Open Lanbot Settings (System Prompt, Skills, Export HTML)' },
    { command: '/export', category: 'session', description: 'Export full unabbreviated HTML session log' },
    { command: '/help', category: 'ui', description: 'Show all available slash commands and skills' },
    { command: '/clear', category: 'ui', description: 'Clear local status notifications' },
  ];

  function loadUiPrefs() {
    try {
      const raw = JSON.parse(localStorage.getItem(UI_STORAGE_KEY) || '{}');
      return {
        open: raw.open ?? (localStorage.getItem(LEGACY_OPEN_KEY) === '1'),
        dock: raw.dock === 'left' ? 'left' : 'right',
        width: Math.max(360, Math.min(820, Number(raw.width) || 430)),
        inputHeight: Math.max(106, Math.min(360, Number(raw.inputHeight) || 110)),
        expanded: Boolean(raw.expanded),
        autoContext: raw.autoContext !== false,
        fabTopRatio: typeof raw.fabTopRatio === 'number' ? raw.fabTopRatio : 0.85,
      };
    } catch {
      return { open: false, dock: 'right', width: 430, inputHeight: 110, expanded: false, autoContext: true, fabTopRatio: 0.85 };
    }
  }

  const prefs = loadUiPrefs();
  function saveUiPrefs() {
    try {
      localStorage.setItem(UI_STORAGE_KEY, JSON.stringify(prefs));
      localStorage.setItem(LEGACY_OPEN_KEY, prefs.open ? '1' : '0');
    } catch {}
  }

  let ws = null;
  let wsConnected = false;
  let reconnectTimer = 0;
  let state = {
    unlocked: true,
    passwordRequired: false,
    isLocal: ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname),
    lanLocked: false,
    busy: false,
    streaming: false,
    greeting: '🏮 Hi, I am Lanbot — your Lantern workspace assistant. Type `/` for commands, paste (`Ctrl+V`) or drag-and-drop images/files directly into the chat!',
    cachedSelection: '',
    cachedSelectionLine: null,
    cachedSelectionEndLine: null,
    sendingImmediate: false,
    steerCount: 0,
    customSystemPrompt: '',
    useGlobalSkills: true,
    customSkillPaths: [],
    discoveredSkills: [],
    clientSessionId: INITIAL_CLIENT_SESSION_ID,
    remoteContext: null,
    sessionId: '',
    sessionFile: null,
    sessionName: '',
    model: null,
    models: [],
    favoriteModels: [],
    lastModel: null,
    thinkingLevel: 'medium',
    thinkingLevels: ['off', 'minimal', 'low', 'medium', 'high', 'xhigh'],
    policy: null,
    messages: [],
    activity: [],
    sessions: [],
    contextUsage: { messageCount: 0, estimatedTokens: 0 },
    hasMoreOlder: false,
    oldestLoadedIndex: 0,
    totalHistoryMessages: 0,
    loadingOlderHistory: false,
    extensionRequests: [],
    dismissedSelection: false,
    dismissedPaths: new Set(),
    skipDraftFlush: false,
    uploadingCount: 0,
  };
  let reconnectAttempts = 0;
  const MAX_RECONNECT_ATTEMPTS = 5;
  let resetBotTimer = 0;

  let slashCommands = [...DEFAULT_SLASH_COMMANDS];
  let slashFiltered = [];
  let slashIndex = 0;
  let activeMarkdownTurn = null;
  let streamingNode = null;
  let streamingThinkingNode = null;
  let streamingToolDetails = null;
  let isUserScrolledUp = false;
  let programmaticScroll = false;
  let lastTranscriptFingerprint = '';
  const activeToolRows = new Map();

  function loadTabCache() {
    try {
      const raw = sessionStorage.getItem(TAB_CACHE_PREFIX + state.clientSessionId);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  function saveTabCache() {
    try {
      const payload = {
        sessionId: state.sessionId,
        sessionName: state.sessionName,
        model: state.model,
        thinkingLevel: state.thinkingLevel,
        messages: Array.isArray(state.messages) ? state.messages.slice(-60) : [],
        scrollTop: els?.transcript ? els.transcript.scrollTop : 0,
        isUserScrolledUp: Boolean(isUserScrolledUp),
      };
      sessionStorage.setItem(TAB_CACHE_PREFIX + state.clientSessionId, JSON.stringify(payload));
    } catch {}
  }

  function updateScrollBottomButton() {
    if (!els?.scrollBottomBtn) return;
    els.scrollBottomBtn.hidden = !isUserScrolledUp;
    els.scrollBottomBtn.classList.toggle('is-streaming', Boolean(state.streaming && isUserScrolledUp));
  }

  function escapeHtml(raw) {
    return String(raw ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  let scrollRafId = 0;
  function scrollTranscriptToBottom(force = false) {
    if (!els?.transcript) return;
    if (force) {
      isUserScrolledUp = false;
      updateScrollBottomButton();
    }
    if (!isUserScrolledUp) {
      if (force) {
        programmaticScroll = true;
        els.transcript.scrollTop = els.transcript.scrollHeight;
        requestAnimationFrame(() => {
          programmaticScroll = false;
          updateScrollBottomButton();
        });
        saveTabCache();
        return;
      }
      if (scrollRafId) return;
      scrollRafId = requestAnimationFrame(() => {
        scrollRafId = 0;
        if (!els?.transcript || isUserScrolledUp) {
          updateScrollBottomButton();
          return;
        }
        programmaticScroll = true;
        els.transcript.scrollTop = els.transcript.scrollHeight;
        requestAnimationFrame(() => {
          programmaticScroll = false;
          updateScrollBottomButton();
        });
        saveTabCache();
      });
    } else {
      updateScrollBottomButton();
    }
  }

  function jumpToLatestMessage() {
    if (!els?.transcript) return;
    isUserScrolledUp = false;
    updateScrollBottomButton();
    programmaticScroll = true;
    if (typeof els.transcript.scrollTo === 'function') {
      els.transcript.scrollTo({ top: els.transcript.scrollHeight, behavior: 'smooth' });
    } else {
      els.transcript.scrollTop = els.transcript.scrollHeight;
    }
    requestAnimationFrame(() => {
      programmaticScroll = false;
      updateScrollBottomButton();
    });
    saveTabCache();
  }

  let lastCommandsFetchAt = 0;
  async function refreshSlashCommands(force = false) {
    const now = Date.now();
    if (!force && now - lastCommandsFetchAt < 2500) return slashCommands;
    lastCommandsFetchAt = now;
    try {
      const r = await fetch('/api/chatbot/commands', { credentials: 'same-origin', cache: 'no-store' });
      if (!r.ok) return slashCommands;
      const data = await r.json();
      if (Array.isArray(data?.commands) && data.commands.length) {
        slashCommands = data.commands;
      }
      if (Array.isArray(data?.skills)) {
        state.discoveredSkills = data.skills;
        if (els?.discoveredSkillsList) {
          els.discoveredSkillsList.textContent = '';
          state.discoveredSkills.forEach(sk => {
            const b = document.createElement('span');
            b.className = 'lc-ctx-pill';
            b.title = sk.description || sk.path || '';
            b.textContent = `🧩 ${sk.name} (${sk.scope || sk.source || 'skill'})`;
            els.discoveredSkillsList.append(b);
          });
        }
      }
      if (els?.input && els.input.value.startsWith('/') && !els.slashPopover?.hidden) {
        updateSlashPopover(true);
      }
    } catch {}
    return slashCommands;
  }
  let messageEndSettleTimer = null;
  let streamTurn = {
    text: '',
    thinking: '',
    subturnText: '',
    subturnThinking: '',
    toolCalls: [],
    subagents: [],
    saved: false,
    hadToolCall: false,
    lastStopReason: '',
  };

  function resetStreamTurn() {
    clearTimeout(messageEndSettleTimer);
    messageEndSettleTimer = null;
    streamTurn = {
      text: '',
      thinking: '',
      subturnText: '',
      subturnThinking: '',
      toolCalls: [],
      subagents: [],
      saved: false,
      hadToolCall: false,
      lastStopReason: '',
    };
    streamingNode = null;
    streamingThinkingNode = null;
  }

  function estimateSessionTokens(messagesList, summarySessionTokens = null) {
    const msgs = Array.isArray(messagesList) ? messagesList : [];
    if (!msgs.length && (!summarySessionTokens || summarySessionTokens <= 0)) return 0;
    let latestReported = 0;
    let trailingChars = 0;
    msgs.forEach(m => {
      if (!m || typeof m !== 'object') return;
      const usage = m.usage;
      if (usage && typeof usage === 'object') {
        const rep = Number(usage.totalTokens || ((Number(usage.input || 0) + Number(usage.output || 0) + Number(usage.cacheRead || 0) + Number(usage.cacheWrite || 0)))) || 0;
        if (rep > 0) {
          latestReported = rep;
          trailingChars = 0;
          return;
        }
      }
      const norm = normalizeRawMessage(m);
      trailingChars += String(norm.text || '').length + String(norm.thinking || '').length;
      if (Array.isArray(norm.toolCalls)) {
        norm.toolCalls.forEach(tc => {
          trailingChars += String(tc.result || '').length + safeText(tc.arguments || '').length;
        });
      }
    });
    const computed = latestReported + (trailingChars > 0 ? Math.max(1, Math.floor(trailingChars / 4)) : 0);
    if (typeof summarySessionTokens === 'number' && summarySessionTokens > computed) {
      return summarySessionTokens;
    }
    return computed;
  }

  function updateTokenBadgeDisplay() {
    if (!els.tokenBadge) return;
    const msgs = Array.isArray(state.messages) ? state.messages : [];
    const msgCount = Math.max(msgs.length, Number(state.totalHistoryMessages || 0));
    const estTok = msgCount === 0 ? 0 : (state.contextUsage?.estimatedTokens || estimateSessionTokens(msgs));
    els.tokenBadge.textContent = `${msgCount} msgs · ${estTok > 0 ? '~' + estTok.toLocaleString() : '0'} tok`;
  }

  function recordAssistantTurnInState(msgObj) {
    if (!msgObj || typeof msgObj !== 'object') return;
    const text = safeText(msgObj.text || '');
    const thinking = safeText(msgObj.thinking || '');
    const toolCalls = Array.isArray(msgObj.toolCalls) ? msgObj.toolCalls : [];
    const subagents = Array.isArray(msgObj.subagents) ? msgObj.subagents : [];
    if (!text && !thinking && !toolCalls.length && !subagents.length) return;

    state.messages = Array.isArray(state.messages) ? state.messages : [];
    const entry = {
      role: 'assistant',
      text,
      thinking,
      toolCalls,
      subagents,
      timestamp: msgObj.timestamp || Date.now(),
      usage: msgObj.usage || null,
    };

    if (state.messages.length > 0 && state.messages[state.messages.length - 1].role === 'assistant') {
      const prev = normalizeRawMessage(state.messages[state.messages.length - 1]);
      const mergedTools = [...(prev.toolCalls || [])];
      const existingIds = new Set(mergedTools.map(t => `${t.id || ''}:${t.result !== undefined ? 'res' : 'call'}`));
      toolCalls.forEach(tc => {
        const key = `${tc.id || ''}:${tc.result !== undefined ? 'res' : 'call'}`;
        if (!tc.id || !existingIds.has(key)) {
          mergedTools.push(tc);
          existingIds.add(key);
        }
      });
      entry.toolCalls = mergedTools;
      if (prev.thinking && thinking && prev.thinking !== thinking && !thinking.includes(prev.thinking)) {
        entry.thinking = `${prev.thinking}\n${thinking}`;
      } else {
        entry.thinking = thinking || prev.thinking || '';
      }
      if (prev.text && text && prev.text !== text && !text.includes(prev.text)) {
        entry.text = `${prev.text}\n\n${text}`;
      } else {
        entry.text = text || prev.text || '';
      }
      state.messages[state.messages.length - 1] = entry;
      streamTurn.saved = true;
    } else {
      state.messages.push(entry);
      streamTurn.saved = true;
    }
    state.contextUsage = {
      messageCount: state.messages.length,
      estimatedTokens: estimateSessionTokens(state.messages),
    };
    updateTokenBadgeDisplay();
  }

  function inferIsImage(pathStr, mime = '') {
    if (mime && String(mime).toLowerCase().startsWith('image/')) return true;
    return IMAGE_EXT_RE.test(String(pathStr || ''));
  }

  function inferPreviewUrl(pathStr, isImage) {
    if (!isImage || !pathStr) return '';
    const clean = String(pathStr).replace(/^\/+/, '');
    if (clean.startsWith('.lantern_uploads/')) {
      return '/' + clean.split('/').map(encodeURIComponent).join('/');
    }
    return `/api/thumb?p=${encodeURIComponent(clean)}`;
  }

  function loadAttachments() {
    try {
      const items = JSON.parse(sessionStorage.getItem(ATTACHMENT_STORAGE_KEY) || '[]');
      if (!Array.isArray(items)) return [];
      return items
        .map(it => {
          if (typeof it === 'string') {
            const isImg = inferIsImage(it);
            return { path: it, name: it.split('/').pop() || it, isDir: false, isImage: isImg, previewUrl: inferPreviewUrl(it, isImg), source: 'manual' };
          }
          if (it && typeof it === 'object' && it.path) {
            const isImg = Boolean(it.isImage || inferIsImage(it.path, it.mime));
            return {
              path: String(it.path),
              name: String(it.name || String(it.path).split('/').pop() || it.path),
              isDir: Boolean(it.isDir),
              isImage: isImg,
              previewUrl: it.previewUrl || inferPreviewUrl(it.path, isImg),
              source: it.source || 'manual',
            };
          }
          return null;
        })
        .filter(Boolean);
    } catch {
      return [];
    }
  }

  function saveAttachments(items) {
    try {
      sessionStorage.setItem(ATTACHMENT_STORAGE_KEY, JSON.stringify(items));
    } catch {}
  }

  function upsertAttachments(newItems) {
    const existing = loadAttachments();
    const byPath = new Map(existing.map(item => [item.path, item]));
    for (const raw of newItems) {
      if (!raw) continue;
      const cleanPath = String(typeof raw === 'string' ? raw : raw.path || '').trim().replace(/^\/+/, '');
      if (!cleanPath) continue;
      state.dismissedPaths.delete(cleanPath);
      const isDir = Boolean(raw.isDir);
      const isImage = !isDir && Boolean(raw.isImage || inferIsImage(cleanPath, raw.mime));
      byPath.set(cleanPath, {
        path: cleanPath,
        name: String(raw.name || cleanPath.split('/').pop() || cleanPath),
        isDir,
        isImage,
        previewUrl: raw.previewUrl || inferPreviewUrl(cleanPath, isImage),
        source: raw.source || 'manual',
      });
    }
    const merged = Array.from(byPath.values()).slice(0, 32);
    saveAttachments(merged);
    renderContextBar();
    return merged;
  }

  function addAttachmentsFromSelection() {
    const selected = typeof window.selectedArray === 'function' ? window.selectedArray() : [];
    if (!Array.isArray(selected)) return loadAttachments();
    const existing = loadAttachments().filter(item => item.source !== 'selection');
    const byPath = new Map(existing.map(item => [item.path, item]));
    selected.forEach(rel => {
      const clean = String(rel || '').trim().replace(/^\/+/, '');
      if (!clean || state.dismissedPaths.has(clean)) return;
      const card = document.querySelector(`.card[data-rel="${CSS.escape(clean)}"]`);
      const isDir = card?.getAttribute('data-isdir') === '1';
      const isImage = !isDir && (card?.getAttribute('data-type') === 'image' || inferIsImage(clean));
      if (!byPath.has(clean)) {
        byPath.set(clean, {
          path: clean,
          name: clean.split('/').pop() || clean,
          isDir,
          isImage,
          previewUrl: inferPreviewUrl(clean, isImage),
          source: 'selection',
        });
      }
    });
    const merged = Array.from(byPath.values()).slice(0, 32);
    saveAttachments(merged);
    return merged;
  }

  function attachmentPaths() {
    return loadAttachments()
      .map(item => String(item.path || '').trim())
      .filter(p => p && !state.dismissedPaths.has(p));
  }

  // Safely stringify any value so [object Object] NEVER appears
  function safeText(val) {
    if (val == null) return '';
    if (typeof val === 'string') return val;
    if (typeof val === 'number' || typeof val === 'boolean') return String(val);
    if (Array.isArray(val)) {
      return val.map(safeText).filter(Boolean).join('\n');
    }
    if (typeof val === 'object') {
      if (typeof val.text === 'string') return val.text;
      if (typeof val.content === 'string') return val.content;
      if (Array.isArray(val.content)) return safeText(val.content);
      if (typeof val.thinking === 'string') return val.thinking;
      if (typeof val.result === 'string') return val.result;
      if (typeof val.summary === 'string') return val.summary;
      try {
        return JSON.stringify(val, null, 2);
      } catch {
        return '';
      }
    }
    return String(val);
  }

  // Parse <task-notification> XML blocks client-side
  function extractSubagentBlocks(rawText) {
    const str = safeText(rawText);
    const subagents = [];
    const regex = /<task-notification>([\s\S]*?)<\/task-notification>(?:\s*Full transcript available at:\s*([^\r\n<]+))?/gi;
    const cleaned = str.replace(regex, (_, body, transcriptAfter) => {
      const tag = name => {
        const m = new RegExp(`<${name}>([\\s\\S]*?)<\\/${name}>`, 'i').exec(body);
        return m ? m[1].trim() : '';
      };
      const outPath = tag('output-file') || (transcriptAfter ? transcriptAfter.trim() : '');
      subagents.push({
        taskId: tag('task-id'),
        toolUseId: tag('tool-use-id'),
        outputFile: outPath,
        status: tag('status') || 'Done',
        summary: tag('summary'),
        result: tag('result'),
        totalTokens: Number(tag('total_tokens') || 0),
        toolUses: Number(tag('tool_uses') || 0),
        contextPercent: Number(tag('context_percent') || 0),
        durationMs: Number(tag('duration_ms') || 0),
      });
      return '';
    });
    return { cleanedText: cleaned.replace(/\n{3,}/g, '\n\n').trim(), subagents };
  }

  // Convert raw Pi message objects into structured UI messages
  function normalizeRawMessage(rawMsg) {
    if (!rawMsg || typeof rawMsg !== 'object') {
      return { role: 'system', text: safeText(rawMsg), thinking: '', toolCalls: [], subagents: [] };
    }
    if (Array.isArray(rawMsg.toolCalls) && typeof rawMsg.text === 'string' && !rawMsg.content) {
      return rawMsg;
    }
    const role = String(rawMsg.role || 'assistant');
    const content = rawMsg.content;
    const textParts = [];
    const thinkingParts = [];
    const toolCalls = [];

    if (typeof content === 'string') {
      textParts.push(content);
    } else if (Array.isArray(content)) {
      content.forEach(item => {
        if (typeof item === 'string') {
          textParts.push(item);
        } else if (item && typeof item === 'object') {
          const btype = String(item.type || '');
          if (btype === 'text') {
            textParts.push(safeText(item.text ?? item.content));
          } else if (btype === 'thinking' || btype === 'reasoning') {
            thinkingParts.push(safeText(item.thinking ?? item.text));
          } else if (btype === 'toolCall' || btype === 'tool_use' || btype === 'tool_call') {
            toolCalls.push({
              id: String(item.id || item.toolCallId || ''),
              name: String(item.name || item.toolName || 'tool'),
              arguments: item.arguments || item.input || item.args || {},
            });
          } else if (btype === 'toolResult' || btype === 'tool_result') {
            toolCalls.push({
              id: String(item.toolUseId || item.toolCallId || ''),
              name: String(item.toolName || 'result'),
              result: safeText(item.content ?? item.text),
              isError: Boolean(item.isError),
              truncated: Boolean(item.truncated || rawMsg.truncated),
              fullLength: Number(item.fullLength || rawMsg.fullLength || 0),
              msgIndex: item.msgIndex ?? rawMsg.msgIndex ?? rawMsg._msgIndex,
              toolIndex: item.toolIndex ?? 0,
            });
          } else if (typeof item.text === 'string') {
            textParts.push(item.text);
          } else if (typeof item.content === 'string') {
            textParts.push(item.content);
          }
        }
      });
    } else if (typeof rawMsg.text === 'string') {
      textParts.push(rawMsg.text);
    }

    let fullText = textParts.join('\n');
    let parsedContext = rawMsg.context || null;

    if (role === 'user') {
      const ctxMatch = fullText.match(/<lantern_context>\s*([\s\S]*?)\s*<\/lantern_context>/i);
      const reqMatch = fullText.match(/<user_request>\s*([\s\S]*?)\s*<\/user_request>/i);
      if (ctxMatch && !parsedContext) {
        const block = ctxMatch[1];
        const pathM = block.match(/logicalPath:\s*([^\r\n]+)/i) || block.match(/path:\s*([^\r\n]+)/i);
        const lineM = block.match(/line:\s*(\d+)/i);
        const attSection = block.split(/attachments:\s*\n/i)[1] || '';
        const atts = attSection
          .split(/\r?\n/)
          .map(l => l.replace(/^\s*-\s*/, '').trim())
          .filter(Boolean);
        parsedContext = {
          path: pathM ? pathM[1].trim().split(/[\\/]/).slice(-2).join('/') : '',
          line: lineM ? Number(lineM[1]) : null,
          attachments: atts.map(a => a.split(/[\\/]/).pop() || a),
        };
      }
      if (reqMatch) {
        fullText = reqMatch[1].trim();
      }
    }

    const { cleanedText, subagents } = extractSubagentBlocks(fullText);
    return {
      role,
      text: cleanedText,
      thinking: thinkingParts.filter(Boolean).join('\n') || safeText(rawMsg.thinking),
      toolCalls: toolCalls.length ? toolCalls : (Array.isArray(rawMsg.tools) ? rawMsg.tools : []),
      subagents,
      context: parsedContext,
      _msgIndex: rawMsg._msgIndex ?? rawMsg.msgIndex,
      truncated: Boolean(rawMsg.truncated),
      fullLength: Number(rawMsg.fullLength || 0),
    };
  }

  // --- Upload Pasted or Dragged OS Files/Images to /api/chatbot/upload ---
  async function uploadClientFiles(fileList, sourceLabel = 'paste') {
    const files = Array.from(fileList || []).filter(f => f && f.size > 0);
    if (!files.length) return [];
    state.uploadingCount += files.length;
    setStatus(`Uploading ${files.length} attachment(s)…`, 'info');
    renderContextBar();
    try {
      const encoded = await Promise.all(
        files.slice(0, 16).map(
          file =>
            new Promise((resolve, reject) => {
              const reader = new FileReader();
              reader.onload = () => {
                const ext = (file.type || '').split('/')[1] || 'png';
                const fallbackName = `pasted-image-${Date.now()}.${ext.replace(/[^a-z0-9]/gi, '') || 'png'}`;
                resolve({
                  name: file.name || fallbackName,
                  type: file.type || 'application/octet-stream',
                  size: file.size,
                  source: sourceLabel,
                  dataBase64: String(reader.result || ''),
                });
              };
              reader.onerror = () => reject(reader.error || new Error('File read error'));
              reader.readAsDataURL(file);
            })
        )
      );

      const resp = await fetch('/api/chatbot/upload', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ files: encoded }),
      });
      const data = await resp.json();
      if (!resp.ok || !data?.ok) {
        throw new Error(data?.error || `Upload failed (HTTP ${resp.status})`);
      }
      const added = upsertAttachments(data.attachments || []);
      setStatus(`Attached ${(data.attachments || []).length} file(s) to context.`, 'info');
      return added;
    } catch (err) {
      setStatus('Attachment upload failed: ' + (err?.message || err), 'error');
      return [];
    } finally {
      state.uploadingCount = Math.max(0, state.uploadingCount - files.length);
      renderContextBar();
    }
  }

  function isSelectionInsideChatDrawer() {
    try {
      const activeEl = document.activeElement;
      if (activeEl && (drawer.contains(activeEl) || fab.contains(activeEl))) return true;
      const sel = window.getSelection?.();
      if (!sel || sel.rangeCount === 0) return false;
      const anchor = sel.anchorNode;
      const focus = sel.focusNode;
      if (anchor && (drawer.contains(anchor) || fab.contains(anchor))) return true;
      if (focus && (drawer.contains(focus) || fab.contains(focus))) return true;
    } catch {}
    return false;
  }

  // --- Capture Live Lantern Context ---
  function captureContext() {
    const rawKind = document.body?.dataset?.lanternChatKind || 'files';
    let activePath = String(document.body?.dataset?.lanternChatPath || '').replace(/^\/+/, '');
    const folder = typeof window.currentPath === 'function'
      ? String(window.currentPath() || '').replace(/^\/+/, '')
      : String(window.APP?.currentPath || '').replace(/^\/+/, '');

    let markdownMode = null;
    let line = null;
    let endLine = null;
    let selectedText = '';

    if (rawKind === 'markdown' && activePath) {
      const rawMode = window.__lanternMdVisual?.state?.mode || (window.__lanternMdPaged ? 'paged' : 'preview');
      markdownMode = rawMode === 'paged' ? 'visual' : rawMode;
      if (window.LanternAnchorBridge && typeof window.LanternAnchorBridge.capture === 'function') {
        try {
          const anchor = window.LanternAnchorBridge.capture(markdownMode);
          if (anchor) {
            line = anchor.line || anchor.startLine || null;
            endLine = anchor.endLine || null;
            selectedText = anchor.selectedText || '';
          }
        } catch {}
      }
      if (!selectedText && markdownMode === 'source') {
        const area = document.querySelector('textarea.md-source-area');
        if (area) {
          const before = area.value.slice(0, area.selectionStart);
          line = before.split('\n').length;
          selectedText = area.value.slice(area.selectionStart, area.selectionEnd);
        }
      }
      if (!selectedText) {
        try {
          if (!isSelectionInsideChatDrawer()) {
            selectedText = String(window.getSelection?.()?.toString() || '').trim();
          }
        } catch {}
      }
    } else if (rawKind === 'file' && activePath) {
      const editArea = document.getElementById('editarea');
      if (editArea && typeof editArea.value === 'string') {
        const startPos = Number(editArea.selectionStart || 0);
        const endPos = Number(editArea.selectionEnd || 0);
        line = editArea.value.slice(0, startPos).split('\n').length;
        if (endPos > startPos) {
          selectedText = editArea.value.slice(startPos, endPos);
          endLine = editArea.value.slice(0, endPos).split('\n').length;
        }
      }
      if (!selectedText && !isSelectionInsideChatDrawer()) {
        try {
          selectedText = String(window.getSelection?.()?.toString() || '').trim();
          const textPre = document.querySelector('pre.text-preview');
          if (selectedText && textPre && textPre.textContent) {
            const idx = textPre.textContent.indexOf(selectedText);
            if (idx >= 0) {
              line = textPre.textContent.slice(0, idx).split('\n').length;
            }
          }
        } catch {}
      }
    } else {
      addAttachmentsFromSelection();
      if (!isSelectionInsideChatDrawer()) {
        try {
          selectedText = String(window.getSelection?.()?.toString() || '').trim();
        } catch {}
      }
    }

    if (selectedText && selectedText.trim().length < 2) {
      selectedText = '';
    }
    if (selectedText) {
      state.cachedSelection = selectedText;
      if (line) state.cachedSelectionLine = line;
      if (endLine) state.cachedSelectionEndLine = endLine;
    } else if (!state.dismissedSelection && state.cachedSelection && state.cachedSelection.trim().length >= 2) {
      selectedText = state.cachedSelection;
      if (!line && state.cachedSelectionLine) line = state.cachedSelectionLine;
      if (!endLine && state.cachedSelectionEndLine) endLine = state.cachedSelectionEndLine;
    }

    const rawAttachments = loadAttachments().filter(item => !state.dismissedPaths.has(item.path));
    // v7.7 fix: On folder view (rawKind === 'files'), selected files MUST stay in `attachments`
    // so their attachment chips (📎/🖼️) always render on the chat context bar!
    // Only deduplicate against `activePath` when viewing a standalone file or markdown document.
    const isStandaloneDoc = (rawKind === 'markdown' || rawKind === 'file') && Boolean(activePath);
    if (!isStandaloneDoc) {
      activePath = '';
    }
    const normActive = isStandaloneDoc ? activePath.replace(/^\/+/, '') : '';
    const attachments = normActive
      ? rawAttachments.filter(item => String(item.path || '').replace(/^\/+/, '') !== normActive)
      : rawAttachments;
    const paths = rawAttachments.map(item => item.path);
    const kind = (rawKind === 'markdown' && activePath)
      ? 'markdown'
      : ((rawKind === 'file' && activePath) ? 'file' : 'folder');

    if (IS_STANDALONE_CHAT && state.remoteContext && typeof state.remoteContext === 'object') {
      return {
        kind: state.remoteContext.kind || kind,
        path: state.remoteContext.path || activePath || null,
        folder: state.remoteContext.folder || folderPath || '/',
        markdownMode: state.remoteContext.markdownMode || markdownMode,
        line: state.remoteContext.line ?? line,
        endLine: state.remoteContext.endLine ?? endLine,
        selectedText: state.remoteContext.selectedText || (state.dismissedSelection ? '' : selectedText.slice(0, 2400)),
        attachments,
        attachmentPaths: paths,
      };
    }
    const resolvedFolder = (folder && folder !== activePath)
      ? folder
      : (activePath.includes('/') ? activePath.split('/').slice(0, -1).join('/') : '');
    const capturedObj = {
      kind,
      path: activePath || '',
      folder: resolvedFolder,
      markdownMode,
      line,
      endLine,
      selectedText: state.dismissedSelection ? '' : selectedText.slice(0, 2400),
      attachments,
      attachmentPaths: paths,
    };
    try {
      contextChannel?.postMessage({
        type: 'context_update',
        clientSessionId: state.clientSessionId,
        context: {
          kind: capturedObj.kind,
          path: capturedObj.path,
          folder: capturedObj.folder,
          markdownMode: capturedObj.markdownMode,
          line: capturedObj.line,
          endLine: capturedObj.endLine,
          selectedText: capturedObj.selectedText,
        },
      });
    } catch {}
    return capturedObj;
  }

  // --- Prepare Markdown Working Copy Before Turn (Layer 1 support) ---
  async function prepareMarkdownTurn(context = null) {
    const kind = context?.kind || document.body?.dataset?.lanternChatKind || '';
    const mdPath = context?.path || document.body?.dataset?.lanternChatPath || '';
    if (kind !== 'markdown' || !mdPath) return { path: null, workHash: null };
    try {
      if (window.__lanternMdPaged && typeof window.__lanternMdPaged.beginBotTurn === 'function') {
        const workHash = await window.__lanternMdPaged.beginBotTurn();
        activeMarkdownTurn = { target: window.__lanternMdPaged, path: mdPath };
        return { path: mdPath, workHash };
      }
      if (window.__lanternMdVisual && typeof window.__lanternMdVisual.beginBotTurn === 'function') {
        const workHash = await window.__lanternMdVisual.beginBotTurn({
          skipDraftFlush: Boolean(state.skipDraftFlush),
        });
        activeMarkdownTurn = { target: window.__lanternMdVisual, path: mdPath };
        return { path: mdPath, workHash };
      }
    } catch (err) {
      console.warn('Lantern Chatbot non-fatal working copy sync warning:', err);
    }
    return { path: mdPath, workHash: null };
  }

  function releaseMarkdownTurn() {
    try {
      if (window.__lanternMdVisual?.cancelBotTurn) window.__lanternMdVisual.cancelBotTurn();
      if (window.__lanternMdPaged?.cancelBotTurn) window.__lanternMdPaged.cancelBotTurn();
    } catch {}
    activeMarkdownTurn = null;
  }

  // --- Build DOM (Lanbot + Glowing Lantern SVG Icon + 100% English UI) ---
  const LANTERN_SVG = `
    <svg class="lc-lantern-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M9 3H15M12 2V4" stroke="#FBBF24" stroke-width="1.8" stroke-linecap="round"/>
      <rect x="6" y="5" width="12" height="13" rx="5" fill="rgba(245, 158, 11, 0.22)" stroke="#F59E0B" stroke-width="1.8"/>
      <path d="M9.5 5C8.3 8.2 8.3 14.8 9.5 18M14.5 5C15.7 8.2 15.7 14.8 14.5 18" stroke="#FBBF24" stroke-width="1.2" stroke-opacity="0.75"/>
      <circle cx="12" cy="11.5" r="2.4" fill="#FDE68A"/>
      <path d="M9 18H15M12 18V21.5M10.5 21.5H13.5" stroke="#FBBF24" stroke-width="1.8" stroke-linecap="round"/>
    </svg>
  `;

  const fab = document.createElement('button');
  fab.type = 'button';
  fab.className = 'lantern-chat-fab';
  fab.title = 'Lanbot (Alt+L — Drag to dock Left/Right, or drop files/images here)';
  fab.setAttribute('aria-label', 'Lanbot');
  fab.innerHTML = `
    ${LANTERN_SVG}
    <span class="lantern-chat-fab-dot"></span>
  `;

  const drawer = document.createElement('aside');
  drawer.className = 'lantern-chat-drawer';
  drawer.id = 'lanternChatDrawer';
  drawer.setAttribute('aria-label', 'Lanbot');
  drawer.innerHTML = `
    <div class="lantern-chat-resizer" title="Drag to resize panel"></div>
    <div class="lc-drop-overlay" id="lcDropOverlay" hidden>
      <div class="lc-drop-overlay-icon">📥</div>
      <div class="lc-drop-overlay-title">Drop images or files here</div>
      <div class="lc-drop-overlay-sub">Automatically attach to Lanbot context</div>
    </div>
    <header class="lc-header">
      <div class="lc-brand">
        <span class="lc-status-dot" id="lcStatusDot"></span>
        ${LANTERN_SVG.replace('lc-lantern-svg', 'lc-brand-svg')}
        <span>Lanbot</span>
        <button type="button" class="lc-icon-btn" id="lcSessionBtn" title="Switch or manage conversations" style="max-width:165px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
          · <span id="lcSessionTitle">New chat</span> ▾
        </button>
      </div>
      <div class="lc-header-actions">
        <button type="button" class="lc-icon-btn" id="lcNewBtn" title="New chat (+)">＋</button>
        <button type="button" class="lc-icon-btn" id="lcPopoutBtn" title="Pop out Lanbot into a standalone window (stays still across folder navigations)">↗</button>
        <button type="button" class="lc-icon-btn" id="lcSettingsBtn" title="Settings (Thinking, System Prompt, Skills & Export HTML)">⚙</button>
        <button type="button" class="lc-icon-btn" id="lcDockBtn" title="Dock Left / Right">⇤</button>
        <button type="button" class="lc-icon-btn" id="lcExpandBtn" title="Expand 50% Split View">⤢</button>
        <button type="button" class="lc-icon-btn" id="lcCloseBtn" title="Close (Alt+L)">✕</button>
      </div>
    </header>
    <div class="lc-subbar">
      <span class="lc-subbar-status" id="lcStatusText">Ready</span>
      <span id="lcTokenBadge" title="Current context size (use /compact to reduce)">0 msgs · 0 tok</span>
    </div>
    <div class="lc-transcript" id="lcTranscript"></div>
    <div class="lc-context-bar" id="lcContextBar"></div>
    <div id="lanternChatAttachments" hidden></div>
    <div class="lc-composer">
      <button type="button" class="lc-scroll-bottom-btn" id="lcScrollBottomBtn" title="Scroll to bottom" aria-label="Scroll to bottom" hidden>↓</button>
      <div class="lc-input-resizer" id="lcInputResizer" title="Drag up or down to resize prompt box"><span></span></div>
      <div class="lc-slash-popover" id="lcSlashPopover" hidden></div>
      <div class="lc-activity-ticker" id="lcActivityTicker" hidden>
        <div class="lc-activity-ticker-left">
          <span class="lc-activity-spinner"></span>
          <span id="lcActivityTickerText">Lanbot is working…</span>
        </div>
        <span id="lcActivitySteerHint" style="font-size:10.5px;color:#93c5fd">Type & press Enter to Steer ↳</span>
      </div>
      <input type="file" id="lcFileInput" multiple hidden />
      <textarea class="lc-input" id="lcInput" rows="5" placeholder="Ask Lanbot, paste images (Ctrl+V), drop files, or type / for commands…"></textarea>
      <div class="lc-composer-foot">
        <div class="lc-composer-foot-left">
          <button type="button" class="lc-model-pill" id="lcModelBtn" title="Select Model & Provider (/model)">
            <span class="lc-provider-tag" id="lanternChatProvider" hidden>auto</span>
            <span id="lanternChatModel">Select model</span> ▾
          </button>
          <button type="button" class="lc-icon-btn" id="lcAttachBtn" title="Attach images or files (or Ctrl+V / Drag & Drop)">📎 Attach</button>
          <button type="button" class="lc-icon-btn" id="lcContextToggle" title="Toggle lightweight metadata context">👁 Context: ON</button>
        </div>
        <div class="lc-composer-foot-right">
          <button type="button" class="lc-stop-btn" id="lcStopBtn" hidden>■ Stop</button>
          <button type="button" class="lc-send-btn" id="lcSendBtn">Send ↵</button>
        </div>
      </div>
    </div>

    <!-- Model Selector Overlay -->
    <div class="lc-overlay-modal" id="lcModelModal" hidden>
      <div class="lc-modal-head">
        <span>🤖 Select Model (Provider / Model · ★ Favorite)</span>
        <button type="button" class="lc-icon-btn" data-close-modal="lcModelModal">✕</button>
      </div>
      <input type="search" class="lc-input" id="lcModelSearch" style="min-height:34px;max-height:34px" placeholder="Filter by provider or model name…" />
      <div class="lc-model-list" id="lcModelList"></div>
    </div>

    <!-- Sessions Overlay -->
    <div class="lc-overlay-modal" id="lcSessionModal" hidden>
      <div class="lc-modal-head">
        <span>🗂 Conversations</span>
        <div style="display:flex;gap:5px">
          <button type="button" class="lc-icon-btn" id="lcCompactBtn" title="Compact context (/compact)">🗜 Compact</button>
          <button type="button" class="lc-icon-btn" id="lcForkBtn" title="Fork session (/fork)">⑂ Fork</button>
          <button type="button" class="lc-icon-btn" data-close-modal="lcSessionModal">✕</button>
        </div>
      </div>
      <div class="lc-model-list" id="lcSessionList"></div>
    </div>

    <!-- Settings Overlay (Tool/Extension/MCP flags are governed strictly by backend YAML) -->
    <div class="lc-overlay-modal" id="lcSettingsModal" hidden>
      <div class="lc-modal-head">
        <span>⚙ Lanbot Settings</span>
        <button type="button" class="lc-icon-btn" data-close-modal="lcSettingsModal">✕</button>
      </div>
      <div style="display:flex;flex-direction:column;gap:12px;overflow-y:auto;padding-right:2px">
        <label style="display:flex;flex-direction:column;gap:5px;font-size:12px;font-weight:700">
          <span>🧠 Thinking Level</span>
          <select id="lcThinkingSelect" class="lc-input" style="min-height:36px"></select>
        </label>
        <div style="display:flex;flex-direction:column;gap:4px;font-size:11.5px;color:var(--lc-muted);padding-top:6px;border-top:1px solid var(--lc-border)">
          <span style="font-size:12px;font-weight:700;color:var(--lc-fg)">🛡️ Backend Access Policy (YAML)</span>
          <span id="lcYamlPolicySummary">Governed by lan_drive_config.yaml (Localhost Full/YOLO "*")</span>
        </div>
        <label style="display:flex;flex-direction:column;gap:5px;font-size:12px;font-weight:700;padding-top:8px;border-top:1px solid var(--lc-border)">
          <span>📝 Custom System Prompt (Appended to Lanbot instructions)</span>
          <textarea id="lcCustomPromptInput" class="lc-input" rows="3" placeholder="Add custom instructions, coding conventions, or persona rules for Lanbot…"></textarea>
        </label>
        <div style="display:flex;flex-direction:column;gap:6px;padding-top:8px;border-top:1px solid var(--lc-border)">
          <span style="font-size:12px;font-weight:700">🧰 Skills Configuration</span>
          <label style="display:flex;align-items:center;gap:7px;font-size:12px;cursor:pointer">
            <input type="checkbox" id="lcUseGlobalSkillsCheck" checked />
            <span>Enable Global Skills on this machine (~/.pi/agent/skills)</span>
          </label>
          <label style="display:flex;flex-direction:column;gap:4px;font-size:11.5px;color:var(--lc-muted)">
            <span>Custom Skill Directories / SKILL.md Paths (one per line or comma-separated):</span>
            <textarea id="lcCustomSkillPathsInput" class="lc-input" rows="2" placeholder="/path/to/custom-skills&#10;./skills/my-skill"></textarea>
          </label>
          <div id="lcDiscoveredSkillsList" style="display:flex;flex-wrap:wrap;gap:4px;margin-top:2px"></div>
          <button type="button" class="lc-send-btn" id="lcSavePrefsBtn" style="align-self:flex-start;margin-top:4px">💾 Save Prompt & Skills</button>
        </div>
        <div style="display:flex;flex-direction:column;gap:6px;padding-top:8px;border-top:1px solid var(--lc-border)">
          <span style="font-size:12px;font-weight:700">📄 Session &amp; Runtime Actions</span>
          <div style="display:flex;gap:6px;flex-wrap:wrap">
            <button type="button" class="lc-diff-btn accept" id="lcExportFullBtn">⤓ Export Full Unabbreviated HTML</button>
            <button type="button" class="lc-diff-btn" id="lcCompactNowBtn">🗜 Compact Context Now</button>
            <button type="button" class="lc-diff-btn" id="lcResetBotBtn" style="border-color:#f59e0b;color:#fcd34d" title="Force-restart Lanbot process and clear stuck turn locks without restarting the server (/reset-bot)">🔄 Reset Lanbot</button>
          </div>
        </div>
        <div id="lcAuthBox" style="display:flex;flex-direction:column;gap:6px;padding-top:8px;border-top:1px solid var(--lc-border)">
          <span style="font-size:12px;font-weight:700">🔒 Terminal & LAN Master Lock (Localhost Keyholder)</span>
          <div style="display:flex;gap:6px;flex-wrap:wrap" id="lcLocalMasterLockRow">
            <button type="button" class="lc-diff-btn" id="lcLockLanBtn" title="Revoke all active LAN sessions and hard-lock LAN access">🔒 Lock All LAN</button>
            <button type="button" class="lc-diff-btn accept" id="lcAllowLanBtn" title="Allow LAN clients to unlock with password">🔓 Allow LAN Login</button>
          </div>
          <div style="display:flex;gap:6px" id="lcLanPasswordRow">
            <input type="password" id="lcPasswordInput" class="lc-input" style="min-height:34px" placeholder="Terminal password (LAN)…" />
            <button type="button" class="lc-send-btn" id="lcUnlockBtn">Unlock</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Subagent Full Transcript Modal -->
    <div class="lc-overlay-modal" id="lcTranscriptModal" hidden>
      <div class="lc-modal-head">
        <span id="lcTranscriptModalTitle">Subagent Transcript</span>
        <button type="button" class="lc-icon-btn" data-close-modal="lcTranscriptModal">✕</button>
      </div>
      <pre id="lcTranscriptModalBody" style="flex:1;margin:0;padding:10px;border-radius:8px;background:#06090f;border:1px solid var(--lc-border);overflow:auto;font:11.5px/1.45 var(--lc-font-mono);white-space:pre-wrap"></pre>
    </div>

    <!-- Fork Checkpoint Picker Modal (v7.5) -->
    <div class="lc-overlay-modal" id="lcForkModal" hidden>
      <div class="lc-modal-head">
        <span id="lcForkModalTitle">⑂ Fork Conversation at Checkpoint</span>
        <button type="button" class="lc-icon-btn" data-close-modal="lcForkModal">✕</button>
      </div>
      <div style="display:flex;gap:6px;align-items:center;margin-bottom:6px">
        <input type="text" class="lc-input" id="lcForkNameInput" style="min-height:32px;max-height:32px;flex:1" placeholder="Optional name for forked session (e.g. Tab 2 - File B)…" />
        <button type="button" class="lc-send-btn" id="lcForkFullBtn" style="height:32px;padding:0 10px;font-size:11.5px;white-space:nowrap">⑂ Fork Latest</button>
      </div>
      <div style="font-size:11px;color:var(--lc-muted);margin-bottom:4px">Or click any turn below to fork right after that step (e.g. right after loading a workflow):</div>
      <div class="lc-model-list" id="lcForkTurnList"></div>
    </div>

    <!-- Workspace Folder Attach Picker Modal (v7.5: Defaults to Current Active Folder A) -->
    <div class="lc-overlay-modal" id="lcAttachModal" hidden>
      <div class="lc-modal-head">
        <span id="lcAttachModalTitle">📎 Attach Files from Folder</span>
        <div style="display:flex;gap:5px;align-items:center">
          <button type="button" class="lc-icon-btn" id="lcAttachUpBtn" title="Go to parent folder">⬆️ Up</button>
          <button type="button" class="lc-icon-btn" id="lcAttachOsBtn" title="Upload external file from your computer">💻 PC File…</button>
          <button type="button" class="lc-icon-btn" data-close-modal="lcAttachModal">✕</button>
        </div>
      </div>
      <div style="display:flex;gap:6px;align-items:center;margin-bottom:6px">
        <span id="lcAttachFolderLabel" style="font:700 11px/1.3 var(--lc-font-mono);color:#68e37a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:48%">/</span>
        <input type="search" class="lc-input" id="lcAttachSearch" style="min-height:30px;max-height:30px;flex:1" placeholder="Filter files in this folder…" />
      </div>
      <div class="lc-model-list" id="lcAttachFileList"></div>
    </div>
  `;

  document.body.append(fab, drawer);

  const els = {
    resizer: drawer.querySelector('.lantern-chat-resizer'),
    inputResizer: drawer.querySelector('#lcInputResizer'),
    dropOverlay: drawer.querySelector('#lcDropOverlay'),
    statusDot: drawer.querySelector('#lcStatusDot'),
    sessionBtn: drawer.querySelector('#lcSessionBtn'),
    sessionTitle: drawer.querySelector('#lcSessionTitle'),
    newBtn: drawer.querySelector('#lcNewBtn'),
    popoutBtn: drawer.querySelector('#lcPopoutBtn'),
    exportBtn: drawer.querySelector('#lcExportBtn'),
    settingsBtn: drawer.querySelector('#lcSettingsBtn'),
    dockBtn: drawer.querySelector('#lcDockBtn'),
    expandBtn: drawer.querySelector('#lcExpandBtn'),
    closeBtn: drawer.querySelector('#lcCloseBtn'),
    statusText: drawer.querySelector('#lcStatusText'),
    tokenBadge: drawer.querySelector('#lcTokenBadge'),
    transcript: drawer.querySelector('#lcTranscript'),
    contextBar: drawer.querySelector('#lcContextBar'),
    scrollBottomBtn: drawer.querySelector('#lcScrollBottomBtn'),
    slashPopover: drawer.querySelector('#lcSlashPopover'),
    fileInput: drawer.querySelector('#lcFileInput'),
    input: drawer.querySelector('#lcInput'),
    modelBtn: drawer.querySelector('#lcModelBtn'),
    providerSpan: drawer.querySelector('#lanternChatProvider'),
    modelSpan: drawer.querySelector('#lanternChatModel'),
    attachBtn: drawer.querySelector('#lcAttachBtn'),
    contextToggle: drawer.querySelector('#lcContextToggle'),
    stopBtn: drawer.querySelector('#lcStopBtn'),
    sendBtn: drawer.querySelector('#lcSendBtn'),
    modelModal: drawer.querySelector('#lcModelModal'),
    modelSearch: drawer.querySelector('#lcModelSearch'),
    modelList: drawer.querySelector('#lcModelList'),
    sessionModal: drawer.querySelector('#lcSessionModal'),
    sessionList: drawer.querySelector('#lcSessionList'),
    compactBtn: drawer.querySelector('#lcCompactBtn'),
    forkBtn: drawer.querySelector('#lcForkBtn'),
    settingsModal: drawer.querySelector('#lcSettingsModal'),
    thinkingSelect: drawer.querySelector('#lcThinkingSelect'),
    yamlPolicySummary: drawer.querySelector('#lcYamlPolicySummary'),
    exportFullBtn: drawer.querySelector('#lcExportFullBtn'),
    compactNowBtn: drawer.querySelector('#lcCompactNowBtn'),
    resetBotBtn: drawer.querySelector('#lcResetBotBtn'),
    passwordInput: drawer.querySelector('#lcPasswordInput'),
    unlockBtn: drawer.querySelector('#lcUnlockBtn'),
    lockLanBtn: drawer.querySelector('#lcLockLanBtn'),
    allowLanBtn: drawer.querySelector('#lcAllowLanBtn'),
    transcriptModal: drawer.querySelector('#lcTranscriptModal'),
    transcriptModalTitle: drawer.querySelector('#lcTranscriptModalTitle'),
    transcriptModalBody: drawer.querySelector('#lcTranscriptModalBody'),
    activityTicker: drawer.querySelector('#lcActivityTicker'),
    activityTickerText: drawer.querySelector('#lcActivityTickerText'),
    activitySteerHint: drawer.querySelector('#lcActivitySteerHint'),
    customPromptInput: drawer.querySelector('#lcCustomPromptInput'),
    useGlobalSkillsCheck: drawer.querySelector('#lcUseGlobalSkillsCheck'),
    customSkillPathsInput: drawer.querySelector('#lcCustomSkillPathsInput'),
    discoveredSkillsList: drawer.querySelector('#lcDiscoveredSkillsList'),
    savePrefsBtn: drawer.querySelector('#lcSavePrefsBtn'),
    forkModal: drawer.querySelector('#lcForkModal'),
    forkModalTitle: drawer.querySelector('#lcForkModalTitle'),
    forkNameInput: drawer.querySelector('#lcForkNameInput'),
    forkFullBtn: drawer.querySelector('#lcForkFullBtn'),
    forkTurnList: drawer.querySelector('#lcForkTurnList'),
    attachModal: drawer.querySelector('#lcAttachModal'),
    attachModalTitle: drawer.querySelector('#lcAttachModalTitle'),
    attachUpBtn: drawer.querySelector('#lcAttachUpBtn'),
    attachOsBtn: drawer.querySelector('#lcAttachOsBtn'),
    attachFolderLabel: drawer.querySelector('#lcAttachFolderLabel'),
    attachSearch: drawer.querySelector('#lcAttachSearch'),
    attachFileList: drawer.querySelector('#lcAttachFileList'),
  };

  // --- Apply Layout & Split Push ---
  function applyLayout() {
    const effectiveWidth = prefs.expanded ? Math.min(window.innerWidth * 0.5, 860) : prefs.width;
    document.documentElement.style.setProperty('--lantern-chat-width', `${Math.round(effectiveWidth)}px`);
    const inputH = Math.max(106, Math.min(360, Number(prefs.inputHeight) || 110));
    drawer.style.setProperty('--lc-input-height', `${Math.round(inputH)}px`);
    if (els.input) els.input.style.height = `${Math.round(inputH)}px`;
    drawer.dataset.dock = prefs.dock;
    fab.dataset.dock = prefs.dock;
    document.body.dataset.chatDock = prefs.dock;
    els.dockBtn.textContent = prefs.dock === 'right' ? '⇤' : '⇥';
    els.expandBtn.textContent = prefs.expanded ? '⤡' : '⤢';
    els.contextToggle.textContent = prefs.autoContext ? '👁 Context: ON' : '👁 Context: OFF';
    els.contextToggle.style.color = prefs.autoContext ? '#68e37a' : '#9fb1c5';

    const topPx = Math.max(16, Math.min(window.innerHeight - 62, Math.round(prefs.fabTopRatio * window.innerHeight)));
    fab.style.top = `${topPx}px`;
    fab.style.bottom = 'auto';

    if (prefs.open) {
      drawer.classList.add('open');
      fab.classList.add('hidden-when-open');
      document.body.classList.add('lantern-chat-open');
    } else {
      drawer.classList.remove('open');
      fab.classList.remove('hidden-when-open');
      document.body.classList.remove('lantern-chat-open');
    }
    saveUiPrefs();
  }

  function setStatus(text, kind = 'info') {
    els.statusText.textContent = text || 'Ready';
    els.statusText.dataset.kind = kind;
    els.statusDot.dataset.state = state.busy ? 'busy' : (kind === 'error' ? 'error' : 'ready');
    fab.dataset.busy = state.busy ? 'true' : 'false';
  }

  function setActivityTicker(text = '', showSteerHint = null) {
    if (!els.activityTicker || !els.activityTickerText) return;
    if (!text) {
      els.activityTicker.hidden = true;
      els.activityTickerText.textContent = '';
      if (els.activitySteerHint) els.activitySteerHint.hidden = true;
      return;
    }
    els.activityTicker.hidden = false;
    els.activityTickerText.textContent = text;
    if (els.activitySteerHint) {
      const canSteer = showSteerHint !== null ? Boolean(showSteerHint) : Boolean(state.busy);
      els.activitySteerHint.hidden = !canSteer;
    }
  }

  function syncSendButtonState() {
    if (!els.sendBtn) return;
    els.sendBtn.classList.remove('is-sending', 'is-steer');
    if (state.sendingImmediate) {
      els.sendBtn.textContent = 'Sending…';
      els.sendBtn.classList.add('is-sending');
      els.sendBtn.disabled = true;
      return;
    }
    if (state.busy) {
      // Keep button label 'Send ↵' while busy; mid-turn messages are auto-tagged with '↳ [Steer]'
      els.sendBtn.textContent = 'Send ↵';
      els.sendBtn.title = 'Send additional instruction to steer Lanbot mid-turn (auto-tagged ↳ [Steer])';
      els.sendBtn.classList.add('is-steer');
      els.sendBtn.disabled = false;
      return;
    }
    els.sendBtn.textContent = 'Send ↵';
    els.sendBtn.title = 'Send message (Enter)';
    els.sendBtn.disabled = false;
  }

  function setStreaming(flag) {
    state.streaming = Boolean(flag);
    state.busy = Boolean(flag);
    if (!state.busy) {
      state.sendingImmediate = false;
      state.steerCount = 0;
      setActivityTicker('');
    }
    els.stopBtn.hidden = !state.busy;
    els.statusDot.dataset.state = state.busy ? 'busy' : 'ready';
    fab.dataset.busy = state.busy ? 'true' : 'false';
    syncSendButtonState();
    if (!state.streaming) {
      drawer.querySelectorAll('.lc-msg.streaming').forEach(el => el.classList.remove('streaming'));
      streamingNode = null;
      streamingThinkingNode = null;
    }
    updateScrollBottomButton();
  }

  function syncAuthUi() {
    const locked = Boolean(state.passwordRequired && !state.unlocked);
    const localRow = drawer.querySelector('#lcLocalMasterLockRow');
    if (localRow) {
      localRow.style.display = state.isLocal ? 'flex' : 'none';
    }
    if (els.input) {
      els.input.disabled = locked;
      els.input.placeholder = locked
        ? '🔒 Lanbot is locked by host — open Settings (⚙) to enter password…'
        : 'Ask Lanbot, paste images (Ctrl+V), drop files, or type / for commands…';
    }
    if (els.sendBtn) els.sendBtn.disabled = locked || state.sendingImmediate;
    if (els.modelBtn) els.modelBtn.disabled = locked;
    if (els.sessionBtn) els.sessionBtn.disabled = locked;
    if (els.newBtn) els.newBtn.disabled = locked;
    if (els.attachBtn) els.attachBtn.disabled = locked;
    if (locked) {
      if (els.modelModal) els.modelModal.hidden = true;
      if (els.sessionModal) els.sessionModal.hidden = true;
      if (els.forkModal) els.forkModal.hidden = true;
      if (els.attachModal) els.attachModal.hidden = true;
    }
  }

  // --- Draggable Launcher with Magnetic Edge Snap ---
  let dragState = null;
  fab.addEventListener('pointerdown', e => {
    if (e.button !== 0) return;
    const rect = fab.getBoundingClientRect();
    dragState = { id: e.pointerId, startX: e.clientX, startY: e.clientY, origLeft: rect.left, origTop: rect.top, moved: false };
    fab.setPointerCapture(e.pointerId);
  });
  fab.addEventListener('pointermove', e => {
    if (!dragState || e.pointerId !== dragState.id) return;
    const dx = e.clientX - dragState.startX;
    const dy = e.clientY - dragState.startY;
    if (Math.hypot(dx, dy) > 5) dragState.moved = true;
    if (!dragState.moved) return;
    const nextTop = Math.max(16, Math.min(window.innerHeight - 62, dragState.origTop + dy));
    fab.style.top = `${nextTop}px`;
    fab.style.left = `${Math.max(10, Math.min(window.innerWidth - 56, dragState.origLeft + dx))}px`;
    fab.style.right = 'auto';
  });
  fab.addEventListener('pointerup', e => {
    if (!dragState || e.pointerId !== dragState.id) return;
    const wasMoved = dragState.moved;
    const rect = fab.getBoundingClientRect();
    dragState = null;
    fab.style.left = '';
    fab.style.right = '';
    if (wasMoved) {
      prefs.dock = (rect.left + rect.width / 2) < window.innerWidth / 2 ? 'left' : 'right';
      prefs.fabTopRatio = rect.top / Math.max(1, window.innerHeight);
      applyLayout();
    } else {
      prefs.open = !prefs.open;
      applyLayout();
      if (prefs.open) {
        if (!wsConnected) connectWs();
        else sendSync();
        renderContextBar();
        setTimeout(() => els.input.focus(), 50);
      }
    }
  });

  // Panel Width Resizer
  els.resizer.addEventListener('pointerdown', e => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = prefs.width;
    const onMove = mv => {
      const delta = prefs.dock === 'right' ? (startX - mv.clientX) : (mv.clientX - startX);
      prefs.expanded = false;
      prefs.width = Math.max(360, Math.min(820, startW + delta));
      applyLayout();
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  });

  // Prompt Box Vertical Drag-Resizer (drag upward to expand, downward to shrink)
  els.inputResizer?.addEventListener('pointerdown', e => {
    e.preventDefault();
    const startY = e.clientY;
    const startH = els.input.getBoundingClientRect().height || prefs.inputHeight || 110;
    const onMove = mv => {
      const deltaY = startY - mv.clientY;
      prefs.inputHeight = Math.max(106, Math.min(360, Math.round(startH + deltaY)));
      drawer.style.setProperty('--lc-input-height', `${prefs.inputHeight}px`);
      els.input.style.height = `${prefs.inputHeight}px`;
    };
    const onUp = () => {
      saveUiPrefs();
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  });

  // Isolate non-scrollable header/footer wheel events while letting .lc-transcript use native GPU smooth scrolling
  drawer.addEventListener('wheel', event => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;
    if (els.transcript && els.transcript.contains(target)) {
      return; // .lc-transcript has overscroll-behavior: contain; never block native smooth wheel scroll
    }
    if (target.closest('.lc-model-list, .lc-slash-popover, .lc-input, .lc-context-bar, pre')) {
      return;
    }
    event.preventDefault();
  }, { passive: false });

  // --- v7.5: Workspace Folder File Picker defaulted to current folder A + OS Upload Fallback ---
  let attachPickerFolder = '';
  let attachPickerItems = [];

  function renderAttachPickerList() {
    if (!els.attachFileList) return;
    els.attachFileList.textContent = '';
    const q = String(els.attachSearch?.value || '').trim().toLowerCase();
    const attachedSet = new Set(attachmentPaths());
    const filtered = attachPickerItems.filter(it => !it.special && (!q || String(it.name || it.rel || '').toLowerCase().includes(q)));
    if (!filtered.length) {
      const empty = document.createElement('div');
      empty.style.color = 'var(--lc-muted)';
      empty.style.fontSize = '12px';
      empty.style.padding = '8px';
      empty.textContent = 'No matching files in this folder.';
      els.attachFileList.appendChild(empty);
      return;
    }
    filtered.forEach(item => {
      const rel = String(item.rel || '').replace(/^\/+/, '');
      const isDir = item.kind === 'dir' || Boolean(item.isDir);
      const isAttached = attachedSet.has(rel);
      const row = document.createElement('div');
      row.className = 'lc-model-row' + (isAttached ? ' active' : '');
      const left = document.createElement('div');
      left.style.display = 'flex';
      left.style.alignItems = 'center';
      left.style.gap = '7px';
      left.style.minWidth = '0';
      left.style.flex = '1';
      const icon = document.createElement('span');
      icon.textContent = isDir ? '📁' : (inferIsImage(rel) ? '🖼️' : '📄');
      const name = document.createElement('span');
      name.style.fontWeight = '700';
      name.style.overflow = 'hidden';
      name.style.textOverflow = 'ellipsis';
      name.style.whiteSpace = 'nowrap';
      name.textContent = item.name || rel.split('/').pop() || rel;
      left.append(icon, name);

      const actionBtn = document.createElement('button');
      actionBtn.type = 'button';
      actionBtn.className = 'lc-diff-btn' + (isAttached ? ' accept' : '');
      actionBtn.textContent = isDir ? 'Open ▸' : (isAttached ? '✓ Attached (×)' : '＋ Attach');
      row.append(left, actionBtn);

      row.addEventListener('click', ev => {
        ev.stopPropagation();
        if (isDir) {
          void openWorkspaceAttachModal(rel);
          return;
        }
        if (attachedSet.has(rel)) {
          state.dismissedPaths.add(rel);
          saveAttachments(loadAttachments().filter(a => a.path !== rel));
        } else {
          state.dismissedPaths.delete(rel);
          upsertAttachments([{
            path: rel,
            name: item.name || rel.split('/').pop() || rel,
            isDir: false,
            isImage: inferIsImage(rel),
            source: 'folder-picker',
          }]);
        }
        renderContextBar();
        renderAttachPickerList();
      });
      els.attachFileList.appendChild(row);
    });
  }

  async function openWorkspaceAttachModal(targetFolder = null) {
    if (!els.attachModal) return;
    const ctx = captureContext();
    const initialFolder = targetFolder !== null
      ? String(targetFolder || '').replace(/^\/+|\/+$/g, '')
      : String(ctx.folder || (ctx.path && ctx.path.includes('/') ? ctx.path.split('/').slice(0, -1).join('/') : '')).replace(/^\/+|\/+$/g, '');
    attachPickerFolder = initialFolder;
    if (els.attachFolderLabel) {
      els.attachFolderLabel.textContent = '📁 /' + (attachPickerFolder || '');
      els.attachFolderLabel.title = '/' + (attachPickerFolder || '');
    }
    els.attachModal.hidden = false;
    els.attachFileList.innerHTML = '<div style="padding:8px;color:var(--lc-muted);font-size:12px">Loading folder files…</div>';
    try {
      const resp = await fetch(`/api/list?path=${encodeURIComponent(attachPickerFolder)}&limit=300`, { cache: 'no-store', credentials: 'same-origin' });
      const data = await resp.json();
      attachPickerItems = Array.isArray(data?.items) ? data.items : [];
      renderAttachPickerList();
    } catch (err) {
      els.attachFileList.innerHTML = `<div style="padding:8px;color:#fca5a5;font-size:12px">Could not list folder: ${err.message}</div>`;
    }
  }

  els.attachBtn.addEventListener('click', () => {
    void openWorkspaceAttachModal(null);
  });
  els.attachUpBtn?.addEventListener('click', () => {
    if (!attachPickerFolder) return;
    const parent = attachPickerFolder.includes('/') ? attachPickerFolder.split('/').slice(0, -1).join('/') : '';
    void openWorkspaceAttachModal(parent);
  });
  els.attachOsBtn?.addEventListener('click', () => {
    els.attachModal.hidden = true;
    els.fileInput.value = '';
    els.fileInput.click();
  });
  els.attachSearch?.addEventListener('input', renderAttachPickerList);
  els.fileInput.addEventListener('change', () => {
    if (els.fileInput.files && els.fileInput.files.length) {
      void uploadClientFiles(els.fileInput.files, 'picker');
    }
  });

  // 1. Clipboard Paste (Ctrl+V) for screenshots, images, and copied files
  drawer.addEventListener('paste', event => {
    const cd = event.clipboardData;
    if (!cd) return;
    const pastedFiles = [];
    if (cd.items && cd.items.length) {
      for (const item of cd.items) {
        if (item.kind === 'file') {
          const f = item.getAsFile();
          if (f) pastedFiles.push(f);
        }
      }
    }
    if (!pastedFiles.length && cd.files && cd.files.length) {
      pastedFiles.push(...cd.files);
    }
    if (pastedFiles.length) {
      event.preventDefault();
      void uploadClientFiles(pastedFiles, 'paste');
    }
  });

  // 2. Make Lantern File Manager cards (.card[data-rel]) draggable into Chatbot
  document.addEventListener('dragstart', event => {
    const card = event.target?.closest?.('.card[data-rel]');
    if (!card || !event.dataTransfer) return;
    const rel = String(card.getAttribute('data-rel') || '').trim().replace(/^\/+/, '');
    if (!rel) return;
    const selected = typeof window.selectedArray === 'function' ? (window.selectedArray() || []) : [];
    const relList = selected.includes(rel) && selected.length > 1 ? selected : [rel];
    const items = relList.map(r => {
      const c = document.querySelector(`.card[data-rel="${CSS.escape(r)}"]`);
      const isDir = c?.getAttribute('data-isdir') === '1';
      const isImage = !isDir && (c?.getAttribute('data-type') === 'image' || inferIsImage(r));
      return {
        path: r,
        name: r.split('/').pop() || r,
        isDir,
        isImage,
        previewUrl: inferPreviewUrl(r, isImage),
        source: 'drag-card',
      };
    });
    try {
      event.dataTransfer.setData('application/x-lantern-paths', JSON.stringify(items));
      event.dataTransfer.setData('text/plain', relList.join('\n'));
      event.dataTransfer.effectAllowed = 'copyMove';
    } catch {}
  });

  function hasDragPayload(dt) {
    if (!dt) return false;
    const types = Array.from(dt.types || []);
    return types.includes('Files') || types.includes('application/x-lantern-paths');
  }

  async function handleDroppedDataTransfer(dt) {
    if (!dt) return;
    const rawLantern = dt.getData('application/x-lantern-paths');
    if (rawLantern) {
      try {
        const items = JSON.parse(rawLantern);
        if (Array.isArray(items) && items.length) {
          upsertAttachments(items);
          setStatus(`Attached ${items.length} item(s) from Lantern to context.`, 'info');
          return;
        }
      } catch {}
    }
    if (dt.files && dt.files.length) {
      await uploadClientFiles(dt.files, 'drop');
    }
  }

  // Drag & Drop over Chatbot Drawer
  let dragDepth = 0;
  drawer.addEventListener('dragenter', event => {
    if (!hasDragPayload(event.dataTransfer)) return;
    event.preventDefault();
    dragDepth += 1;
    els.dropOverlay.hidden = false;
  });
  drawer.addEventListener('dragover', event => {
    if (!hasDragPayload(event.dataTransfer)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
    els.dropOverlay.hidden = false;
  });
  drawer.addEventListener('dragleave', event => {
    if (!hasDragPayload(event.dataTransfer)) return;
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) {
      els.dropOverlay.hidden = true;
    }
  });
  drawer.addEventListener('drop', event => {
    if (!hasDragPayload(event.dataTransfer)) return;
    event.preventDefault();
    event.stopPropagation();
    dragDepth = 0;
    els.dropOverlay.hidden = true;
    void handleDroppedDataTransfer(event.dataTransfer);
  });

  // Drag & Drop over Floating Lantern Launcher (auto-opens drawer or attaches directly)
  let fabHoverTimer = 0;
  fab.addEventListener('dragenter', event => {
    if (!hasDragPayload(event.dataTransfer)) return;
    event.preventDefault();
    fab.classList.add('drag-over');
    clearTimeout(fabHoverTimer);
    fabHoverTimer = setTimeout(() => {
      prefs.open = true;
      applyLayout();
      renderContextBar();
    }, 380);
  });
  fab.addEventListener('dragover', event => {
    if (!hasDragPayload(event.dataTransfer)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
  });
  fab.addEventListener('dragleave', () => {
    clearTimeout(fabHoverTimer);
    fab.classList.remove('drag-over');
  });
  fab.addEventListener('drop', event => {
    clearTimeout(fabHoverTimer);
    fab.classList.remove('drag-over');
    if (!hasDragPayload(event.dataTransfer)) return;
    event.preventDefault();
    event.stopPropagation();
    prefs.open = true;
    applyLayout();
    void handleDroppedDataTransfer(event.dataTransfer);
  });

  function jumpToMarkdownLine(lineNo) {
    if (!lineNo || !Number.isFinite(Number(lineNo))) return;
    const targetLine = Math.max(1, Number(lineNo));
    const mode = window.__lanternMdVisual?.state?.mode || 'preview';
    if (window.LanternAnchorBridge?.restore) {
      void window.LanternAnchorBridge.restore(mode, { line: targetLine, column: 0 }, document.querySelector('article.md-preview'));
      return;
    }
    const blk = document.querySelector(`article.md-preview [data-l="${targetLine}"]`);
    if (blk) blk.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  // --- Render Live Context Bar with Unified Bidirectional Chips & Image Thumbnails ---
  function renderContextBar() {
    els.contextBar.textContent = '';
    if (!prefs.autoContext) {
      const muted = document.createElement('span');
      muted.style.color = 'var(--lc-dim)';
      muted.style.fontSize = '11px';
      muted.textContent = 'Context is OFF — sending pure prompt only.';
      els.contextBar.append(muted);
      return;
    }
    const ctx = captureContext();
    const addChip = (label, onRemove = null, title = '', opts = {}) => {
      const chip = document.createElement('span');
      chip.className = 'lc-chip' + (opts.className ? ` ${opts.className}` : '') + (opts.onClick ? ' is-interactive' : '');
      if (title) chip.title = title;
      if (opts.thumbUrl) {
        const img = document.createElement('img');
        img.className = 'lc-chip-thumb';
        img.src = opts.thumbUrl;
        img.alt = label;
        img.loading = 'lazy';
        chip.append(img);
      }
      const text = document.createElement('span');
      text.textContent = label;
      chip.append(text);
      if (opts.onClick) {
        chip.addEventListener('click', ev => {
          if (ev.target.tagName === 'BUTTON') return;
          opts.onClick();
        });
      }
      if (onRemove) {
        const rm = document.createElement('button');
        rm.type = 'button';
        rm.textContent = '×';
        rm.title = 'Remove from this turn';
        rm.addEventListener('click', ev => {
          ev.stopPropagation();
          onRemove();
          renderContextBar();
        });
        chip.append(rm);
      }
      els.contextBar.append(chip);
    };

    if (ctx.kind === 'markdown' && ctx.path) {
      addChip(`📄 ${ctx.path.split('/').pop()}`, null, `Click to jump to active line in ${ctx.path}`, {
        onClick: () => jumpToMarkdownLine(ctx.line || 1),
      });
      const modeName = ctx.markdownMode === 'visual' ? 'Edit visually' : (ctx.markdownMode === 'source' ? 'Source' : 'Preview');
      addChip(`✏️ ${modeName}${ctx.line ? ` · L${ctx.line}` : ''}`, null, 'Click to scroll to this line in the document', {
        onClick: () => jumpToMarkdownLine(ctx.line || 1),
      });
      const mdDirty = Boolean(window.__lanternMdVisual?.state?.dirty);
      if (mdDirty && !state.skipDraftFlush) {
        addChip(
          '● Unsaved draft',
          () => { state.skipDraftFlush = true; },
          'Click × to skip syncing unsaved draft and let Lanbot read the saved disk file only',
          { className: 'is-draft' }
        );
      } else if (mdDirty && state.skipDraftFlush) {
        addChip(
          '○ Saved file only (skip draft)',
          () => { state.skipDraftFlush = false; },
          'Click to re-enable live draft sync before sending'
        );
      }
    } else if (ctx.kind === 'file' && ctx.path) {
      addChip(`📄 ${ctx.path.split('/').pop()}`, null, ctx.path);
      if (ctx.folder) addChip(`📁 ${ctx.folder}`);
    } else if (ctx.folder) {
      addChip(`📁 ${ctx.folder}`);
    } else {
      addChip('📁 / (root)');
    }
    addChip('＋ Attach file', null, `Pick sibling files in /${ctx.folder || ''} to attach`, {
      onClick: () => { void openWorkspaceAttachModal(null); },
    });

    if (ctx.selectedText) {
      addChip(
        `✂️ "${ctx.selectedText.slice(0, 22)}…" (${ctx.selectedText.length}c)`,
        () => {
          state.dismissedSelection = true;
          state.cachedSelection = '';
          try { window.getSelection?.()?.removeAllRanges?.(); } catch {}
        },
        ctx.selectedText,
        {
          onClick: () => jumpToMarkdownLine(ctx.line || state.cachedSelectionLine || 1),
        }
      );
    }

    if (state.uploadingCount > 0) {
      addChip(`⏳ Uploading ${state.uploadingCount} file(s)…`);
    }

    if (Array.isArray(ctx.attachments) && ctx.attachments.length) {
      ctx.attachments.forEach(att => {
        const isImg = Boolean(att.isImage || inferIsImage(att.path));
        const icon = att.isDir ? '📁 ' : (isImg ? '🖼️ ' : '📎 ');
        const displayName = att.name || att.path.split('/').pop() || att.path;
        addChip(
          `${isImg ? '' : icon}${displayName}`,
          () => {
            state.dismissedPaths.add(att.path);
            const next = loadAttachments().filter(item => item.path !== att.path);
            saveAttachments(next);
            const card = document.querySelector(`.card[data-rel="${CSS.escape(att.path)}"]`);
            const cb = card?.querySelector('input[type="checkbox"]');
            if (cb && cb.checked) cb.click();
          },
          att.path,
          {
            className: isImg ? 'is-image' : '',
            thumbUrl: isImg ? (att.previewUrl || inferPreviewUrl(att.path, true)) : '',
          }
        );
      });
      if (ctx.attachments.length > 1) {
        addChip('🗑 Clear all', () => {
          ctx.attachments.forEach(a => state.dismissedPaths.add(a.path));
          saveAttachments([]);
        }, 'Remove all attached files/images');
      }
    }
  }

  document.addEventListener('selectionchange', () => {
    if (isSelectionInsideChatDrawer()) return;
    try {
      const sel = String(window.getSelection?.()?.toString() || '').trim();
      if (sel && sel.length >= 2) {
        state.cachedSelection = sel;
        state.dismissedSelection = false;
      }
    } catch {}
    if (prefs.open) renderContextBar();
  });

  document.addEventListener('click', e => {
    if (e.target.closest?.('.card')) {
      setTimeout(() => { if (prefs.open) renderContextBar(); }, 60);
    }
  });

  // --- Subagent Card Renderer ---
  function createSubagentGrid(subagents) {
    const grid = document.createElement('div');
    grid.className = 'lc-subagent-grid';
    subagents.forEach(sub => {
      const card = document.createElement('div');
      card.className = 'lc-subagent-card';
      const top = document.createElement('div');
      top.className = 'lc-subagent-top';
      const title = document.createElement('div');
      title.className = 'lc-subagent-title';
      title.textContent = `🤖 ${sub.summary || sub.taskId || 'Subagent Task'}`;
      const badge = document.createElement('span');
      badge.className = 'lc-subagent-badge';
      badge.textContent = sub.status || 'Done';
      top.append(title, badge);
      card.append(top);

      if (sub.result) {
        const res = document.createElement('div');
        res.className = 'lc-subagent-result';
        res.textContent = sub.result;
        card.append(res);
      }

      const foot = document.createElement('div');
      foot.className = 'lc-subagent-foot';
      const stats = document.createElement('span');
      const dur = sub.durationMs ? `${(sub.durationMs / 1000).toFixed(2)}s` : '';
      const tok = sub.totalTokens ? `${sub.totalTokens.toLocaleString()} tok` : '';
      stats.textContent = [ `ID: ${(sub.taskId || '').slice(0, 12)}`, tok, dur ].filter(Boolean).join(' · ');
      foot.append(stats);

      if (sub.outputFile) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'lc-diff-btn';
        btn.textContent = '📄 Full Transcript';
        btn.addEventListener('click', async () => {
          els.transcriptModalTitle.textContent = `Transcript · ${sub.taskId || 'Subagent'}`;
          els.transcriptModalBody.textContent = 'Loading transcript…';
          els.transcriptModal.hidden = false;
          try {
            const resp = await fetch(`/api/chatbot/subagent-transcript?path=${encodeURIComponent(sub.outputFile)}`, { credentials: 'same-origin' });
            const data = await resp.json();
            els.transcriptModalBody.textContent = data.content || data.error || 'Empty transcript.';
          } catch (err) {
            els.transcriptModalBody.textContent = 'Failed to load transcript: ' + err.message;
          }
        });
        foot.append(btn);
      }
      card.append(foot);
      grid.append(card);
    });
    return grid;
  }

  // --- Pure-Logic Clickable Line Citation Pills for Modified Markdown Hunks (#18, #19) ---
  async function appendMarkdownDiffCardIfChanged(container, mdPath) {
    if (!mdPath || !container) return;
    try {
      const resp = await fetch(`/api/work?p=${encodeURIComponent(mdPath)}`, { cache: 'no-store', credentials: 'same-origin' });
      const data = await resp.json();
      if (!data?.hasDiff || !data?.saved || !data?.work) return;
      const diffEngine = window.LanternMarkdownDiff;
      const hunks = diffEngine?.diffLines ? diffEngine.diffLines(data.saved.content || '', data.work.content || '') : [];
      if (!hunks.length) return;

      const lastAssistantCard = [...container.querySelectorAll('.lc-msg.assistant')].pop() || container;
      let bar = lastAssistantCard.querySelector('.lc-citation-bar');
      if (bar) bar.remove();
      bar = document.createElement('div');
      bar.className = 'lc-citation-bar';

      const label = document.createElement('span');
      label.className = 'lc-citation-label';
      label.textContent = '📍 Modified lines (click to jump):';
      bar.append(label);

      const shortFile = mdPath.split('/').pop() || mdPath;
      hunks.slice(0, 10).forEach((h, idx) => {
        const startLine = Math.max(1, (h.draftStart || 0) + 1);
        const endLine = Math.max(startLine, h.draftEnd || startLine);
        const rangeStr = endLine > startLine ? `L${startLine}–L${endLine}` : `L${startLine}`;
        const pill = document.createElement('button');
        pill.type = 'button';
        pill.className = 'lc-citation-pill';
        pill.textContent = `📍 ${shortFile}:${rangeStr} (${String(h.kind || 'mod').toUpperCase()})`;
        pill.title = `Jump directly to hunk #${idx + 1} at line ${startLine}`;
        pill.addEventListener('click', () => {
          if (window.__lanternMdVisual?.jumpToDiffHunk) {
            window.__lanternMdVisual.jumpToDiffHunk(idx);
          } else {
            jumpToMarkdownLine(startLine);
          }
        });
        bar.append(pill);
      });

      lastAssistantCard.append(bar);
    } catch {}
  }

  // --- Copy to Clipboard Helper (Works on both HTTPS/localhost and HTTP LAN) ---
  async function copyTextToClipboard(text) {
    const val = String(text ?? '');
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(val);
        return true;
      }
    } catch {}
    try {
      const ta = document.createElement('textarea');
      ta.value = val;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
      return true;
    } catch {
      return false;
    }
  }

  // --- Rich Markdown Renderer for Chat Responses (GFM Tables, Code Blocks, Lists, Headings, Inline) ---
  function formatChatInlineHtml(raw) {
    const esc = s => String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
    const codeSlots = [];
    let text = String(raw ?? '').replace(/`([^`\n]+)`/g, (_, code) => {
      const idx = codeSlots.length;
      codeSlots.push(`<code>${esc(code)}</code>`);
      return `\u0000CODE${idx}\u0000`;
    });
    text = text.replace(/&lt;br\s*\/?&gt;|<br\s*\/?>/gi, '\u0000BR\u0000');
    text = esc(text);
    text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+|\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/~~([^~]+)~~/g, '<del>$1</del>');
    text = text.replace(/(^|[\s(])\*([^\s*][^*]*?)\*(?=[\s).,!?:;]|$)/g, '$1<em>$2</em>');
    text = text.replace(/\u0000BR\u0000/g, '<br>');
    text = text.replace(/\u0000CODE(\d+)\u0000/g, (_, idx) => codeSlots[Number(idx)] || '');
    return text;
  }

  function splitChatTablePipeRow(line) {
    const t = String(line ?? '').trim();
    if (!t.startsWith('|') && (t.match(/\|/g) || []).length < 2) return null;
    const inner = t.replace(/^\|/, '').replace(/\|$/, '');
    const cells = [];
    let cur = '';
    for (let i = 0; i < inner.length; i++) {
      if (inner[i] === '\\' && inner[i + 1] === '|') {
        cur += '|';
        i++;
      } else if (inner[i] === '|') {
        cells.push(cur.trim());
        cur = '';
      } else {
        cur += inner[i];
      }
    }
    cells.push(cur.trim());
    return cells;
  }

  function isChatTableSeparator(cells) {
    return Array.isArray(cells) && cells.length > 0 && cells.every(c => /^:?-{2,}:?$/.test(c));
  }

  function renderChatMarkdownHtml(mdText) {
    const esc = s => String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
    const lines = String(mdText ?? '').replace(/\r\n?/g, '\n').split('\n');
    const out = [];
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      const fenceMatch = line.match(/^\s*(`{3,}|~{3,})\s*([^\s`~]*)/);
      if (fenceMatch) {
        const fence = fenceMatch[1];
        const lang = fenceMatch[2] || 'text';
        const codeLines = [];
        i++;
        while (i < lines.length && !lines[i].trim().startsWith(fence)) {
          codeLines.push(lines[i]);
          i++;
        }
        if (i < lines.length) i++;
        const rawCode = codeLines.join('\n');
        const encodedCode = encodeURIComponent(rawCode);
        out.push(
          `<div class="lc-md-codewrap">` +
            `<div class="lc-md-codehead">` +
              `<span class="lc-md-codelang">${esc(lang)}</span>` +
              `<button type="button" class="lc-md-codecopy" data-copy-code="${encodedCode}">📋 Copy code</button>` +
            `</div>` +
            `<pre><code>${esc(rawCode)}</code></pre>` +
          `</div>`
        );
        continue;
      }

      if (!line.trim()) {
        i++;
        continue;
      }

      // Horizontal Rule (deduplicate consecutive --- lines so tool/thought separators never stack)
      if (/^\s*(?:---+|_{3,}|\*\*\*+)\s*$/.test(line)) {
        if (out.length > 0 && out[out.length - 1] !== '<hr class="lc-md-hr">') {
          out.push('<hr class="lc-md-hr">');
        }
        i++;
        continue;
      }

      // Heading
      const hm = line.match(/^\s*(#{1,6})\s+(.+)$/);
      if (hm) {
        const lvl = hm[1].length;
        out.push(`<h${lvl} class="lc-md-h lc-md-h${lvl}">${formatChatInlineHtml(hm[2])}</h${lvl}>`);
        i++;
        continue;
      }

      // GFM Pipe Table
      const firstCells = splitChatTablePipeRow(line);
      if (firstCells && i + 1 < lines.length && isChatTableSeparator(splitChatTablePipeRow(lines[i + 1]))) {
        const headerCells = firstCells;
        i += 2;
        const bodyRows = [];
        while (i < lines.length && lines[i].trim()) {
          const rCells = splitChatTablePipeRow(lines[i]);
          if (!rCells) break;
          if (!isChatTableSeparator(rCells)) bodyRows.push(rCells);
          i++;
        }
        let tbl = '<div class="lc-md-table-scroll"><table class="lc-md-table"><thead><tr>';
        headerCells.forEach(c => { tbl += `<th>${formatChatInlineHtml(c)}</th>`; });
        tbl += '</tr></thead><tbody>';
        bodyRows.forEach(r => {
          tbl += '<tr>';
          for (let cIdx = 0; cIdx < headerCells.length; cIdx++) {
            tbl += `<td>${formatChatInlineHtml(r[cIdx] ?? '')}</td>`;
          }
          tbl += '</tr>';
        });
        tbl += '</tbody></table></div>';
        out.push(tbl);
        continue;
      }

      // Blockquote
      if (/^\s*>\s?/.test(line)) {
        const qLines = [];
        while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
          qLines.push(lines[i].replace(/^\s*>\s?/, ''));
          i++;
        }
        out.push(`<blockquote class="lc-md-quote">${qLines.map(formatChatInlineHtml).join('<br>')}</blockquote>`);
        continue;
      }

      // Unordered or Ordered List
      if (/^\s*(?:[-*+]|\d+\.)\s+/.test(line)) {
        const isOrdered = /^\s*\d+\.\s+/.test(line);
        const tag = isOrdered ? 'ol' : 'ul';
        const items = [];
        while (i < lines.length && /^\s*(?:[-*+]|\d+\.)\s+/.test(lines[i])) {
          const itemMatch = lines[i].match(/^(\s*)(?:[-*+]|\d+\.)\s+(.*)$/);
          if (itemMatch) {
            const indentLvl = Math.min(3, Math.floor((itemMatch[1] || '').length / 2));
            items.push(`<li style="margin-left:${indentLvl * 14}px">${formatChatInlineHtml(itemMatch[2])}</li>`);
          }
          i++;
        }
        out.push(`<${tag} class="lc-md-list">${items.join('')}</${tag}>`);
        continue;
      }

      // Paragraph
      const pLines = [];
      while (
        i < lines.length &&
        lines[i].trim() &&
        !/^\s*(?:`{3,}|~{3,})/.test(lines[i]) &&
        !/^\s*#{1,6}\s+/.test(lines[i]) &&
        !/^\s*(?:---+|_{3,}|\*\*\*+)\s*$/.test(lines[i]) &&
        !/^\s*>\s?/.test(lines[i]) &&
        !/^\s*(?:[-*+]|\d+\.)\s+/.test(lines[i]) &&
        !(splitChatTablePipeRow(lines[i]) && i + 1 < lines.length && isChatTableSeparator(splitChatTablePipeRow(lines[i + 1])))
      ) {
        pLines.push(formatChatInlineHtml(lines[i]));
        i++;
      }
      out.push(`<p class="lc-md-p">${pLines.join('<br>')}</p>`);
    }
    return out.join('');
  }

  // Close any open per-message '...' dropdown when clicking outside
  document.addEventListener('click', ev => {
    drawer.querySelectorAll('.lc-msg-more-wrap.open').forEach(wrap => {
      if (!wrap.contains(ev.target)) {
        wrap.classList.remove('open');
        const dd = wrap.querySelector('.lc-msg-dropdown');
        if (dd) dd.hidden = true;
      }
    });
  });

  async function rerunAssistantTurn(turnIdx) {
    if (state.busy) {
      setStatus('Lanbot is currently busy. Stop the current turn before re-running.', 'warn');
      return;
    }
    const rawMsgs = Array.isArray(state.messages) ? state.messages : [];
    let userIdx = -1;
    let promptText = '';
    for (let i = Math.min(turnIdx, rawMsgs.length - 1); i >= 0; i--) {
      const norm = normalizeRawMessage(rawMsgs[i]);
      if (norm.role === 'user' && norm.text) {
        userIdx = typeof rawMsgs[i]._msgIndex === 'number' ? rawMsgs[i]._msgIndex : i;
        promptText = norm.text;
        break;
      }
    }
    if (!promptText) {
      setStatus('Could not find the user prompt for this response to re-run.', 'warn');
      return;
    }
    state.sendingImmediate = true;
    syncSendButtonState();
    resetStreamTurn();

    let ctxPayload = {};
    let workHash = null;
    if (prefs.autoContext) {
      const captured = captureContext();
      const prep = await prepareMarkdownTurn(captured);
      if (prep.workHash) workHash = prep.workHash;
      ctxPayload = {
        kind: captured.kind,
        path: captured.path,
        folder: captured.folder,
        markdownMode: captured.markdownMode,
        line: captured.line,
        selectedText: captured.selectedText,
        attachments: captured.attachmentPaths,
      };
    }

    // Trim local messages up to and including the user prompt being re-run
    const localCutIdx = rawMsgs.findIndex((m, idx) => (typeof m._msgIndex === 'number' ? m._msgIndex === userIdx : idx === userIdx));
    if (localCutIdx >= 0) {
      state.messages = rawMsgs.slice(0, localCutIdx + 1);
    }
    isUserScrolledUp = false;
    renderTranscript({ force: true, scrollToBottom: true });
    setStreaming(true);
    setActivityTicker('↻ Re-running prompt in Lanbot…', true);
    setStatus('Re-running prompt…', 'info');
    sendWs({
      type: 'chat_rerun',
      reqId: 'rerun-' + Date.now().toString(36),
      turnIndex: userIdx,
      message: promptText,
      context: ctxPayload,
      workHash,
    });
  }

  function populateMessageBodyAndActions(card, head, bodyEl, rawMarkdownText, msgMeta = {}) {
    const textVal = String(rawMarkdownText ?? '');
    if (bodyEl) {
      bodyEl.dataset.rawMd = textVal;
      const isRaw = card.dataset.viewMode === 'raw';
      if (isRaw) {
        bodyEl.classList.add('is-raw');
        bodyEl.textContent = textVal;
      } else {
        bodyEl.classList.remove('is-raw');
        bodyEl.innerHTML = renderChatMarkdownHtml(textVal);
      }
    }

    const role = msgMeta.role || (card.classList.contains('user') ? 'user' : 'assistant');
    const turnIdx = typeof msgMeta.turnIndex === 'number' ? msgMeta.turnIndex : -1;

    let actions = head.querySelector('.lc-msg-actions');
    if (!actions) {
      actions = document.createElement('div');
      actions.className = 'lc-msg-actions';

      const moreWrap = document.createElement('div');
      moreWrap.className = 'lc-msg-more-wrap';

      const moreBtn = document.createElement('button');
      moreBtn.type = 'button';
      moreBtn.className = 'lc-msg-more-btn';
      moreBtn.textContent = '⋯';
      moreBtn.title = 'Message actions (Raw, Copy, Fork, Re-run)';

      const dropdown = document.createElement('div');
      dropdown.className = 'lc-msg-dropdown';
      dropdown.hidden = true;

      const closeDropdown = () => {
        moreWrap.classList.remove('open');
        dropdown.hidden = true;
      };

      moreBtn.addEventListener('click', ev => {
        ev.stopPropagation();
        const isOpen = !dropdown.hidden;
        drawer.querySelectorAll('.lc-msg-more-wrap.open').forEach(w => {
          w.classList.remove('open');
          const d = w.querySelector('.lc-msg-dropdown');
          if (d) d.hidden = true;
        });
        if (!isOpen) {
          moreWrap.classList.add('open');
          dropdown.hidden = false;
        }
      });

      const isRawInit = card.dataset.viewMode === 'raw';
      const toggleBtn = document.createElement('button');
      toggleBtn.type = 'button';
      toggleBtn.className = 'lc-msg-dropdown-item lc-msg-toggle-btn';
      toggleBtn.textContent = isRawInit ? '👁 Preview' : '📝 Raw';
      toggleBtn.title = 'Toggle between rendered Markdown Preview and Raw .md source';
      toggleBtn.addEventListener('click', ev => {
        ev.stopPropagation();
        closeDropdown();
        if (!bodyEl) return;
        const nextRaw = card.dataset.viewMode !== 'raw';
        card.dataset.viewMode = nextRaw ? 'raw' : 'preview';
        toggleBtn.textContent = nextRaw ? '👁 Preview' : '📝 Raw';
        const latestText = bodyEl.dataset.rawMd || '';
        if (nextRaw) {
          bodyEl.classList.add('is-raw');
          bodyEl.textContent = latestText;
        } else {
          bodyEl.classList.remove('is-raw');
          bodyEl.innerHTML = renderChatMarkdownHtml(latestText);
        }
      });

      const copyBtn = document.createElement('button');
      copyBtn.type = 'button';
      copyBtn.className = 'lc-msg-dropdown-item lc-msg-copy-btn';
      copyBtn.textContent = '📋 Copy';
      copyBtn.title = 'Copy message Markdown to clipboard';
      copyBtn.addEventListener('click', async ev => {
        ev.stopPropagation();
        const latestText = bodyEl ? (bodyEl.dataset.rawMd || '') : textVal;
        const ok = await copyTextToClipboard(latestText);
        copyBtn.textContent = ok ? '✓ Copied!' : '⚠️ Failed';
        setTimeout(() => {
          copyBtn.textContent = '📋 Copy';
          closeDropdown();
        }, 700);
      });

      const forkItemBtn = document.createElement('button');
      forkItemBtn.type = 'button';
      forkItemBtn.className = 'lc-msg-dropdown-item lc-msg-fork-btn';
      forkItemBtn.textContent = '⑂ Fork';
      forkItemBtn.title = 'Fork conversation directly from this message into a new branch';
      forkItemBtn.addEventListener('click', ev => {
        ev.stopPropagation();
        closeDropdown();
        const upto = turnIdx >= 0 ? turnIdx : undefined;
        setStatus(`Forking conversation from message #${(turnIdx >= 0 ? turnIdx : 0) + 1}…`, 'info');
        sendWs({
          type: 'chat_fork',
          uptoIndex: upto,
        });
      });

      dropdown.append(toggleBtn, copyBtn, forkItemBtn);

      // v7.7: Re-run button ONLY on ASSISTANT messages (USER messages do not need Re-run)
      if (role === 'assistant') {
        const rerunBtn = document.createElement('button');
        rerunBtn.type = 'button';
        rerunBtn.className = 'lc-msg-dropdown-item lc-msg-rerun-btn';
        rerunBtn.textContent = '↻ Re-run';
        rerunBtn.title = 'Re-run the prompt that generated this assistant response';
        rerunBtn.addEventListener('click', ev => {
          ev.stopPropagation();
          closeDropdown();
          void rerunAssistantTurn(turnIdx >= 0 ? turnIdx : (state.messages.length - 1));
        });
        dropdown.append(rerunBtn);
      }

      moreWrap.append(moreBtn, dropdown);
      actions.append(moreWrap);
      head.append(actions);
    }
  }

  // --- Render Transcript Messages ---
  function renderTranscript(options = {}) {
    const rawCheck = (Array.isArray(state.messages) ? state.messages : []).map(normalizeRawMessage);
    const mdPathCheck = document.body?.dataset?.lanternChatPath || '';
    const fp = JSON.stringify(rawCheck.map(m => [
      m.role,
      m.text,
      m.thinking,
      (m.toolCalls || []).map(t => [t.name, t.result !== undefined ? 1 : 0, t.isError ? 1 : 0, t.truncated ? 1 : 0]),
    ])) + '|' + mdPathCheck + '|' + state.greeting + '|' + Boolean(state.hasMoreOlder) + '|' + Number(state.oldestLoadedIndex || 0);
    if (!options.force && els.transcript.childElementCount > 0 && fp === lastTranscriptFingerprint && !state.streaming) {
      return;
    }
    lastTranscriptFingerprint = fp;
    const prevScrollTop = els.transcript.scrollTop;
    const hadChildren = els.transcript.childElementCount > 0;
    els.transcript.textContent = '';
    streamingNode = null;
    streamingThinkingNode = null;
    streamingToolDetails = null;
    activeToolRows.clear();

    const rawNormalized = (Array.isArray(state.messages) ? state.messages : [])
      .map((m, idx) => {
        const norm = normalizeRawMessage(m);
        norm._rawIdx = typeof m?._msgIndex === 'number' ? m._msgIndex : idx;
        return norm;
      });
    const normalizedList = [];
    rawNormalized.forEach(m => {
      if (m.role === 'system' && !m.text) return;
      if (m.role === 'toolResult' || m.role === 'tool') {
        const prev = normalizedList[normalizedList.length - 1];
        if (prev && prev.role === 'assistant') {
          if (m.toolCalls && m.toolCalls.length) {
            prev.toolCalls = [...(prev.toolCalls || []), ...m.toolCalls];
          } else if (m.text) {
            prev.toolCalls = [...(prev.toolCalls || []), {
              id: '',
              name: 'result',
              result: m.text,
              truncated: Boolean(m.truncated),
              fullLength: Number(m.fullLength || 0),
              msgIndex: m._rawIdx,
              toolIndex: 0,
            }];
          }
          prev._turnIdx = m._rawIdx;
        }
        return;
      }
      if (m.role !== 'user') {
        const hasBody = Boolean(m.text || m.thinking || (m.toolCalls && m.toolCalls.length) || (m.subagents && m.subagents.length));
        if (!hasBody) return;
        const prev = normalizedList[normalizedList.length - 1];
        if (prev && prev.role === 'assistant') {
          prev.toolCalls = [...(prev.toolCalls || []), ...(m.toolCalls || [])];
          prev.subagents = [...(prev.subagents || []), ...(m.subagents || [])];
          if (m.thinking && m.thinking !== prev.thinking) {
            prev.thinking = prev.thinking ? `${prev.thinking}\n${m.thinking}` : m.thinking;
          }
          if (m.text && m.text !== prev.text) {
            prev.text = prev.text ? `${prev.text}\n\n${m.text}` : m.text;
          }
          prev._turnIdx = m._rawIdx;
          return;
        }
        m.role = 'assistant';
      }
      normalizedList.push({ ...m, _turnIdx: m._rawIdx });
    });

    if (!normalizedList.length) {
      const welcome = document.createElement('div');
      welcome.className = 'lc-msg system';
      welcome.textContent = state.greeting || 'Ask Lanbot about your files or Markdown document.';
      els.transcript.append(welcome);
      return;
    }

    // v7.7 + v7.91: Lazy-load older messages on scroll-up or button click
    if (state.hasMoreOlder && state.oldestLoadedIndex > 0) {
      const loadOlderBtn = document.createElement('button');
      loadOlderBtn.type = 'button';
      loadOlderBtn.className = 'lc-load-older-btn';
      const remainingCount = state.oldestLoadedIndex;
      loadOlderBtn.disabled = Boolean(state.loadingOlderHistory);
      loadOlderBtn.textContent = state.loadingOlderHistory
        ? '⏳ Đang tải tin nhắn cũ hơn…'
        : `⬆️ Tải thêm (${remainingCount} tin nhắn cũ hơn)`;
      loadOlderBtn.addEventListener('click', () => {
        triggerLazyLoadOlderHistory();
      });
      els.transcript.append(loadOlderBtn);
    }

    normalizedList.forEach((msg, listIdx) => {
      const turnIdx = typeof msg._turnIdx === 'number' ? msg._turnIdx : listIdx;
      const card = document.createElement('article');
      card.className = `lc-msg ${msg.role === 'user' ? 'user' : 'assistant'}`;
      card.dataset.turnIndex = String(turnIdx);
      const head = document.createElement('div');
      head.className = 'lc-msg-head';
      card.append(head);

      if (msg.thinking) {
        const think = document.createElement('details');
        think.className = 'lc-thinking-card';
        const sum = document.createElement('summary');
        sum.textContent = '💭 Thinking process';
        const pre = document.createElement('pre');
        pre.textContent = safeText(msg.thinking);
        think.append(sum, pre);
        card.append(think);
      }

      if (Array.isArray(msg.toolCalls) && msg.toolCalls.length) {
        const toolDetails = document.createElement('details');
        toolDetails.className = 'lc-tool-card';
        const sum = document.createElement('summary');
        sum.textContent = `⚡ ${msg.toolCalls.length} tool call(s): ${msg.toolCalls.map(t => t.name).join(', ')}`;
        const pre = document.createElement('pre');
        pre.textContent = msg.toolCalls.map(t => {
          if (t.result !== undefined) {
            const limit = t.truncated ? 1400 : 1200;
            return `[${t.name}] -> ${safeText(t.result).slice(0, limit)}`;
          }
          return `${t.name}(${safeText(t.arguments)})`;
        }).join('\n\n');
        toolDetails.append(sum, pre);

        // v7.7: On-demand full tool output button for large truncated tool results
        msg.toolCalls.forEach((t, tIdx) => {
          if (t && t.truncated) {
            const fullBtn = document.createElement('button');
            fullBtn.type = 'button';
            fullBtn.className = 'lc-tool-load-full-btn';
            const kb = t.fullLength ? `${(t.fullLength / 1024).toFixed(1)} KB` : 'full';
            fullBtn.textContent = `📥 Xem đầy đủ kết quả tool (${t.name || 'tool'} · ${kb})`;
            fullBtn.addEventListener('click', async ev => {
              ev.stopPropagation();
              fullBtn.disabled = true;
              fullBtn.textContent = '⏳ Đang tải kết quả đầy đủ…';
              const targetMsgIdx = typeof t.msgIndex === 'number' ? t.msgIndex : turnIdx;
              const targetToolIdx = typeof t.toolIndex === 'number' ? t.toolIndex : tIdx;
              try {
                const resp = await fetch(
                  `/api/chatbot/tool-output?msgIndex=${encodeURIComponent(targetMsgIdx)}&toolIndex=${encodeURIComponent(targetToolIdx)}&clientSessionId=${encodeURIComponent(state.clientSessionId || '')}`,
                  { credentials: 'same-origin' }
                );
                const data = await resp.json();
                if (data && data.ok && typeof data.content === 'string') {
                  t.result = data.content;
                  t.truncated = false;
                  pre.textContent = msg.toolCalls.map(tc => {
                    if (tc.result !== undefined) return `[${tc.name}] -> ${safeText(tc.result)}`;
                    return `${tc.name}(${safeText(tc.arguments)})`;
                  }).join('\n\n');
                  fullBtn.remove();
                } else {
                  throw new Error(data?.error || 'Failed to load tool output');
                }
              } catch (err) {
                fullBtn.disabled = false;
                fullBtn.textContent = `⚠️ Lỗi tải (${err.message || 'thử lại'})`;
              }
            });
            toolDetails.append(fullBtn);
          }
        });

        card.append(toolDetails);
      }

      const rawText = safeText(msg.text);
      const { cleanedText, subagents: parsedSub } = extractSubagentBlocks(rawText);
      const allSubagents = (Array.isArray(msg.subagents) && msg.subagents.length) ? msg.subagents : parsedSub;

      if (cleanedText) {
        const body = document.createElement('div');
        body.className = 'lc-msg-body';
        populateMessageBodyAndActions(card, head, body, cleanedText, { role: msg.role, turnIndex: turnIdx });
        card.append(body);
      } else {
        populateMessageBodyAndActions(card, head, null, '', { role: msg.role, turnIndex: turnIdx });
      }

      if (allSubagents.length) {
        card.append(createSubagentGrid(allSubagents));
      }

      if (msg.context && typeof msg.context === 'object') {
        const pills = document.createElement('div');
        pills.className = 'lc-ctx-pills';
        if (msg.context.path) {
          const p = document.createElement('span');
          p.className = 'lc-ctx-pill';
          p.textContent = `📄 ${msg.context.path}${msg.context.line ? `:${msg.context.line}` : ''}`;
          pills.append(p);
        }
        if (Array.isArray(msg.context.attachments)) {
          msg.context.attachments.forEach(a => {
            const p = document.createElement('span');
            p.className = 'lc-ctx-pill';
            const label = typeof a === 'string' ? a : (a.name || a.path || '');
            p.textContent = `${inferIsImage(label) ? '🖼️' : '📎'} ${label.split('/').pop() || label}`;
            pills.append(p);
          });
        }
        if (pills.childElementCount) card.append(pills);
      }

      els.transcript.append(card);
    });

    const mdPath = document.body?.dataset?.lanternChatPath || '';
    if (mdPath) {
      void appendMarkdownDiffCardIfChanged(els.transcript, mdPath);
    }

    programmaticScroll = true;
    if (options.preserveScroll && typeof options.scrollTop === 'number') {
      els.transcript.scrollTop = options.scrollTop;
    } else if (isUserScrolledUp && hadChildren && !options.scrollToBottom) {
      els.transcript.scrollTop = prevScrollTop;
    } else {
      els.transcript.scrollTop = els.transcript.scrollHeight;
    }
    requestAnimationFrame(() => { programmaticScroll = false; });
    saveTabCache();
  }

  // --- Update Header & Controls from Snapshot / chat_state ---
  function applySnapshot(snap) {
    if (!snap || typeof snap !== 'object') return;
    const prevSessionId = state.sessionId;
    if (snap.state && typeof snap.state === 'object') {
      state.sessionId = snap.state.sessionId || state.sessionId;
      state.sessionFile = snap.state.sessionFile || state.sessionFile;
      if (snap.state.model) state.model = snap.state.model;
    }
    if (snap.summary && typeof snap.summary === 'object') {
      state.busy = Boolean(snap.summary.streaming);
      state.streaming = Boolean(snap.summary.streaming);
      if (snap.summary.model) state.model = snap.summary.model;
      if (Array.isArray(snap.summary.favorites)) state.favoriteModels = snap.summary.favorites;
      if (snap.summary.thinkingLevel) state.thinkingLevel = snap.summary.thinkingLevel;
      if (snap.summary.policy) {
        state.policy = snap.summary.policy;
        if (snap.summary.policy.greeting) state.greeting = snap.summary.policy.greeting;
      }
    }
    if (Array.isArray(snap.models)) state.models = snap.models;
    if (Array.isArray(snap.messages)) {
      const sessionChanged = Boolean(snap.state?.sessionId && prevSessionId && snap.state.sessionId !== prevSessionId) || Boolean(snap.isSwitch);
      if (snap.isNew || sessionChanged || snap.messages.length === 0 || snap.messages.length >= (state.messages?.length || 0)) {
        state.messages = snap.messages;
      } else if (snap.messages.length === 0 || snap.messages.length >= (state.messages?.length || 0)) {
        state.messages = snap.messages;
      } else if (snap.messages.length > 0 && state.messages?.length > snap.messages.length) {
        const serverHasAssistant = snap.messages.some(m => normalizeRawMessage(m).role === 'assistant');
        const localHasAssistant = state.messages.some(m => normalizeRawMessage(m).role === 'assistant');
        if (serverHasAssistant || !localHasAssistant) {
          state.messages = snap.messages;
        }
      }
    }
    if (snap.isNew) {
      state.messages = [];
      state.hasMoreOlder = false;
      state.oldestLoadedIndex = 0;
      state.totalHistoryMessages = 0;
    }
    if (typeof snap.summary?.messageCount === 'number' && snap.summary.messageCount >= 0) {
      state.totalHistoryMessages = snap.summary.messageCount;
    }
    state.contextUsage = {
      messageCount: Math.max(Array.isArray(state.messages) ? state.messages.length : 0, Number(state.totalHistoryMessages || 0)),
      estimatedTokens: snap.isNew ? 0 : estimateSessionTokens(state.messages, snap.summary?.sessionTokens),
    };
    if (Array.isArray(snap.sessions)) state.sessions = snap.sessions;
    if (typeof snap.summary?.sessionName === 'string') state.sessionName = snap.summary.sessionName;
    if (snap.sessionName) state.sessionName = snap.sessionName;

    els.sessionTitle.textContent = state.sessionName || (state.sessionId ? `Session #${String(state.sessionId).slice(0, 6)}` : 'New chat');
    const curModel = state.model;
    if (curModel && (curModel.id || curModel.name)) {
      els.providerSpan.textContent = curModel.provider || 'auto';
      els.providerSpan.hidden = !curModel.provider;
      els.modelSpan.textContent = curModel.name || curModel.id || 'model';
    } else {
      els.providerSpan.textContent = 'auto';
      els.providerSpan.hidden = true;
      els.modelSpan.textContent = 'Default model';
    }

    updateTokenBadgeDisplay();

    setStreaming(state.busy);
    setStatus(state.busy ? 'Lanbot is working…' : 'Ready', 'info');

    els.thinkingSelect.textContent = '';
    (state.thinkingLevels || ['off', 'low', 'medium', 'high']).forEach(lvl => {
      const opt = new Option(lvl.toUpperCase(), lvl, lvl === state.thinkingLevel, lvl === state.thinkingLevel);
      els.thinkingSelect.add(opt);
    });

    if (els.yamlPolicySummary && state.policy) {
      const scopeName = state.policy.scope === 'lan' ? 'LAN' : 'Localhost';
      const toolsStr = Array.isArray(state.policy.tools) ? state.policy.tools.join(', ') : '*';
      const extStr = state.policy.extensions ? 'ON' : 'OFF';
      const mcpStr = state.policy.mcp ? 'ON' : 'OFF';
      els.yamlPolicySummary.textContent = `${scopeName} · Tools: [${toolsStr}] · Extensions: ${extStr} · MCP: ${mcpStr}`;
    }

    if (typeof snap.summary?.customSystemPrompt === 'string') {
      state.customSystemPrompt = snap.summary.customSystemPrompt;
      if (els.customPromptInput && document.activeElement !== els.customPromptInput) {
        els.customPromptInput.value = state.customSystemPrompt;
      }
    }
    if (typeof snap.summary?.useGlobalSkills === 'boolean') {
      state.useGlobalSkills = snap.summary.useGlobalSkills;
      if (els.useGlobalSkillsCheck) els.useGlobalSkillsCheck.checked = state.useGlobalSkills;
    }
    if (Array.isArray(snap.summary?.customSkillPaths)) {
      state.customSkillPaths = snap.summary.customSkillPaths;
      if (els.customSkillPathsInput && document.activeElement !== els.customSkillPathsInput) {
        els.customSkillPathsInput.value = state.customSkillPaths.join('\n');
      }
    }
    if (Array.isArray(snap.summary?.discoveredSkills)) {
      state.discoveredSkills = snap.summary.discoveredSkills;
      if (els.discoveredSkillsList) {
        els.discoveredSkillsList.textContent = '';
        state.discoveredSkills.forEach(sk => {
          const b = document.createElement('span');
          b.className = 'lc-ctx-pill';
          b.title = sk.description || sk.path || '';
          b.textContent = `🧩 ${sk.name} (${sk.source || 'skill'})`;
          els.discoveredSkillsList.append(b);
        });
      }
    }

    const hasMessagesUpdate = Array.isArray(snap.messages) || Boolean(snap.isNew) || Boolean(snap.isSwitch);
    if (hasMessagesUpdate || els.transcript.childElementCount === 0) {
      renderTranscript({
        force: Boolean(snap.isNew || snap.isSwitch),
        scrollToBottom: Boolean(snap.isNew || snap.isSwitch),
      });
    }
    renderContextBar();
    saveTabCache();
  }

  // --- Render Model Selector Modal (Provider + Favorites) ---
  function renderModelList() {
    els.modelList.textContent = '';
    const q = (els.modelSearch.value || '').trim().toLowerCase();
    const favSet = new Set(state.favoriteModels || []);
    const models = Array.isArray(state.models) ? [...state.models] : [];
    models.sort((a, b) => {
      const ka = `${a.provider}/${a.id}`;
      const kb = `${b.provider}/${b.id}`;
      const fa = (a.favorite || favSet.has(ka)) ? 0 : 1;
      const fb = (b.favorite || favSet.has(kb)) ? 0 : 1;
      if (fa !== fb) return fa - fb;
      return ka.localeCompare(kb);
    });

    models.forEach(m => {
      const key = `${m.provider}/${m.id}`;
      const label = `${m.provider} / ${m.name || m.id}`;
      if (q && !label.toLowerCase().includes(q) && !key.toLowerCase().includes(q)) return;

      const isFav = Boolean(m.favorite || favSet.has(key));
      const row = document.createElement('div');
      row.className = 'lc-model-row' + (state.model?.provider === m.provider && state.model?.id === m.id ? ' active' : '');

      const info = document.createElement('div');
      info.style.display = 'flex';
      info.style.alignItems = 'center';
      info.style.gap = '7px';
      info.style.minWidth = '0';

      const prov = document.createElement('span');
      prov.className = 'lc-provider-tag';
      prov.textContent = m.provider;

      const name = document.createElement('span');
      name.style.fontWeight = '750';
      name.style.overflow = 'hidden';
      name.style.textOverflow = 'ellipsis';
      name.style.whiteSpace = 'nowrap';
      name.textContent = m.name || m.id;

      info.append(prov, name);
      if (m.reasoning) {
        const r = document.createElement('span');
        r.style.fontSize = '10px';
        r.style.color = '#68e37a';
        r.textContent = '🧠';
        info.append(r);
      }

      const star = document.createElement('button');
      star.type = 'button';
      star.className = 'lc-fav-star' + (isFav ? ' active' : '');
      star.textContent = isFav ? '★' : '☆';
      star.title = 'Toggle Favorite Model';
      star.addEventListener('click', ev => {
        ev.stopPropagation();
        sendWs({ type: 'chat_toggle_favorite', provider: m.provider, modelId: m.id, modelKey: key });
      });

      row.addEventListener('click', () => {
        sendWs({ type: 'chat_set_model', provider: m.provider, modelId: m.id });
        els.modelModal.hidden = true;
      });

      row.append(info, star);
      els.modelList.append(row);
    });
  }

  // --- Fork Checkpoint Picker Modal & Session Rename Support (v7.5) ---
  let forkTargetSessionPath = null;

  function openForkCheckpointModal(sourceSession = null) {
    if (!els.forkModal || !els.forkTurnList) {
      sendWs({ type: 'chat_fork' });
      return;
    }
    forkTargetSessionPath = sourceSession?.path || null;
    const baseTitle = sourceSession?.label || sourceSession?.name || state.sessionName || state.sessionId || 'Current Session';
    if (els.forkModalTitle) {
      els.forkModalTitle.textContent = `⑂ Fork Checkpoint · ${String(baseTitle).slice(0, 32)}`;
    }
    if (els.forkNameInput) {
      els.forkNameInput.value = '';
    }
    els.forkTurnList.textContent = '';
    const msgs = (Array.isArray(state.messages) ? state.messages : []).map(normalizeRawMessage);
    if (!msgs.length) {
      const note = document.createElement('div');
      note.style.padding = '8px';
      note.style.fontSize = '12px';
      note.style.color = 'var(--lc-muted)';
      note.textContent = 'Click "⑂ Fork Latest" above to branch this session.';
      els.forkTurnList.appendChild(note);
    } else {
      msgs.forEach((m, idx) => {
        const row = document.createElement('div');
        row.className = 'lc-model-row';
        const left = document.createElement('div');
        left.style.minWidth = '0';
        left.style.flex = '1';
        const head = document.createElement('div');
        head.style.fontWeight = '750';
        head.style.fontSize = '11.5px';
        head.style.color = m.role === 'user' ? '#68e37a' : '#93c5fd';
        head.textContent = `#${idx + 1} · ${m.role === 'user' ? '👤 You' : '🏮 Lanbot'}`;
        const snip = document.createElement('div');
        snip.style.fontSize = '11px';
        snip.style.color = 'var(--lc-fg)';
        snip.style.overflow = 'hidden';
        snip.style.textOverflow = 'ellipsis';
        snip.style.whiteSpace = 'nowrap';
        const cleanTxt = String(m.text || '').replace(/\s+/g, ' ').trim();
        snip.textContent = cleanTxt.slice(0, 90) || (m.toolCalls?.length ? `[${m.toolCalls.length} tool call(s)]` : '(turn)');
        left.append(head, snip);

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'lc-diff-btn accept';
        btn.textContent = `⑂ Fork after #${idx + 1}`;
        row.append(left, btn);
        row.addEventListener('click', () => {
          const customName = (els.forkNameInput?.value || '').trim();
          els.forkModal.hidden = true;
          els.sessionModal.hidden = true;
          setStatus(`Forking conversation after turn #${idx + 1}…`, 'info');
          sendWs({
            type: 'chat_fork',
            uptoIndex: idx,
            sourceSessionPath: forkTargetSessionPath,
            customName,
          });
        });
        els.forkTurnList.appendChild(row);
      });
    }
    els.forkModal.hidden = false;
  }

  els.forkFullBtn?.addEventListener('click', () => {
    const customName = (els.forkNameInput?.value || '').trim();
    els.forkModal.hidden = true;
    els.sessionModal.hidden = true;
    setStatus('Forking full session into a new branch…', 'info');
    sendWs({
      type: 'chat_fork',
      sourceSessionPath: forkTargetSessionPath,
      customName,
    });
  });

  // --- Render Sessions Modal ---
  function renderSessionList() {
    els.sessionList.textContent = '';
    const sessions = Array.isArray(state.sessions) ? state.sessions : [];
    if (!sessions.length) {
      const empty = document.createElement('div');
      empty.style.color = 'var(--lc-muted)';
      empty.style.fontSize = '12px';
      empty.textContent = 'No saved sessions yet.';
      els.sessionList.append(empty);
      return;
    }
    sessions.forEach(s => {
      const row = document.createElement('div');
      row.className = 'lc-model-row' + (s.current ? ' active' : '');
      const left = document.createElement('div');
      left.style.minWidth = '0';
      left.style.flex = '1';
      const title = document.createElement('div');
      title.style.fontWeight = '750';
      title.style.display = 'flex';
      title.style.alignItems = 'center';
      title.style.gap = '6px';
      const nameSpan = document.createElement('span');
      nameSpan.style.overflow = 'hidden';
      nameSpan.style.textOverflow = 'ellipsis';
      nameSpan.style.whiteSpace = 'nowrap';
      nameSpan.textContent = s.label || s.name || s.id;
      title.append(nameSpan);
      if (s.shared) {
        const sharedBadge = document.createElement('span');
        sharedBadge.className = 'lc-ctx-pill';
        sharedBadge.style.color = '#38bdf8';
        sharedBadge.textContent = '🌐 Shared';
        title.append(sharedBadge);
      }
      if (s.busy) {
        const busyBadge = document.createElement('span');
        busyBadge.className = 'lc-ctx-pill';
        busyBadge.style.color = '#fbbf24';
        busyBadge.textContent = '⚡ Running';
        title.append(busyBadge);
      } else if (s.current) {
        const curBadge = document.createElement('span');
        curBadge.className = 'lc-ctx-pill';
        curBadge.style.color = '#68e37a';
        curBadge.textContent = 'Current';
        title.append(curBadge);
      }
      const sub = document.createElement('div');
      sub.style.fontSize = '11px';
      sub.style.color = 'var(--lc-muted)';
      const countText = typeof s.messageCount === 'number' ? `${s.messageCount} msgs · ` : '';
      sub.textContent = `${countText}${s.updatedAt || s.id}`;
      left.append(title, sub);

      const rightBtns = document.createElement('div');
      rightBtns.style.display = 'inline-flex';
      rightBtns.style.gap = '4px';
      rightBtns.style.flexShrink = '0';

      // v7.8: 🌐 Share button ONLY on localhost and ONLY for localhost sessions (not [Lan]-... sessions)
      if (state.isLocal && s.sessionScope !== 'lan') {
        const rowShareBtn = document.createElement('button');
        rowShareBtn.type = 'button';
        rowShareBtn.className = 'lc-icon-btn' + (s.shared ? ' active' : '');
        rowShareBtn.style.color = s.shared ? '#38bdf8' : '';
        rowShareBtn.textContent = '🌐';
        rowShareBtn.title = s.shared
          ? 'Shared with LAN (click to stop sharing)'
          : 'Share this localhost session with LAN';
        rowShareBtn.addEventListener('click', ev => {
          ev.stopPropagation();
          sendWs({
            type: 'chat_share_session',
            sessionId: s.id,
            sessionPath: s.path,
            shared: !s.shared,
          });
        });
        rightBtns.append(rowShareBtn);
      }

      const renameBtn = document.createElement('button');
      renameBtn.type = 'button';
      renameBtn.className = 'lc-icon-btn';
      renameBtn.textContent = '✏️';
      renameBtn.title = 'Rename this session';
      renameBtn.addEventListener('click', ev => {
        ev.stopPropagation();
        const nextName = window.prompt('Rename session:', s.name || s.label || s.id);
        if (nextName === null) return;
        sendWs({
          type: 'chat_rename_session',
          sessionId: s.id,
          sessionPath: s.path,
          sessionScope: s.sessionScope || '',
          name: nextName.trim(),
        });
      });

      const rowForkBtn = document.createElement('button');
      rowForkBtn.type = 'button';
      rowForkBtn.className = 'lc-icon-btn';
      rowForkBtn.textContent = '⑂';
      rowForkBtn.title = 'Fork this session (or pick checkpoint)';
      rowForkBtn.addEventListener('click', ev => {
        ev.stopPropagation();
        if (s.current) {
          openForkCheckpointModal(s);
        } else {
          lastTranscriptFingerprint = '';
          sendWs({
            type: 'chat_switch_session',
            sessionPath: s.path,
            sessionId: s.id,
            sessionScope: s.sessionScope || '',
          });
          setTimeout(() => openForkCheckpointModal(s), 220);
        }
      });

      const rowDeleteBtn = document.createElement('button');
      rowDeleteBtn.type = 'button';
      rowDeleteBtn.className = 'lc-icon-btn';
      rowDeleteBtn.style.color = '#f87171';
      rowDeleteBtn.textContent = '🗑️';
      rowDeleteBtn.title = 'Delete this session';
      rowDeleteBtn.addEventListener('click', ev => {
        ev.stopPropagation();
        const label = s.label || s.name || s.id;
        if (!window.confirm(`Delete session "${label}"?`)) return;
        sendWs({
          type: 'chat_delete_session',
          sessionId: s.id,
          sessionPath: s.path,
          sessionScope: s.sessionScope || '',
        });
      });

      rightBtns.append(renameBtn, rowForkBtn, rowDeleteBtn);
      row.append(left, rightBtns);
      row.addEventListener('click', () => {
        if (s.id && s.id === state.sessionId && !s.busy) {
          els.sessionModal.hidden = true;
          return;
        }
        resetStreamTurn();
        releaseMarkdownTurn();
        activeToolRows.clear();
        state.sendingImmediate = false;
        setStreaming(Boolean(s.busy));
        lastTranscriptFingerprint = '';
        isUserScrolledUp = false;
        state.sessionId = s.id || state.sessionId;
        state.sessionName = s.label || s.name || s.id || '';
        els.sessionTitle.textContent = state.sessionName || 'Chat';
        els.sessionModal.hidden = true;
        state.messages = [];
        els.transcript.textContent = '';
        const loader = document.createElement('div');
        loader.className = 'lc-msg system';
        loader.textContent = `⏳ Loading ${s.label || s.id}…`;
        els.transcript.append(loader);
        sendWs({
          type: 'chat_switch_session',
          sessionPath: s.path,
          sessionId: s.id,
          sessionScope: s.sessionScope || '',
          limit: 8,
        });
        setStatus(`Switched to ${s.label || s.id}.`, 'info');
      });
      els.sessionList.append(row);
    });
  }

  // --- Slash Command Autocomplete with ArrowUp/Down & Tab ---
  function updateSlashPopover(skipRemoteRefresh = false) {
    const val = els.input.value;
    if (!val.startsWith('/') || val.includes('\n')) {
      els.slashPopover.hidden = true;
      slashFiltered = [];
      return;
    }
    if (!skipRemoteRefresh) {
      void refreshSlashCommands(false);
    }
    const token = val.trim().split(/\s+/)[0].toLowerCase();
    slashFiltered = slashCommands.filter(c => c.command.toLowerCase().startsWith(token));
    if (!slashFiltered.length) {
      els.slashPopover.hidden = true;
      return;
    }
    slashIndex = Math.max(0, Math.min(slashIndex, slashFiltered.length - 1));
    els.slashPopover.textContent = '';
    slashFiltered.forEach((item, idx) => {
      const row = document.createElement('div');
      row.className = 'lc-slash-item' + (idx === slashIndex ? ' active' : '');
      const isSkill = item.category === 'skill';
      const badgeLabel = isSkill ? `skill · ${item.scope || 'workspace'}` : (item.category || 'core');
      const badgeCls = isSkill ? 'lc-slash-scope' : 'lc-slash-scope is-builtin';
      row.innerHTML = `
        <span class="lc-slash-cmd">${escapeHtml(item.command)}</span>
        <span class="${badgeCls}">${escapeHtml(badgeLabel)}</span>
        <span class="lc-slash-desc">${escapeHtml(item.description || item.category || '')}</span>
      `;
      row.addEventListener('mousedown', ev => {
        ev.preventDefault();
        applySlashCompletion(item, true);
      });
      els.slashPopover.append(row);
    });
    els.slashPopover.hidden = false;
  }

  function applySlashCompletion(item, executeNow = false) {
    if (!item) return;
    const curVal = els.input.value.trim();
    const parts = curVal.split(/\s+/);
    const trailingArgs = parts.length > 1 ? ' ' + parts.slice(1).join(' ') : '';
    els.input.value = executeNow ? (item.command + trailingArgs) : (item.command + ' ');
    els.slashPopover.hidden = true;
    els.input.focus();
    if (executeNow) {
      void handleSend();
    }
  }

  // --- Execute Local UI & Pi Core Slash Commands without Sending as Raw Chat Prompt ---
  async function executeLocalSlashIfMatched(rawText) {
    const trimmed = rawText.trim();
    if (!trimmed.startsWith('/')) return false;
    const [cmd, ...rest] = trimmed.split(/\s+/);
    const arg = rest.join(' ').trim();
    const lower = cmd.toLowerCase();

    if (lower === '/model' || lower === '/models') {
      els.input.value = '';
      els.slashPopover.hidden = true;
      if (arg) {
        const q = arg.toLowerCase();
        const match = (state.models || []).find(
          m => `${m.provider}/${m.id}`.toLowerCase() === q
            || (m.id || '').toLowerCase() === q
            || (m.name || '').toLowerCase().includes(q)
        );
        if (match) {
          sendWs({ type: 'chat_set_model', provider: match.provider, modelId: match.id });
          return true;
        }
      }
      renderModelList();
      els.modelModal.hidden = false;
      setTimeout(() => els.modelSearch.focus(), 40);
      return true;
    }
    if (lower === '/reset-bot') {
      els.input.value = '';
      els.slashPopover.hidden = true;
      triggerResetBotRuntime();
      return true;
    }
    if (lower === '/new' || lower === '/reset') {
      els.input.value = '';
      els.slashPopover.hidden = true;
      requestNewChat();
      return true;
    }
    if (lower === '/compact') {
      els.input.value = '';
      els.slashPopover.hidden = true;
      setActivityTicker('🗜 Compacting session context via Pi core…');
      setStatus('Compacting session context via Pi core…', 'info');
      sendWs({ type: 'chat_compact', instructions: arg });
      return true;
    }
    if (lower === '/fork') {
      els.input.value = '';
      els.slashPopover.hidden = true;
      if (arg && /^\d+$/.test(arg)) {
        sendWs({ type: 'chat_fork', uptoIndex: Math.max(0, Number(arg) - 1) });
      } else {
        openForkCheckpointModal(null);
      }
      return true;
    }
    if (lower === '/session' || lower === '/sessions' || lower === '/resume') {
      els.input.value = '';
      els.slashPopover.hidden = true;
      sendWs({ type: 'chat_list_sessions' });
      renderSessionList();
      els.sessionModal.hidden = false;
      return true;
    }
    if (lower === '/thinking' || lower === '/think') {
      els.input.value = '';
      els.slashPopover.hidden = true;
      const validLevels = ['off', 'minimal', 'low', 'medium', 'high', 'xhigh'];
      if (arg && validLevels.includes(arg.toLowerCase())) {
        const lvl = arg.toLowerCase();
        sendWs({ type: 'chat_set_thinking', level: lvl });
        setStatus(`Thinking level set to ${lvl.toUpperCase()} in Pi core.`, 'info');
        return true;
      }
      els.settingsModal.hidden = false;
      setTimeout(() => els.thinkingSelect?.focus(), 40);
      return true;
    }
    if (lower === '/settings' || lower === '/config') {
      els.input.value = '';
      els.slashPopover.hidden = true;
      els.settingsModal.hidden = false;
      return true;
    }
    if (lower === '/export') {
      els.input.value = '';
      els.slashPopover.hidden = true;
      window.open('/api/chatbot/export', '_blank');
      return true;
    }
    if (lower === '/clear') {
      els.input.value = '';
      els.slashPopover.hidden = true;
      setActivityTicker('');
      setStatus('Ready', 'info');
      return true;
    }
    return false;
  }

  function requestNewChat() {
    resetStreamTurn();
    releaseMarkdownTurn();
    activeToolRows.clear();
    setStreaming(false);
    state.contextUsage = { messageCount: 0, estimatedTokens: 0 };
    if (!state.messages || state.messages.length === 0) {
      updateTokenBadgeDisplay();
      sendWs({ type: 'chat_new', skipIfEmpty: true });
      setStatus('Ready', 'info');
      return;
    }
    state.messages = [];
    updateTokenBadgeDisplay();
    renderTranscript();
    setStatus('Started a new conversation.', 'info');
    sendWs({ type: 'chat_new', skipIfEmpty: false });
  }

  function isPureAdminSlashCommand(rawText) {
    const trimmed = String(rawText || '').trim();
    if (!trimmed.startsWith('/')) return false;
    const [cmd, ...rest] = trimmed.split(/\s+/);
    const arg = rest.join(' ').trim().toLowerCase();
    const lower = cmd.toLowerCase();
    if ([
      '/help', '/?', '/reset-bot', '/new', '/reset', '/compact', '/fork',
      '/thinking', '/think', '/tools', '/tool', '/mode', '/model', '/models',
      '/session', '/sessions', '/resume', '/settings', '/config', '/export', '/clear', '/harness',
    ].includes(lower)) {
      return true;
    }
    if ((lower === '/skills' || lower === '/skill') && !arg) return true;
    if (lower === '/mcp' && (!arg || arg.startsWith('list') || arg.startsWith('status') || arg.startsWith('info'))) return true;
    return false;
  }

  // --- Send Prompt & Mid-Turn Steer Handler (Prev #1, #3 + v7.9 Skill Context Support) ---
  async function handleSend() {
    const text = els.input.value.trim();
    if (!text) return;
    if (await executeLocalSlashIfMatched(text)) return;

    const isAdminSlash = isPureAdminSlashCommand(text);
    const includeCtx = !isAdminSlash && (prefs.autoContext || (Array.isArray(state.attachments) && state.attachments.length > 0));

    if (state.busy) {
      // Mid-turn steering: queue steer message while Lanbot is responding!
      const captured = includeCtx ? captureContext() : {};
      const ctxPayload = includeCtx ? {
        kind: captured.kind,
        path: captured.path,
        folder: captured.folder,
        markdownMode: captured.markdownMode,
        line: captured.line,
        selectedText: captured.selectedText,
        attachments: captured.attachmentPaths,
      } : {};
      state.messages = Array.isArray(state.messages) ? state.messages : [];
      state.messages.push({
        role: 'user',
        text: `↳ [Steer] ${text}`,
        context: includeCtx ? { path: captured.path || captured.folder, line: captured.line } : null,
      });
      renderTranscript();
      els.input.value = '';
      els.slashPopover.hidden = true;
      state.steerCount = (state.steerCount || 0) + 1;
      setActivityTicker(`↳ Steer instruction queued (${state.steerCount})…`);
      setStatus(`Steer instruction queued (${state.steerCount}). Lanbot will apply it next.`, 'info');
      sendWs({
        type: 'chat_steer',
        reqId: 'steer-' + Date.now().toString(36),
        message: text,
        context: ctxPayload,
      });
      return;
    }

    // Immediate visual feedback on Send button before async turn setup
    state.sendingImmediate = true;
    syncSendButtonState();
    resetStreamTurn();

    let ctxPayload = {};
    let workHash = null;
    let uiCtx = null;

    if (includeCtx) {
      const captured = captureContext();
      const prep = await prepareMarkdownTurn(captured);
      if (prep.workHash) workHash = prep.workHash;
      ctxPayload = {
        kind: captured.kind,
        path: captured.path,
        folder: captured.folder,
        markdownMode: captured.markdownMode,
        line: captured.line,
        selectedText: captured.selectedText,
        attachments: captured.attachmentPaths,
      };
      uiCtx = {
        path: captured.path || captured.folder,
        line: captured.line,
        attachments: captured.attachments,
      };
    }

    // Append user turn card immediately for responsive UX
    state.messages = Array.isArray(state.messages) ? state.messages : [];
    state.messages.push({
      role: 'user',
      text,
      context: uiCtx,
    });
    isUserScrolledUp = false;
    updateScrollBottomButton();
    renderTranscript({ force: true, scrollToBottom: true });

    els.input.value = '';
    els.slashPopover.hidden = true;
    if (isAdminSlash) {
      state.sendingImmediate = false;
      syncSendButtonState();
      setActivityTicker('');
      setStatus('Executing command…', 'info');
    } else {
      setStreaming(true);
      setActivityTicker('🚀 Sending prompt to Lanbot…');
      setStatus('Sending to Lanbot…', 'info');
    }

    sendWs({
      type: 'chat_prompt',
      reqId: 'chat-' + Date.now().toString(36),
      message: text,
      context: isAdminSlash ? {} : ctxPayload,
      workHash,
    });
  }

  // --- Input Keybindings ---
  els.input.addEventListener('input', updateSlashPopover);
  els.input.addEventListener('keydown', event => {
    if (!els.slashPopover.hidden && slashFiltered.length) {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        slashIndex = (slashIndex + 1) % slashFiltered.length;
        updateSlashPopover();
        return;
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault();
        slashIndex = (slashIndex - 1 + slashFiltered.length) % slashFiltered.length;
        updateSlashPopover();
        return;
      }
      if (event.key === 'Tab') {
        event.preventDefault();
        applySlashCompletion(slashFiltered[slashIndex], false);
        return;
      }
      if (event.key === 'Escape') {
        event.preventDefault();
        els.slashPopover.hidden = true;
        return;
      }
    }

    if (event.key !== 'Enter') return;
    if (event.shiftKey || event.ctrlKey) return;
    event.preventDefault();
    if (!els.slashPopover.hidden && slashFiltered.length) {
      const picked = slashFiltered[slashIndex] || slashFiltered[0];
      if (picked) {
        const cur = els.input.value.trim();
        const parts = cur.split(/\s+/);
        const tail = parts.length > 1 ? ' ' + parts.slice(1).join(' ') : '';
        els.input.value = picked.command + tail;
        els.slashPopover.hidden = true;
      }
    }
    void handleSend();
  });

  // --- Header & Modal Events ---
  els.sendBtn.addEventListener('click', () => { void handleSend(); });
  els.stopBtn.addEventListener('click', () => {
    sendWs({ type: 'chat_abort' });
    releaseMarkdownTurn();
    setStreaming(false);
    setStatus('Stopped.', 'warn');
  });
  els.transcript.addEventListener('click', async ev => {
    const codeBtn = ev.target instanceof Element ? ev.target.closest('[data-copy-code]') : null;
    if (!codeBtn) return;
    const rawCode = decodeURIComponent(codeBtn.getAttribute('data-copy-code') || '');
    const ok = await copyTextToClipboard(rawCode);
    codeBtn.textContent = ok ? '✓ Copied!' : '⚠️ Failed';
    setTimeout(() => { codeBtn.textContent = '📋 Copy code'; }, 1500);
  });

  els.newBtn.addEventListener('click', requestNewChat);
  els.exportFullBtn.addEventListener('click', () => {
    const cidParam = state.clientSessionId ? `?clientSessionId=${encodeURIComponent(state.clientSessionId)}` : '';
    window.open(`/api/chatbot/export${cidParam}`, '_blank', 'noopener');
  });
  els.popoutBtn?.addEventListener('click', () => {
    const ctx = captureContext();
    const qs = new URLSearchParams();
    if (state.clientSessionId) qs.set('client_session', state.clientSessionId);
    if (ctx.path) qs.set('path', ctx.path);
    else if (ctx.folder) qs.set('path', ctx.folder);
    if (ctx.kind) qs.set('kind', ctx.kind);
    const popUrl = `/chat?${qs.toString()}`;
    window.open(popUrl, `lanbot_${state.clientSessionId || 'standalone'}`, 'width=460,height=820,resizable=yes,scrollbars=yes');
    prefs.open = false;
    applyLayout();
  });
  els.compactBtn.addEventListener('click', () => {
    sendWs({ type: 'chat_compact' });
    els.sessionModal.hidden = true;
  });
  async function triggerResetBotRuntime() {
    resetStreamTurn();
    releaseMarkdownTurn();
    activeToolRows.clear();
    state.sendingImmediate = false;
    setStreaming(false);
    setActivityTicker('🔄 Resetting Lanbot runtime…', false);
    setStatus('Resetting Lanbot runtime…', 'info');
    els.settingsModal.hidden = true;

    clearTimeout(resetBotTimer);
    let settled = false;
    const ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    resetBotTimer = setTimeout(() => {
      if (settled) return;
      settled = true;
      try { ctrl?.abort(); } catch {}
      setActivityTicker('');
      setStatus('⚠️ Reset Lanbot quá thời gian phản hồi (timeout 10s). Kiểm tra kết nối hoặc tiến trình Pi.', 'error');
    }, 10000);

    // Send via WebSocket if open, and also invoke independent HTTP POST /api/chatbot/reset
    // so reset succeeds even if the WebSocket was dropped or blocked.
    if (ws && ws.readyState === WebSocket.OPEN) {
      sendWs({ type: 'chat_reset_bot' });
    }
    try {
      const resp = await fetch('/api/chatbot/reset', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clientSessionId: state.clientSessionId }),
        signal: ctrl ? ctrl.signal : undefined,
      });
      const data = await resp.json().catch(() => ({}));
      if (settled) return;
      settled = true;
      clearTimeout(resetBotTimer);
      setActivityTicker('');
      if (!resp.ok || data.ok === false) {
        setStatus('⚠️ Reset Lanbot thất bại: ' + (data.error || `HTTP ${resp.status}`), 'error');
        return;
      }
      applySnapshot({ ...data, isSwitch: true });
      setStatus('✓ Lanbot runtime reset and ready.', 'info');
      if (!wsConnected) {
        reconnectAttempts = 0;
        connectWs(true);
      } else {
        sendWs({ type: 'chat_load_history', limit: 24 });
      }
    } catch (err) {
      if (settled) return;
      settled = true;
      clearTimeout(resetBotTimer);
      setActivityTicker('');
      setStatus('⚠️ Không thể reset Lanbot (mất kết nối hoặc timeout): ' + (err?.message || err), 'error');
    }
  }

  els.compactNowBtn.addEventListener('click', () => {
    sendWs({ type: 'chat_compact' });
    els.settingsModal.hidden = true;
  });
  els.resetBotBtn?.addEventListener('click', () => {
    triggerResetBotRuntime();
  });
  els.forkBtn.addEventListener('click', () => {
    openForkCheckpointModal(null);
  });
  els.sessionBtn.addEventListener('click', () => {
    sendWs({ type: 'chat_list_sessions' });
    renderSessionList();
    els.sessionModal.hidden = !els.sessionModal.hidden;
  });
  els.modelBtn.addEventListener('click', () => {
    renderModelList();
    els.modelModal.hidden = !els.modelModal.hidden;
    if (!els.modelModal.hidden) setTimeout(() => els.modelSearch.focus(), 40);
  });
  els.modelSearch.addEventListener('input', renderModelList);
  els.settingsBtn.addEventListener('click', () => {
    els.settingsModal.hidden = !els.settingsModal.hidden;
    if (!els.settingsModal.hidden) {
      void refreshSlashCommands(true);
    }
  });
  els.dockBtn.addEventListener('click', () => {
    prefs.dock = prefs.dock === 'right' ? 'left' : 'right';
    applyLayout();
  });
  els.expandBtn.addEventListener('click', () => {
    prefs.expanded = !prefs.expanded;
    applyLayout();
  });
  els.closeBtn.addEventListener('click', () => {
    prefs.open = false;
    applyLayout();
  });
  els.contextToggle.addEventListener('click', () => {
    prefs.autoContext = !prefs.autoContext;
    applyLayout();
    renderContextBar();
  });
  els.thinkingSelect.addEventListener('change', () => {
    sendWs({ type: 'chat_set_thinking', level: els.thinkingSelect.value });
  });
  els.savePrefsBtn?.addEventListener('click', async () => {
    const customSystemPrompt = els.customPromptInput?.value || '';
    const useGlobalSkills = Boolean(els.useGlobalSkillsCheck?.checked);
    const customSkillPaths = String(els.customSkillPathsInput?.value || '')
      .split(/[\r\n,]+/)
      .map(s => s.trim())
      .filter(Boolean);
    sendWs({
      type: 'chat_set_prefs',
      customSystemPrompt,
      useGlobalSkills,
      customSkillPaths,
    });
    try {
      await fetch('/api/chatbot/prefs', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ customSystemPrompt, useGlobalSkills, customSkillPaths }),
      });
    } catch {}
    void refreshSlashCommands(true);
    setStatus('Saved Custom System Prompt & Skills settings.', 'info');
    els.settingsModal.hidden = true;
  });
  els.lockLanBtn?.addEventListener('click', async () => {
    try {
      const resp = await fetch('/api/terminal/logout', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hardLock: true }),
      });
      const d = await resp.json().catch(() => ({}));
      if ('lanLocked' in d) state.lanLocked = Boolean(d.lanLocked);
      if (!resp.ok) {
        setStatus(d.error || `Lock failed (HTTP ${resp.status})`, 'error');
        return;
      }
      setStatus(d.isLocal
        ? `🔒 Locked LAN (${d.revokedLanSessions || 0} session(s) revoked) — LAN now requires password.`
        : '🔒 Session locked.', 'info');
    } catch (err) {
      setStatus(err.message || 'Lock failed', 'error');
    }
  });
  els.allowLanBtn?.addEventListener('click', async () => {
    try {
      const resp = await fetch('/api/terminal/logout', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hardLock: false }),
      });
      const d = await resp.json().catch(() => ({}));
      if ('lanLocked' in d) state.lanLocked = Boolean(d.lanLocked);
      if (!resp.ok) {
        setStatus(d.error || `Unlock failed (HTTP ${resp.status})`, 'error');
        return;
      }
      setStatus('🔓 Unlocked LAN — LAN clients can now access without password.', 'info');
    } catch (err) {
      setStatus(err.message || 'Operation failed', 'error');
    }
  });
  els.unlockBtn.addEventListener('click', async () => {
    const pwd = els.passwordInput.value || '';
    els.passwordInput.value = '';
    try {
      const resp = await fetch('/api/terminal/login', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: pwd }),
      });
      if (resp.ok) {
        state.unlocked = true;
        els.settingsModal.hidden = true;
        connectWs(true);
      } else {
        const d = await resp.json().catch(() => ({}));
        setStatus(d.error || 'Unlock failed', 'error');
      }
    } catch (err) {
      setStatus(err.message || 'Unlock failed', 'error');
    }
  });

  drawer.querySelectorAll('[data-close-modal]').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.getAttribute('data-close-modal');
      const modal = drawer.querySelector(`#${id}`);
      if (modal) modal.hidden = true;
    });
  });

  document.addEventListener('keydown', e => {
    if (e.altKey && e.key.toLowerCase() === 'l') {
      e.preventDefault();
      prefs.open = !prefs.open;
      applyLayout();
      if (prefs.open) {
        renderContextBar();
        setTimeout(() => els.input.focus(), 40);
      }
    }
  });

  // --- WebSocket Connection & Native Pi Streaming Event Handling ---
  function sendWs(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      const enriched = (payload && typeof payload === 'object' && state.clientSessionId && !payload.clientSessionId)
        ? { ...payload, clientSessionId: state.clientSessionId }
        : payload;
      ws.send(JSON.stringify(enriched));
      return true;
    }
    return false;
  }

  function sendSync() {
    sendWs({ type: 'chat_sync', separateHistory: true, historyLimit: 8 });
  }

  function triggerLazyLoadOlderHistory() {
    if (!state.hasMoreOlder || state.loadingOlderHistory || !(state.oldestLoadedIndex > 0)) return;
    state.loadingOlderHistory = true;
    const btn = els.transcript?.querySelector('.lc-load-older-btn');
    if (btn) {
      btn.disabled = true;
      btn.textContent = '⏳ Đang tải tin nhắn cũ hơn…';
    }
    sendWs({
      type: 'chat_load_history',
      beforeIndex: state.oldestLoadedIndex,
      limit: 12,
    });
  }

  function extractAssistantTextDelta(ev) {
    if (typeof ev?.delta === 'string' && (ev.type === 'assistant_delta' || ev.type === 'message_update')) return ev.delta;
    const inner = ev?.assistantMessageEvent || ev?.event;
    if (inner && inner.type === 'text_delta') {
      if (typeof inner.delta === 'string') return inner.delta;
      if (typeof inner.text === 'string') return inner.text;
    }
    return '';
  }

  function extractThinkingDelta(ev) {
    if (typeof ev?.delta === 'string' && ev.type === 'thinking_delta') return ev.delta;
    const inner = ev?.assistantMessageEvent || ev?.event;
    if (inner && (inner.type === 'thinking_delta' || inner.type === 'reasoning_delta' || inner.type === 'thinking_end')) {
      if (typeof inner.delta === 'string') return inner.delta;
      if (typeof inner.thinking === 'string') return inner.thinking;
      if (typeof inner.text === 'string') return inner.text;
      if (typeof inner.content === 'string') return inner.content;
    }
    return '';
  }

  function ensureStreamingTurnCard() {
    if (streamingNode && streamingNode.isConnected) {
      const existingCard = streamingNode.closest('.lc-msg.assistant');
      if (existingCard) return existingCard;
    }
    if (streamingThinkingNode && streamingThinkingNode.isConnected) {
      const existingCard = streamingThinkingNode.closest('.lc-msg.assistant');
      if (existingCard) return existingCard;
    }
    if (streamingToolDetails && streamingToolDetails.isConnected) {
      const existingCard = streamingToolDetails.closest('.lc-msg.assistant');
      if (existingCard) return existingCard;
    }
    const card = document.createElement('article');
    card.className = 'lc-msg assistant streaming';
    const head = document.createElement('div');
    head.className = 'lc-msg-head';
    card.append(head);
    els.transcript.append(card);
    return card;
  }

  function ensureStreamingThinkingNode() {
    if (streamingThinkingNode && streamingThinkingNode.isConnected) return streamingThinkingNode;
    const card = ensureStreamingTurnCard();
    const details = document.createElement('details');
    details.className = 'lc-thinking-card';
    details.open = true;
    details.innerHTML = `<summary>💭 Thinking…</summary>`;
    streamingThinkingNode = document.createElement('pre');
    details.append(streamingThinkingNode);
    const beforeAnchor = streamingToolDetails?.isConnected
      ? streamingToolDetails
      : (streamingNode?.isConnected ? streamingNode : null);
    if (beforeAnchor && card.contains(beforeAnchor)) {
      card.insertBefore(details, beforeAnchor);
    } else {
      card.append(details);
    }
    return streamingThinkingNode;
  }

  function ensureStreamingToolCard() {
    if (streamingToolDetails && streamingToolDetails.isConnected) return streamingToolDetails;
    const card = ensureStreamingTurnCard();
    const details = document.createElement('details');
    details.className = 'lc-tool-card';
    details.open = true;
    const sum = document.createElement('summary');
    sum.textContent = '⚡ Running tools…';
    const pre = document.createElement('pre');
    details.append(sum, pre);
    if (streamingNode && streamingNode.isConnected && card.contains(streamingNode)) {
      card.insertBefore(details, streamingNode);
    } else {
      card.append(details);
    }
    streamingToolDetails = details;
    return details;
  }

  function updateStreamingToolCardSummary() {
    if (!streamingToolDetails || !streamingToolDetails.isConnected) return;
    const sum = streamingToolDetails.querySelector('summary');
    const pre = streamingToolDetails.querySelector('pre');
    const calls = streamTurn.toolCalls || [];
    const runningList = Array.from(activeToolRows.values());
    if (sum) {
      if (runningList.length > 0) {
        const latestName = runningList[runningList.length - 1].toolName;
        sum.textContent = `⚡ Running ${latestName} (${calls.filter(c => c.result === undefined).length || runningList.length} tool call${calls.length > 1 ? 's' : ''})…`;
      } else {
        const names = Array.from(new Set(calls.map(c => c.name).filter(Boolean))).join(', ');
        sum.textContent = `✓ ${calls.length} tool call(s) completed: ${names || 'done'}`;
      }
    }
    if (pre) {
      const lines = [];
      calls.forEach(tc => {
        if (tc.result !== undefined) {
          lines.push(`[${tc.isError ? '❌' : '✓'} ${tc.name}] -> ${safeText(tc.result).slice(0, 400)}`);
        } else {
          lines.push(`⚡ ${tc.name}(${safeText(tc.arguments).slice(0, 240)})`);
        }
      });
      pre.textContent = lines.join('\n\n');
    }
  }

  function ensureStreamingAssistantNode() {
    if (streamingNode && streamingNode.isConnected) return streamingNode;
    const card = ensureStreamingTurnCard();
    streamingNode = document.createElement('div');
    streamingNode.className = 'lc-msg-body';
    card.append(streamingNode);
    return streamingNode;
  }

  function handleStreamEvent(ev) {
    if (!ev || typeof ev !== 'object') return;
    if (window.__lanternMdVisual?.touchBotTurn) window.__lanternMdVisual.touchBotTurn();
    const typ = String(ev.type || '');

    if (typ === 'agent_start') {
      resetStreamTurn();
      setStreaming(true);
      setActivityTicker('⚡ Lanbot started turn…');
      setStatus('Lanbot is working…', 'info');
      return;
    }

    if (typ === 'turn_start') {
      streamTurn.hadToolCall = false;
      streamTurn.lastStopReason = '';
      streamTurn.subturnText = '';
      streamTurn.subturnThinking = '';
      setStreaming(true);
      setActivityTicker('⚡ Lanbot is working…');
      setStatus('Lanbot is working…', 'info');
      return;
    }

    // Show live toolcall preparation from message_update inner events
    const innerEv = ev?.assistantMessageEvent || ev?.event;
    if (innerEv && typeof innerEv === 'object') {
      const itype = String(innerEv.type || '');
      if (itype === 'toolcall_start' || itype === 'toolcall_delta') {
        const tName = innerEv.toolName || innerEv.name || innerEv.partial?.name || '';
        setActivityTicker(tName ? `⚡ Preparing tool: ${tName}…` : '⚡ Preparing tool call…');
      } else if (itype === 'thinking_start') {
        setActivityTicker('💭 Thinking…');
      }
    }

    const thinkDelta = extractThinkingDelta(ev);
    if (thinkDelta) {
      setStreaming(true);
      setActivityTicker('💭 Thinking…');
      const chunk = safeText(thinkDelta);
      if (innerEv?.type === 'thinking_end' && streamTurn.subturnThinking) {
        // Already accumulated via deltas
      } else {
        streamTurn.subturnThinking += chunk;
        const tNode = ensureStreamingThinkingNode();
        tNode.textContent = streamTurn.subturnThinking;
        scrollTranscriptToBottom(false);
      }
    }

    const txtDelta = extractAssistantTextDelta(ev);
    if (txtDelta) {
      setStreaming(true);
      setActivityTicker('✍️ Writing response…');
      streamTurn.subturnText += safeText(txtDelta);
      const node = ensureStreamingAssistantNode();
      const card = node.closest('.lc-msg');
      const head = card?.querySelector('.lc-msg-head');
      if (card && head) {
        populateMessageBodyAndActions(card, head, node, streamTurn.subturnText);
      } else {
        node.innerHTML = renderChatMarkdownHtml(streamTurn.subturnText);
      }
      scrollTranscriptToBottom(false);
      return;
    }

    if (typ === 'tool_execution_start') {
      streamTurn.hadToolCall = true;
      setStreaming(true);
      const id = String(ev.toolCallId || ev.id || Math.random());
      const toolName = String(ev.toolName || ev.name || 'tool');
      const toolArgs = ev.args || ev.arguments || {};
      streamTurn.toolCalls.push({ id, name: toolName, arguments: toolArgs });
      const isSub = /subagent|task/i.test(toolName);
      setActivityTicker(isSub ? `🤖 Running subagent (${toolName})…` : `⚡ Running tool: ${toolName}…`);
      const details = ensureStreamingToolCard();
      const sum = details.querySelector('summary');
      const pre = details.querySelector('pre');
      activeToolRows.set(id, { details, sum, pre, toolName });
      updateStreamingToolCardSummary();
      scrollTranscriptToBottom(false);
      return;
    }

    if (typ === 'tool_execution_end') {
      const id = String(ev.toolCallId || ev.id || '');
      const row = activeToolRows.get(id);
      const failed = Boolean(ev.isError || ev.error);
      if (ev.result !== undefined) {
        streamTurn.toolCalls.push({
          id,
          name: row?.toolName || String(ev.toolName || ev.name || 'result'),
          result: safeText(ev.result),
          isError: failed,
        });
      }
      if (row) {
        activeToolRows.delete(id);
      }
      updateStreamingToolCardSummary();
      if (activeToolRows.size === 0 && streamingToolDetails) {
        streamingToolDetails.open = false;
      }
      return;
    }

    if (typ === 'message_end' && (!ev.message?.role || ev.message.role === 'assistant')) {
      const parsed = normalizeRawMessage(ev.message || {});
      // Crucial fix (v7.3): ONLY use text/thinking from THIS sub-turn (parsed or subturn*),
      // NEVER fall back to streamTurn.text from an earlier sub-turn!
      const subText = (parsed.text || streamTurn.subturnText || '').trim();
      const subThinking = (parsed.thinking || streamTurn.subturnThinking || '').trim();

      if (subThinking) {
        const tNode = ensureStreamingThinkingNode();
        tNode.textContent = subThinking;
        if (!streamTurn.thinking.includes(subThinking)) {
          streamTurn.thinking = streamTurn.thinking ? `${streamTurn.thinking}\n${subThinking}` : subThinking;
        }
      }

      if (subText) {
        // Avoid duplicating if the server synthesized the full turn message at the final step
        const isAlreadyFullTurnText = streamTurn.text && subText.includes(streamTurn.text) && subText !== streamTurn.text;
        const displaySubText = isAlreadyFullTurnText
          ? (subText.slice(streamTurn.text.length).trim() || subText)
          : subText;
        const node = ensureStreamingAssistantNode();
        const card = node.closest('.lc-msg');
        const head = card?.querySelector('.lc-msg-head');
        if (card && head) {
          populateMessageBodyAndActions(card, head, node, displaySubText);
        } else {
          node.innerHTML = renderChatMarkdownHtml(displaySubText);
        }
        if (isAlreadyFullTurnText) {
          streamTurn.text = subText;
        } else if (!streamTurn.text.includes(subText)) {
          streamTurn.text = streamTurn.text ? `${streamTurn.text}\n\n${subText}` : subText;
        }
      }

      streamTurn.subturnText = '';
      streamTurn.subturnThinking = '';

      const finalTools = (parsed.toolCalls && parsed.toolCalls.length) ? parsed.toolCalls : [...streamTurn.toolCalls];
      const finalSubagents = (parsed.subagents && parsed.subagents.length) ? parsed.subagents : [...streamTurn.subagents];

      if (finalSubagents.length) {
        els.transcript.append(createSubagentGrid(finalSubagents));
      }
      // Step 3 (v7): Persist assistant message into state.messages so it never disappears on next send!
      recordAssistantTurnInState({
        text: subText,
        thinking: subThinking,
        toolCalls: finalTools,
        subagents: finalSubagents,
        timestamp: ev.message?.timestamp,
        usage: ev.message?.usage || null,
      });
      if (ev.message?.errorMessage) {
        setStatus('Error: ' + ev.message.errorMessage, 'error');
      }
      const stopReason = String(ev.message?.stopReason || '').toLowerCase();
      streamTurn.lastStopReason = stopReason;
      if (stopReason === 'tooluse' || stopReason === 'tool_use' || (parsed.toolCalls && parsed.toolCalls.length && !subText)) {
        streamTurn.hadToolCall = true;
      }
      if (stopReason && stopReason !== 'tooluse' && stopReason !== 'tool_use') {
        clearTimeout(messageEndSettleTimer);
        messageEndSettleTimer = setTimeout(() => {
          if (state.busy && activeToolRows.size === 0) {
            resetStreamTurn();
            setStreaming(false);
            releaseMarkdownTurn();
            setStatus('Ready', 'info');
            renderTranscript({ force: true });
          }
        }, 350);
      }
      scrollTranscriptToBottom(false);
      return;
    }

    if (typ === 'extension_ui_request') {
      const reqId = String(ev.id || ev.requestId || '');
      const kind = String(ev.kind || ev.method || 'confirm');
      const promptText = String(ev.message || ev.title || 'Extension requires confirmation');
      if (kind === 'confirm') {
        const ok = window.confirm(promptText);
        sendWs({ type: 'chat_extension_ui_response', requestId: reqId, value: ok });
      } else if (kind === 'input') {
        const val = window.prompt(promptText, String(ev.defaultValue || ''));
        sendWs({ type: 'chat_extension_ui_response', requestId: reqId, value: val });
      }
      return;
    }

    if (typ === 'turn_end') {
      if (streamTurn.hadToolCall || streamTurn.lastStopReason === 'tooluse' || streamTurn.lastStopReason === 'tool_use' || activeToolRows.size > 0) {
        streamTurn.hadToolCall = false;
        return;
      }
    }

    if (typ === 'agent_settled' || typ === 'agent_end' || typ === 'turn_end') {
      if (!streamTurn.saved && (streamTurn.text || streamTurn.thinking || streamTurn.toolCalls.length || streamTurn.subagents.length)) {
        recordAssistantTurnInState({
          text: streamTurn.text,
          thinking: streamTurn.thinking,
          toolCalls: [...streamTurn.toolCalls],
          subagents: [...streamTurn.subagents],
        });
      }
      resetStreamTurn();
      setStreaming(false);
      releaseMarkdownTurn();
      setStatus(ev.aborted ? 'Stopped' : 'Ready', 'info');
      renderTranscript({ force: true });
      if (document.body?.dataset?.lanternChatKind === 'file' && document.body?.dataset?.lanternChatPath) {
        const relFile = document.body.dataset.lanternChatPath.replace(/^\/+/, '');
        const rawUrl = '/' + relFile.split('/').map(encodeURIComponent).join('/');
        fetch(rawUrl, { cache: 'no-store', credentials: 'same-origin' })
          .then(r => r.ok ? r.text() : null)
          .then(freshText => {
            if (typeof freshText !== 'string') return;
            const editArea = document.getElementById('editarea');
            if (editArea && editArea.value !== freshText) editArea.value = freshText;
            const textPre = document.querySelector('pre.text-preview');
            if (textPre && textPre.textContent !== freshText) textPre.textContent = freshText;
          })
          .catch(() => {});
      }
    }
  }

  function connectWs(forceReconnect = false) {
    if (forceReconnect) {
      reconnectAttempts = 0;
      if (ws) {
        try { ws.close(); } catch {}
        ws = null;
      }
    }
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
    clearTimeout(reconnectTimer);
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(`${proto}//${location.host}/ws?v=2`);
    ws = socket;
    socket.addEventListener('open', () => {
      if (ws !== socket) return;
      wsConnected = true;
      reconnectAttempts = 0;
      sendWs({ type: 'terminal_client_v2' });
      sendSync();
    });
    socket.addEventListener('message', event => {
      let msg;
      try { msg = JSON.parse(event.data); } catch { return; }
      if (!msg || typeof msg !== 'object') return;
      if (
        msg &&
        msg.clientSessionId &&
        state.clientSessionId &&
        msg.clientSessionId !== state.clientSessionId &&
        !['chat_work_changed', 'chat_work_locked', 'chat_work_error', 'chat_real_file_touched', 'chat_sessions_changed', 'chat_commands_changed', 'chat_shared_refresh'].includes(msg.type)
      ) {
        return;
      }

      if (msg.type === 'terminal_auth') {
        if (msg.isLocal !== undefined) state.isLocal = Boolean(msg.isLocal);
        if (msg.lanLocked !== undefined) state.lanLocked = Boolean(msg.lanLocked);
        state.unlocked = Boolean(msg.authenticated);
        state.passwordRequired = Boolean(msg.required);
        syncAuthUi();
        if (state.unlocked) {
          sendSync();
        } else {
          const noPwd = msg.configured === false;
          setStatus(
            noPwd
              ? '🔒 LAN is locked and no password is configured on host (--set-terminal-password).'
              : '🔒 Terminal & Lanbot are locked. Open Settings (⚙) to enter password.',
            'warn'
          );
        }
      } else if (msg.type === 'hello') {
        state.unlocked = Boolean(msg.terminalUnlocked);
        state.passwordRequired = Boolean(msg.terminalPasswordRequired);
        if (state.unlocked) sendSync();
      } else if (msg.type === 'terminal_auth_ok') {
        state.unlocked = Boolean(msg.unlocked);
        if (state.unlocked) {
          els.settingsModal.hidden = true;
          sendSync();
        } else if (msg.error) {
          setStatus(msg.error, 'error');
        }
      } else if (msg.type === 'chat_state' || msg.type === 'chat_snapshot') {
        const isBusy = Boolean(msg.summary?.streaming ?? msg.busy);
        if (!isBusy) releaseMarkdownTurn();
        applySnapshot(msg);
      } else if (msg.type === 'chat_history_page') {
        state.loadingOlderHistory = false;
        const pageMsgs = Array.isArray(msg.messages) ? msg.messages : [];
        state.hasMoreOlder = Boolean(msg.hasMoreOlder);
        state.oldestLoadedIndex = typeof msg.oldestIndex === 'number' ? msg.oldestIndex : 0;
        if (typeof msg.totalMessages === 'number') {
          state.totalHistoryMessages = msg.totalMessages;
        }
        if (msg.prepend && state.messages && state.messages.length) {
          const prevScrollHeight = els.transcript.scrollHeight;
          const prevScrollTop = els.transcript.scrollTop;
          state.messages = [...pageMsgs, ...state.messages];
          renderTranscript({ force: true, preserveScroll: true, scrollTop: prevScrollTop });
          requestAnimationFrame(() => {
            const newScrollHeight = els.transcript.scrollHeight;
            els.transcript.scrollTop = prevScrollTop + Math.max(0, newScrollHeight - prevScrollHeight);
          });
        } else {
          state.messages = pageMsgs;
          renderTranscript({ force: true, scrollToBottom: true });
        }
        state.contextUsage = {
          messageCount: Math.max(state.messages.length, Number(state.totalHistoryMessages || 0)),
          estimatedTokens: estimateSessionTokens(state.messages, state.contextUsage?.estimatedTokens),
        };
        updateTokenBadgeDisplay();
      } else if (msg.type === 'chat_history_error') {
        state.loadingOlderHistory = false;
        setStatus(`⚠️ Không tải được lịch sử (${msg.error || 'quá lớn'}), nhưng Lanbot và Model vẫn sẵn sàng chat.`, 'warn');
        renderTranscript({ force: true });
      } else if (msg.type === 'chat_bot_event' || msg.type === 'chat_event') {
        if (msg.sessionId && state.sessionId && msg.sessionId !== state.sessionId) {
          return;
        }
        handleStreamEvent(msg.event);
      } else if (msg.type === 'chat_prompt_accepted') {
        state.sendingImmediate = false;
        if (msg.slashHandled) {
          setStreaming(false);
          setActivityTicker('');
          setStatus('Ready', 'info');
        } else {
          setStreaming(true);
          setActivityTicker('💭 Lanbot is thinking…', true);
          setStatus('Lanbot is working…', 'info');
        }
      } else if (msg.type === 'chat_steer_queued') {
        state.steerCount = Number(msg.queuedCount || msg.queueSize || 1);
        setActivityTicker(`↳ Steer instruction queued (${state.steerCount})…`, true);
      } else if (msg.type === 'chat_session_changed') {
        if (msg.state) state.sessionId = msg.state.sessionId || state.sessionId;
        sendSync();
      } else if (msg.type === 'chat_prefs_changed') {
        if (msg.summary) applySnapshot({ summary: msg.summary });
      } else if (msg.type === 'chat_model_changed') {
        if (msg.state?.model) state.model = msg.state.model;
        if (msg.summary?.model) state.model = msg.summary.model;
        applySnapshot({ state: msg.state, summary: msg.summary });
        setStatus(`Model switched to ${state.model?.provider || ''}/${state.model?.id || ''}`, 'info');
      } else if (msg.type === 'chat_favorites_changed') {
        if (Array.isArray(msg.favorites)) state.favoriteModels = msg.favorites;
        if (Array.isArray(msg.models)) state.models = msg.models;
        renderModelList();
      } else if (msg.type === 'chat_sessions_changed') {
        sendWs({ type: 'chat_list_sessions' });
        if (msg.shared === false && msg.sessionId && msg.sessionId === state.sessionId && !state.isLocal) {
          sendSync();
        }
      } else if (msg.type === 'chat_shared_refresh') {
        if (!msg.sessionId || !state.sessionId || msg.sessionId === state.sessionId) {
          if (!msg.senderClientSessionId || msg.senderClientSessionId !== state.clientSessionId) {
            sendWs({ type: 'chat_load_history', limit: 24 });
          }
        }
      } else if (msg.type === 'chat_sessions_list') {
        if (Array.isArray(msg.sessions)) state.sessions = msg.sessions;
        if (msg.renamedSessionId && msg.renamedSessionId === state.sessionId) {
          state.sessionName = msg.sessionName || '';
          els.sessionTitle.textContent = state.sessionName || `Session #${String(state.sessionId).slice(0, 6)}`;
        }
        renderSessionList();
        if (msg.openModal) {
          setStreaming(false);
          els.sessionModal.hidden = false;
        }
      } else if (msg.type === 'chat_bot_reset') {
        clearTimeout(resetBotTimer);
        resetStreamTurn();
        releaseMarkdownTurn();
        activeToolRows.clear();
        state.sendingImmediate = false;
        setStreaming(false);
        setActivityTicker('');
        applySnapshot({ ...msg, isSwitch: true });
        setStatus('✓ Lanbot runtime reset and ready.', 'info');
      } else if (msg.type === 'chat_compacted') {
        setStreaming(false);
        setActivityTicker('');
        if (msg.state || msg.summary || msg.messages) {
          applySnapshot(msg);
        }
        const ok = msg.result?.ok !== false;
        setStatus(ok ? '✓ Session context compacted via Pi core.' : ('Compact notice: ' + (msg.result?.error || 'completed')), ok ? 'info' : 'warn');
      } else if (msg.type === 'chat_slash_message') {
        setStreaming(false);
        setActivityTicker('');
        if (msg.text) {
          state.messages = Array.isArray(state.messages) ? state.messages : [];
          state.messages.push({
            role: 'assistant',
            text: String(msg.text),
          });
          renderTranscript();
        }
        setStatus('Ready', 'info');
      } else if (msg.type === 'chat_commands_changed') {
        void refreshSlashCommands(true);
      } else if (msg.type === 'chat_work_locked') {
        const isLocked = Boolean(msg.locked);
        if (!isLocked) releaseMarkdownTurn();
        if (window.__lanternMdVisual?.onWorkLocked) {
          window.__lanternMdVisual.onWorkLocked(msg.path, isLocked);
        }
        if (window.__lanternMdPaged?.onBotWorkLocked) {
          window.__lanternMdPaged.onBotWorkLocked(msg.path, isLocked);
        }
      } else if (msg.type === 'chat_work_changed') {
        const isFinal = Boolean(msg.final);
        const hashVal = msg.hash || msg.workHash || null;
        if (isFinal) releaseMarkdownTurn();
        if (window.__lanternMdVisual?.onWorkChanged) {
          void window.__lanternMdVisual.onWorkChanged(msg.path, hashVal, isFinal);
        }
        if (window.__lanternMdPaged?.onBotWorkChanged) {
          void window.__lanternMdPaged.onBotWorkChanged(isFinal);
        }
        renderContextBar();
      } else if (msg.type === 'chat_work_error' || msg.type === 'chat_real_file_touched') {
        releaseMarkdownTurn();
        setStatus(msg.error || 'Working copy sync warning', 'error');
      } else if (msg.type === 'chat_aborted') {
        releaseMarkdownTurn();
        setStreaming(false);
        setStatus('Stopped.', 'warn');
      } else if (msg.type === 'chat_process_exit') {
        releaseMarkdownTurn();
        setStreaming(false);
        const detail = msg.stderr ? ` (${msg.stderr})` : '';
        setStatus(`Lanbot runtime exited${detail}. Send a message to auto-restart.`, 'error');
      } else if (msg.type === 'chat_error') {
        clearTimeout(resetBotTimer);
        state.loadingOlderHistory = false;
        releaseMarkdownTurn();
        setStreaming(false);
        setActivityTicker('');
        setStatus(msg.error || 'Chatbot error', 'error');
      }
    });
    socket.addEventListener('close', ev => {
      if (ws !== socket) return;
      wsConnected = false;
      ws = null;
      releaseMarkdownTurn();
      if (state.busy) {
        setStreaming(false);
      }
      setActivityTicker('');
      reconnectAttempts += 1;
      const reason = ev?.reason ? ` (${ev.reason})` : '';
      if (reconnectAttempts <= MAX_RECONNECT_ATTEMPTS) {
        const delayMs = Math.min(8000, 1500 * reconnectAttempts);
        setStatus(
          `⚠️ Mất kết nối tới server${reason} — đang thử kết nối lại (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})…`,
          'warn'
        );
        reconnectTimer = setTimeout(() => connectWs(false), delayMs);
      } else {
        setStatus(
          `❌ Đã mất kết nối tới server sau ${MAX_RECONNECT_ATTEMPTS} lần thử${reason}. Bấm Reset Lanbot hoặc tải lại trang.`,
          'error'
        );
      }
    });
  }

  // Fetch dynamic slash commands (skills + templates)
  void refreshSlashCommands(true);

  globalThis.LanternChat = {
    open: () => { prefs.open = true; applyLayout(); renderContextBar(); },
    close: () => { prefs.open = false; applyLayout(); },
    captureContext,
    prepareMarkdownTurn,
    refreshContext: renderContextBar,
    refreshCommands: () => refreshSlashCommands(true),
    uploadFiles: uploadClientFiles,
  };

  // Immediate user upward scroll intent (wheel / touch) eliminates tug-of-war jitter completely
  els.transcript.addEventListener('wheel', ev => {
    if (ev.deltaY < 0) {
      const dist = els.transcript.scrollHeight - els.transcript.scrollTop - els.transcript.clientHeight;
      if (dist > 8 || state.streaming) {
        isUserScrolledUp = true;
        updateScrollBottomButton();
        saveTabCache();
      }
    }
  }, { passive: true });

  let touchStartY = null;
  els.transcript.addEventListener('touchstart', ev => {
    if (ev.touches && ev.touches.length === 1) {
      touchStartY = ev.touches[0].clientY;
    }
  }, { passive: true });

  els.transcript.addEventListener('touchmove', ev => {
    if (touchStartY !== null && ev.touches && ev.touches.length === 1) {
      const dy = ev.touches[0].clientY - touchStartY;
      // Finger dragging down => scrolling up toward older messages
      if (dy > 8) {
        isUserScrolledUp = true;
        updateScrollBottomButton();
      }
    }
  }, { passive: true });

  els.transcript.addEventListener('scroll', () => {
    if (!programmaticScroll) {
      const dist = els.transcript.scrollHeight - els.transcript.scrollTop - els.transcript.clientHeight;
      if (!isUserScrolledUp) {
        isUserScrolledUp = dist > 48;
      } else if (dist <= 12) {
        isUserScrolledUp = false;
      }
      updateScrollBottomButton();
      if (isUserScrolledUp && els.transcript.scrollTop <= 80 && state.hasMoreOlder && !state.loadingOlderHistory) {
        triggerLazyLoadOlderHistory();
      }
    }
    saveTabCache();
  }, { passive: true });

  els.scrollBottomBtn?.addEventListener('click', () => {
    jumpToLatestMessage();
  });

  try {
    if (typeof BroadcastChannel !== 'undefined' && !IS_STANDALONE_CHAT) {
      const tabGuardChan = new BroadcastChannel('lantern_tab_cid_guard_v791');
      tabGuardChan.addEventListener('message', ev => {
        const d = ev?.data;
        if (!d || typeof d !== 'object') return;
        if (d.type === 'tab_cid_check' && d.cid === state.clientSessionId && d.runtimeId !== TAB_RUNTIME_ID) {
          tabGuardChan.postMessage({
            type: 'tab_cid_in_use',
            cid: state.clientSessionId,
            targetRuntimeId: d.runtimeId,
          });
        } else if (d.type === 'tab_cid_in_use' && d.cid === state.clientSessionId && d.targetRuntimeId === TAB_RUNTIME_ID) {
          state.clientSessionId = persistTabSessionId(generateFreshTabSessionId());
          if (wsConnected) sendSync();
        }
      });
      tabGuardChan.postMessage({
        type: 'tab_cid_check',
        cid: state.clientSessionId,
        runtimeId: TAB_RUNTIME_ID,
      });
    }
  } catch {}

  if (contextChannel) {
    contextChannel.addEventListener('message', ev => {
      const data = ev?.data;
      if (!data || data.type !== 'context_update') return;
      if (IS_STANDALONE_CHAT && (!data.clientSessionId || data.clientSessionId === state.clientSessionId)) {
        state.remoteContext = data.context || null;
        renderContextBar();
      }
    });
  }

  const cachedTab = loadTabCache();
  if (cachedTab) {
    if (cachedTab.sessionId) state.sessionId = cachedTab.sessionId;
    if (cachedTab.sessionName) state.sessionName = cachedTab.sessionName;
    if (cachedTab.model) state.model = cachedTab.model;
    if (cachedTab.thinkingLevel) state.thinkingLevel = cachedTab.thinkingLevel;
    if (Array.isArray(cachedTab.messages) && cachedTab.messages.length > 0) {
      state.messages = cachedTab.messages;
    }
    isUserScrolledUp = Boolean(cachedTab.isUserScrolledUp);
    els.sessionTitle.textContent = state.sessionName || (state.sessionId ? `Session #${String(state.sessionId).slice(0, 6)}` : 'New chat');
    if (state.model && (state.model.id || state.model.name)) {
      els.providerSpan.textContent = state.model.provider || 'auto';
      els.providerSpan.hidden = !state.model.provider;
      els.modelSpan.textContent = state.model.name || state.model.id || 'model';
    }
    updateTokenBadgeDisplay();
    renderTranscript({
      force: true,
      preserveScroll: typeof cachedTab.scrollTop === 'number',
      scrollTop: cachedTab.scrollTop,
    });
  }

  if (IS_STANDALONE_CHAT) {
    prefs.open = true;
  }
  applyLayout();
  renderContextBar();
  requestAnimationFrame(() => {
    setTimeout(() => {
      document.body?.classList?.add('lantern-chat-ready');
    }, 60);
  });
  connectWs();
})();
