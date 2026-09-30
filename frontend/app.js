/* 绘梦subtitle v3 · 工作台前端 */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const LANGS = [
    { code: "zh", name: "中文", flag: "🇨🇳" }, { code: "en", name: "英语", flag: "🇺🇸" },
    { code: "ja", name: "日语", flag: "🇯🇵" }, { code: "ko", name: "韩语", flag: "🇰🇷" },
    { code: "es", name: "西班牙语", flag: "🇪🇸" }, { code: "fr", name: "法语", flag: "🇫🇷" },
    { code: "de", name: "德语", flag: "🇩🇪" }, { code: "ru", name: "俄语", flag: "🇷🇺" },
    { code: "pt", name: "葡萄牙语", flag: "🇵🇹" }, { code: "it", name: "意大利语", flag: "🇮🇹" },
    { code: "ar", name: "阿拉伯语", flag: "🇸🇦" }, { code: "th", name: "泰语", flag: "🇹🇭" },
    { code: "vi", name: "越南语", flag: "🇻🇳" }, { code: "id", name: "印尼语", flag: "🇮🇩" },
  ];
  const langName = (code) => (LANGS.find((l) => l.code === code) || {}).name || code || "—";
  const langFlag = (code) => (LANGS.find((l) => l.code === code) || {}).flag || "";
  const GROUPS = { default: "默认", notes: "随堂笔记", meetings: "会议整理" };
  const PAGE_NAMES = { home: "首页", live: "实时翻译", transcribe: "文件转写", default: "默认", notes: "随堂笔记", meetings: "会议整理", settings: "设置" };

  const MODELS = [
    { key: "main", activeKey: "main_active", tone: "deep", name: "深度思考模型", tag: "后台处理",
      desc: "用于会议整理、随堂笔记、对话结束后的后台深度整理",
      sub: "在任务结束后后台运行，负责长文本分析、重点提炼、结构化整理和高质量总结",
      icon: "i-sparkle", enableLabel: "启用后台整理", enabled: true, hasLang: false, thinking: true },
    { key: "light", activeKey: "light_active", tone: "light", name: "轻量实时模型", tag: "低延迟",
      desc: "用于实时翻译过程中的快速总结与即时输出",
      sub: "低延迟运行，快速提取当前内容、生成简短提示和实时摘要，默认模式下不调用",
      icon: "i-wave", enableLabel: "实时快速总结", enabled: true, hasLang: false, thinking: true },
    { key: "mt", activeKey: "mt_active", tone: "mt", name: "专用翻译模型", tag: "翻译专用",
      desc: "用于实时翻译和语言转换",
      sub: "专门负责原文到目标语言的翻译，不参与长文本整理",
      icon: "i-translate", enableLabel: "启用翻译模型", enabled: true, hasLang: true, thinking: false },
  ];
  const THINK_HINT = "关闭思考响应最快，适合实时；深度思考会先推理再作答，耗时更长但结构更完整；标准交给模型自己决定。";
  const PROVIDERS = [
    { id: "deepseek", name: "DeepSeek", base: "https://api.deepseek.com/v1" },
    { id: "dashscope", name: "阿里云百炼（通义）", base: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
    { id: "openai", name: "OpenAI", base: "https://api.openai.com/v1" },
    { id: "moonshot", name: "月之暗面 Kimi", base: "https://api.moonshot.cn/v1" },
    { id: "zhipu", name: "智谱 GLM", base: "https://open.bigmodel.cn/api/paas/v4" },
    { id: "custom", name: "自定义 / 兼容 OpenAI 接口", base: "" },
  ];

  const state = {
    page: "home",
    mode: "default",
    health: null,
    summary: { default: [], notes: [], meetings: [] },
    tasks: [],
    selected: { default: null, notes: null, meetings: null },
    sort: { default: "new", notes: "new", meetings: "new" },
    filter: { default: "", notes: "", meetings: "" },
    capture: { active: false, paused: false, startedAt: 0, timer: null, poll: null, rms: 0, wave: [] },
    live: { items: [], quick: "", sentCount: 0, lastCurrentLen: 0, coachBusy: false,
            coachTimer: null, lastCoachAt: 0, coachUpdates: 0, sig: "" },
    monitorTimer: null, pendingTimer: null, statusSnapshot: {},
    settings: { language: "zh-CN", microphone: "default", models: {}, realtime: false, sourceLang: "en",
                fileSourceLang: "zh", targetLang: "zh",
                summarySource: "target", analysisOutput: "target" },
    profiles: { mt: [], main: [], light: [], mt_active: "", main_active: "", light_active: "", mt_engine: "auto" },
    storage: { recordings_dir: "", archives_dir: "" },
    group: "default",
    savedGroups: {},
  };

  /* ------------------------------ 工具 ------------------------------ */
  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>'"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[ch]));
  }
  function showToast(message, isError = false) {
    const toast = $("#toast");
    if (!toast) return;
    toast.textContent = message;
    toast.className = "toast show" + (isError ? " error" : "");
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => { toast.className = "toast"; }, 3400);
  }
  function pad(n) { return String(n).padStart(2, "0"); }
  function fmtDur(seconds) {
    const s = Math.max(0, Math.round(Number(seconds) || 0));
    const h = Math.floor(s / 3600);
    return `${pad(h)}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
  }
  function fmtClock(seconds) {
    const s = Math.max(0, Math.round(Number(seconds) || 0));
    return `${pad(Math.floor(s / 60))}:${pad(s % 60)}`;
  }
  function todayText() { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`; }
  function nowStamp() {
    const d = new Date();
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }
  function fmtSize(bytes) {
    const n = Number(bytes) || 0;
    if (!n) return "—";
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
    return `${(n / 1024 / 1024).toFixed(1)} MB`;
  }
  function fmtDate(value) {
    const text = String(value || "").trim();
    if (!text) return "—";
    return text.replace("_", " ").replace(/-/g, "-").slice(0, 16);
  }
  function relativeDay(value) {
    const text = String(value || "");
    const date = new Date(text.replace("_", " ").replace(/-/g, "/").slice(0, 10));
    if (isNaN(date.getTime())) return "更早";
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const diff = Math.round((today - date) / 86400000);
    if (diff <= 0) return "今天";
    if (diff === 1) return "昨天";
    return text.slice(0, 10);
  }
  function icon(id, cls = "") { return `<svg class="${cls}"><use href="#${id}"/></svg>`; }
  function fileKind(name) {
    const ext = String(name).split(".").pop().toLowerCase();
    if (["mp3", "m4a", "wav", "aac", "flac", "ogg"].includes(ext)) return { kind: "audio", label: ext.toUpperCase() };
    if (["mp4", "mov", "mkv", "avi", "webm"].includes(ext)) return { kind: "video", label: ext.toUpperCase() };
    if (["pdf", "doc", "docx", "txt", "md", "rtf"].includes(ext)) return { kind: "doc", label: ext.toUpperCase() };
    return { kind: "other", label: ext ? ext.toUpperCase() : "FILE" };
  }

  async function api(path, options) {
    try {
      const res = await fetch(path, options);
      const body = await res.json().catch(() => ({}));
      if (!res.ok && !body.message && !body.detail) body.message = `请求失败（${res.status}）`;
      if (!body.message && body.detail) body.message = body.detail;
      return body;
    } catch (err) {
      return { ok: false, message: "无法连接到本地服务，请确认应用仍在运行。", error: String(err) };
    }
  }
  const apiGet = (path) => api(path);
  const apiPost = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  const apiDel = (path) => api(path, { method: "DELETE" });

  /* ------------------------------ 语言下拉 ------------------------------ */
  function fillLangSelect(select, selected, withAuto) {
    if (!select) return;
    const auto = withAuto ? `<option value="auto">自动识别</option>` : "";
    select.innerHTML = auto + LANGS.map((l) => `<option value="${l.code}">${l.flag} ${l.name}</option>`).join("");
    if (selected) select.value = selected;
  }
  function fillAllLangSelects() {
    fillLangSelect($("#liveSrcLang"), state.settings.sourceLang || "en");
    fillLangSelect($("#liveTgtLang"), state.settings.targetLang || "zh");
    fillLangSelect($("#fileLang"), state.settings.fileSourceLang || "zh", true);
    fillLangSelect($("#fileOutputLang"), state.settings.targetLang || "zh");
    fillLangSelect($("#defaultSourceLang"), state.settings.sourceLang || "en");
    fillLangSelect($("#defaultTargetLang"), state.settings.targetLang || "zh");
    fillLangSelect($("#saveTargetLang"), state.settings.targetLang || "zh");
  }

  /* ------------------------------ 导航 ------------------------------ */
  const OPENERS = {
    settings: () => openSettings(),
  };
  function switchPage(page) {
    if (!PAGE_NAMES[page]) return;
    if (OPENERS[page]) { OPENERS[page](); markRail(page); return; }
    state.page = page;
    $$(".page").forEach((el) => el.classList.toggle("active", el.id === `page-${page}`));
    markRail(page);
    const scroller = $(`#page-${page} .page-body`);
    if (scroller) scroller.scrollTop = 0;
    if (page === "live" && !state.capture.active) clearTimerDisplay();
    if (page === "home") loadWorkspace();
    if (page === "transcribe") loadTasks();
    if (["default", "notes", "meetings"].includes(page)) loadWorkspace();
  }
  function markRail(page) {
    $$(".rail-item").forEach((el) => el.classList.toggle("active", el.dataset.page === page));
  }
  function bindNavigation() {
    $$("[data-page]").forEach((el) => el.addEventListener("click", () => switchPage(el.dataset.page)));
    $("#railBrand").addEventListener("click", () => $("#rail").classList.toggle("open"));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeOverlays(); });
  }

  /* ------------------------------ 首页 ------------------------------ */
  function renderHome() {
    const hour = new Date().getHours();
    const greet = hour < 6 ? "夜深了，注意休息" : hour < 11 ? "早上好，欢迎回来" : hour < 14 ? "中午好，欢迎回来" : hour < 19 ? "下午好，欢迎回来" : "晚上好，欢迎回来";
    $("#homeGreeting").textContent = greet;
    $("#homeDate").textContent = todayText();
    const total = state.summary.default.length + state.summary.notes.length + state.summary.meetings.length;
    $("#homeTaskCount").textContent = `共 ${total} 条记录`;
    const chip = $("#homeServiceChip");
    if (state.health && state.health.version) {
      const v = $("#appVersion");
      if (v) v.textContent = `绘梦subtitle v${state.health.version}`;
    }
    if (state.health && state.health.ok) {
      const st = state.health.engine_status || {};
      chip.textContent = `本地服务正常 · 识别 ${st.asr_available ? "就绪" : "未就绪"} · 翻译 ${st.mt_available ? "就绪" : "未就绪"}`;
      chip.className = "chip ok";
    } else {
      chip.textContent = "本地服务未连接";
      chip.className = "chip bad";
    }
    renderRecent();
  }
  function allRecords() {
    const rows = [];
    Object.keys(GROUPS).forEach((group) => {
      (state.summary[group] || []).forEach((row) => rows.push({ ...row, group }));
    });
    return rows.sort((a, b) => String(b.created || "").localeCompare(String(a.created || "")));
  }
  function secondsSince(text) {
    const stamp = new Date(String(text || "").replace(/-/g, "/")).getTime();
    if (!stamp) return 0;
    return Math.max(0, Math.round((Date.now() - stamp) / 1000));
  }
  function statusChip(row) {
    if (row.status === "analyzing") {
      const secs = secondsSince(row.updated || row.created);
      return `<span class="chip busy">AI 分析中${secs ? ` · ${secs}s` : ""}</span>`;
    }
    if (row.status === "failed") return `<span class="chip bad">分析失败</span>`;
    if (row.group === "default") return `<span class="chip">已保存</span>`;
    return `<span class="chip ok">分析成功</span>`;
  }
  function renderRecent() {
    const filter = $("#homeGroupFilter").value;
    const rows = allRecords().filter((row) => filter === "all" || row.group === filter);
    const box = $("#recentList");
    if (!rows.length) {
      box.innerHTML = `<div class="empty"><svg><use href="#i-folder"/></svg><b>还没有文件记录</b><small>从实时翻译或文件转写开始，最近文件会出现在这里。</small></div>`;
      return;
    }
    box.innerHTML = rows.slice(0, 12).map((row) => {
      const iconId = row.group === "notes" ? "i-book" : row.group === "meetings" ? "i-users" : "i-file";
      const kind = row.source_type === "transcribe" ? "转写文件" : "实时会话";
      const dur = row.duration ? ` · ${fmtDur(row.duration)}` : "";
      return `<div class="recent-item" role="button" tabindex="0" data-open="${row.group}:${row.id}">
        <span class="recent-icon ${row.group}">${icon(iconId)}</span>
        <span class="recent-main"><b>${escapeHtml(row.title || "未命名记录")}</b><small>${kind}${dur} · ${escapeHtml(fmtDate(row.created))}</small></span>
        <span class="recent-side"><span class="recent-tag ${row.group}">${GROUPS[row.group]}</span>${statusChip(row)}
          ${row.status === "failed" ? `<button class="btn text" data-retry="${row.group}:${row.id}">重试</button>` : ""}</span>
      </div>`;
    }).join("");
    $$("[data-retry]", box).forEach((el) => el.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      const [group, id] = el.dataset.retry.split(":");
      const res = await apiPost(`/api/workspace/files/${group}/${id}/retry`, {});
      showToast(res.message || "已重新加入分析队列", !res.ok);
      await loadWorkspace();
    }));
    $$("[data-open]", box).forEach((el) => el.addEventListener("click", () => {
      const [group, id] = el.dataset.open.split(":");
      if (group === "default") { switchPage("default"); selectRecord("default", id); }
      else if (group === "notes") { switchPage("notes"); selectRecord("notes", id); }
      else { switchPage("meetings"); selectRecord("meetings", id); }
    }));
  }

  /* ------------------------------ 工作区数据 ------------------------------ */
  async function loadWorkspace() {
    const data = await apiGet("/api/workspace/summary");
    if (data && data.groups) {
      state.summary = { default: data.groups.default || [], notes: data.groups.notes || [], meetings: data.groups.meetings || [] };
    }
    $("#defaultCount").textContent = `共 ${state.summary.default.length} 条记录`;
    $("#notesCount").textContent = `共 ${state.summary.notes.length} 份笔记`;
    $("#meetingsCount").textContent = `共 ${state.summary.meetings.length} 场会议`;
    renderRecent();
    renderRepo("default");
    renderRepo("notes");
    renderRepo("meetings");
    state.statusSnapshot = collectStatuses();
    ensurePendingPoll();
  }
  function collectStatuses() {
    const map = {};
    Object.keys(GROUPS).forEach((group) => {
      (state.summary[group] || []).forEach((row) => { map[`${group}:${row.id}`] = row.status; });
    });
    return map;
  }
  function pendingAnalyses() {
    const rows = [];
    Object.keys(GROUPS).forEach((group) => {
      (state.summary[group] || []).forEach((row) => {
        if (row.status === "analyzing") rows.push({ group, id: row.id, title: row.title });
      });
    });
    return rows;
  }
  function ensurePendingPoll() {
    if (!pendingAnalyses().length) {
      if (state.pendingTimer) {
        clearInterval(state.pendingTimer);
        state.pendingTimer = null;
      }
      return;
    }
    if (state.pendingTimer) return;
    // 后台整理平均 15~25 秒，3 秒一轮能把"完成"几乎实时地反映到界面上
    state.pendingTimer = setInterval(pollPendingAnalyses, 3000);
  }
  async function pollPendingAnalyses() {
    const before = state.statusSnapshot || {};
    await loadWorkspace();
    const after = state.statusSnapshot || {};
    Object.keys(after).forEach((key) => {
      if (before[key] !== "analyzing" || after[key] === "analyzing") return;
      const [group, id] = key.split(":");
      const row = (state.summary[group] || []).find((r) => r.id === id);
      const title = row ? row.title : "记录";
      if (after[key] === "ready") {
        showToast(`「${title}」AI 整理完成`);
      } else {
        showToast(`「${title}」AI 整理失败，可在详情里重试`, true);
      }
      // 正看着这条记录就顺手把详情刷新掉
      if (state.selected[group] === id && state.page === group) {
        if (group === "notes") renderNotesDetail(id);
        else if (group === "meetings") renderMeetingsDetail(id);
        else renderDetail(group, id);
      }
    });
    ensurePendingPoll();
  }
  async function checkHealth() {
    const data = await apiGet("/api/health");
    state.health = data;
    const dot = $(".rail-status i");
    const label = $("#railStatus");
    if (data && data.ok) {
      dot.classList.remove("bad");
      label.textContent = "本地服务正常";
    } else {
      dot.classList.add("bad");
      label.textContent = "服务未连接";
    }
    renderHome();
  }

  /* ------------------------------ 实时翻译 ------------------------------ */
  const SOURCE_LABEL = { target: "译文", source: "原文", both: "双语" };
  const OUTPUT_LABEL = {
    target: "译文为主，关键处附原文",
    source: "原文",
    both: "双语对照",
  };
  async function persistPreferences() {
    const models = {
      ...state.settings.models,
      realtime: state.settings.realtime,
      sourceLang: state.settings.sourceLang,
      fileSourceLang: state.settings.fileSourceLang,
      targetLang: state.settings.targetLang,
      summarySource: state.settings.summarySource,
      analysisOutput: state.settings.analysisOutput,
    };
    state.settings.models = models;
    await apiPost("/api/workspace/settings", {
      language: state.settings.language,
      microphone: state.settings.microphone,
      models,
    });
  }
  function applySourceSeg() {
    const seg = $("#summarySourceSeg");
    if (!seg) return;
    const mode = state.settings.summarySource || "target";
    $$("button", seg).forEach((btn) => btn.classList.toggle("active", btn.dataset.src === mode));
    const hint = $("#aiEmptyHint");
    if (hint) hint.textContent = `AI 总结当前基于「${SOURCE_LABEL[mode]}」，可在上方随时切换。`;
  }
  function setSummarySource(mode) {
    state.settings.summarySource = mode;
    applySourceSeg();
    persistPreferences();
    showToast(`AI 总结改为基于「${SOURCE_LABEL[mode] || mode}」`);
  }
  function applyOutputSeg() {
    const seg = $("#saveOutputSeg");
    const mode = state.settings.analysisOutput || "target";
    if (seg) $$("button", seg).forEach((btn) => btn.classList.toggle("active", btn.dataset.mode === mode));
    const help = $("#saveOutputHelp");
    if (help) help.textContent = `整理结果按「${OUTPUT_LABEL[mode]}」输出。`;
  }
  function setAnalysisOutput(mode, persist = true) {
    state.settings.analysisOutput = mode;
    applyOutputSeg();
    const select = $("#fileOutputMode");
    if (select) select.value = mode;
    if (persist) persistPreferences();
  }
  function resetCoachState() {
    if (state.live.coachTimer) {
      clearTimeout(state.live.coachTimer);
      state.live.coachTimer = null;
    }
    state.live.session = (state.live.session || 0) + 1;
    state.live.quick = "";
    state.live.sentCount = 0;
    state.live.lastCurrentLen = 0;
    state.live.coachUpdates = 0;
    state.live.coachBusy = false;
    state.live.lastCoachAt = 0;
  }
  function resetCoachPanel() {
    resetCoachState();
    const body = $("#aiSummaryBody");
    const chip = $("#aiStateChip");
    if (!body) return;
    if (state.mode === "default") {
      if (chip) { chip.textContent = "未启用"; chip.className = "chip"; }
      body.innerHTML = `<div class="empty">${icon("i-sparkle")}<b>当前为默认模式，不调用 AI 总结</b><small>如需使用 AI 总结，请切换到随堂模式或会议模式</small></div>`;
      return;
    }
    if (chip) { chip.textContent = "已启用"; chip.className = "chip ok"; }
    body.innerHTML = `<div class="coach-status"><i></i><span id="coachStatusText">等待内容积累…</span></div><div class="ai-live" id="coachNotes"><div class="empty">${icon("i-sparkle")}<b>等待内容积累</b><small id="aiEmptyHint">AI 总结当前基于「${SOURCE_LABEL[state.settings.summarySource] || "译文"}」，说完一句就提炼一次，可在上方随时切换。</small></div></div>`;
  }
  function setMode(mode) {
    state.mode = mode;
    $$(".mode-card").forEach((el) => el.classList.toggle("active", el.dataset.mode === mode));
    resetCoachPanel();
    $("#liveFootStatus").textContent = `当前模式：${mode === "default" ? "默认（只翻译）" : mode === "notes" ? "随堂模式" : "会议模式"}`;
  }
  function renderLiveItems() {
    const items = state.live.items;
    const empty = (id, text, hint, iconId) => `<div class="empty">${icon(iconId)}<b>${text}</b><small>${hint}</small></div>`;
    const orig = $("#originalTranscript");
    const tran = $("#translatedTranscript");
    if (!items.length) {
      orig.innerHTML = empty("", "原文会显示在这里", "开始说话后，识别结果会按时间线出现。", "i-wave");
      tran.innerHTML = empty("", "译文会显示在这里", "翻译结果会和原文一一对应。", "i-translate");
      refreshStopAvailability();
      return;
    }
    orig.innerHTML = items.map((it, i) => `<div class="t-item${it.partial ? " partial" : ""}" data-i="${i}"><time>${fmtClock(it.start || 0)}</time><p>${escapeHtml(it.ko || it.text || "")}</p></div>`).join("");
    tran.innerHTML = items.map((it, i) => `<div class="t-item${it.partial ? " partial" : ""}" data-i="${i}"><time>${fmtClock(it.start || 0)}</time><p>${escapeHtml(it.zh || "")}</p></div>`).join("");
    orig.scrollTop = orig.scrollHeight;
    tran.scrollTop = tran.scrollHeight;
    refreshStopAvailability();
  }
  function paintWave() {
    const canvas = $("#waveCanvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    const bars = state.capture.wave;
    const n = 64, step = w / n, mid = h / 2;
    ctx.fillStyle = getComputedStyle(canvas).color || "#7a6bff";
    for (let i = 0; i < n; i++) {
      const v = bars[i] || 0;
      const amp = Math.max(2, Math.min(mid - 2, v * mid * 3.2));
      const x = i * step + step * 0.3;
      const bw = Math.max(1.6, step * 0.4);
      ctx.globalAlpha = v > 0.005 ? 0.95 : 0.28;
      ctx.beginPath();
      const r = bw / 2;
      const y1 = mid - amp, y2 = mid + amp;
      ctx.moveTo(x + r, y1);
      ctx.lineTo(x + bw - r, y1);
      ctx.quadraticCurveTo(x + bw, y1, x + bw, y1 + r);
      ctx.lineTo(x + bw, y2 - r);
      ctx.quadraticCurveTo(x + bw, y2, x + bw - r, y2);
      ctx.lineTo(x + r, y2);
      ctx.quadraticCurveTo(x, y2, x, y2 - r);
      ctx.lineTo(x, y1 + r);
      ctx.quadraticCurveTo(x, y1, x + r, y1);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }
  function updateLiveClock() {
    const seconds = state.capture.active ? (Date.now() - state.capture.startedAt) / 1000 : 0;
    const text = fmtDur(seconds);
    $("#liveTimer").textContent = text;
    $("#controlTimer").textContent = text;
  }
  function refreshStopAvailability() {
    const hasContent = state.capture.active || state.live.items.length > 0;
    $("#liveStopButton").disabled = !hasContent;
    $("#livePauseButton").disabled = !state.capture.active;
  }
  function setLiveUI(active, paused) {
    const bar = $("#controlBar");
    bar.classList.toggle("recording", active && !paused);
    bar.classList.toggle("paused", active && paused);
    if (!active && state.live.items.length) {
      $("#liveStateChip").textContent = "待保存";
      $("#liveStateChip").className = "chip busy";
    } else {
      $("#liveStateChip").textContent = active ? (paused ? "已暂停" : "录制中") : "待开始";
      $("#liveStateChip").className = "chip" + (active ? (paused ? " busy" : " bad") : "");
    }
    refreshStopAvailability();
    $("#liveMainButton").innerHTML = active ? icon("i-wave") : icon("i-play");
    $("#liveMainButton").title = active ? "正在录制" : "开始翻译";
    $("#livePauseButton").innerHTML = paused ? `${icon("i-play")}<span>继续</span>` : `${icon("i-pause")}<span>暂停</span>`;
    $$("#page-live select, #page-live .mode-card").forEach((el) => { el.disabled = active; });
    if (!active) {
      $("#liveCrumbTime").textContent = "未开始";
      $("#liveTitle").textContent = "实时翻译";
      $("#liveDate").textContent = todayText();
      $("#liveFootStatus").textContent = `当前模式：${state.mode === "default" ? "默认（只翻译）" : state.mode === "notes" ? "随堂模式" : "会议模式"}`;
    }
  }
  // 只把计时器的显示归零；startedAt 保留，因为保存弹窗还要靠它算时长
  function clearTimerDisplay() {
    $("#liveTimer").textContent = "00:00:00";
    $("#controlTimer").textContent = "00:00:00";
  }
  // 清掉上一段会话在界面上留下的痕迹（时间、字幕、状态）
  function resetLiveDisplay() {
    clearInterval(state.capture.timer);
    clearInterval(state.capture.poll);
    state.capture.timer = null;
    state.capture.poll = null;
    state.capture.active = false;
    state.capture.paused = false;
    state.capture.startedAt = 0;
    state.capture.finalSeconds = 0;
    state.capture.wave = [];
    clearTimerDisplay();
    $("#liveCrumbTime").textContent = "未开始";
    $("#liveTitle").textContent = "实时翻译";
    $("#liveDate").textContent = todayText();
    paintWave();
  }
  // 接管一个已经在后端跑着的会话（比如界面重开过）
  function attachCapture() {
    state.capture.active = true;
    state.capture.paused = false;
    state.capture.timer = setInterval(updateLiveClock, 500);
    state.capture.poll = setInterval(pollCapture, 400);
    setLiveUI(true, false);
    updateLiveClock();
  }
  async function startLive() {
    // 先和后端对一下账：避免"界面以为在跑、其实没跑"导致点了没反应
    const status = await apiGet("/api/capture/status");
    if (status && status.active) {
      if (!state.capture.poll) attachCapture();
      showToast("检测到正在进行的会话，已接管显示");
      return;
    }
    // 后端没在跑：把上一段的残留（旧时间、旧状态）先清干净再启动
    resetLiveDisplay();
    const src = $("#liveSrcLang").value;
    const tgt = $("#liveTgtLang").value;
    if (src === tgt) { showToast("原文语言和目标语言相同，请先调整语言方向", true); return; }
    showToast("正在启动麦克风…");
    const micSelect = $("#liveMicrophone");
    const micLabel = micSelect && micSelect.value !== "default" ? micSelect.value : "default";
    const res = await apiPost("/api/capture/start", {
      src, tgt, mode: state.settings.realtime ? "realtime" : "local", device: micLabel,
    });
    if (!res.ok) {
      const msg = res.message || "麦克风启动失败";
      showToast(msg, true);
      $("#liveStateChip").textContent = "启动失败";
      $("#liveStateChip").className = "chip bad";
      $("#liveFootStatus").textContent = msg;
      return;
    }
    state.pipeline = res.mode || "local";
    state.live.items = [];
    state.live.sig = "";
    resetCoachPanel();   // 新会话：上一段的 AI 总结与提炼进度必须清空
    state.capture.active = true;
    state.capture.paused = false;
    state.capture.startedAt = Date.now();
    state.capture.wave = [];
    const stamp = nowStamp();
    $("#liveCrumbTime").textContent = stamp;
    $("#liveTitle").textContent = stamp;
    $("#liveDate").textContent = stamp.slice(0, 16);
    setLiveUI(true, false);
    renderLiveItems();
    state.capture.timer = setInterval(updateLiveClock, 500);
    state.capture.poll = setInterval(pollCapture, 400);
    updateLiveClock();
    showToast(res.message || "已开始采集");
  }
  async function pollCapture() {
    const [status, subs] = await Promise.all([apiGet("/api/capture/status"), apiGet("/api/live/subtitles")]);
    if (status && status.ok) {
      state.capture.rms = Number(status.rms) || 0;
      state.capture.wave.push(state.capture.rms);
      if (state.capture.wave.length > 64) state.capture.wave.shift();
      paintWave();
      if (status.mode) state.pipeline = status.mode;
      if (status.active === false && state.capture.active) {
        // 后端已停止（异常或外部终止）
        finishCaptureUI();
      }
    }
    if (subs && subs.ok && Array.isArray(subs.subtitles)) {
      const list = subs.subtitles.filter((s) => (s.ko || s.text || "").trim() || (s.zh || "").trim());
      // 实时同传是逐字增量刷新的：只有「内容变了」才重绘，不能只比条数
      const sig = list.map((s) => `${s.ko || s.text || ""}\u0001${s.zh || ""}\u0001${s.partial ? 1 : 0}`).join("\u0002");
      if (sig !== state.live.sig) {
        state.live.sig = sig;
        state.live.items = list;
        renderLiveItems();
        updateLiveCounters();
        if (state.mode !== "default") scheduleQuickNotes(false);
      }
    }
    if (!state.live.items.length && state.health) {
      const st = state.health.engine_status || {};
      const pipeline = state.pipeline === "realtime" ? "实时同传" : "本地转写";
      const net = state.health.ok ? "网络正常" : "网络异常";
      $("#liveFootStatus").textContent = `麦克风采集中 · ${pipeline} · ${net} · 翻译引擎 ${st.mt_available ? "就绪" : "未就绪"}`;
    }
  }
  function updateLiveCounters() {
    const n = state.live.items.length;
    const secs = state.live.items.reduce((acc, it) => Math.max(acc, Number(it.end) || 0), 0);
    const pipeline = state.pipeline === "realtime" ? "实时同传" : "本地转写";
    $("#liveFootStatus").textContent = `${pipeline} · 已识别 ${n} 段 · 时间轴 ${fmtClock(secs)}`;
  }
  const COACH_INTERVAL = 3500;   // 两次实时总结之间的最小间隔
  const COACH_FORCE_CHARS = 60;  // 长句未结束时，累计这么多字也送一次

  function coachFrame() {
    const body = $("#aiSummaryBody");
    if (!body.querySelector(".coach-status")) {
      body.innerHTML = `<div class="coach-status"><i></i><span id="coachStatusText">等待内容积累…</span></div><div class="ai-live" id="coachNotes"></div>`;
    }
    return $("#coachNotes");
  }
  function setCoachStatus(text, tone) {
    coachFrame();
    const el = $("#coachStatusText");
    if (el) el.textContent = text;
    const box = $(".coach-status");
    if (box) box.className = "coach-status" + (tone ? ` ${tone}` : "");
  }
  function paintCoachNotes() {
    const box = coachFrame();
    if (!box) return;
    box.innerHTML = state.live.quick
      ? `<div class="md">${mdToHtml(state.live.quick)}</div>`
      : `<div class="empty"><svg><use href="#i-sparkle"/></svg><b>等待内容积累</b><small>说完一句就会自动提炼一次，不必等到结束。</small></div>`;
    const body = $("#aiSummaryBody");
    if (body) body.scrollTop = body.scrollHeight;
  }
  function scheduleQuickNotes(force) {
    if (state.mode === "default") return;
    if (state.live.coachTimer) {
      if (force) { clearTimeout(state.live.coachTimer); state.live.coachTimer = null; }
      else return;
    }
    const wait = force ? 0 : Math.max(400, COACH_INTERVAL - (Date.now() - state.live.lastCoachAt));
    state.live.coachTimer = setTimeout(() => {
      state.live.coachTimer = null;
      runQuickNotes(force);
    }, wait);
  }
  async function runQuickNotes(force) {
    if (state.mode === "default" || state.live.coachBusy) return;
    const session = state.live.session || 0;
    const items = state.live.items;
    if (!items.length) return;
    // 「已说完」的句子：最后一条还在流式增长时先不动它
    const settled = items.filter((it, i) => i < items.length - 1 || !it.partial);
    let batch = settled.slice(state.live.sentCount);
    if (!batch.length) {
      const last = items[items.length - 1];
      const text = last.ko || last.text || "";
      const grew = text.length - (state.live.lastCurrentLen || 0);
      if (!force && grew < COACH_FORCE_CHARS) return;   // 没有新内容，等下一轮
      batch = [last];
    }
    const contentMode = state.settings.summarySource || "target";
    const lines = batch
      .map((it) => {
        const origin = (it.ko || it.text || "").trim();
        const target = (it.zh || "").trim();
        if (contentMode === "source") return origin;
        // 「译文」和「双语」都要同时给原文：模型必须先看到原文，才能在关键处引用原词
        const paired = [target ? `译文：${target}` : "", origin ? `原文：${origin}` : ""]
          .filter(Boolean).join("\n");
        return paired || origin;
      })
      .filter((line) => line.trim());
    if (!lines.length) {
      state.live.sentCount = settled.length;
      return;
    }
    state.live.coachBusy = true;
    state.live.lastCoachAt = Date.now();
    setCoachStatus("正在提炼重点…");
    const res = await apiPost("/api/coach/notes", {
      new_lines: lines, notes_so_far: state.live.quick, content: contentMode,
    });
    // 会话已经结束或被清空：这次结果作废，别污染下一段
    if (session !== (state.live.session || 0)) {
      state.live.coachBusy = false;
      return;
    }
    state.live.coachBusy = false;
    const isSettled = settled.length > state.live.sentCount;
    if (isSettled) {
      state.live.sentCount = settled.length;
      state.live.lastCurrentLen = 0;
    } else {
      state.live.lastCurrentLen = (batch[batch.length - 1].ko || batch[batch.length - 1].text || "").length;
    }
    if (!res.ok) {
      setCoachStatus(res.message || "实时总结暂时不可用", "bad");
      $("#aiStateChip").textContent = "降级";
      $("#aiStateChip").className = "chip bad";
      return;
    }
    if (res.notes && res.notes.trim()) {
      state.live.quick += (state.live.quick ? "\n" : "") + res.notes.trim();
      state.live.coachUpdates += 1;
      paintCoachNotes();
      setCoachStatus(`已更新 ${state.live.coachUpdates} 次 · 继续听`, "ok");
      $("#aiStateChip").textContent = "实时更新";
      $("#aiStateChip").className = "chip ok";
    } else {
      // 模型认为这段没有值得记录的实质内容：属于正常结果，不是失败
      setCoachStatus("这段没有值得记录的重点，继续听…");
    }
  }
  function finishCaptureUI() {
    clearInterval(state.capture.timer);
    clearInterval(state.capture.poll);
    state.capture.timer = null;
    state.capture.poll = null;
    state.capture.active = false;
    state.capture.paused = false;
    state.capture.wave = [];
    clearTimerDisplay();
    paintWave();
    // 会话意外结束时也要把徽标/按钮状态收回来，
    // 否则会出现"徽标写着录制中、计时却是 00:00:00"的矛盾界面
    setLiveUI(false, false);
  }
  async function stopLive(confirmed) {
    if (!state.capture.active && !state.live.items.length) return;
    if (!confirmed) { $("#stopModal").classList.remove("hidden"); return; }
    $("#stopModal").classList.add("hidden");
    clearInterval(state.capture.timer);
    clearInterval(state.capture.poll);
    state.capture.timer = null;
    state.capture.poll = null;
    // 结束后不再自动提炼：清掉排队中的定时任务，只保留下面这一次收尾
    if (state.live.coachTimer) {
      clearTimeout(state.live.coachTimer);
      state.live.coachTimer = null;
    }
    if (state.capture.active) await apiPost("/api/capture/stop", {});
    const subs = await apiGet("/api/live/subtitles");
    // 后端有字幕时以后端为准；纯手动输入（后端为空）时保留本地内容
    if (subs && subs.ok && Array.isArray(subs.subtitles) && subs.subtitles.length) state.live.items = subs.subtitles;
    // 时长在"点停止"这一刻定格：否则会把停止确认弹窗停留的时间也算进去
    state.capture.finalSeconds = state.capture.startedAt
      ? (Date.now() - state.capture.startedAt) / 1000 : 0;
    state.capture.active = false;
    state.capture.paused = false;
    setLiveUI(false, false);
    clearTimerDisplay();   // 结束后立刻归零，别把上一段的时长留在界面上
    renderLiveItems();
    // 先弹保存窗口：收尾那次提炼要请求大模型，可能好几秒，
    // 不能让它挡在弹窗前面（否则第一次点确认看起来"没反应"）
    openSaveModal();
    if (state.mode !== "default" && state.live.items.length) {
      setCoachStatus("正在收尾最后一段…");
      runQuickNotes(true);   // 不 await：后台跑完就行
    }
  }
  async function togglePause() {
    if (!state.capture.active) return;
    const next = !state.capture.paused;
    await apiPost(next ? "/api/capture/pause" : "/api/capture/resume", {});
    state.capture.paused = next;
    setLiveUI(true, next);
  }
  function openSaveModal() {
    const duration = state.capture.finalSeconds || (Date.now() - state.capture.startedAt) / 1000;
    $("#saveRecordMeta").textContent = `时长 ${fmtDur(duration)} · 刚刚`;
    const defaultTitle = $("#liveTitle").textContent === "实时翻译" ? nowStamp() : $("#liveTitle").textContent;
    $("#saveTitle").value = defaultTitle.slice(0, 20);
    $("#saveTitleCount").textContent = `${$("#saveTitle").value.length}/20`;
    $("#saveDescription").value = "";
    $("#saveModalHint").innerHTML = state.mode === "default"
      ? `${icon("i-sparkle")}默认模式：只保存时间线、原文和译文，不调用 AI`
      : `${icon("i-sparkle")}即将开始 AI 分析，整理完成后可在${GROUPS[state.mode]}仓库查看`;
    const noAnalysis = state.mode === "default";
    applyOutputSeg();
    $$("#saveOutputSeg button").forEach((btn) => { btn.disabled = noAnalysis; });
    if (noAnalysis) {
      $("#saveOutputHelp").textContent = "默认模式只保存时间线、原文和译文，不调用 AI 整理。";
    }
    $("#saveModal").classList.remove("hidden");
    setTimeout(() => $("#saveTitle").focus(), 60);
  }
  async function confirmSave() {
    const title = $("#saveTitle").value.trim() || nowStamp();
    const description = $("#saveDescription").value.trim();
    const duration = state.capture.finalSeconds || (Date.now() - state.capture.startedAt) / 1000;
    const timeline = state.live.items.map((it) => ({
      start: it.start || 0, end: it.end || 0,
      source: it.ko || it.text || "", target: it.zh || "",
    }));
    const body = {
      group: state.mode,
      title,
      source_type: "live",
      source_name: "",
      transcript: state.live.items.map((it) => it.ko || it.text || "").filter(Boolean).join("\n"),
      translation: state.live.items.map((it) => it.zh || "").filter(Boolean).join("\n"),
      timeline,
      quick_summary: state.live.quick || "",
      analysis: "",
      analyze: state.mode !== "default",
      output_mode: state.mode === "default" ? "target" : (state.settings.analysisOutput || "target"),
    };
    $("#saveModal").classList.add("hidden");
    const res = await apiPost("/api/workspace/files", { ...body, description, duration });
    if (!res.ok) { showToast(res.message || "保存失败", true); return; }
    state.savedGroups[res.id] = state.mode;
    if (state.mode === "default") {
      showToast("已保存到默认分组");
      await loadWorkspace();
      switchPage("default");
      selectRecord("default", res.id);
    } else {
      showToast(`已保存，${GROUPS[state.mode]}后台整理中`);
      await loadWorkspace();
      switchPage("home");
    }
    state.live.items = [];
    state.live.sig = "";
    resetCoachPanel();
    setLiveUI(false, false);
    renderLiveItems();
  }

  /* ------------------------------ 文件转写 ------------------------------ */
  async function loadTasks() {
    const res = await apiGet("/api/tasks");
    state.tasks = (res && res.tasks) || [];
    renderTasks();
  }
  function renderTasks() {
    const filter = $("#taskFilter").value;
    const rows = state.tasks.filter((t) => filter === "all" || t.status === filter);
    const box = $("#taskList");
    $("#transcribeTaskCount").textContent = `共 ${state.tasks.length} 个任务`;
    $("#transcribeCrumbTime").textContent = nowStamp();
    $("#transcribeDate").textContent = todayText();
    if (!rows.length) {
      box.innerHTML = `<div class="empty" style="padding:44px 20px">${icon("i-file")}<b>还没有转写任务</b><small>选择一个音频、视频或文档文件，任务会出现在这里。</small></div>`;
      return;
    }
    box.innerHTML = rows.map((t) => {
      const info = fileKind(t.name);
      const stateText = { waiting: "等待转写", running: t.stage || "转写中", done: "转写完成", failed: "转写失败" }[t.status] || t.status;
      const action = t.status === "done"
        ? `<button class="btn text" data-view="${t.id}">查看结果</button>`
        : t.status === "failed"
          ? `<button class="btn text" data-retry="${t.id}">重试</button>`
          : `<button class="btn text" data-cancel="${t.id}">取消</button>`;
      const progress = t.status === "running" || t.status === "waiting"
        ? `<div class="task-progress"><div class="task-progress-bar"><span style="width:${t.progress || 0}%"></span></div><span class="status-line ${t.status}"><i></i>${t.status === "running" ? `已处理 ${t.progress || 0}%` : "排队中"}</span></div>`
        : `<span class="status-line ${t.status}"><i></i>${stateText}</span>`;
      return `<div class="task-item" data-row="${t.id}">
        <div class="task-row">
          <div class="task-name"><span class="task-kind ${info.kind}">${info.kind === "audio" ? icon("i-wave") : info.kind === "video" ? icon("i-play") : icon("i-file")}</span><b title="${escapeHtml(t.name)}">${escapeHtml(t.name)}</b></div>
          <span class="task-cell">${info.label}</span>
          <span class="task-cell">${fmtSize(t.size)}</span>
          <span class="task-cell">${escapeHtml(fmtDate(t.created))}</span>
          <div>${progress}</div>
          <div class="task-actions">${action}<span class="task-cell" title="归档位置">${GROUPS[t.group] || ""}</span></div>
        </div>
      </div>`;
    }).join("");
    $$("[data-view]", box).forEach((el) => el.addEventListener("click", () => viewTask(el.dataset.view)));
    $$("[data-retry]", box).forEach((el) => el.addEventListener("click", async () => {
      const res = await apiPost(`/api/tasks/${el.dataset.retry}/retry`, {});
      showToast(res.message || "已重新加入队列", !res.ok);
      loadTasks();
    }));
    $$("[data-cancel]", box).forEach((el) => el.addEventListener("click", async () => {
      await apiDel(`/api/tasks/${el.dataset.cancel}`);
      showToast("已取消任务");
      loadTasks();
    }));
  }
  async function viewTask(id) {
    const res = await apiGet(`/api/tasks/${id}`);
    if (!res.ok) { showToast(res.message || "读取失败", true); return; }
    const segs = res.segments || [];
    const withTime = $("#showTimeline").checked;
    $("#detailModalTitle").textContent = res.name || "转写结果";
    $("#detailModalBody").innerHTML = `
      <div class="detail-toolbar"><h3>${segs.length} 段内容 · 归档到 ${GROUPS[res.group] || "默认"}</h3>
        <div class="detail-actions">
          <button class="btn line" id="taskExportSrt">${icon("i-download")}导出 SRT</button>
          <button class="btn line" id="taskExportTxt">${icon("i-download")}导出文本</button>
        </div>
      </div>
      <div class="timeline">${segs.map((s) => `
        <div class="timeline-item">${withTime ? `<time>${fmtClock(s.start)}</time>` : `<time>·</time>`}
          <div class="tl-body"><p>${escapeHtml(s.text || "")}</p>${s.zh && s.zh !== s.text ? `<p class="zh">${escapeHtml(s.zh)}</p>` : ""}</div>
        </div>`).join("") || `<div class="empty"><b>没有可显示的片段</b></div>`}</div>`;
    $("#detailModal").classList.remove("hidden");
    $("#taskExportSrt")?.addEventListener("click", () => exportSrt(res.name, segs));
    $("#taskExportTxt")?.addEventListener("click", () => exportText(res.name, segs));
  }
  async function exportText(name, segs) {
    const content = segs.map((s) => `${s.text || ""}\n${s.zh || ""}`.trim()).join("\n\n");
    await saveFile((name || "transcript").replace(/\.[^.]+$/, "") + ".txt", content);
  }
  async function exportSrt(name, segs) {
    const line = (t) => {
      const ms = Math.floor((Number(t) % 1) * 1000);
      const total = Math.floor(Number(t) || 0);
      return `${pad(Math.floor(total / 3600))}:${pad(Math.floor((total % 3600) / 60))}:${pad(total % 60)},${String(ms).padStart(3, "0")}`;
    };
    const content = segs.map((s, i) => `${i + 1}\n${line(s.start)} --> ${line(s.end)}\n${s.text || ""}\n${s.zh || ""}`.trim()).join("\n\n");
    await saveFile((name || "transcript").replace(/\.[^.]+$/, "") + ".srt", content);
  }
  async function saveFile(filename, content) {
    const res = await apiPost("/api/export", { filename, content });
    if (res.ok) showToast(`已导出到 ${res.path}`);
    else showToast(res.message || "导出失败", true);
  }
  async function uploadFiles(files) {
    const list = Array.from(files || []);
    if (!list.length) return;
    for (const file of list) {
      const group = state.group;
      const form = new FormData();
      form.append("file", file);
      form.append("group", group);
      form.append("src_lang", $("#fileLang").value || "auto");
      form.append("tgt_lang", $("#fileOutputLang").value || "zh");
      form.append("diarization", $("#speakerDiarization").checked ? "1" : "0");
      form.append("timeline", $("#showTimeline").checked ? "1" : "0");
      form.append("vocab", $("#vocabBoost").checked ? "1" : "0");
      form.append("output_mode", $("#fileOutputMode").value || "target");
      const res = await api("/api/tasks", { method: "POST", body: form });
      if (!res.ok) showToast(res.message || "创建任务失败", true);
    }
    showToast(`已加入 ${list.length} 个转写任务`);
    loadTasks();
  }
  function bindTranscribe() {
    const zone = $("#dropzone");
    const input = $("#fileInput");
    $("#chooseFileButton").addEventListener("click", () => input.click());
    input.addEventListener("change", () => { uploadFiles(input.files); input.value = ""; });
    ["dragenter", "dragover"].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add("hover"); }));
    ["dragleave", "drop"].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.remove("hover"); }));
    zone.addEventListener("drop", (e) => uploadFiles(e.dataTransfer.files));
    $("#homeChooseFile").addEventListener("click", () => $("#homeFileInput").click());
    $("#homeFileInput").addEventListener("change", (e) => { switchPage("transcribe"); uploadFiles(e.target.files); e.target.value = ""; });
    $("#taskFilter").addEventListener("change", renderTasks);

    const dropdown = $("#groupDropdown");
    $("#groupDropdownToggle").addEventListener("click", (e) => { e.stopPropagation(); dropdown.classList.toggle("open"); });
    document.addEventListener("click", () => dropdown.classList.remove("open"));
    $$(".dropdown-option", dropdown).forEach((opt) => opt.addEventListener("click", () => {
      state.group = opt.dataset.group;
      $$(".dropdown-option", dropdown).forEach((o) => o.classList.toggle("active", o === opt));
      $("#groupDropdownLabel").textContent = GROUPS[state.group];
      $("#groupHelp").textContent = state.group === "default"
        ? "只转写 / 翻译，不调用深度思考模型。"
        : `转写完成后调用深度思考模型，整理结果归档到「${GROUPS[state.group]}」。`;
      dropdown.classList.remove("open");
    }));
    $("#fileOutputMode").addEventListener("change", () => setAnalysisOutput($("#fileOutputMode").value));
    $("#fileLang").addEventListener("change", () => {
      state.settings.fileSourceLang = $("#fileLang").value;
      persistPreferences();
    });
    $("#moreSettingsToggle").addEventListener("click", () => {
      $("#moreSettingsToggle").classList.toggle("open");
      $("#moreSettingsPanel").classList.toggle("hidden");
    });
    setInterval(() => {
      if (state.page === "transcribe" && state.tasks.some((t) => t.status === "running" || t.status === "waiting")) loadTasks();
    }, 1800);
  }

  /* ------------------------------ 仓库通用 ------------------------------ */
  function renderRepo(group) {
    const keyword = ($(`#${group}Search`) || {}).value || "";
    const sort = state.sort[group];
    let rows = (state.summary[group] || []).slice();
    if (keyword.trim()) rows = rows.filter((r) => String(r.title || "").toLowerCase().includes(keyword.trim().toLowerCase()));
    rows.sort((a, b) => sort === "old"
      ? String(a.created || "").localeCompare(String(b.created || ""))
      : String(b.created || "").localeCompare(String(a.created || "")));
    const box = $(`#${group}List`);
    if (!box) return;
    if (!rows.length) {
      const label = group === "default" ? "还没有原始记录" : group === "notes" ? "还没有随堂笔记" : "还没有会议整理";
      box.innerHTML = `<div class="empty">${icon("i-folder")}<b>${label}</b><small>完成一次${group === "default" ? "默认模式实时翻译" : group === "notes" ? "随堂模式" : "会议模式"}后会出现在这里。</small></div>`;
      return;
    }
    let lastDay = "";
    box.innerHTML = rows.map((row) => {
      const day = relativeDay(row.created);
      const groupLabel = day !== lastDay ? `<div class="repo-group">${day}</div>` : "";
      lastDay = day;
      const statusText = { analyzing: "AI 分析中", failed: "分析失败", ready: group === "default" ? "已保存" : "已整理" }[row.status] || "已保存";
      const statusCls = row.status === "analyzing" ? "busy" : row.status === "failed" ? "failed" : "ready";
      const iconId = group === "meetings" ? "i-users" : group === "notes" ? "i-book" : "i-file";
      return `${groupLabel}<button class="repo-item${state.selected[group] === row.id ? " active" : ""}" data-id="${row.id}">
        <span class="repo-icon">${icon(iconId)}</span>
        <span class="repo-item-main"><b title="${escapeHtml(row.title)}">${escapeHtml(row.title || "未命名")}</b>
        <small>${escapeHtml(fmtDate(row.created))}${row.duration ? ` · ${fmtDur(row.duration)}` : ""}</small>
        <span class="repo-state ${statusCls}"><i></i>${statusText}</span></span>
      </button>`;
    }).join("");
    $$("[data-id]", box).forEach((el) => el.addEventListener("click", () => selectRecord(group, el.dataset.id)));
  }
  async function selectRecord(group, id) {
    state.selected[group] = id;
    renderRepo(group);
    if (group === "notes") return renderNotesDetail(id);
    if (group === "meetings") return renderMeetingsDetail(id);
    return renderDetail(group, id);
  }
  async function fetchRecord(group, id) {
    const res = await apiGet(`/api/workspace/files/${group}/${id}`);
    if (!res.ok) { showToast(res.message || "读取记录失败", true); return null; }
    return res;
  }
  function detailHead(row, actions) {
    return `<div class="detail-head">
      <div>
        <h2>${escapeHtml(row.title || "未命名记录")}</h2>
        <div class="detail-meta">
          <span>${icon("i-calendar")}${escapeHtml(fmtDate(row.created))}</span>
          ${row.duration ? `<span>${icon("i-clock")}时长 ${fmtDur(row.duration)}</span>` : ""}
          <span>${icon("i-folder")}${GROUPS[row.group] || "默认"}</span>
          <span>${icon("i-list")}${row.source_type === "transcribe" ? "文件转写" : "实时翻译"}</span>
        </div>
      </div>
      <div class="detail-actions">${actions}</div>
    </div>`;
  }
  function timelineHtml(row) {
    const items = row.timeline || [];
    if (!items.length) {
      if (!row.transcript) return `<div class="empty"><b>没有时间线内容</b></div>`;
      return `<div class="detail-toolbar"><h3>原文与译文</h3></div>
        <div class="analysis-box"><p class="plain-text">${escapeHtml(row.transcript)}</p>
        ${row.translation ? `<p class="plain-text" style="margin-top:12px;color:var(--ink)">${escapeHtml(row.translation)}</p>` : ""}</div>`;
    }
    const hasTime = items.some((it) => (Number(it.start) || 0) > 0);
    return `<div class="detail-toolbar"><h3>时间线 · 原文与译文</h3></div>
      <div class="timeline${hasTime ? "" : " flat"}">${items.map((it) => {
        const source = it.source || it.ko || it.text || "";
        const target = it.target || it.zh || "";
        return `<div class="timeline-item">${hasTime ? `<time>${fmtClock(it.start || 0)}</time>` : `<time>·</time>`}
          <div class="tl-body"><p>${escapeHtml(source)}</p>
          ${target && target !== source ? `<p class="zh">${escapeHtml(target)}</p>` : ""}</div>
        </div>`;
      }).join("")}</div>`;
  }
  async function renderDetail(group, id) {
    const container = $(`#${group}Detail`);
    if (!container) return;
    container.innerHTML = `<div class="empty big"><b>正在载入…</b></div>`;
    const row = await fetchRecord(group, id);
    if (!row) { container.innerHTML = `<div class="empty big">${icon("i-folder")}<b>记录读取失败</b><small>请稍后重试。</small></div>`; return; }
    const statusHtml = row.status === "analyzing"
      ? `<span class="chip busy">AI 分析中</span>`
      : row.status === "failed" ? `<span class="chip bad">分析失败</span>` : `<span class="chip ok">${group === "default" ? "已保存" : "已整理"}</span>`;
    const actions = `
      ${row.status === "failed" ? `<button class="btn line" data-retry-record>${icon("i-swap")}重试整理</button>` : ""}
      ${group !== "default" ? `<button class="btn line" data-reanalyze>${icon("i-sparkle")}重新整理</button>` : ""}
      <button class="btn line" data-export>${icon("i-download")}导出</button>
      <button class="btn danger" data-delete>${icon("i-trash")}删除</button>`;
    container.innerHTML = detailHead(row, actions) +
      statusHtml.replace("chip", "chip") +
      timelineHtml(row) +
      (row.analysis ? `<div class="detail-toolbar"><h3>${group === "meetings" ? "整理结果" : "笔记正文"}</h3></div>
        <div class="analysis-box"><div class="md">${mdToHtml(row.analysis)}</div></div>` : "");
    const head = container.querySelector(".detail-head + .chip");
    if (head) head.style.marginBottom = "16px";
    container.querySelector("[data-export]")?.addEventListener("click", () => exportRecord(row));
    container.querySelector("[data-delete]")?.addEventListener("click", () => deleteRecord(row.group, row.id));
    container.querySelector("[data-retry-record]")?.addEventListener("click", () => retryRecord(row.group, row.id));
    container.querySelector("[data-reanalyze]")?.addEventListener("click", () => retryRecord(row.group, row.id));
  }
  async function deleteRecord(group, id) {
    if (!confirm("确认删除这条记录？原始文件和已有记录不受影响。")) return;
    const res = await apiDel(`/api/workspace/files/${group}/${id}`);
    if (!res.ok) { showToast(res.message || "删除失败", true); return; }
    state.selected[group] = null;
    showToast("已删除");
    await loadWorkspace();
    const empty = group === "default" ? "选择一条记录" : group === "notes" ? "还没有随堂笔记" : "还没有会议整理";
    $(`#${group}Detail`).innerHTML = `<div class="empty big">${icon("i-folder")}<b>${empty}</b><small>左侧列表中的记录会显示在这里。</small></div>`;
  }
  async function retryRecord(group, id) {
    const res = await apiPost(`/api/workspace/files/${group}/${id}/retry`, {});
    showToast(res.message || "已重新加入分析队列", !res.ok);
    await loadWorkspace();
    renderDetail(group, id);
  }
  async function exportRecord(row) {
    const lines = [`# ${row.title || "记录"}`];
    lines.push(`时间：${row.created || ""}`);
    if (row.duration) lines.push(`时长：${fmtDur(row.duration)}`);
    lines.push(`分组：${GROUPS[row.group] || "默认"}`);
    if (row.analysis) lines.push("", "## 整理结果", row.analysis);
    if (row.transcript) lines.push("", "## 原文", row.transcript);
    if (row.translation) lines.push("", "## 译文", row.translation);
    await saveFile(`${(row.title || "record").replace(/[\\/:*?"<>|]/g, "_")}.md`, lines.join("\n"));
  }

  /* ------------------------------ 随堂笔记编辑器 ------------------------------ */
  async function renderNotesDetail(id) {
    const container = $("#notesEditor");
    container.innerHTML = `<div class="empty big"><b>正在载入…</b></div>`;
    const row = await fetchRecord("notes", id);
    if (!row) { container.innerHTML = `<div class="empty big">${icon("i-book")}<b>笔记读取失败</b></div>`; return; }
    const parsed = parseAnalysis(row.analysis, "notes");
    const stateChip = row.status === "analyzing" ? `<span class="chip busy">AI 分析中</span>`
      : row.status === "failed" ? `<span class="chip bad">分析失败，可重试</span>`
        : `<span class="chip ok">${icon("i-check")}已自动保存</span>`;
    container.innerHTML = `
      <div class="note-head">
        <input class="note-title-input" id="noteTitle" value="${escapeHtml(row.title || "未命名笔记")}" maxlength="40" />
        <div class="note-tag-field"><span>课程 / 主题</span>
          <div class="select-box"><select id="noteTag">
            <option>人工智能导记</option><option>产品与运营</option><option>语言学习</option><option>专业课程</option><option>未分类</option>
          </select>${icon("i-chevron", "caret")}</div>
        </div>
        <div class="note-state"><span>保存状态</span>${stateChip}</div>
      </div>
      <div class="note-toolbar">
        <button data-cmd="bold" title="加粗">B</button>
        <button data-cmd="italic" title="斜体" style="font-style:italic">I</button>
        <button data-cmd="formatBlock" data-value="h3" title="标题">H1</button>
        <button data-cmd="formatBlock" data-value="h3" title="标题">H2</button>
        <span class="sep"></span>
        <button data-cmd="insertUnorderedList" title="列表">${icon("i-list")}</button>
        <button data-cmd="insertOrderedList" title="编号">1.</button>
        <button data-cmd="insertHTML" data-value="&#9744;&nbsp;" title="待办">${icon("i-check")}</button>
        <span class="sep"></span>
        <button data-cmd="createLink" title="插入链接">${icon("i-arrow")}</button>
        <button data-cmd="insertHTML" data-value="⏱ " title="插入时间戳">${icon("i-clock")}</button>
      </div>
      <div class="note-editable" id="noteEditable" contenteditable="true">${mdToHtml(row.analysis || row.transcript || "")}</div>
      ${row.quick_summary ? `<div class="note-summary"><b>课堂小结：</b>${escapeHtml(row.quick_summary.slice(0, 300))}</div>` : ""}
      <div class="note-body-foot">
        <button class="btn text" data-note-delete>${icon("i-trash")}删除</button>
        <button class="btn line" data-note-export>${icon("i-download")}导出笔记</button>
        <button class="btn primary" data-note-save>${icon("i-sparkle")}保存修改</button>
      </div>`;
    $$(".note-toolbar button", container).forEach((btn) => btn.addEventListener("click", () => {
      const cmd = btn.dataset.cmd;
      let value = btn.dataset.value || null;
      if (cmd === "createLink") value = prompt("请输入链接地址", "https://") || null;
      if (!value && cmd !== "bold" && cmd !== "italic" && cmd !== "insertUnorderedList" && cmd !== "insertOrderedList") return;
      document.execCommand(cmd, false, value);
      $("#noteEditable").focus();
    }));
    container.querySelector("[data-note-save]")?.addEventListener("click", () => saveNote(row, container));
    container.querySelector("[data-note-export]")?.addEventListener("click", () => saveFile(`${(row.title || "note").replace(/[\\/:*?"<>|]/g, "_")}.md`, `# ${row.title}\n\n${$("#noteEditable").innerText}`));
    container.querySelector("[data-note-delete]")?.addEventListener("click", () => deleteRecord("notes", row.id));
    renderNotesSide(row, parsed);
  }
  async function saveNote(row, container) {
    const title = $("#noteTitle").value.trim() || row.title;
    const text = $("#noteEditable").innerText;
    const res = await apiPost("/api/workspace/files", {
      group: "notes", title, source_type: row.source_type || "live",
      transcript: row.transcript || "", translation: row.translation || "",
      timeline: row.timeline || [], quick_summary: row.quick_summary || "",
      analysis: text, analyze: false,
    });
    if (!res.ok) { showToast(res.message || "保存失败", true); return; }
    await apiDel(`/api/workspace/files/notes/${row.id}`);
    state.selected.notes = res.id;
    showToast("笔记已保存");
    await loadWorkspace();
    selectRecord("notes", res.id);
  }
  function renderNotesSide(row, parsed) {
    const box = $("#notesAiBody");
    const blocks = [];
    if (parsed.points.length) {
      blocks.push(`<div class="side-block lavender"><h4>${icon("i-sparkle")}核心要点</h4>
        <ol class="num-list">${parsed.points.map((p) => `<li><span>${escapeHtml(p)}</span></li>`).join("")}</ol></div>`);
    }
    if (parsed.keywords.length) {
      blocks.push(`<div class="side-block blue"><h4>${icon("i-list")}关键词</h4>
        <div class="chip-list">${parsed.keywords.map((k) => `<span>${escapeHtml(k)}</span>`).join("")}</div></div>`);
    }
    if (parsed.todos.length) {
      blocks.push(`<div class="side-block orange"><h4>${icon("i-check")}待办事项</h4>
        <div class="todo-list">${parsed.todos.map((t) => `<label><input type="checkbox" /><span>${escapeHtml(t.text || t)}</span></label>`).join("")}</div></div>`);
    }
    if (!blocks.length) {
      box.innerHTML = `<div class="empty">${icon("i-sparkle")}<b>暂无要点</b><small>${row.status === "analyzing" ? "深度思考模型正在后台整理，稍后回来查看。" : "重新整理后可生成核心要点、关键词和待办事项。"}</small></div>`;
      return;
    }
    box.innerHTML = blocks.join("");
  }

  /* ------------------------------ 会议整理 ------------------------------ */
  async function renderMeetingsDetail(id) {
    const container = $("#meetingsDetail");
    container.innerHTML = `<div class="empty big"><b>正在载入…</b></div>`;
    const row = await fetchRecord("meetings", id);
    if (!row) { container.innerHTML = `<div class="empty big">${icon("i-users")}<b>会议记录读取失败</b></div>`; return; }
    const parsed = parseAnalysis(row.analysis, "meetings");
    const statusChip = row.status === "analyzing" ? `<span class="chip busy">AI 整理中</span>`
      : row.status === "failed" ? `<span class="chip bad">整理失败</span>`
        : `<span class="chip ok">${icon("i-check")}已完成整理</span>`;
    $("#meetingsStateChip").textContent = row.status === "analyzing" ? "AI 整理中" : row.status === "failed" ? "整理失败" : "已完成整理";
    container.innerHTML = `
      <div class="detail-head">
        <div><h2>${escapeHtml(row.title || "未命名会议")}</h2>
          <div class="detail-meta">
            <span>${icon("i-calendar")}${escapeHtml(fmtDate(row.created))}</span>
            ${row.duration ? `<span>${icon("i-clock")}时长 ${fmtDur(row.duration)}</span>` : ""}
            <span>${icon("i-folder")}会议整理</span>
          </div>
        </div>
        <div class="detail-actions">${statusChip}
          <button class="btn line" data-meeting-export>${icon("i-download")}导出结果</button>
          <button class="btn danger" data-meeting-delete>${icon("i-trash")}删除</button>
        </div>
      </div>
      ${parsed.summary ? `<div class="side-block lavender" style="margin-bottom:14px"><h4>${icon("i-sparkle")}会议总结</h4><p style="font-size:13px;line-height:1.9">${escapeHtml(parsed.summary)}</p></div>` : ""}
      ${parsed.decisions.length ? `<div class="side-block green" style="margin-bottom:14px"><h4>${icon("i-check")}关键决策</h4>
        <ol class="num-list">${parsed.decisions.map((d) => `<li><span>${escapeHtml(d)}</span></li>`).join("")}</ol></div>` : ""}
      ${parsed.todos.length ? `<div class="side-block orange" style="margin-bottom:14px"><h4>${icon("i-clock")}待办事项</h4>
        <ol class="num-list">${parsed.todos.map((t) => `<li><span>${escapeHtml(t.text || t)}</span>${t.owner ? `<span class="owner">${escapeHtml(t.owner)}</span>` : ""}</li>`).join("")}</ol></div>` : ""}
      ${parsed.participants.length ? `<div class="side-block blue" style="margin-bottom:14px"><h4>${icon("i-users")}参与人任务</h4>
        <ul class="num-list" style="list-style:none">${parsed.participants.map((p) => `<li><span>${escapeHtml(p)}</span></li>`).join("")}</ul></div>` : ""}
      ${row.quick_summary ? `<div class="note-summary" style="margin:0"><b>实时重点：</b>${escapeHtml(row.quick_summary.slice(0, 400))}</div>` : ""}
      ${!parsed.summary && !parsed.decisions.length && !parsed.todos.length && !parsed.participants.length
        ? `<div class="empty big">${icon("i-sparkle")}<b>${row.status === "analyzing" ? "深度思考模型正在后台整理" : "还没有整理结果"}</b><small>点击「重新整理」把时间线、原文、译文交给深度思考模型处理。</small></div>` : ""}
      <div class="note-body-foot" style="margin:18px -28px -24px;border-radius:0">
        <button class="btn line" data-meeting-reanalyze>${icon("i-sparkle")}生成整理</button>
        <button class="btn line" data-meeting-export2>${icon("i-download")}导出结果</button>
      </div>`;
    container.querySelector("[data-meeting-export]")?.addEventListener("click", () => exportRecord(row));
    container.querySelector("[data-meeting-export2]")?.addEventListener("click", () => exportRecord(row));
    container.querySelector("[data-meeting-delete]")?.addEventListener("click", () => deleteRecord("meetings", row.id));
    container.querySelector("[data-meeting-reanalyze]")?.addEventListener("click", () => retryRecord("meetings", row.id));
  }

  /* ------------------------------ 分析结果解析 ------------------------------ */
  function parseAnalysis(markdown, kind) {
    const text = String(markdown || "").trim();
    const out = { summary: "", points: [], keywords: [], todos: [], decisions: [], participants: [] };
    if (!text) return out;
    const lines = text.split(/\r?\n/);
    let section = "";
    const push = (target, value) => { const v = cleanItem(value); if (v) out[target].push(v); };
    lines.forEach((raw) => {
      const line = raw.trim();
      if (!line) return;
      const heading = line.replace(/^#{1,6}\s*/, "").replace(/^\*\*(.+?)\*\*$/, "$1").replace(/^【(.+?)】$/, "$1").replace(/[：:]\s*$/, "");
      if (/^(#{1,6}\s|[【*])/.test(line) && heading.length <= 18 && !/[。，,；;]$/.test(heading)) {
        section = heading; return;
      }
      const isBullet = /^([-*•]|\d+[.)、])\s+/.test(line);
      const item = line.replace(/^[-*•]\s*/, "").replace(/^\d+[.)、]\s*/, "");
      if (/关键词|关键字/.test(section)) {
        cleanItem(item).split(/[、,，;；\s]+/).map((k) => k.trim()).filter((k) => k && k.length <= 12 && !out.keywords.includes(k))
          .forEach((k) => out.keywords.push(k));
        return;
      }
      if (/决策|结论/.test(section)) return push("decisions", item);
      if (/待办|行动|下一步|任务分配/.test(section)) {
        const m = item.split(/\s*[｜|]\s*/);
        const ownerMatch = item.match(/(\d{1,2}\s*月\s*\d{1,2}\s*日[^｜|]*|[^｜|]*负责)/);
        out.todos.push({ text: cleanItem(m[0]), owner: m[1] ? cleanItem(m.slice(1).join(" ")) : (ownerMatch ? cleanItem(ownerMatch[1]) : "") });
        return;
      }
      if (/参与人|负责人|分工/.test(section)) return push("participants", item);
      if (/摘要|总结|概述|简介/.test(section)) { out.summary += (out.summary ? "\n" : "") + item; return; }
      if (/重点|要点|核心|知识结构|结构|概念/.test(section)) return push("points", item);
      if (/复习|思考|作业/.test(section)) return push("todos", item);
      if (!section) {
        // 标题之前的内容：列表项算要点，整段散文是模型的开场说明
        if (isBullet) out.points.push(cleanItem(item));
        else out.summary += (out.summary ? "\n" : "") + item;
      }
    });
    if (!out.summary && kind === "meetings") {
      const first = text.split(/\n{2,}/).find((p) => p.length > 40);
      if (first) out.summary = first.replace(/[#*]/g, "").trim();
    }
    if (kind === "notes" && !out.points.length && !out.keywords.length) {
      out.points = text.split(/\n/).map(cleanItem).filter((l) => l.length > 4 && l.length < 90).slice(0, 6);
    }
    return out;
  }
  function cleanItem(value) {
    return String(value == null ? "" : value)
      .replace(/\*\*(.+?)\*\*/g, "$1").replace(/[*`]/g, "")
      .replace(/^[-•]\s*/, "").replace(/^\d+[.)、]\s*/, "")
      .replace(/^(定义|要点|例子|小结|重点|待复习)\s*[:：]\s*/, "")
      .replace(/^[：:、\s]+/, "")
      .replace(/[。；;]+$/, "")
      .trim();
  }

  /* ------------------------------ Markdown 渲染 ------------------------------ */
  function mdToHtml(markdown) {
    const text = String(markdown || "");
    if (!text.trim()) return "";
    const inline = (s) => escapeHtml(s)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`(.+?)`/g, "<code>$1</code>");
    const html = [];
    let list = null;
    const closeList = () => { if (list) { html.push(`</${list}>`); list = null; } };
    text.split(/\r?\n/).forEach((raw) => {
      const line = raw.trim();
      if (!line) { closeList(); return; }
      const heading = line.match(/^(#{1,6})\s+(.*)$/) || line.match(/^\*\*(.+?)\*\*$/);
      if (heading) { closeList(); html.push(`<h3>${inline(heading[2] || heading[1])}</h3>`); return; }
      const bracket = line.match(/^【(.+?)】\s*:?$/);
      if (bracket) { closeList(); html.push(`<h3>${inline(bracket[1])}</h3>`); return; }
      const ul = line.match(/^[-*•]\s+(.*)$/);
      if (ul) { if (list !== "ul") { closeList(); html.push("<ul>"); list = "ul"; } html.push(`<li>${inline(ul[1])}</li>`); return; }
      const ol = line.match(/^\d+[.)、]\s+(.*)$/);
      if (ol) { if (list !== "ol") { closeList(); html.push("<ol>"); list = "ol"; } html.push(`<li>${inline(ol[1])}</li>`); return; }
      closeList();
      html.push(`<p>${inline(line)}</p>`);
    });
    closeList();
    return html.join("");
  }

  /* ------------------------------ 设置 ------------------------------ */
  function openSettings() {
    $("#settingsOverlay").classList.remove("hidden");
    loadSettingsData();
    if ($(".settings-tab.active")?.dataset.pane === "microphone") startMicMonitor();
  }
  function closeOverlays() {
    stopMicMonitor();
    $("#settingsOverlay").classList.add("hidden");
    $("#stopModal").classList.add("hidden");
    $("#saveModal").classList.add("hidden");
    $("#detailModal").classList.add("hidden");
  }
  async function loadSettingsData() {
    const [ws, profiles, storage] = await Promise.all([
      apiGet("/api/workspace/settings"), apiGet("/api/profiles"), apiGet("/api/storage"),
    ]);
    if (ws && ws.ok !== false) {
      state.settings.language = ws.language || "zh-CN";
      state.settings.microphone = ws.microphone || "default";
      state.settings.models = ws.models || {};
      if (ws.models) {
        state.settings.realtime = !!ws.models.realtime;
        if (ws.models.sourceLang) state.settings.sourceLang = ws.models.sourceLang;
        if (ws.models.fileSourceLang) state.settings.fileSourceLang = ws.models.fileSourceLang;
        if (ws.models.targetLang) state.settings.targetLang = ws.models.targetLang;
        if (ws.models.summarySource) state.settings.summarySource = ws.models.summarySource;
        if (ws.models.analysisOutput) state.settings.analysisOutput = ws.models.analysisOutput;
      }
    }
    if (profiles && profiles.ok) {
      state.profiles = {
        mt: profiles.mt || [], main: profiles.main || [], light: profiles.light || [],
        mt_active: profiles.mt_active || "", main_active: profiles.main_active || "",
        light_active: profiles.light_active || "", mt_engine: profiles.mt_engine || "auto",
        live_model: profiles.live_model || "",
      };
    }
    if (storage && storage.ok) state.storage = { recordings_dir: storage.recordings_dir || "", archives_dir: storage.archives_dir || "" };
    fillAllLangSelects();
    applySourceSeg();
    applyOutputSeg();
    const outputMode = $("#fileOutputMode");
    if (outputMode) outputMode.value = state.settings.analysisOutput;
    $("#uiLanguage").value = state.settings.language;
    $("#realtimeModeToggle").checked = !!state.settings.realtime;
    renderStoragePane();
    renderModelPanels();
    updateMicrophoneLists();
  }
  function renderStoragePane() {
    $("#storageRoot").value = state.storage.archives_dir || "";
    const rec = $("#recordingsRoot");
    if (rec) rec.value = state.storage.recordings_dir || "";
    renderFolderPreview();
  }
  function renderFolderPreview() {
    const root = ($("#storageRoot").value || "").trim();
    const join = (base, sub) => (base ? `${base.replace(/\/$/, "")}/${sub}` : "—");
    $("#defaultFolderPath").textContent = join(root, "default");
    $("#notesFolderPath").textContent = join(root, "notes");
    $("#meetingsFolderPath").textContent = join(root, "meetings");
  }
  function profileOf(key) {
    const list = state.profiles[key] || [];
    const active = state.profiles[key === "main" ? "main_active" : key === "mt" ? "mt_active" : "light_active"];
    return list.find((p) => p.name === active) || list[0] || { name: "", base_url: "", model: "", api_key: "", has_key: false };
  }
  function providerOf(baseUrl) {
    const hit = PROVIDERS.find((p) => p.base && baseUrl && baseUrl.startsWith(p.base.replace(/\/$/, "")));
    return hit ? hit.id : (baseUrl ? "custom" : "deepseek");
  }
  function renderModelPanels() {
    const box = $("#modelPanels");
    box.innerHTML = MODELS.map((meta) => {
      const profile = profileOf(meta.key);
      const enabledKey = `${meta.key}Enabled`;
      const enabled = state.settings.models[enabledKey] !== false;
      const provider = providerOf(profile.base_url);
      const hasKey = !!(profile.has_key || profile.api_key);
      const statusText = profile.base_url && profile.model
        ? (hasKey ? "已配置 · 未测试" : "缺少 API Key")
        : "未配置";
      return `
      <div class="model-panel ${meta.tone}" data-model="${meta.key}">
        <div class="model-top">
          <span class="model-avatar">${icon(meta.icon)}</span>
          <div class="model-title">
            <div class="tline"><b>${meta.name}</b><em class="role-tag">${meta.tag}</em></div>
            <small>${meta.desc}</small>
            <small class="sub">${meta.sub}</small>
          </div>
          <div class="model-enable">
            <label class="toggle bare"><input type="checkbox" data-enable="${meta.key}" ${enabled ? "checked" : ""} /><i></i></label>
            <span>${meta.enableLabel}</span>
          </div>
        </div>
        <div class="model-grid">
          <div class="field"><label>模型服务商</label>
            <div class="select-box"><select data-field="provider" data-model="${meta.key}">
              ${PROVIDERS.map((p) => `<option value="${p.id}" ${p.id === provider ? "selected" : ""}>${p.name}</option>`).join("")}
            </select>${icon("i-chevron", "caret")}</div>
          </div>
          <div class="field"><label>模型名称</label><input data-field="model" data-model="${meta.key}" value="${escapeHtml(profile.model || "")}" placeholder="例如 deepseek-chat" /></div>
          <div class="field"><label>API 地址</label><input data-field="base_url" data-model="${meta.key}" value="${escapeHtml(profile.base_url || "")}" placeholder="https://api.deepseek.com/v1" /></div>
          <div class="field"><label>API Key</label>
            <div class="key-wrap"><input type="password" data-field="api_key" data-model="${meta.key}" value="" placeholder="${hasKey ? "已保存，留空保持不变" : "请输入 API Key"}" />
            <button type="button" data-eye>${icon("i-key")}</button></div>
          </div>
          ${meta.key === "mt" ? `
          <div class="live-model-row">
            <div class="field"><label>实时同传模型</label>
              <input data-field="live_model" value="${escapeHtml(state.profiles.live_model || "qwen3.5-livetranslate-flash-realtime")}" placeholder="qwen3.5-livetranslate-flash-realtime" />
            </div>
            <p class="field-help">录音时打开「实时同传模式」走的是百炼专用 WebSocket 接口，<b>与上面这个 API Key 共用</b>（所以这里的 Key 必须是百炼的）。关掉同传开关时、以及文件转写，用的仍是上面填的模型。<br>
              推荐 <code>qwen3.5-livetranslate-flash-realtime</code>（久经验证）或 <code>qwen3.8-livetranslate-flash-realtime</code>（更新，标点与大小写更规范），两者价格相同。换别的名字前建议先确认服务端支持。</p>
          </div>` : ""}
          ${meta.hasLang ? `<div class="lang-row">
            <div class="field"><label>默认原文语言</label><div class="select-box"><select data-field="src_lang">${LANGS.map((l) => `<option value="${l.code}" ${l.code === state.settings.sourceLang ? "selected" : ""}>${l.flag} ${l.name}</option>`).join("")}</select>${icon("i-chevron", "caret")}</div></div>
            <div class="field"><label>目标语言</label><div class="select-box"><select data-field="tgt_lang">${LANGS.map((l) => `<option value="${l.code}" ${l.code === state.settings.targetLang ? "selected" : ""}>${l.flag} ${l.name}</option>`).join("")}</select>${icon("i-chevron", "caret")}</div></div>
          </div>` : ""}
        </div>
        <div class="model-foot">
          <div class="foot-left">
            ${meta.thinking ? `<span class="mini-label">思考强度</span>
            <div class="select-box mini"><select data-field="thinking" data-model="${meta.key}" title="${THINK_HINT}">
              <option value="off"${(profile.thinking || "") === "off" ? " selected" : ""}>关闭思考 · 最快</option>
              <option value=""${!profile.thinking ? " selected" : ""}>标准</option>
              <option value="deep"${profile.thinking === "deep" ? " selected" : ""}>深度思考 · 最仔细</option>
            </select>${icon("i-chevron", "caret")}</div>` : ""}
            <span class="model-status" data-status="${meta.key}"><i></i>${statusText}</span>
          </div>
          <button class="btn text" data-test="${meta.key}">测试连接</button>
        </div>
      </div>`;
    }).join("");

    $$("[data-eye]", box).forEach((btn) => btn.addEventListener("click", () => {
      const input = btn.parentElement.querySelector("input");
      input.type = input.type === "password" ? "text" : "password";
    }));
    $$("[data-field='provider']", box).forEach((sel) => sel.addEventListener("change", () => {
      const key = sel.dataset.model;
      const base = (PROVIDERS.find((p) => p.id === sel.value) || {}).base;
      if (base) $(`[data-field='base_url'][data-model='${key}']`).value = base;
    }));
    $$("[data-test]", box).forEach((btn) => btn.addEventListener("click", () => testModel(btn.dataset.test)));
  }
  function collectProfiles() {
    const out = { mt: [], main: [], light: [], mt_active: "", main_active: "", light_active: "", mt_engine: state.profiles.mt_engine || "auto" };
    MODELS.forEach((meta) => {
      const field = (name) => { const el = $(`[data-field='${name}'][data-model='${meta.key}']`); return el ? el.value.trim() : ""; };
      const name = field("model") || profileOf(meta.key).name || `${meta.key}-default`;
      const profile = { name, base_url: field("base_url"), api_key: field("api_key"),
                        model: field("model"), thinking: field("thinking") };
      out[meta.key].push(profile);
      out[meta.key === "main" ? "main_active" : meta.key === "mt" ? "mt_active" : "light_active"] = name;
    });
    const liveInput = $("[data-field='live_model']");
    out.live_model = liveInput ? liveInput.value.trim() : "";
    const src = $("[data-field='src_lang']");
    const tgt = $("[data-field='tgt_lang']");
    if (src) out.src_lang = src.value;
    if (tgt) out.tgt_lang = tgt.value;
    return out;
  }
  async function saveSettings() {
    const profiles = collectProfiles();
    // 必须和已有设置合并：直接覆盖会把 fileSourceLang / summarySource / analysisOutput 抹掉
    const models = {
      ...state.settings.models,
      realtime: $("#realtimeModeToggle").checked,
      mainEnabled: $("[data-enable='main']")?.checked !== false,
      lightEnabled: $("[data-enable='light']")?.checked !== false,
      mtEnabled: $("[data-enable='mt']")?.checked !== false,
      sourceLang: profiles.src_lang || $("#defaultSourceLang").value,
      targetLang: profiles.tgt_lang || $("#defaultTargetLang").value,
      fileSourceLang: state.settings.fileSourceLang,
      summarySource: state.settings.summarySource,
      analysisOutput: state.settings.analysisOutput,
    };
    const payload = {
      mt: profiles.mt, main: profiles.main, light: profiles.light,
      mt_active: profiles.mt_active, main_active: profiles.main_active, light_active: profiles.light_active,
      mt_engine: profiles.mt_engine,
      live_model: profiles.live_model,
    };
    const [p1] = await Promise.all([
      apiPost("/api/profiles", payload),
      apiPost("/api/workspace/settings", { language: $("#uiLanguage").value, microphone: $("#settingsMicrophone").value || "default", models }),
      apiPost("/api/storage", {
        recordings_dir: ($("#recordingsRoot")?.value || "").trim() || state.storage.recordings_dir,
        archives_dir: $("#storageRoot").value.trim() || state.storage.archives_dir,
      }),
    ]);
    if (!p1.ok) { showToast(p1.message || "保存失败", true); return; }
    state.settings.language = $("#uiLanguage").value;
    state.settings.microphone = $("#settingsMicrophone").value;
    state.settings.realtime = models.realtime;
    state.settings.sourceLang = models.sourceLang;
    state.settings.targetLang = models.targetLang;
    state.settings.models = { ...state.settings.models, ...models };
    fillAllLangSelects();
    await loadSettingsData();
    await loadWorkspace();   // 目录换了，最近文件/仓库要重新读
    showToast("设置已保存并生效");
    closeOverlays();
  }
  async function testModel(key) {
    const status = $(`[data-status='${key}']`);
    if (status) { status.className = "model-status"; status.innerHTML = `<i></i>测试中…`; }
    const endpoint = key === "main" ? "/api/orchestrator/check_main" : key === "light" ? "/api/orchestrator/check_light" : "/api/orchestrator/check";
    const res = await apiPost(endpoint, {});
    const ok = !!(res && res.ok);
    if (status) {
      status.className = `model-status ${ok ? "ok" : "bad"}`;
      status.innerHTML = `<i></i>${res && res.message ? res.message : ok ? "连接正常" : "连接失败"}`;
    }
    showToast(res && res.message ? res.message : ok ? "连接正常" : "连接失败", !ok);
  }
  function updateMicrophoneLists() {
    const fill = (select) => {
      if (!select) return;
      const current = select.value;
      select.innerHTML = `<option value="default">系统默认麦克风</option>`;
      if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
        navigator.mediaDevices.enumerateDevices().then((devices) => {
          devices.filter((d) => d.kind === "audioinput").forEach((d, i) => {
            const opt = document.createElement("option");
            opt.value = d.label || `麦克风 ${i + 1}`;
            opt.textContent = d.label || `麦克风 ${i + 1}`;
            select.appendChild(opt);
          });
          if (current) select.value = current;
        }).catch(() => {});
      }
    };
    fill($("#liveMicrophone"));
    fill($("#settingsMicrophone"));
  }
  async function checkPermission() {
    const box = $("#permissionBox");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
      box.classList.remove("warn");
      $("#permissionTitle").textContent = "麦克风权限已授权";
      $("#permissionHint").textContent = "可以开始实时翻译了。";
      showToast("麦克风可用");
    } catch (err) {
      box.classList.add("warn");
      $("#permissionTitle").textContent = "麦克风权限未授权";
      $("#permissionHint").textContent = "请在「系统设置 → 隐私与安全性 → 麦克风」中允许本应用，然后重新检查。";
      showToast("未获得麦克风权限", true);
    }
  }
  async function pickFolder(which) {
    const res = await apiPost("/api/storage/pick", {});
    if (res && res.ok && res.path) {
      if (which === "recordings" && $("#recordingsRoot")) {
        $("#recordingsRoot").value = res.path;
      } else {
        $("#storageRoot").value = res.path;
        renderFolderPreview();   // 三个分组路径即时跟着变，不用等保存
      }
      showToast(`已选择：${res.path}`);
    } else if (res && res.cancelled) {
      showToast("已取消选择");
    } else {
      showToast(res.message || "无法打开文件夹选择器（系统可能未授权「文件与文件夹」访问）", true);
    }
  }
  function micDeviceLabel() {
    const sel = $("#settingsMicrophone");
    if (!sel || !sel.selectedOptions.length) return "default";
    return sel.selectedOptions[0].textContent.trim();
  }
  function paintMeter(rms) {
    const fill = $("#micMeterFill");
    if (!fill) return;
    const pct = Math.min(100, Math.round(Math.sqrt(Math.max(0, Number(rms) || 0)) * 260));
    fill.style.width = `${pct}%`;
    return pct;
  }
  async function startMicMonitor() {
    stopMicMonitor();
    const box = $("#permissionBox");
    const res = await apiPost("/api/capture/monitor", { device: micDeviceLabel() });
    if (!res.ok) {
      box.classList.add("warn");
      $("#permissionTitle").textContent = "麦克风打不开";
      $("#permissionHint").textContent = res.message || "请检查系统权限或换一个输入设备。";
      return;
    }
    state.monitorTimer = setInterval(async () => {
      const s = await apiGet("/api/capture/monitor");
      if (!s || !s.ok) return;
      if (s.error) {
        box.classList.add("warn");
        $("#permissionTitle").textContent = "麦克风打不开";
        $("#permissionHint").textContent = s.error;
        return;
      }
      const pct = paintMeter(s.rms);
      box.classList.remove("warn");
      $("#permissionTitle").textContent = "麦克风正在工作";
      $("#permissionHint").textContent = (pct || 0) > 2
        ? "正在接收声音，音量条会跟着你说话变化。"
        : "已打开麦克风，说句话试试音量条会不会动。";
    }, 150);
  }
  function stopMicMonitor() {
    if (state.monitorTimer) {
      clearInterval(state.monitorTimer);
      state.monitorTimer = null;
    }
    paintMeter(0);
    apiPost("/api/capture/monitor/stop", {});
  }
  /* ------------------------- 关于 / 更新 ------------------------- */
  const UPDATE_POLL = { id: null };
  let updateInfo = null;

  const fmtMB = (bytes) => `${(Number(bytes) / 1048576).toFixed(1)} MB`;

  function paintUpdate(s) {
    const box = $("#updateBox");
    if (!box) return;
    const percent = Math.max(0, Math.min(100, Number(s.percent) || 0));
    if (s.state === "downloading") {
      box.innerHTML = `
        <div class="update-state">
          <div class="row"><b>正在下载 v${escapeHtml(s.version || "")}</b><span>${percent.toFixed(1)}%</span></div>
          <div class="progress-wrap">
            <div class="progress-bar"><span style="width:${percent}%"></span></div>
            <div class="progress-meta">
              <span>${fmtMB(s.received)}${s.total ? ` / ${fmtMB(s.total)}` : ""}</span>
              <span>${s.speed ? fmtMB(s.speed) + "/s" : "…"}</span>
            </div>
          </div>
        </div>`;
      return;
    }
    if (s.state === "ready") {
      box.innerHTML = `
        <div class="update-state ok">
          <div class="row">
            <div><b>v${escapeHtml(s.version || "")} 下载完成</b><br><small>${escapeHtml(s.filename || "")}</small></div>
            <button class="btn primary" id="installUpdateButton">${icon("i-download")}重启并安装</button>
          </div>
        </div>`;
      $("#installUpdateButton")?.addEventListener("click", installUpdate);
      return;
    }
    if (s.state === "installing") {
      box.innerHTML = `<div class="update-state ok"><b>正在安装…</b><br><small>应用会自动退出并重新打开，请稍候。</small></div>`;
      return;
    }
    if (s.state === "failed") {
      box.innerHTML = `<div class="update-state bad"><b>下载失败</b><br><small>${escapeHtml(s.error || "")}</small>
        <div style="margin-top:10px"><button class="btn line" id="retryDownloadButton">重试</button></div></div>`;
      $("#retryDownloadButton")?.addEventListener("click", () => startUpdateDownload(updateInfo));
      return;
    }
    box.innerHTML = "";
  }

  async function pollUpdateStatus() {
    const s = await apiGet("/api/update/status");
    if (!s || !s.ok) return;
    if (s.state !== "downloading" && UPDATE_POLL.id) {
      clearInterval(UPDATE_POLL.id);
      UPDATE_POLL.id = null;
      if (s.state === "ready") showToast("下载完成，可以重启安装了");
      if (s.state === "failed") showToast(`下载失败：${s.error || ""}`, true);
    }
    paintUpdate(s);
  }

  function startUpdatePolling() {
    if (UPDATE_POLL.id) return;
    UPDATE_POLL.id = setInterval(pollUpdateStatus, 500);
  }

  async function checkUpdate(manual = true) {
    const btn = $("#checkUpdateButton");
    if (btn) { btn.disabled = true; btn.textContent = "检查中…"; }
    const res = await apiGet("/api/update/check");
    if (btn) { btn.disabled = false; btn.innerHTML = `${icon("i-swap")}检查更新`; }
    if (!res || !res.ok) {
      if (manual) showToast(res && res.message ? res.message : "检查更新失败", true);
      $("#updateBox").innerHTML = `<div class="update-state bad">${escapeHtml((res && res.message) || "检查更新失败")}</div>`;
      return;
    }
    updateInfo = res;
    if ($("#aboutVersion")) $("#aboutVersion").textContent = `v${res.current || ""}`;
    const hint = $("#aboutFeedHint");
    if (hint) hint.textContent = res.configured ? "" : "（未配置更新源，无法接收新版本）";
    if (!res.update_available) {
      $("#updateBox").innerHTML = `<div class="update-state ok"><b>${icon("i-check")} 已是最新版本</b>
        <br><small>当前 v${escapeHtml(res.current || "")}${res.latest ? ` · 线上最新 v${escapeHtml(res.latest)}` : ""}</small></div>`;
      return;
    }
    $("#updateBox").innerHTML = `
      <div class="update-state">
        <div class="row">
          <div><b>发现新版本 v${escapeHtml(res.latest || "")}</b><br>
            <small>当前 v${escapeHtml(res.current || "")}${res.size ? ` · 安装包约 ${fmtMB(res.size)}` : ""}</small></div>
          <button class="btn primary" id="downloadUpdateButton">${icon("i-download")}下载更新</button>
        </div>
      </div>
      ${res.notes ? `<div class="update-note">${escapeHtml(res.notes)}</div>` : ""}`;
    $("#downloadUpdateButton")?.addEventListener("click", () => startUpdateDownload(res));
    if (manual) showToast(res.message || "已检查");
  }

  async function startUpdateDownload(info) {
    if (!info || !info.download_url) { showToast("没有可用的下载地址", true); return; }
    const res = await apiPost("/api/update/download", { url: info.download_url, version: info.latest || "" });
    if (!res || !res.ok) { showToast((res && res.message) || "开始下载失败", true); return; }
    paintUpdate({ state: "downloading", percent: 0, received: 0, total: info.size || 0, version: info.latest });
    startUpdatePolling();
    showToast("已开始下载更新");
  }

  async function installUpdate() {
    if (!confirm("现在安装更新？应用会自动退出并重新打开。")) return;
    const res = await apiPost("/api/update/install", {});
    if (!res || !res.ok) { showToast((res && res.message) || "安装失败", true); return; }
    showToast("正在安装，应用即将重启…");
    paintUpdate({ state: "installing" });
    setTimeout(() => apiPost("/api/app/quit", {}), 1200);
  }

  async function loadAbout() {
    const h = state.health || await apiGet("/api/health");
    state.health = h;
    if (h && h.version && $("#aboutVersion")) $("#aboutVersion").textContent = `v${h.version}`;
    await pollUpdateStatus();   // 打开设置时同步一次下载状态
  }

  function bindSettings() {
    $$(".settings-tab").forEach((tab) => tab.addEventListener("click", () => {
      $$(".settings-tab").forEach((t) => t.classList.toggle("active", t === tab));
      $$(".set-pane").forEach((p) => p.classList.toggle("active", p.id === `pane-${tab.dataset.pane}`));
      const scroller = $(".settings-scroll");
      if (scroller) scroller.scrollTop = 0;   // 换面板要回到顶部，否则短面板会顶出一片空白
      if (tab.dataset.pane === "microphone") startMicMonitor();
      else stopMicMonitor();
      if (tab.dataset.pane === "about") loadAbout();
    }));
    $("#settingsCloseButton").addEventListener("click", closeOverlays);
    $("#settingsCancelButton").addEventListener("click", closeOverlays);
    $("#settingsSaveButton").addEventListener("click", saveSettings);
    $("#testModelsButton").addEventListener("click", async () => {
      for (const meta of MODELS) await testModel(meta.key);
    });
    $("#checkPermissionButton").addEventListener("click", checkPermission);
    $("#checkUpdateButton")?.addEventListener("click", () => checkUpdate(true));
    $("#settingsMicrophone").addEventListener("change", () => {
      if ($(".settings-tab.active")?.dataset.pane === "microphone") startMicMonitor();
    });
    $("#storageRoot").addEventListener("input", renderFolderPreview);
    $("#chooseStorageButton").addEventListener("click", () => pickFolder("archives"));
    $("#chooseRecordingsButton")?.addEventListener("click", () => pickFolder("recordings"));
    $("#restoreStorageButton").addEventListener("click", () => {
      $("#storageRoot").value = "~/Library/Application Support/intrealtimetranslate/archives";
      if ($("#recordingsRoot")) $("#recordingsRoot").value = "~/Documents/intrealtimetranslate-recordings";
      renderFolderPreview();
      showToast("已恢复默认位置，保存后生效");
    });
    $("#settingsOverlay").addEventListener("click", (e) => { if (e.target.id === "settingsOverlay") closeOverlays(); });
  }

  /* ------------------------------ 模态与实时翻译事件 ------------------------------ */
  function bindLive() {
    $$(".mode-card").forEach((card) => card.addEventListener("click", () => {
      if (state.capture.active) { showToast("录制中无法切换模式，请先结束录制", true); return; }
      setMode(card.dataset.mode);
    }));
    $("#liveMainButton").addEventListener("click", startLive);
    $$("#summarySourceSeg button").forEach((btn) => btn.addEventListener("click", () => setSummarySource(btn.dataset.src)));
    $$("#saveOutputSeg button").forEach((btn) => btn.addEventListener("click", () => setAnalysisOutput(btn.dataset.mode)));
    $("#liveStopButton").addEventListener("click", () => stopLive(false));
    $("#livePauseButton").addEventListener("click", togglePause);
    $("#swapLangButton").addEventListener("click", () => {
      const src = $("#liveSrcLang"), tgt = $("#liveTgtLang");
      const a = src.value; src.value = tgt.value; tgt.value = a;
      updateLangLabels();
    });
    $("#liveSrcLang").addEventListener("change", updateLangLabels);
    $("#liveTgtLang").addEventListener("change", updateLangLabels);
    $("#liveClearButton").addEventListener("click", () => {
      state.live.items = [];
      state.capture.startedAt = 0;
      resetCoachPanel();
      renderLiveItems();
      refreshStopAvailability();
      showToast("已清空当前内容");
    });
    $("#liveCopyButton").addEventListener("click", async () => {
      const text = state.live.items.map((it) => `${fmtClock(it.start || 0)}  ${it.ko || it.text || ""}\n      ${it.zh || ""}`).join("\n");
      if (!text) { showToast("暂无可复制内容", true); return; }
      try { await navigator.clipboard.writeText(text); showToast("已复制到剪贴板"); }
      catch { showToast("复制失败，请手动选择", true); }
    });
    $("#liveExportButton").addEventListener("click", () => {
      if (!state.live.items.length) { showToast("暂无可导出内容", true); return; }
      const text = state.live.items.map((it) => `[${fmtClock(it.start || 0)}] ${it.ko || it.text || ""}\n${it.zh || ""}`).join("\n\n");
      saveFile(`实时翻译_${nowStamp().replace(/[: ]/g, "-")}.txt`, text);
    });
    $("#liveKeyboardButton").addEventListener("click", () => {
      const text = prompt("输入要翻译的原文");
      if (!text || !text.trim()) return;
      if (!state.capture.startedAt) state.capture.startedAt = Date.now();
      const start = state.live.items.length ? (state.live.items[state.live.items.length - 1].end || 0) : 0;
      state.live.items.push({ ko: text.trim(), zh: "", start, end: start, partial: true });
      renderLiveItems();
      refreshStopAvailability();
      translateTyped(text.trim(), state.live.items.length - 1, start);
    });
    $("#cancelStopButton").addEventListener("click", () => $("#stopModal").classList.add("hidden"));
    $("#confirmStopButton").addEventListener("click", () => stopLive(true));
    $("#saveTitle").addEventListener("input", (e) => { $("#saveTitleCount").textContent = `${e.target.value.length}/20`; });
    $("#closeSaveModal").addEventListener("click", () => $("#saveModal").classList.add("hidden"));
    $("#cancelSaveButton").addEventListener("click", () => $("#saveModal").classList.add("hidden"));
    $("#confirmSaveButton").addEventListener("click", confirmSave);
    $("#closeDetailModal").addEventListener("click", () => $("#detailModal").classList.add("hidden"));
    $("#detailModal").addEventListener("click", (e) => { if (e.target.id === "detailModal") $("#detailModal").classList.add("hidden"); });
    $("#homeRefreshButton").addEventListener("click", async () => { await checkHealth(); await loadWorkspace(); showToast("状态已刷新"); });
    $("#homeGroupFilter").addEventListener("change", renderRecent);
    $$(".repo-tools input").forEach((input) => input.addEventListener("input", () => {
      const group = input.id.replace("Search", "");
      state.filter[group] = input.value;
      renderRepo(group);
    }));
    ["default", "notes", "meetings"].forEach((group) => {
      const sortEl = $(`#${group}Sort`);
      sortEl?.addEventListener("change", () => { state.sort[group] = sortEl.value; renderRepo(group); });
      $(`#${group}DirButton`)?.addEventListener("click", () => {
        state.sort[group] = state.sort[group] === "new" ? "old" : "new";
        if (sortEl) sortEl.value = state.sort[group];
        renderRepo(group);
      });
    });
    $("#meetingsReanalyzeButton").addEventListener("click", () => {
      const id = state.selected.meetings;
      if (!id) { showToast("请先在左侧选择一场会议", true); return; }
      retryRecord("meetings", id);
    });
    document.addEventListener("visibilitychange", () => { if (!document.hidden) { loadTasks(); loadWorkspace(); } });
  }
  async function translateTyped(text, index, start) {
    const res = await apiPost("/api/translate", { texts: [text], src: $("#liveSrcLang").value, tgt: $("#liveTgtLang").value });
    const out = res && res.translations && res.translations[0];
    if (out && state.live.items[index]) {
      state.live.items[index].zh = out;
      state.live.items[index].partial = false;
      renderLiveItems();
    }
  }
  function updateLangLabels() {
    $("#originalLangLabel").textContent = langName($("#liveSrcLang").value);
    $("#targetLangLabel").textContent = langName($("#liveTgtLang").value);
  }

  /* ------------------------------ 启动 ------------------------------ */
  async function boot() {
    bindNavigation();
    bindLive();
    bindTranscribe();
    bindSettings();
    switchPage("home");
    setMode("default");
    updateLangLabels();
    paintWave();
    $("#homeDate").textContent = todayText();
    $("#liveDate").textContent = todayText();
    $("#transcribeDate").textContent = todayText();
    fillAllLangSelects();
    updateLangLabels();
    await checkHealth();
    await loadSettingsData();
    await loadWorkspace();
    await loadTasks();
    setInterval(checkHealth, 30000);
  }
  boot();
})();
