/* 出行建议官 · 前端逻辑（原生 JS，无构建步骤） */

/* 本地同源部署时为空；GitHub Pages 由 config.js 注入 Render 后端地址 */
const API_BASE = (window.TRAVEL_ADVISOR_API_BASE || "").replace(/\/+$/, "");

const state = {
  modes: [],
  modeId: null,
  selectedCity: null,
  suggestions: [],
  suggestionIndex: -1,
  loading: false,
  lastPayload: null,
};

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
};

const $ = (selector) => document.querySelector(selector);

function todayISO() {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  return new Date(now.getTime() - offset * 60000).toISOString().slice(0, 10);
}

function addDaysISO(iso, days) {
  const date = new Date(iso + "T00:00:00");
  date.setDate(date.getDate() + days);
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60000).toISOString().slice(0, 10);
}

function nextSaturdayISO() {
  const now = new Date();
  const delta = (6 - now.getDay() + 7) % 7 || 7;
  const target = new Date(now.getTime() + delta * 86400000);
  const offset = target.getTimezoneOffset();
  return new Date(target.getTime() - offset * 60000).toISOString().slice(0, 10);
}

async function api(path, options) {
  const response = await fetch(API_BASE + path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    const message = typeof detail === "string" ? detail : JSON.stringify(detail || data);
    throw new Error(message || `请求失败（${response.status}）`);
  }
  return data;
}

/* ---------- 初始化 ---------- */

async function init() {
  $("#dateInput").value = todayISO();
  bindForm();
  bindCityInput();
  bindExamples();

  if (!API_BASE && /\.github\.io$/i.test(window.location.hostname)) {
    showError(
      "当前是 GitHub Pages 静态前端，后端 API 尚未配置：请先在 Render 部署服务，再把地址写入仓库变量 TRAVEL_API_BASE，然后重新运行 Pages 工作流。"
    );
    return;
  }

  await Promise.all([loadModes(), loadHealth()]);
  await applyDeepLink();
}

/* 支持 /?city=上海&date=2026-12-24&mode=travel 直接出结果，方便分享 */
async function applyDeepLink() {
  const params = new URLSearchParams(window.location.search);
  const city = (params.get("city") || "").trim();
  const day = (params.get("date") || "").trim();
  const mode = (params.get("mode") || "").trim();
  if (!city || !day || !mode) return;
  if (!state.modes.some((item) => item.id === mode)) return;

  $("#cityInput").value = city;
  $("#dateInput").value = day;
  selectMode(mode);
  await submitAdvice({ city, date: day, mode, options: readOptions() });
}

async function loadModes() {
  try {
    const data = await api("/api/modes");
    state.modes = data.modes || [];
    renderModeChips();
    if (state.modes.length) {
      selectMode(state.modes[0].id);
    }
  } catch (error) {
    showError(`无法加载出行模式：${error.message}`);
  }
}

async function loadHealth() {
  try {
    const data = await api("/api/health");
    const enabled = data.llm && data.llm.enabled;
    $("#statusDot").classList.toggle("off", !enabled);
    $("#statusText").textContent = enabled ? "大模型已连接" : "纯规则模式";
    $("#footLlm").textContent = enabled
      ? `大模型润色：${data.llm.model}`
      : "大模型润色：未配置（纯规则）";
    if (!enabled) {
      $("#llmNote").textContent = "（当前未配置 Key，自动使用纯规则）";
    }
  } catch (error) {
    $("#statusText").textContent = "服务未连接";
    $("#statusDot").classList.add("off");
  }
}

/* ---------- 模式与选项 ---------- */

function renderModeChips() {
  const container = $("#modeChips");
  container.replaceChildren();
  for (const mode of state.modes) {
    const button = el("button", "chip", null);
    button.type = "button";
    button.dataset.mode = mode.id;
    button.setAttribute("role", "radio");
    const icon = el("span", null, mode.icon || "•");
    button.append(icon, document.createTextNode(mode.name));
    button.addEventListener("click", () => selectMode(mode.id));
    container.append(button);
  }
}

function currentMode() {
  return state.modes.find((mode) => mode.id === state.modeId) || null;
}

function selectMode(modeId) {
  state.modeId = modeId;
  document.querySelectorAll("#modeChips .chip").forEach((chip) => {
    const active = chip.dataset.mode === modeId;
    chip.classList.toggle("selected", active);
    chip.setAttribute("aria-checked", active ? "true" : "false");
  });
  renderModeOptions(currentMode());
}

function renderModeOptions(mode) {
  const container = $("#modeOptions");
  container.replaceChildren();
  if (!mode || !mode.options || !mode.options.length) return;

  for (const option of mode.options) {
    const row = el("div", "option-row");
    const label = el("span", "label", option.label);
    row.append(label);

    if (option.type === "time") {
      const input = el("input");
      input.type = "time";
      input.value = option.default || "08:00";
      input.dataset.option = option.key;
      row.append(input);
    } else if (option.type === "number") {
      const input = el("input");
      input.type = "number";
      input.min = option.min ?? 1;
      input.max = option.max ?? 10;
      input.value = option.default ?? 2;
      input.dataset.option = option.key;
      row.append(input);
    } else if (option.type === "select") {
      const select = el("select");
      select.dataset.option = option.key;
      for (const choice of option.choices || []) {
        const item = el("option", null, choice.label);
        item.value = choice.value;
        if (choice.value === option.default) item.selected = true;
        select.append(item);
      }
      row.append(select);
    } else if (option.type === "multi") {
      const grid = el("div", "option-grid");
      for (const choice of option.choices || []) {
        const pill = el("button", "option-pill", choice.label);
        pill.type = "button";
        pill.dataset.value = choice.value;
        pill.addEventListener("click", () => pill.classList.toggle("selected"));
        grid.append(pill);
      }
      row.append(grid);
    }
    container.append(row);
  }
}

function readOptions() {
  const mode = currentMode();
  const options = {};
  if (!mode || !mode.options) return options;

  for (const spec of mode.options) {
    const container = $("#modeOptions");
    if (spec.type === "multi") {
      options[spec.key] = [...container.querySelectorAll(".option-pill.selected")].map((pill) => pill.dataset.value);
      continue;
    }
    const input = container.querySelector(`[data-option="${spec.key}"]`);
    if (!input) continue;
    if (spec.type === "number") {
      options[spec.key] = Number(input.value) || spec.default;
    } else {
      options[spec.key] = input.value;
    }
  }
  return options;
}

/* ---------- 城市联想 ---------- */

function bindCityInput() {
  const input = $("#cityInput");
  const panel = $("#citySuggest");
  let timer = null;

  const close = () => {
    panel.hidden = true;
    state.suggestionIndex = -1;
  };

  const render = (cities) => {
    panel.replaceChildren();
    state.suggestions = cities;
    state.suggestionIndex = -1;
    if (!cities.length) {
      panel.hidden = true;
      return;
    }
    cities.forEach((city, index) => {
      const button = el("button", null);
      button.type = "button";
      button.dataset.index = String(index);
      const name = el("span", null, city.name);
      const meta = el("span", "city-province", city.province || "");
      button.append(name, meta);
      button.addEventListener("mousedown", (event) => {
        event.preventDefault();
        chooseCity(city);
      });
      panel.append(button);
    });
    panel.hidden = false;
  };

  const chooseCity = (city) => {
    input.value = city.name;
    state.selectedCity = city;
    $("#cityHint").textContent = `${city.province || ""}${city.province ? " · " : ""}${city.tags.join(" · ")}`;
    close();
  };

  input.addEventListener("input", () => {
    state.selectedCity = null;
    $("#cityHint").textContent = "支持 30 个主要城市，可输入中文、拼音或简称";
    clearTimeout(timer);
    const value = input.value.trim();
    if (!value) {
      close();
      return;
    }
    timer = setTimeout(async () => {
      try {
        const data = await api(`/api/cities?q=${encodeURIComponent(value)}&limit=8`);
        render(data.cities || []);
      } catch {
        close();
      }
    }, 140);
  });

  input.addEventListener("keydown", (event) => {
    if (panel.hidden) return;
    const buttons = [...panel.querySelectorAll("button")];
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      state.suggestionIndex = (state.suggestionIndex + step + buttons.length) % buttons.length;
      buttons.forEach((button, index) => button.classList.toggle("active", index === state.suggestionIndex));
      buttons[state.suggestionIndex].scrollIntoView({ block: "nearest" });
    } else if (event.key === "Enter") {
      if (state.suggestionIndex >= 0) {
        event.preventDefault();
        const city = state.suggestions[state.suggestionIndex];
        if (city) chooseCity(city);
      }
    } else if (event.key === "Escape") {
      close();
    }
  });

  input.addEventListener("blur", () => setTimeout(close, 120));
}

/* ---------- 提交与渲染 ---------- */

function bindForm() {
  $("#adviceForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.loading) return;

    const city = $("#cityInput").value.trim();
    const day = $("#dateInput").value;
    if (!city) {
      showError("请先填写城市，例如「上海」或「shanghai」。");
      $("#cityInput").focus();
      return;
    }
    if (!day) {
      showError("请选择出行日期。");
      $("#dateInput").focus();
      return;
    }
    if (!state.modeId) {
      showError("请选择一个出行模式。");
      return;
    }

    await submitAdvice({ city, date: day, mode: state.modeId, options: readOptions() });
  });
}

async function submitAdvice(payload) {
  state.loading = true;
  state.lastPayload = payload;
  const button = $("#submitBtn");
  button.disabled = true;
  button.querySelector(".btn-label").textContent = "正在计算…";

  $("#emptyState").hidden = true;
  $("#result").hidden = true;
  $("#errorState").hidden = true;
  $("#loadingState").hidden = false;

  try {
    const data = await api("/api/advice", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...payload, use_llm: $("#llmToggle").checked }),
    });
    renderResult(data);
  } catch (error) {
    showError(`生成失败：${error.message}`);
  } finally {
    state.loading = false;
    button.disabled = false;
    button.querySelector(".btn-label").textContent = "生成建议";
    $("#loadingState").hidden = true;
  }
}

function showError(message) {
  const box = $("#errorState");
  box.textContent = message;
  box.hidden = false;
  $("#emptyState").hidden = true;
  $("#loadingState").hidden = true;
  $("#result").hidden = true;
}

function scoreColor(score) {
  if (score >= 85) return "#0f766e";
  if (score >= 70) return "#0d9488";
  if (score >= 55) return "#d97706";
  if (score >= 40) return "#ea580c";
  return "#b42318";
}

function renderResult(data) {
  $("#emptyState").hidden = true;
  $("#errorState").hidden = true;
  $("#loadingState").hidden = true;
  $("#result").hidden = false;

  const city = data.city || {};
  const calendar = data.date || {};
  const result = data.result || {};

  $("#resultMeta").textContent = [
    city.name || state.lastPayload.city,
    data.request.date,
    calendar.weekday || "",
    `· ${result.mode_name || ""}`,
  ]
    .filter(Boolean)
    .join(" ");

  $("#headline").textContent = result.headline || "";

  const tags = $("#tags");
  tags.replaceChildren();
  for (const tag of result.tags || []) tags.append(el("span", "tag", tag));

  const score = Math.max(0, Math.min(100, Number(result.score) || 0));
  const circumference = 2 * Math.PI * 40;
  const ring = $("#ringFg");
  ring.style.stroke = scoreColor(score);
  ring.style.strokeDashoffset = String(circumference * (1 - score / 100));
  $("#scoreNum").textContent = String(score);
  $("#scoreLabel").textContent = result.score_label || "出行指数";

  const polish = data.polish || {};
  $("#polish").hidden = !polish.text;
  $("#polishText").textContent = polish.text || "";

  const sections = $("#sections");
  sections.replaceChildren();
  for (const section of result.sections || []) {
    const card = el("div", "section-card");
    const header = el("header");
    header.append(el("span", "icon", section.icon || "•"), el("h3", null, section.title || ""));
    card.append(header);
    for (const item of section.items || []) {
      const row = el("div", `section-item ${item.level || "info"}`);
      row.append(el("span", "item-label", item.label), el("span", "item-text", item.text));
      card.append(row);
    }
    sections.append(card);
  }

  const facts = $("#factStrip");
  facts.replaceChildren();
  const weather = (data.facts && data.facts.weather) || {};
  const chips = [
    ["气温", `${Math.round(weather.t_min)}~${Math.round(weather.t_max)}℃`],
    ["降水概率", `${Math.round((weather.rain_prob || 0) * 100)}%`],
    ["体感", weather.comfort || "-"],
    ["天气来源", weather.estimated ? "常年估算" : weather.provider || "预报"],
    ["日期性质", calendar.type_label || "-"],
  ];
  if (data.facts && data.facts.solar_term && data.facts.solar_term.upcoming) {
    const term = data.facts.solar_term;
    const offset = Number(term.days_until) || 0;
    let suffix = "";
    if (offset > 0) suffix = `（${offset} 天后）`;
    else if (offset < 0) suffix = `（${-offset} 天前）`;
    chips.push([offset >= 0 ? "临近节气" : "节气", `${term.upcoming}${suffix}`]);
  }
  for (const [label, value] of chips) {
    const chip = el("span", "fact");
    chip.append(document.createTextNode(`${label} `), el("b", null, value));
    facts.append(chip);
  }

  const warnings = $("#warnings");
  warnings.replaceChildren();
  warnings.hidden = !(data.warnings || []).length;
  for (const text of data.warnings || []) warnings.append(el("div", "warning", text));

  const modelText = polish.used
    ? `润色：${polish.model || "大模型"}`
    : `纯规则生成${polish.error ? "（模型未启用）" : ""}`;
  $("#footMeta").textContent = [
    `引擎 v${(data.meta && data.meta.engine_version) || "1.0"}`,
    modelText,
    (data.meta && data.meta.generated_at) ? `生成于 ${data.meta.generated_at.replace("T", " ").slice(0, 16)}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  $("#footMeta").title = (data.meta && data.meta.disclaimer) || "";

  $("#copyBtn").onclick = () => copyAdvice(data);
}

async function copyAdvice(data) {
  const result = data.result || {};
  const city = data.city || {};
  const calendar = data.date || {};
  const lines = [
    `【出行建议】${city.name} ${data.request.date} ${calendar.weekday || ""} · ${result.mode_name}`,
    result.headline || "",
  ];
  if (data.polish && data.polish.text) lines.push("", data.polish.text);
  for (const section of result.sections || []) {
    lines.push("", `▍${section.title}`);
    for (const item of section.items || []) lines.push(`- ${item.label}：${item.text}`);
  }
  lines.push("", "由「出行建议官」生成：规则引擎 + 可选大模型润色");

  try {
    await navigator.clipboard.writeText(lines.join("\n"));
    const button = $("#copyBtn");
    const original = button.textContent;
    button.textContent = "已复制";
    setTimeout(() => (button.textContent = original), 1600);
  } catch {
    showError("复制失败，请手动选择文本复制。");
  }
}

/* ---------- 示例 ---------- */

function bindExamples() {
  const examples = {
    commute: { city: "上海", date: addDaysISO(todayISO(), 1), mode: "commute" },
    travel: { city: "杭州", date: nextSaturdayISO(), mode: "travel" },
    holiday: { city: "北京", date: "2027-02-06", mode: "travel" },
  };

  document.querySelectorAll("[data-example]").forEach((button) => {
    button.addEventListener("click", async () => {
      const sample = examples[button.dataset.example];
      if (!sample) return;
      $("#cityInput").value = sample.city;
      $("#dateInput").value = sample.date;
      if (state.modes.some((mode) => mode.id === sample.mode)) selectMode(sample.mode);
      await submitAdvice({ city: sample.city, date: sample.date, mode: sample.mode, options: readOptions() });
    });
  });
}

document.addEventListener("DOMContentLoaded", init);
