import { currentEffect, loadCatalog, loadEffectLabels } from "./catalog.js?v=0.0.1-b11";
import { adjustedTime, createPlan, formatDuration, isInstantNextLevel, researchLevelsAfterPlan, shortestAvailable } from "./planning.js?v=0.0.1-b11";
import { RESOURCE_KEYS, backupPayload, defaultState, freeSecondsForVip, loadState, saveState, stateFromBackup } from "./state.js?v=0.0.1-b11";

const RELEASE_VERSION = "0.0.1";
const DEVELOPMENT_BUILD = 11;
const DEVELOPMENT_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);
const APP_VERSION = DEVELOPMENT_HOSTS.has(window.location.hostname)
  ? `${RELEASE_VERSION}+b${DEVELOPMENT_BUILD}`
  : RELEASE_VERSION;
const RESOURCE_NAMES = {
  "ja-JP": { food: "食糧", stone: "石材", timber: "木材", ore: "鉱石", gold: "ゴールド", ancient_tomes: "古代の書物", lunite: "月晶", mana_ore: "マナ鉱石", special: "特殊資材" },
  "en-US": { food: "Food", stone: "Stone", timber: "Timber", ore: "Ore", gold: "Gold", ancient_tomes: "Ancient Tomes", lunite: "Lunite", mana_ore: "Mana Ore", special: "Special" },
};
const CARD_WIDTH = 250;
const CARD_HEIGHT = 174;
const GAP_X = 42;
const GAP_Y = 62;
const PADDING = 36;

let catalog;
let effectLabels = {};
let state = loadState();
let selectedCategoryId = "";
let selectedBulkCategoryId = "";
let selectedNodeId = "";
let zoom = window.innerWidth < 650 ? 0.72 : 1;
let planMode = "target";
let currentPlan = null;
let toastTimer;
let saveTimer;
let suppressCardClick = false;

const byId = (id) => document.getElementById(id);
const create = (tag, className = "", text = "") => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== "") node.textContent = text;
  return node;
};

async function start() {
  try {
    [catalog, effectLabels] = await Promise.all([loadCatalog(), loadEffectLabels()]);
    selectedCategoryId = catalog.categories[0]?.id || "";
    selectedBulkCategoryId = selectedCategoryId;
    bindNavigation();
    bindTreeControls();
    bindDialog();
    bindSettings();
    bindPlans();
    bindConnectivity();
    populateSettings();
    renderCategoryOptions();
    renderTree();
    renderShortest();
    renderCatalogStatus();
    byId("app-version").textContent = APP_VERSION;
    byId("language-select").value = state.locale;
  } catch (error) {
    const target = byId("startup-error");
    const message = byId("startup-error-message");
    if (target && message) { message.textContent = `研究データを読み込めませんでした: ${error.message}`; target.hidden = false; }
  }
}

function renderCatalogStatus() {
  const status = byId("catalog-data-status");
  const notes = byId("catalog-data-notes");
  if (!status || !notes) return;
  const nodes = [...catalog.nodes.values()];
  const maximum = nodes.reduce((sum, node) => sum + node.maxLevel, 0);
  const levels = nodes.reduce((sum, node) => sum + node.levels.size, 0);
  const times = nodes.reduce((sum, node) => sum + [...node.levels.values()].filter((level) => level.baseTimeSeconds != null).length, 0);
  const costs = nodes.reduce((sum, node) => sum + [...node.levels.values()].filter((level) => Object.keys(level.costs).length > 0).length, 0);
  status.textContent = `${catalog.categories.length}分野・${nodes.length}研究を収録しています。全${maximum.toLocaleString(state.locale)}レベル中、詳細${levels.toLocaleString(state.locale)}、研究時間${times.toLocaleString(state.locale)}、資源${costs.toLocaleString(state.locale)}レベル分が登録済みです。`;
  const incomplete = catalog.categories.filter((category) => {
    const expected = category.nodes.reduce((sum, node) => sum + node.maxLevel, 0);
    return category.dataStats.times < expected || category.dataStats.costs < expected;
  }).map((category) => catalog.categoryTitle(category, state.locale));
  notes.textContent = incomplete.length ? `公開元で数値を確認できていないレベルを含む分野: ${incomplete.join("、")}。未収録値は推測で補完しません。` : "全レベルの時間・資源データを収録しています。";
}

function bindNavigation() {
  document.querySelectorAll(".tab-button").forEach((button) => button.addEventListener("click", () => showTab(button.dataset.tab)));
  byId("startup-retry")?.addEventListener("click", () => location.reload());
}

function showTab(tab) {
  document.querySelectorAll(".tab-button").forEach((button) => button.classList.toggle("is-active", button.dataset.tab === tab));
  document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.toggle("is-active", panel.id === `tab-${tab}`));
  if (tab === "tree") requestAnimationFrame(renderTree);
  if (tab === "plan" && planMode === "shortest") renderShortest();
}

function bindTreeControls() {
  byId("category-select").addEventListener("change", (event) => { selectedCategoryId = event.target.value; renderTree(true); });
  byId("category-drawer-open")?.addEventListener("click", () => {
    renderCategoryOptions();
    byId("category-drawer")?.showModal();
  });
  byId("tree-search").addEventListener("input", () => { renderCategoryOptions(); renderTree(true); });
  byId("instant-only").addEventListener("change", () => { renderCategoryOptions(); renderTree(true); });
  byId("zoom-out").addEventListener("click", () => setZoom(zoom - 0.1));
  byId("zoom-in").addEventListener("click", () => setZoom(zoom + 0.1));
  byId("tree-viewport").addEventListener("wheel", (event) => {
    if (!event.ctrlKey) return;
    event.preventDefault();
    setZoom(zoom + (event.deltaY < 0 ? 0.1 : -0.1));
  }, { passive: false });

  const viewport = byId("tree-viewport");
  let drag = null;
  viewport.addEventListener("pointerdown", (event) => {
    if (event.pointerType !== "mouse" || event.button !== 0 || !event.isPrimary) return;
    drag = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, left: viewport.scrollLeft, top: viewport.scrollTop, moved: false };
  });
  viewport.addEventListener("pointermove", (event) => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) > 6) {
      drag.moved = true;
      suppressCardClick = true;
      viewport.classList.add("is-dragging");
      viewport.setPointerCapture(event.pointerId);
    }
    if (!drag.moved) return;
    event.preventDefault();
    viewport.scrollLeft = drag.left - dx;
    viewport.scrollTop = drag.top - dy;
  });
  const endDrag = (event) => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    const moved = drag?.moved;
    drag = null;
    viewport.classList.remove("is-dragging");
    if (moved) window.setTimeout(() => { suppressCardClick = false; }, 0);
  };
  viewport.addEventListener("pointerup", endDrag);
  viewport.addEventListener("pointercancel", endDrag);
  window.addEventListener("resize", debounce(() => renderTree(), 120));
}

function setZoom(value) {
  zoom = Math.min(1.5, Math.max(0.5, Math.round(value * 10) / 10));
  byId("zoom-output").textContent = `${Math.round(zoom * 100)}%`;
  renderTree();
}

function matchingNodes(category) {
  const term = byId("tree-search")?.value.trim().toLocaleLowerCase(state.locale) || "";
  const instantOnly = Boolean(byId("instant-only")?.checked);
  return category.nodes.filter((node) => {
    const name = catalog.nodeName(node, state.locale).toLocaleLowerCase(state.locale);
    return (!term || name.includes(term) || node.id.includes(term)) && (!instantOnly || isInstantNextLevel(node, state));
  });
}

function renderCategoryOptions() {
  const select = byId("category-select");
  if (!select || !catalog) return;
  const available = catalog.categories.filter((category) => matchingNodes(category).length > 0);
  const shown = available.length ? available : catalog.categories;
  if (!shown.some((category) => category.id === selectedCategoryId)) selectedCategoryId = shown[0]?.id || "";
  select.replaceChildren(...shown.map((category) => {
    const option = create("option", "", catalog.categoryTitle(category, state.locale));
    option.value = category.id;
    option.selected = category.id === selectedCategoryId;
    return option;
  }));
  const selected = catalog.categories.find((category) => category.id === selectedCategoryId);
  const current = byId("category-current");
  if (selected && current) current.textContent = catalog.categoryTitle(selected, state.locale);
  renderCategoryDrawer(shown);
}

function renderCategoryDrawer(categories) {
  const list = byId("category-drawer-list");
  if (!list) return;
  list.replaceChildren(...categories.map((category) => {
    const button = create("button", "category-drawer-item");
    button.type = "button";
    if (category.id === selectedCategoryId) button.classList.add("is-active");
    button.append(create("span", "", catalog.categoryTitle(category, state.locale)), create("small", "", `${matchingNodes(category).length}件`));
    button.addEventListener("click", () => {
      selectedCategoryId = category.id;
      byId("category-select").value = category.id;
      byId("category-drawer")?.close();
      renderCategoryOptions();
      renderTree(true);
    });
    return button;
  }));
}

function renderTree(resetScroll = false) {
  if (!catalog) return;
  const category = catalog.categories.find((item) => item.id === selectedCategoryId) || catalog.categories[0];
  if (!category) return;
  selectedCategoryId = category.id;
  const nodes = matchingNodes(category);
  const visibleIds = new Set(nodes.map((node) => node.id));
  const width = Math.max(byId("tree-viewport").clientWidth - 2, (PADDING * 2 + category.columnCount * CARD_WIDTH + (category.columnCount - 1) * GAP_X) * zoom);
  const height = Math.max(byId("tree-viewport").clientHeight - 2, (PADDING * 2 + category.rowCount * CARD_HEIGHT + (category.rowCount - 1) * GAP_Y) * zoom);
  const stage = byId("tree-stage");
  stage.style.width = `${width}px`;
  stage.style.height = `${height}px`;
  const positions = new Map();
  for (const node of nodes) {
    positions.set(node.id, {
      x: (PADDING + node.column * (CARD_WIDTH + GAP_X)) * zoom,
      y: (PADDING + node.row * (CARD_HEIGHT + GAP_Y)) * zoom,
      width: CARD_WIDTH * zoom,
      height: CARD_HEIGHT * zoom,
    });
  }
  renderLines(category, visibleIds, positions, width, height);
  const cards = byId("tree-cards");
  cards.replaceChildren(...nodes.map((node) => renderCard(node, positions.get(node.id))));
  byId("tree-empty").hidden = nodes.length > 0;
  byId("tree-viewport").hidden = nodes.length === 0;
  byId("zoom-output").textContent = `${Math.round(zoom * 100)}%`;
  if (resetScroll) { byId("tree-viewport").scrollLeft = 0; byId("tree-viewport").scrollTop = 0; }
}

function renderLines(category, visibleIds, positions, width, height) {
  const svg = byId("tree-lines");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("width", width);
  svg.setAttribute("height", height);
  const paths = [];
  for (const [fromId, toId] of category.edges) {
    if (!visibleIds.has(fromId) || !visibleIds.has(toId)) continue;
    const from = positions.get(fromId); const to = positions.get(toId);
    if (!from || !to) continue;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    if (Math.abs(from.y - to.y) < 2) {
      const fromRight = from.x < to.x;
      const x1 = fromRight ? from.x + from.width : from.x;
      const x2 = fromRight ? to.x : to.x + to.width;
      const y = from.y + from.height / 2;
      path.setAttribute("d", `M ${x1} ${y} H ${x2}`);
    } else {
      const x1 = from.x + from.width / 2; const y1 = from.y + from.height;
      const x2 = to.x + to.width / 2; const y2 = to.y;
      const mid = y1 + Math.max(12 * zoom, (y2 - y1) / 2);
      path.setAttribute("d", `M ${x1} ${y1} V ${mid} H ${x2} V ${y2}`);
    }
    paths.push(path);
  }
  svg.replaceChildren(...paths);
}

function renderCard(node, position) {
  const level = Math.min(node.maxLevel, Number(state.researchLevels[node.id] || 0));
  const current = effectFor(node, level);
  const next = level < node.maxLevel ? effectFor(node, level + 1) : "";
  const card = create("button", "research-card");
  card.type = "button";
  card.dataset.nodeId = node.id;
  card.style.left = `${position.x}px`;
  card.style.top = `${position.y}px`;
  card.style.width = `${position.width}px`;
  card.style.height = `${position.height}px`;
  card.style.setProperty("--node-scale", zoom);
  if (level >= node.maxLevel) card.classList.add("is-complete");
  else if (level > 0) card.classList.add("is-progress");
  else if (!nodeAvailableIgnoringTime(node)) card.classList.add("is-locked");
  const name = create("span", "research-name", catalog.nodeName(node, state.locale));
  const nameLength = [...name.textContent].reduce((sum, character) => sum + (character.charCodeAt(0) > 255 ? 1 : .58), 0);
  name.style.fontSize = `${Math.max(13, Math.min(25, 215 / Math.max(5, nameLength))) * zoom}px`;
  const meter = create("span", "research-meter");
  const fill = create("span"); fill.style.width = `${node.maxLevel ? level / node.maxLevel * 100 : 0}%`; meter.append(fill);
  const levelText = create("span", "research-level", `${level} / ${node.maxLevel}`);
  const effect = create("span", "research-effect", current || "—");
  effect.title = current;
  card.append(name, meter, levelText, effect);
  if (next) { const nextText = create("span", "research-effect research-next", next); nextText.title = next; card.append(nextText); }
  card.addEventListener("click", () => { if (!suppressCardClick) openNodeDialog(node.id); });
  return card;
}

function nodeAvailableIgnoringTime(node) {
  const next = Number(state.researchLevels[node.id] || 0) + 1;
  if (next > node.maxLevel) return true;
  const data = node.levels.get(next);
  if (!data) return false;
  const academy = Math.max(Number(data.academyLevel || 0), Number(data.buildings.academy || 0));
  return academy <= state.settings.academyLevel && data.requirements.every((requirement) => Number(state.researchLevels[requirement.researchId] || 0) >= requirement.level);
}

function bindDialog() {
  const number = byId("node-level-number"); const range = byId("node-level-range");
  const decrease = byId("node-level-down"); const increase = byId("node-level-up");
  const updateStepButtons = (level) => {
    decrease.disabled = level <= Number(range.min || 0);
    increase.disabled = level >= Number(range.max || 0);
  };
  const update = (value) => {
    const node = catalog.nodes.get(selectedNodeId); if (!node) return;
    const level = Math.max(0, Math.min(node.maxLevel, Math.trunc(Number(value) || 0)));
    number.value = level; range.value = level; state.researchLevels[node.id] = level;
    updateStepButtons(level);
    renderDialogEffects(node, level); populateTargetLevels(node, level); scheduleSave(); renderTree(); renderBulkLevels(); refreshCurrentPlan();
  };
  number.addEventListener("input", (event) => update(event.target.value));
  range.addEventListener("input", (event) => update(event.target.value));
  decrease.addEventListener("click", () => update(Number(range.value) - 1));
  increase.addEventListener("click", () => update(Number(range.value) + 1));
  byId("open-plan").addEventListener("click", () => {
    const target = Number(byId("node-target-level").value);
    byId("node-dialog").close();
    buildTargetPlan(selectedNodeId, target);
    setPlanMode("target"); showTab("plan");
  });
}

function openNodeDialog(nodeId) {
  const node = catalog.nodes.get(nodeId); if (!node) return;
  selectedNodeId = nodeId;
  const category = catalog.categories.find((item) => item.id === node.categoryId);
  const level = Math.min(node.maxLevel, Number(state.researchLevels[node.id] || 0));
  byId("node-dialog-category").textContent = catalog.categoryTitle(category, state.locale);
  byId("node-dialog-name").textContent = catalog.nodeName(node, state.locale);
  byId("node-level-number").max = node.maxLevel;
  byId("node-level-number").value = level;
  byId("node-level-range").max = node.maxLevel;
  byId("node-level-range").value = level;
  byId("node-level-down").disabled = level <= 0;
  byId("node-level-up").disabled = level >= node.maxLevel;
  byId("node-level-max").textContent = `/ ${node.maxLevel}`;
  renderDialogEffects(node, level);
  populateTargetLevels(node, level);
  window.scrollTo({ left: 0, top: window.scrollY, behavior: "auto" });
  byId("node-dialog").showModal();
}

function populateTargetLevels(node, level) {
  const target = byId("node-target-level");
  const previous = Number(target.value || 0);
  const levels = level < node.maxLevel
    ? Array.from({ length: node.maxLevel - level }, (_, index) => level + index + 1)
    : [node.maxLevel];
  target.replaceChildren(...levels.map((targetLevel) => {
    const option = create("option", "", `Lv.${targetLevel}`);
    option.value = targetLevel;
    option.selected = targetLevel === previous;
    return option;
  }));
  byId("open-plan").disabled = level >= node.maxLevel;
}

function renderDialogEffects(node, level) {
  const box = byId("node-effects");
  const current = create("p", "", effectFor(node, level) || "—");
  const next = create("p", "", level < node.maxLevel ? effectFor(node, level + 1) || "—" : "最大レベルです");
  box.replaceChildren(current, next);
  renderNodeNextDetails(node, level);
}

function renderNodeNextDetails(node, level) {
  const target = byId("node-next-detail");
  if (!target) return;
  if (level >= node.maxLevel) {
    target.replaceChildren(create("p", "muted", "最大レベルに到達しています。"));
    return;
  }
  const nextLevel = level + 1;
  const data = node.levels.get(nextLevel);
  const heading = create("h3", "", `Lv.${nextLevel} の必要条件`);
  if (!data) {
    target.replaceChildren(heading, create("p", "muted", "このレベルの時間・資源・前提条件データは未収録です。現在レベルの記録はできます。"));
    return;
  }
  const grid = create("div", "detail-grid");
  const time = create("div", "detail-item");
  time.append(create("span", "", "研究時間"), create("strong", "", data.baseTimeSeconds == null ? "未収録" : formatDuration(adjustedTime(data.baseTimeSeconds, state.settings))));
  const academy = Math.max(Number(data.academyLevel || 0), Number(data.buildings.academy || 0));
  const facility = create("div", "detail-item");
  const facilityParts = [];
  if (academy) facilityParts.push(`アカデミー Lv.${academy}`);
  if (data.buildings.mana_academy) facilityParts.push(`マナアカデミー Lv.${data.buildings.mana_academy}`);
  facility.append(create("span", "", "必要施設"), create("strong", "", facilityParts.join(" / ") || "なし"));
  grid.append(time, facility);
  const resourceBox = create("div", "detail-resources");
  const costs = RESOURCE_KEYS.filter((key) => Number(data.costs[key] || 0) > 0);
  if (costs.length) {
    for (const key of costs) resourceBox.append(create("span", "", `${RESOURCE_NAMES[state.locale][key]} ${Number(data.costs[key]).toLocaleString(state.locale)}`));
  } else resourceBox.append(create("span", "", data.costsVerified ? "資源なし" : "資源データ未収録"));
  const requirements = create("ul", "detail-requirements");
  if (data.requirements.length) {
    for (const requirement of data.requirements) {
      const prerequisite = catalog.nodes.get(requirement.researchId);
      requirements.append(create("li", "", `${prerequisite ? catalog.nodeName(prerequisite, state.locale) : requirement.researchId} Lv.${requirement.level}`));
    }
  } else requirements.append(create("li", "", "前提研究なし"));
  target.replaceChildren(heading, grid, resourceBox, requirements);
}

function bindSettings() {
  const inputs = {
    "setting-vip": ["vipLevel", true], "setting-castle": ["castleLevel", true], "setting-academy": ["academyLevel", true],
    "setting-speed": ["researchSpeedPercent", false], "setting-boost": ["researchSpeedBoostPercent", false], "setting-helps": ["maxGuildHelps", true],
  };
  for (const [id, [key, integer]] of Object.entries(inputs)) {
    byId(id).addEventListener("input", (event) => {
      state.settings[key] = Math.max(0, integer ? Math.trunc(Number(event.target.value) || 0) : Number(event.target.value) || 0);
      if (key === "vipLevel") state.settings[key] = Math.max(1, Math.min(15, state.settings[key]));
      if (key === "castleLevel" || key === "academyLevel") state.settings[key] = Math.max(1, Math.min(25, state.settings[key]));
      updateVipHint(); scheduleSave(); renderTree(); refreshCurrentPlan(); if (planMode === "shortest") renderShortest();
    });
  }
  const resourceInputs = byId("resource-inputs");
  for (const key of RESOURCE_KEYS) {
    const label = create("label", "field"); label.append(create("span", "", RESOURCE_NAMES[state.locale][key]));
    const input = create("input"); input.type = "number"; input.inputMode = "numeric"; input.min = "0"; input.dataset.resource = key;
    input.addEventListener("input", () => { state.settings.resources[key] = Math.max(0, Math.trunc(Number(input.value) || 0)); scheduleSave(); refreshCurrentPlan(); });
    label.append(input); resourceInputs.append(label);
  }
  byId("bulk-category-select")?.addEventListener("change", (event) => { selectedBulkCategoryId = event.target.value; renderBulkLevels(); });
  byId("bulk-level-search")?.addEventListener("input", renderBulkLevels);
  byId("language-select").addEventListener("change", (event) => { state.locale = event.target.value; scheduleSave(); populateSettings(); renderCategoryOptions(); renderTree(); renderPlan(); renderShortest(); renderCatalogStatus(); });
  byId("export-backup").addEventListener("click", exportBackup);
  byId("import-backup").addEventListener("change", importBackup);
  byId("reset-player").addEventListener("click", () => {
    if (!window.confirm("プレイヤー設定と全研究レベルをクリアしますか？")) return;
    const locale = state.locale; state = defaultState(); state.locale = locale; saveNow(); populateSettings(); renderCategoryOptions(); renderTree(true); currentPlan = null; renderPlan(); renderShortest(); toast("設定をクリアしました");
  });
}

function populateSettings() {
  byId("setting-vip").value = state.settings.vipLevel;
  byId("setting-castle").value = state.settings.castleLevel;
  byId("setting-academy").value = state.settings.academyLevel;
  byId("setting-speed").value = state.settings.researchSpeedPercent;
  byId("setting-boost").value = state.settings.researchSpeedBoostPercent;
  byId("setting-helps").value = state.settings.maxGuildHelps;
  byId("language-select").value = state.locale;
  document.querySelectorAll("[data-resource]").forEach((input) => { input.value = state.settings.resources[input.dataset.resource] || 0; input.previousElementSibling.textContent = RESOURCE_NAMES[state.locale][input.dataset.resource]; });
  updateVipHint();
  populateBulkCategoryOptions();
  renderBulkLevels();
}

function populateBulkCategoryOptions() {
  const select = byId("bulk-category-select");
  if (!catalog || !select) return;
  if (!catalog.categories.some((category) => category.id === selectedBulkCategoryId)) selectedBulkCategoryId = catalog.categories[0]?.id || "";
  select.replaceChildren(...catalog.categories.map((category) => {
    const option = create("option", "", catalog.categoryTitle(category, state.locale));
    option.value = category.id; option.selected = category.id === selectedBulkCategoryId; return option;
  }));
}

function renderBulkLevels() {
  if (!catalog) return;
  const list = byId("bulk-level-list");
  if (!list) return;
  const category = catalog.categories.find((item) => item.id === selectedBulkCategoryId) || catalog.categories[0];
  if (!category) return;
  selectedBulkCategoryId = category.id;
  const term = byId("bulk-level-search")?.value.trim().toLocaleLowerCase(state.locale) || "";
  const nodes = category.nodes.filter((node) => {
    const name = catalog.nodeName(node, state.locale).toLocaleLowerCase(state.locale);
    return !term || name.includes(term) || node.id.includes(term);
  });
  list.replaceChildren(...nodes.map((node) => {
    const row = create("div", "bulk-level-row");
    const open = create("button", "", catalog.nodeName(node, state.locale)); open.type = "button";
    open.addEventListener("click", () => { jumpToNode(node); requestAnimationFrame(() => openNodeDialog(node.id)); });
    const input = create("input"); input.type = "number"; input.inputMode = "numeric"; input.min = "0"; input.max = String(node.maxLevel); input.value = String(Math.min(node.maxLevel, Number(state.researchLevels[node.id] || 0))); input.setAttribute("aria-label", `${catalog.nodeName(node, state.locale)}の現在レベル`);
    input.addEventListener("input", () => {
      const level = Math.max(0, Math.min(node.maxLevel, Math.trunc(Number(input.value) || 0)));
      state.researchLevels[node.id] = level;
      updateBulkProgress(category); scheduleSave(); renderTree(); refreshCurrentPlan(); if (planMode === "shortest") renderShortest();
    });
    row.append(open, input, create("span", "max-label", `/ ${node.maxLevel}`)); return row;
  }));
  updateBulkProgress(category);
}

function updateBulkProgress(category) {
  const progress = byId("bulk-level-progress");
  if (!progress) return;
  const current = category.nodes.reduce((sum, node) => sum + Math.min(node.maxLevel, Number(state.researchLevels[node.id] || 0)), 0);
  const maximum = category.nodes.reduce((sum, node) => sum + node.maxLevel, 0);
  progress.textContent = `${current} / ${maximum}`;
}

function updateVipHint() { byId("vip-free-time").textContent = `VIP ${state.settings.vipLevel} の無料スピードアップ: ${Math.round(freeSecondsForVip(state.settings.vipLevel) / 60)}分`; }
function scheduleSave() { byId("save-indicator").textContent = "保存中…"; clearTimeout(saveTimer); saveTimer = setTimeout(saveNow, 250); }
function saveNow() { saveState(state); byId("save-indicator").textContent = "保存済み"; }

function exportBackup() {
  saveNow();
  const blob = new Blob([JSON.stringify(backupPayload(state), null, 2)], { type: "application/json" });
  const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = `RLMResearchPlanner_${new Date().toISOString().slice(0, 10)}.json`; link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000); toast("バックアップを書き出しました");
}

async function importBackup(event) {
  const file = event.target.files?.[0]; if (!file) return;
  try {
    const imported = stateFromBackup(JSON.parse(await file.text())); imported.locale = state.locale; state = imported; saveNow(); populateSettings(); renderCategoryOptions(); renderTree(true); currentPlan = null; renderPlan(); renderShortest(); toast("バックアップを読み込みました");
  } catch (error) { toast(error.message); }
  finally { event.target.value = ""; }
}

function bindPlans() {
  byId("plan-target-mode").addEventListener("click", () => setPlanMode("target"));
  byId("plan-shortest-mode").addEventListener("click", () => setPlanMode("shortest"));
  byId("complete-plan").addEventListener("click", completeCurrentPlan);
  byId("shortest-limit").addEventListener("change", renderShortest);
}

function setPlanMode(mode) {
  planMode = mode;
  byId("plan-target-mode").classList.toggle("is-active", mode === "target");
  byId("plan-shortest-mode").classList.toggle("is-active", mode === "shortest");
  byId("target-plan-view").hidden = mode !== "target";
  byId("shortest-plan-view").hidden = mode !== "shortest";
  if (mode === "shortest") renderShortest();
}

function buildTargetPlan(researchId, level) {
  try { currentPlan = createPlan(catalog, state, researchId, level); renderPlan(); }
  catch (error) { toast(error.message); }
}

function refreshCurrentPlan() {
  if (!currentPlan) return;
  const { targetId, targetLevel } = currentPlan;
  try { currentPlan = createPlan(catalog, state, targetId, targetLevel); }
  catch (error) { currentPlan = null; toast(error.message); }
  renderPlan();
}

function completeCurrentPlan() {
  if (!currentPlan?.steps.length) return;
  const previous = state.researchLevels;
  const completed = researchLevelsAfterPlan(currentPlan, previous);
  const changed = Object.keys(completed).filter(
    (researchId) => Number(completed[researchId] || 0) > Number(previous[researchId] || 0),
  );
  state.researchLevels = completed;
  saveNow();
  populateSettings();
  renderCategoryOptions();
  renderTree();
  refreshCurrentPlan();
  renderShortest();
  toast(`目標研究と前提研究を含む${changed.length}件のレベルを反映しました`);
}

function renderPlan() {
  byId("plan-placeholder").hidden = Boolean(currentPlan);
  byId("plan-result").hidden = !currentPlan;
  if (!currentPlan) return;
  const target = catalog.nodes.get(currentPlan.targetId);
  byId("plan-target-name").textContent = `${catalog.nodeName(target, state.locale)} Lv.${currentPlan.targetLevel}`;
  byId("plan-total-time").textContent = currentPlan.totals.unknownTime ? `${formatDuration(currentPlan.totals.adjustedSeconds)} + 未確認` : formatDuration(currentPlan.totals.adjustedSeconds);
  const resources = RESOURCE_NAMES[state.locale];
  byId("resource-summary").replaceChildren(...RESOURCE_KEYS.map((key) => {
    const chip = create("div", "resource-chip"); const needed = currentPlan.totals.costs[key] || 0; const available = state.settings.resources[key] || 0;
    if (needed > available) chip.classList.add("is-short");
    chip.append(create("span", "", resources[key]), create("strong", "", needed.toLocaleString(state.locale)), create("span", "", needed > available ? `不足 ${(needed - available).toLocaleString(state.locale)}` : "所持数以内")); return chip;
  }));
  byId("plan-steps").replaceChildren(...currentPlan.steps.map((step) => planRow(step)));
  byId("complete-plan").disabled = currentPlan.steps.length === 0;
  const issueParts = [];
  if (currentPlan.totals.unknownTime) issueParts.push(`時間未確認 ${currentPlan.totals.unknownTime}件`);
  if (currentPlan.totals.unknownCosts) issueParts.push(`資源未確認 ${currentPlan.totals.unknownCosts}件`);
  issueParts.push(...currentPlan.issues);
  byId("plan-issues").textContent = issueParts.join(" / ");
}

function renderShortest() {
  if (!catalog) return;
  const limit = Number(byId("shortest-limit")?.value || 20);
  const steps = shortestAvailable(catalog, state).slice(0, limit);
  const list = byId("shortest-list");
  list.replaceChildren(...steps.map((step) => planRow(step)));
  if (!steps.length) list.append(create("div", "callout", "現在の条件で開始でき、時間データが確認済みの研究はありません。"));
}

function planRow(step) {
  const node = catalog.nodes.get(step.researchId);
  const row = create("article", "plan-row");
  const nameButton = create("button", "", `${catalog.nodeName(node, state.locale)} Lv.${step.level}`); nameButton.type = "button";
  nameButton.addEventListener("click", () => jumpToNode(node));
  const details = create("div");
  const categoryName = catalog.categoryTitle(catalog.categories.find((item) => item.id === node.categoryId), state.locale);
  const costs = RESOURCE_KEYS.filter((key) => Number(step.costs[key] || 0) > 0).map((key) => `${RESOURCE_NAMES[state.locale][key]} ${Number(step.costs[key]).toLocaleString(state.locale)}`);
  details.append(nameButton, create("small", "plan-row-meta", costs.length ? `${categoryName} · ${costs.join(" / ")}` : `${categoryName} · 資源データ未収録`));
  row.append(details, create("strong", "plan-row-time", step.adjustedSeconds == null ? "未確認" : formatDuration(step.adjustedSeconds))); return row;
}

function jumpToNode(node) {
  selectedCategoryId = node.categoryId; byId("tree-search").value = ""; byId("instant-only").checked = false;
  renderCategoryOptions(); renderTree(); showTab("tree");
  requestAnimationFrame(() => {
    const card = document.querySelector(`[data-node-id="${CSS.escape(node.id)}"]`);
    card?.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
    card?.focus({ preventScroll: true });
  });
}

function bindConnectivity() {
  const update = () => { byId("connection-status").textContent = navigator.onLine ? "オンライン" : "オフライン"; byId("connection-status").classList.toggle("is-offline", !navigator.onLine); };
  window.addEventListener("online", update); window.addEventListener("offline", update); update();
}

function effectFor(node, level) {
  return currentEffect(node, level, { locale: state.locale, labels: state.locale === "ja-JP" ? effectLabels : {}, name: catalog.nodeName(node, state.locale) });
}

function toast(message) {
  const target = byId("toast"); target.textContent = message; target.classList.add("is-visible"); clearTimeout(toastTimer); toastTimer = setTimeout(() => target.classList.remove("is-visible"), 2800);
}

function debounce(callback, delay) { let timer; return (...args) => { clearTimeout(timer); timer = setTimeout(() => callback(...args), delay); }; }

start();
