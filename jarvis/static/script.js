/* ==========================================================================
   JARVIS-OMEGA — HUD client
   WebSocket link, markdown rendering, voice input, live trace terminal.
   ========================================================================== */
(() => {
  "use strict";

  /* ----------------------------- DOM refs ----------------------------- */
  const $ = (id) => document.getElementById(id);

  const els = {
    feed: $("feed"),
    form: $("chatForm"),
    input: $("chatInput"),
    send: $("btnSend"),
    voice: $("btnVoice"),
    terminal: $("terminal"),
    termStatus: $("termStatus"),
    termCount: $("termCount"),
    clock: $("clock"),
    clockDate: $("clockDate"),
    wsDot: $("wsDot"),
    wsLabel: $("wsLabel"),
    llmDot: $("llmDot"),
    llmLabel: $("llmLabel"),
    statUptime: $("statUptime"),
    statMsgs: $("statMsgs"),
    statLatency: $("statLatency"),
    statCore: $("statCore"),
    loadBar: $("loadBar"),
    memBar: $("memBar"),
    memCount: $("memCount"),
    memSession: $("memSession"),
    feedMeta: $("feedMeta"),
    agentList: $("agentList"),
    btnClear: $("btnClear"),
    btnExport: $("btnExport"),
    btnClearLog: $("btnClearLog"),
  };

  /* ------------------------------ State ------------------------------- */
  const state = {
    ws: null,
    connected: false,
    busy: false,
    sessionId: "sess-" + Math.random().toString(36).slice(2, 10),
    messageCount: 0,
    eventCount: 0,
    startedAt: Date.now(),
    pendingTimer: null,
    listening: false,
    recognition: null,
    retry: 0,
    maxRetry: 20000,
  };

  /* ==================================================================== */
  /* Utilities                                                            */
  /* ==================================================================== */
  const pad = (n) => String(n).padStart(2, "0");

  function nowTime() {
    const d = new Date();
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function scrollFeed() {
    const el = els.feed;
    el.scrollTop = el.scrollHeight;
  }

  function scrollTerm() {
    els.terminal.scrollTop = els.terminal.scrollHeight;
  }

  /* ==================================================================== */
  /* Minimal, safe markdown renderer (no external deps)                   */
  /* ==================================================================== */

  const KEYWORDS = new Set([
    "def", "class", "return", "if", "else", "elif", "for", "while", "import",
    "from", "as", "try", "except", "finally", "with", "lambda", "yield",
    "async", "await", "pass", "raise", "in", "is", "not", "and", "or",
    "none", "true", "false", "None", "True", "False", "self", "const", "let",
    "var", "function", "new", "this", "throw", "catch", "switch", "case",
    "default", "break", "continue", "export", "default", "typeof", "instanceof",
    "void", "delete", "static", "public", "private", "interface", "type",
    "enum", "package", "func", "struct", "go", "defer", "map", "range", "echo",
    "then", "fi", "do", "done", "esac", "local", "fi", "sudo", "export",
  ]);

  function highlight(code, lang) {
    const esc = escapeHtml(code);
    if (!lang || ["text", "output", "plain", "log"].includes(lang)) return esc;

    // Work on escaped text; tokenise comments, strings, numbers, keywords.
    let out = esc;

    // Comments (// ... and # ...) — only when at line start or after whitespace
    out = out.replace(/(^|\n)(\s*)(#[^\n]*|\/\/[^\n]*)/g,
      (m, nl, sp, c) => `${nl}${sp}<span class="tok-com">${c}</span>`);

    // Strings (single, double, backtick)
    out = out.replace(/(&quot;.*?&quot;|&#39;.*?&#39;|`[^`]*`)/g,
      (m) => `<span class="tok-str">${m}</span>`);

    // Numbers
    out = out.replace(/\b(\d+(?:\.\d+)?)\b/g,
      (m) => `<span class="tok-num">${m}</span>`);

    // Keywords (avoid touching HTML we already injected)
    out = out.replace(/\b([A-Za-z_$][\w$]*)\b/g, (m) => {
      if (KEYWORDS.has(m) || KEYWORDS.has(m.toLowerCase())) {
        return `<span class="tok-key">${m}</span>`;
      }
      return m;
    });

    // Function calls
    out = out.replace(/\b([A-Za-z_$][\w$]*)(\s*\()/g, (m, fn, paren) => {
      if (fn.includes("span")) return m;
      return `<span class="tok-fn">${fn}</span>${paren}`;
    });

    return out;
  }

  function renderInline(text) {
    let s = escapeHtml(text);
    // inline code first (protect from other replacements)
    const codes = [];
    s = s.replace(/`([^`]+)`/g, (m, c) => {
      codes.push(c);
      return `\u0000CODE${codes.length - 1}\u0000`;
    });

    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    s = s.replace(/~~([^~]+)~~/g, "<del>$1</del>");
    s = s.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    // bare URLs
    s = s.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g,
      '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>');

    s = s.replace(/\u0000CODE(\d+)\u0000/g,
      (m, i) => `<code>${codes[Number(i)]}</code>`);
    return s;
  }

  function renderMarkdown(md) {
    const lines = String(md).replace(/\r\n/g, "\n").split("\n");
    const html = [];
    let i = 0;

    while (i < lines.length) {
      const line = lines[i];

      // fenced code block
      const fence = line.match(/^```(\w*)\s*$/);
      if (fence) {
        const lang = (fence[1] || "").toLowerCase();
        const body = [];
        i++;
        while (i < lines.length && !/^```\s*$/.test(lines[i])) {
          body.push(lines[i]);
          i++;
        }
        i++; // closing fence
        html.push(
          `<pre><code class="lang-${escapeHtml(lang || "text")}">` +
          highlight(body.join("\n"), lang) +
          `</code></pre>`
        );
        continue;
      }

      // horizontal rule
      if (/^\s*(---+|\*\*\*+|___+)\s*$/.test(line)) {
        html.push("<hr />");
        i++;
        continue;
      }

      // headings
      const h = line.match(/^(#{1,6})\s+(.*)$/);
      if (h) {
        const lvl = Math.min(6, h[1].length);
        html.push(`<h${lvl}>${renderInline(h[2])}</h${lvl}>`);
        i++;
        continue;
      }

      // blockquote
      if (/^>\s?/.test(line)) {
        const quote = [];
        while (i < lines.length && /^>\s?/.test(lines[i])) {
          quote.push(lines[i].replace(/^>\s?/, ""));
          i++;
        }
        html.push(`<blockquote>${renderInline(quote.join(" "))}</blockquote>`);
        continue;
      }

      // unordered list
      if (/^\s*[-*+]\s+/.test(line)) {
        const items = [];
        while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
          items.push(lines[i].replace(/^\s*[-*+]\s+/, ""));
          i++;
        }
        html.push("<ul>" + items.map((t) => `<li>${renderInline(t)}</li>`).join("") + "</ul>");
        continue;
      }

      // ordered list
      if (/^\s*\d+[.)]\s+/.test(line)) {
        const items = [];
        while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
          items.push(lines[i].replace(/^\s*\d+[.)]\s+/, ""));
          i++;
        }
        html.push("<ol>" + items.map((t) => `<li>${renderInline(t)}</li>`).join("") + "</ol>");
        continue;
      }

      // blank
      if (!line.trim()) {
        i++;
        continue;
      }

      // paragraph
      const para = [];
      while (
        i < lines.length &&
        lines[i].trim() &&
        !/^```/.test(lines[i]) &&
        !/^(#{1,6})\s+/.test(lines[i]) &&
        !/^\s*[-*+]\s+/.test(lines[i]) &&
        !/^\s*\d+[.)]\s+/.test(lines[i]) &&
        !/^>\s?/.test(lines[i]) &&
        !/^\s*(---+|\*\*\*+|___+)\s*$/.test(lines[i])
      ) {
        para.push(lines[i]);
        i++;
      }
      html.push(`<p>${renderInline(para.join(" "))}</p>`);
    }

    return html.join("\n");
  }

  /* ==================================================================== */
  /* Feed rendering                                                       */
  /* ==================================================================== */
  function addMessage({ role = "system", author = "JARVIS-OMEGA", avatar = "Ω", content = "", raw = false, time }) {
    const wrap = document.createElement("article");
    wrap.className = `msg msg--${role}`;

    const avatarEl = document.createElement("div");
    avatarEl.className = "msg__avatar";
    avatarEl.textContent = avatar;

    const body = document.createElement("div");
    body.className = "msg__body";

    const meta = document.createElement("div");
    meta.className = "msg__meta";
    meta.innerHTML = `<span class="msg__author">${escapeHtml(author)}</span>` +
                     `<span class="msg__time">${escapeHtml(time || nowTime())}</span>`;

    const contentEl = document.createElement("div");
    contentEl.className = "msg__content";
    if (raw) contentEl.innerHTML = content;
    else contentEl.innerHTML = renderMarkdown(content);

    body.appendChild(meta);
    body.appendChild(contentEl);
    wrap.appendChild(avatarEl);
    wrap.appendChild(body);

    els.feed.appendChild(wrap);
    scrollFeed();
    return { wrap, contentEl };
  }

  function addThinking(agentName) {
    const { wrap, contentEl } = addMessage({
      role: "system",
      author: agentName || "JARVIS-OMEGA",
      avatar: "◈",
      raw: true,
      content: `<span class="thinking"><i></i><i></i><i></i></span>
                <span class="dim" style="font-size:11px;margin-left:8px">processing…</span>`,
    });
    return wrap;
  }

  /* ==================================================================== */
  /* Terminal rendering                                                   */
  /* ==================================================================== */
  const TAG_MAP = {
    route: ["ROUTE", "tline--route"],
    thought: ["THINK", "tline--thought"],
    tool_call: ["TOOL", "tline--tool"],
    tool_result: ["RESULT", "tline--result"],
    final: ["FINAL", "tline--final"],
    error: ["ERR", "tline--error"],
    ack: ["SYS", "tline--sys"],
    sys: ["SYS", "tline--sys"],
  };

  function termLine(kind, message, agent) {
    const [tag, cls] = TAG_MAP[kind] || ["LOG", "tline--sys"];
    const line = document.createElement("div");
    line.className = `tline ${cls}`;

    const time = document.createElement("span");
    time.className = "tline__time";
    time.textContent = nowTime();

    const tagEl = document.createElement("span");
    tagEl.className = "tline__tag";
    tagEl.textContent = agent ? `[${agent}]` : `[${tag}]`;

    const msg = document.createElement("span");
    msg.className = "tline__msg";
    const short = String(message || "").replace(/\s+/g, " ").trim();
    msg.textContent = short.length > 220 ? short.slice(0, 220) + "…" : short;

    line.append(time, tagEl, msg);
    els.terminal.appendChild(line);

    // Cap the trace so memory stays bounded.
    while (els.terminal.childElementCount > 400) {
      els.terminal.removeChild(els.terminal.firstChild);
    }

    state.eventCount += 1;
    els.termCount.textContent = `${state.eventCount} event${state.eventCount === 1 ? "" : "s"}`;
    scrollTerm();
  }

  /* ==================================================================== */
  /* Agent monitor                                                        */
  /* ==================================================================== */
  function setAgentActive(name) {
    document.querySelectorAll(".agent").forEach((el) => {
      el.classList.remove("is-active");
      if (el.dataset.agent === name) el.classList.add("is-active");
    });
    const load = Math.min(96, 22 + Math.random() * 55);
    els.loadBar.style.width = `${load}%`;
  }

  function markAgentDone(name) {
    document.querySelectorAll(".agent").forEach((el) => {
      if (el.dataset.agent === name) {
        el.classList.remove("is-active");
        el.classList.add("is-done");
      }
    });
    els.loadBar.style.width = "10%";
    setTimeout(() => {
      document.querySelectorAll(".agent.is-done").forEach((el) => el.classList.remove("is-done"));
    }, 2600);
  }

  /* ==================================================================== */
  /* WebSocket                                                            */
  /* ==================================================================== */
  function wsUrl() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    // Relative to the current origin so it works behind proxies / previews.
    return `${proto}//${location.host}/ws/chat`;
  }

  function setLink(dotEl, labelEl, stateName, text) {
    dotEl.className = `dot dot--${stateName}`;
    labelEl.textContent = text;
  }

  function connect() {
    try {
      state.ws = new WebSocket(wsUrl());
    } catch (err) {
      scheduleReconnect();
      return;
    }

    state.ws.addEventListener("open", () => {
      state.connected = true;
      state.retry = 0;
      setLink(els.wsDot, els.wsLabel, "live", "LINKED");
      termLine("sys", "Neural link established.", "System");
      els.feedMeta.textContent = `session: ${state.sessionId}`;
      els.memSession.textContent = state.sessionId.slice(-6);
    });

    state.ws.addEventListener("message", (ev) => {
      let data;
      try {
        data = JSON.parse(ev.data);
      } catch {
        return;
      }
      handleEvent(data);
    });

    state.ws.addEventListener("close", () => {
      state.connected = false;
      setLink(els.wsDot, els.wsLabel, "error", "LINK LOST");
      termLine("error", "Neural link dropped. Attempting reconnect…", "System");
      finishPending();
      scheduleReconnect();
    });

    state.ws.addEventListener("error", () => {
      setLink(els.wsDot, els.wsLabel, "error", "LINK ERR");
    });
  }

  function scheduleReconnect() {
    state.retry = Math.min(state.maxRetry, Math.max(1200, state.retry * 1.8 || 1200));
    setTimeout(() => {
      if (!state.connected) connect();
    }, state.retry);
  }

  /* --------------------------- Event handling ------------------------- */
  function handleEvent(data) {
    const type = data.type || "sys";
    const agent = data.agent || "System";
    const message = data.message || "";

    // Latency: from send to first response event.
    if (state.pendingTimer) {
      els.statLatency.textContent = `${Date.now() - state.pendingTimer} ms`;
      els.statLatency.className = "stat__value mono ok";
      state.pendingTimer = null;
    }

    switch (type) {
      case "ack":
        termLine("ack", message, agent);
        break;

      case "route":
        setAgentActive(agent);
        termLine("route", message, agent);
        break;

      case "thought":
        setAgentActive(agent);
        termLine("thought", message, agent);
        break;

      case "tool_call":
        setAgentActive(agent);
        termLine("tool_call", message, agent);
        break;

      case "tool_result":
        termLine("tool_result", message, agent);
        break;

      case "error":
        termLine("error", message, agent);
        removeThinking();
        addMessage({
          role: "error",
          author: "SYSTEM FAULT",
          avatar: "!",
          content: message,
        });
        finishPending();
        break;

      case "final":
        removeThinking();
        markAgentDone(agent);
        termLine("final", `Response delivered (${message.length} chars)`, agent);
        addMessage({
          role: "assistant",
          author: `${agent.toUpperCase()} AGENT`,
          avatar: "Ω",
          content: message,
        });
        state.messageCount += 1;
        els.statMsgs.textContent = String(state.messageCount);
        finishPending();
        refreshMemory();
        break;

      default:
        termLine("sys", message, agent);
    }
  }

  /* ------------------------- Pending indicator ------------------------ */
  let thinkingEl = null;

  function startPending(agentName) {
    state.busy = true;
    els.send.disabled = true;
    els.statCore.textContent = "BUSY";
    els.statCore.className = "stat__value warn";
    thinkingEl = addThinking(agentName);
    state.pendingTimer = Date.now();
    els.termStatus.textContent = "processing";
  }

  function removeThinking() {
    if (thinkingEl && thinkingEl.parentNode) {
      thinkingEl.parentNode.removeChild(thinkingEl);
    }
    thinkingEl = null;
  }

  function finishPending() {
    removeThinking();
    state.busy = false;
    els.send.disabled = false;
    els.statCore.textContent = "ONLINE";
    els.statCore.className = "stat__value ok";
    els.termStatus.textContent = "idle";
    document.querySelectorAll(".agent.is-active").forEach((el) => el.classList.remove("is-active"));
    els.loadBar.style.width = "8%";
  }

  /* ==================================================================== */
  /* Sending messages                                                     */
  /* ==================================================================== */
  function send(text) {
    const message = (text || "").trim();
    if (!message) return;

    if (!state.connected || !state.ws || state.ws.readyState !== WebSocket.OPEN) {
      addMessage({
        role: "error",
        author: "LINK ERROR",
        avatar: "!",
        content: "Neural link is not established. Reconnecting — please try again in a moment.",
      });
      termLine("error", "Send aborted: socket not open.", "System");
      connect();
      return;
    }

    if (state.busy) {
      termLine("sys", "Core busy; message queued request ignored.", "System");
      return;
    }

    addMessage({
      role: "user",
      author: "OPERATOR",
      avatar: "▸",
      content: message,
    });
    termLine("sys", `Transmitting: ${message}`, "Operator");

    try {
      state.ws.send(JSON.stringify({
        session_id: state.sessionId,
        message,
      }));
    } catch (err) {
      termLine("error", `Transmit failed: ${err}`, "System");
      return;
    }

    startPending("ROUTER");
    els.input.value = "";
    els.input.focus();
    state.messageCount += 1;
    els.statMsgs.textContent = String(state.messageCount);
  }

  /* ==================================================================== */
  /* Voice input (Web Speech API)                                         */
  /* ==================================================================== */
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  function initVoice() {
    if (!SpeechRecognition) {
      els.voice.disabled = true;
      els.voice.title = "Speech recognition not supported in this browser";
      return;
    }

    const rec = new SpeechRecognition();
    rec.lang = navigator.language || "en-US";
    rec.interimResults = true;
    rec.continuous = false;
    rec.maxAlternatives = 1;

    rec.addEventListener("result", (ev) => {
      let transcript = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        transcript += ev.results[i][0].transcript;
      }
      els.input.value = transcript;
      if (ev.results[ev.results.length - 1].isFinal) {
        stopVoice();
        const text = transcript.trim();
        if (text) send(text);
      }
    });

    rec.addEventListener("error", (ev) => {
      termLine("error", `Voice error: ${ev.error}`, "System");
      stopVoice();
    });

    rec.addEventListener("end", () => stopVoice());

    state.recognition = rec;
    els.voice.addEventListener("click", toggleVoice);
  }

  function toggleVoice() {
    if (state.listening) {
      stopVoice();
    } else {
      startVoice();
    }
  }

  function startVoice() {
    if (!state.recognition) return;
    try {
      state.recognition.start();
      state.listening = true;
      els.voice.classList.add("is-listening");
      els.input.placeholder = "Listening…";
      els.termStatus.textContent = "listening";
      termLine("sys", "Voice input engaged.", "System");
    } catch (err) {
      termLine("error", `Cannot start voice: ${err.message}`, "System");
    }
  }

  function stopVoice() {
    state.listening = false;
    els.voice.classList.remove("is-listening");
    els.input.placeholder = "Speak or type a command…";
    els.termStatus.textContent = "idle";
    try {
      if (state.recognition) state.recognition.stop();
    } catch { /* noop */ }
  }

  /* ==================================================================== */
  /* Clock, uptime, status polling                                        */
  /* ==================================================================== */
  function tickClock() {
    const d = new Date();
    els.clock.textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    els.clockDate.textContent = d.toLocaleDateString(undefined, {
      weekday: "short", year: "numeric", month: "short", day: "2-digit",
    });

    const elapsed = Math.floor((Date.now() - state.startedAt) / 1000);
    const h = pad(Math.floor(elapsed / 3600));
    const m = pad(Math.floor((elapsed % 3600) / 60));
    const s = pad(elapsed % 60);
    els.statUptime.textContent = `${h}:${m}:${s}`;
  }

  async function refreshStatus() {
    try {
      const res = await fetch("/api/status", { cache: "no-store" });
      if (!res.ok) throw new Error(String(res.status));
      const data = await res.json();

      if (data.llm_configured) {
        setLink(els.llmDot, els.llmLabel, "live", "GEMINI");
      } else {
        setLink(els.llmDot, els.llmLabel, "idle", "OFFLINE AI");
      }

      if (Array.isArray(data.agents) && data.agents.length) {
        // Keep the static roster markup; just annotate titles.
        data.agents.forEach((a) => {
          const el = document.querySelector(`.agent[data-agent="${a.name}"]`);
          if (el) el.title = a.description || a.name;
        });
      }
    } catch {
      setLink(els.llmDot, els.llmLabel, "error", "NO CORE");
    }
  }

  async function refreshMemory() {
    try {
      const res = await fetch("/api/memory?limit=100", { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      const count = data.count || 0;
      els.memCount.textContent = String(count);
      els.memBar.style.width = `${Math.min(100, 4 + count * 6)}%`;
    } catch { /* silent */ }
  }

  /* ==================================================================== */
  /* Wiring                                                               */
  /* ==================================================================== */
  function init() {
    // Form submit
    els.form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      send(els.input.value);
    });

    // Quick action chips
    document.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const cmd = chip.dataset.cmd;
        if (cmd) {
          els.input.value = cmd;
          send(cmd);
        }
      });
    });

    // Enter to send (Shift+Enter newline not applicable to input, keep simple)
    els.input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && !ev.shiftKey) {
        ev.preventDefault();
        send(els.input.value);
      }
      if (ev.key === "Escape") {
        els.input.value = "";
        els.input.blur();
      }
    });

    // Global "/" focus shortcut
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "/" && document.activeElement !== els.input) {
        ev.preventDefault();
        els.input.focus();
      }
    });

    // Clear feed
    els.btnClear.addEventListener("click", () => {
      els.feed.innerHTML = "";
      addMessage({
        role: "system",
        author: "JARVIS-OMEGA",
        avatar: "Ω",
        content: "Feed purged. Core still online.",
      });
      termLine("sys", "Conversation feed purged by operator.", "System");
    });

    // Clear trace
    els.btnClearLog.addEventListener("click", () => {
      els.terminal.innerHTML = "";
      state.eventCount = 0;
      els.termCount.textContent = "0 events";
      termLine("sys", "Execution trace cleared.", "System");
    });

    // Export log
    els.btnExport.addEventListener("click", () => {
      const lines = [];
      els.terminal.querySelectorAll(".tline").forEach((l) => {
        lines.push(l.textContent.trim());
      });
      const text =
        `JARVIS-OMEGA execution trace\n` +
        `session: ${state.sessionId}\n` +
        `exported: ${new Date().toISOString()}\n` +
        `${"-".repeat(60)}\n` +
        lines.join("\n") + "\n";

      const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `jarvis-trace-${Date.now()}.log`;
      a.click();
      URL.revokeObjectURL(url);
      termLine("sys", "Execution trace exported.", "System");
    });

    // Boot sequence
    tickClock();
    setInterval(tickClock, 1000);

    initVoice();
    connect();
    refreshStatus();
    refreshMemory();

    setInterval(refreshStatus, 20000);
    setInterval(refreshMemory, 30000);

    termLine("sys", "HUD initialised. Awaiting neural link…", "System");
    els.input.focus();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
