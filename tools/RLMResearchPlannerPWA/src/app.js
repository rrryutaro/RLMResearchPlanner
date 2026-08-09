import { currentEffect, loadCatalog, loadLocaleData } from "./catalog.js?v=0.0.12-b2";
import { adjustedTime, createPlan, defaultTargetLevel, formatDuration, isInstantNextLevel, isResearchConnectionUnlocked, researchLevelsAfterPlan, shortestAvailable } from "./planning.js?v=0.0.12-b2";
import { RESOURCE_KEYS, backupPayload, defaultState, freeSecondsForVip, guildHelpCount, loadState, maxGuildHelpsForCastle, saveState, stateFromBackup } from "./state.js?v=0.0.12-b2";
import { explicitTreeLayout } from "./tree-layout.js?v=0.0.12-b2";
import { clampTreeZoom, fitTreeZoom } from "./tree-zoom.js?v=0.0.12-b2";
import { formatResourceAmount } from "./resource-format.js?v=0.0.12-b2";
import { CASTLE_RESOURCE_KEYS, buildingLevelsAfterCastleStep, castleProgressLabel, createCastlePlan, loadCastleCatalog, minimumBuildingLevels } from "./castle-planning.js?v=0.0.12-b2";

const RELEASE_VERSION = "0.0.12";
const DEVELOPMENT_BUILD = 2;
const DEVELOPMENT_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);
const APP_VERSION = DEVELOPMENT_HOSTS.has(window.location.hostname)
  ? `${RELEASE_VERSION}+b${DEVELOPMENT_BUILD}`
  : RELEASE_VERSION;
const RESOURCE_NAMES = {
  "ja-JP": { food: "食糧", stone: "石材", timber: "木材", ore: "鉱石", gold: "ゴールド", gold_hammer: "ゴールドハンマー", war_tome: "戦典", steel_cuffs: "鋼鉄の手枷", soul_crystal: "霊魂石", ancient_tomes: "古代の書物", lunite: "月晶", mana_ore: "マナ鉱石", mana_crystal: "マナクリスタル", mana_steel: "マナスチール", special: "特殊資材" },
  "en-US": { food: "Food", stone: "Stone", timber: "Timber", ore: "Ore", gold: "Gold", gold_hammer: "Gold Hammer", war_tome: "War Tome", steel_cuffs: "Steel Cuffs", soul_crystal: "Soul Crystal", ancient_tomes: "Ancient Tomes", lunite: "Lunite", mana_ore: "Mana Ore", mana_crystal: "Mana Crystal", mana_steel: "Manasteel", special: "Special" },
};
const CARD_WIDTH = 250;
const CARD_HEIGHT = 174;
const GAP_X = 42;
const GAP_Y = 62;
const PADDING = 36;

let catalog;
let castleCatalog;
let effectLabels = {};
let messages = {};
let state = loadState();
let selectedCategoryId = "";
let selectedBulkCategoryId = "";
let selectedNodeId = "";
let zoom = window.innerWidth < 650 ? 0.72 : 1;
let planMode = "target";
let currentPlan = null;
let castleTargetLevel = 0;
let castleTargetManaStage = 0;
let constructionTargetBuildingId = "castle";
let constructionFacilityTargetLevel = 0;
let toastTimer;
let saveTimer;
let suppressCardClick = false;
const categoryLayouts = new Map();

const byId = (id) => document.getElementById(id);
const create = (tag, className = "", text = "") => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== "") node.textContent = text;
  return node;
};

async function start() {
  try {
    const [loadedCatalog, loadedCastleCatalog, localeData] = await Promise.all([loadCatalog(), loadCastleCatalog(), loadLocaleData()]);
    catalog = loadedCatalog;
    castleCatalog = loadedCastleCatalog;
    effectLabels = localeData.effect_labels || {};
    messages = localeData.messages || {};
    selectedCategoryId = catalog.categories[0]?.id || "";
    selectedBulkCategoryId = selectedCategoryId;
    bindNavigation();
    bindTreeControls();
    bindDialog();
    bindSettings();
    bindPlans();
    bindCastle();
    installStaticNumberSteppers();
    bindConnectivity();
    populateSettings();
    renderCategoryOptions();
    renderTree();
    renderShortest();
    renderTasks();
    renderCastle();
    renderCatalogStatus();
    renderCommonHelp();
    byId("app-version").textContent = APP_VERSION;
    byId("language-select").value = state.locale;
  } catch (error) {
    const target = byId("startup-error");
    const message = byId("startup-error-message");
    if (target && message) { message.textContent = `研究データを読み込めませんでした: ${error.message}`; target.hidden = false; }
  }
}

function renderCommonHelp() {
  const plan = byId("help-plan-body");
  const construction = byId("help-construction-body");
  if (plan) plan.innerHTML = messages["help.plan.body"] || "";
  if (construction) construction.innerHTML = messages["help.castle.body"] || "";
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
  if (tab === "plan" && planMode === "tasks") renderTasks();
  if (tab === "castle") renderCastle();
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
  byId("zoom-fit").addEventListener("click", fitWholeTree);
  byId("tree-viewport").addEventListener("wheel", (event) => {
    if (!event.ctrlKey) return;
    event.preventDefault();
    setZoom(zoom + (event.deltaY < 0 ? 0.1 : -0.1), { clientX: event.clientX, clientY: event.clientY });
  }, { passive: false });

  const viewport = byId("tree-viewport");
  let drag = null;
  const touches = new Map();
  let touchPan = null;
  let pinch = null;
  viewport.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "touch") {
      touches.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (touches.size === 1) {
        touchPan = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, left: viewport.scrollLeft, top: viewport.scrollTop, moved: false };
      } else if (touches.size === 2) {
        const [first, second] = [...touches.values()];
        const rect = viewport.getBoundingClientRect();
        const midpoint = { x: (first.x + second.x) / 2, y: (first.y + second.y) / 2 };
        pinch = {
          distance: Math.max(1, Math.hypot(second.x - first.x, second.y - first.y)),
          zoom,
          contentX: (viewport.scrollLeft + midpoint.x - rect.left) / zoom,
          contentY: (viewport.scrollTop + midpoint.y - rect.top) / zoom,
        };
        touchPan = null;
        suppressCardClick = true;
        viewport.classList.add("is-dragging");
        for (const pointerId of touches.keys()) viewport.setPointerCapture(pointerId);
      }
      return;
    }
    if (event.pointerType === "mouse" && event.button === 0 && event.isPrimary) {
      drag = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, left: viewport.scrollLeft, top: viewport.scrollTop, moved: false };
    }
  });
  viewport.addEventListener("pointermove", (event) => {
    if (event.pointerType === "touch" && touches.has(event.pointerId)) {
      touches.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (pinch && touches.size >= 2) {
        event.preventDefault();
        const [first, second] = [...touches.values()];
        const distance = Math.max(1, Math.hypot(second.x - first.x, second.y - first.y));
        setZoom(pinch.zoom * distance / pinch.distance, {
          clientX: (first.x + second.x) / 2,
          clientY: (first.y + second.y) / 2,
          contentX: pinch.contentX,
          contentY: pinch.contentY,
        });
        return;
      }
      if (!touchPan || touchPan.pointerId !== event.pointerId) return;
      const dx = event.clientX - touchPan.x;
      const dy = event.clientY - touchPan.y;
      if (!touchPan.moved && Math.hypot(dx, dy) > 6) {
        touchPan.moved = true;
        suppressCardClick = true;
        viewport.classList.add("is-dragging");
        viewport.setPointerCapture(event.pointerId);
      }
      if (!touchPan.moved) return;
      event.preventDefault();
      viewport.scrollLeft = touchPan.left - dx;
      viewport.scrollTop = touchPan.top - dy;
      return;
    }
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
    if (event.pointerType === "touch" && touches.has(event.pointerId)) {
      const moved = Boolean(pinch || touchPan?.moved);
      touches.delete(event.pointerId);
      pinch = null;
      if (touches.size === 1) {
        const [pointerId, point] = [...touches.entries()][0];
        touchPan = { pointerId, x: point.x, y: point.y, left: viewport.scrollLeft, top: viewport.scrollTop, moved: true };
      } else {
        touchPan = null;
        viewport.classList.remove("is-dragging");
        if (moved) window.setTimeout(() => { suppressCardClick = false; }, 0);
      }
      return;
    }
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

function layoutForCategory(category) {
  if (!categoryLayouts.has(category.id)) categoryLayouts.set(category.id, explicitTreeLayout(category.nodes));
  return categoryLayouts.get(category.id);
}

function treeContentSize(category) {
  const layout = layoutForCategory(category);
  return {
    width: PADDING * 2 + layout.columnCount * CARD_WIDTH + Math.max(0, layout.columnCount - 1) * GAP_X,
    height: PADDING * 2 + layout.rowCount * CARD_HEIGHT + Math.max(0, layout.rowCount - 1) * GAP_Y,
  };
}

function fittedZoom(category) {
  const viewport = byId("tree-viewport");
  const size = treeContentSize(category);
  const bounds = viewport.getBoundingClientRect();
  return fitTreeZoom(bounds.width, bounds.height, size.width, size.height);
}

function setZoom(value, anchor = null) {
  const category = catalog?.categories.find((item) => item.id === selectedCategoryId) || catalog?.categories[0];
  if (!category) return;
  const viewport = byId("tree-viewport");
  const rect = viewport.getBoundingClientRect();
  const localX = anchor?.clientX == null ? viewport.clientWidth / 2 : anchor.clientX - rect.left;
  const localY = anchor?.clientY == null ? viewport.clientHeight / 2 : anchor.clientY - rect.top;
  const contentX = anchor?.contentX ?? (viewport.scrollLeft + localX) / zoom;
  const contentY = anchor?.contentY ?? (viewport.scrollTop + localY) / zoom;
  zoom = clampTreeZoom(value, fittedZoom(category));
  renderTree();
  viewport.scrollLeft = contentX * zoom - localX;
  viewport.scrollTop = contentY * zoom - localY;
}

function fitWholeTree() {
  const category = catalog?.categories.find((item) => item.id === selectedCategoryId) || catalog?.categories[0];
  if (!category) return;
  zoom = fittedZoom(category);
  renderTree(true);
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
  zoom = clampTreeZoom(zoom, fittedZoom(category));
  const nodes = matchingNodes(category);
  const visibleIds = new Set(nodes.map((node) => node.id));
  const layout = layoutForCategory(category);
  const contentSize = treeContentSize(category);
  const width = Math.max(byId("tree-viewport").clientWidth - 2, contentSize.width * zoom);
  const height = Math.max(byId("tree-viewport").clientHeight - 2, contentSize.height * zoom);
  const stage = byId("tree-stage");
  stage.style.width = `${width}px`;
  stage.style.height = `${height}px`;
  const positions = new Map();
  for (const node of nodes) {
    const slot = layout.slots.get(node.id) ?? node.column;
    positions.set(node.id, {
      x: (PADDING + slot * (CARD_WIDTH + GAP_X)) * zoom,
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
  const inactivePaths = [];
  const activePaths = [];
  for (const [fromId, toId] of category.edges) {
    if (!visibleIds.has(fromId) || !visibleIds.has(toId)) continue;
    const from = positions.get(fromId); const to = positions.get(toId);
    if (!from || !to) continue;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const unlocked = isResearchConnectionUnlocked(catalog.nodes.get(toId), state);
    path.classList.add(unlocked ? "is-active" : "is-inactive");
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
    (unlocked ? activePaths : inactivePaths).push(path);
  }
  svg.replaceChildren(...inactivePaths, ...activePaths);
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
  if (node.id === selectedNodeId) card.classList.add("is-selected");
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
  const defaultLevel = defaultTargetLevel(level, node.maxLevel);
  const levels = level < node.maxLevel
    ? Array.from({ length: node.maxLevel - level }, (_, index) => level + index + 1)
    : [node.maxLevel];
  target.replaceChildren(...levels.map((targetLevel) => {
    const option = create("option", "", `Lv.${targetLevel}`);
    option.value = targetLevel;
    option.selected = targetLevel === defaultLevel;
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
  const effect = create("div", "detail-item detail-effect");
  effect.append(create("span", "", "効果"), create("strong", "", effectFor(node, nextLevel) || "未収録"));
  grid.append(time, facility, effect);
  const resourceBox = create("div", "detail-resources");
  const costs = RESOURCE_KEYS.filter((key) => Number(data.costs[key] || 0) > 0);
  if (costs.length) {
    for (const key of costs) {
      const item = create("div", "detail-resource");
      item.append(create("span", "", RESOURCE_NAMES[state.locale][key]), create("strong", "", formatResource(data.costs[key])));
      resourceBox.append(item);
    }
  } else {
    const item = create("div", "detail-resource");
    item.append(create("span", "", data.costsVerified ? "資源なし" : "資源データ未収録"));
    resourceBox.append(item);
  }
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
    "setting-vip": ["vipLevel", true], "setting-castle": ["castleLevel", true], "setting-castle-mana": ["castleManaStage", true], "setting-academy": ["academyLevel", true],
    "setting-construction-speed": ["constructionSpeedPercent", false], "setting-construction-boost": ["constructionSpeedBoostPercent", false],
    "setting-speed": ["researchSpeedPercent", false], "setting-boost": ["researchSpeedBoostPercent", false], "setting-helps": ["maxGuildHelps", true],
  };
  for (const [id, [key, integer]] of Object.entries(inputs)) {
    byId(id).addEventListener("input", (event) => {
      state.settings[key] = Math.max(0, integer ? Math.trunc(Number(event.target.value) || 0) : Number(event.target.value) || 0);
      if (key === "vipLevel") state.settings[key] = Math.max(1, Math.min(15, state.settings[key]));
      if (key === "castleLevel" || key === "academyLevel") state.settings[key] = Math.max(1, Math.min(25, state.settings[key]));
      if (key === "castleManaStage") state.settings[key] = state.settings.castleLevel === 25 ? Math.max(0, Math.min(5, state.settings[key])) : 0;
      if (key === "castleLevel") {
        if (state.settings.castleLevel < 25) state.settings.castleManaStage = 0;
        castleTargetLevel = Math.min(25, state.settings.castleLevel + 1);
        state.settings.maxGuildHelps = guildHelpCount(state.settings);
      }
      if (key === "maxGuildHelps") state.settings.maxGuildHelps = guildHelpCount(state.settings);
      if (key === "castleLevel" || key === "castleManaStage") {
        castleTargetManaStage = state.settings.castleLevel === 25 && state.settings.castleManaStage < 5
          ? state.settings.castleManaStage + 1
          : state.settings.castleManaStage;
        state.settings.castleTargetManaStage = castleTargetManaStage;
      }
      updateGuildHelpLimit(); updateVipHint(); scheduleSave(); renderTree(); refreshCurrentPlan(); renderCastle(); if (planMode === "shortest") renderShortest();
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
  byId("language-select").addEventListener("change", (event) => { state.locale = event.target.value; scheduleSave(); populateSettings(); renderCategoryOptions(); renderTree(); renderPlan(); renderShortest(); renderTasks(); renderCastle(); renderCatalogStatus(); });
  byId("export-backup").addEventListener("click", exportBackup);
  byId("import-backup").addEventListener("change", importBackup);
  byId("reset-player").addEventListener("click", () => {
    if (!window.confirm("プレイヤー設定と全研究レベルをクリアしますか？")) return;
    const locale = state.locale; state = defaultState(); state.locale = locale; castleTargetLevel = 0; castleTargetManaStage = 0; saveNow(); populateSettings(); renderCategoryOptions(); renderTree(true); currentPlan = null; renderPlan(); renderShortest(); renderTasks(); renderCastle(); toast("設定をクリアしました");
  });
}

function populateSettings() {
  byId("setting-vip").value = state.settings.vipLevel;
  byId("setting-castle").value = state.settings.castleLevel;
  byId("setting-castle-mana").value = state.settings.castleManaStage;
  byId("setting-castle-mana").disabled = state.settings.castleLevel !== 25;
  byId("setting-construction-speed").value = state.settings.constructionSpeedPercent;
  byId("setting-construction-boost").value = state.settings.constructionSpeedBoostPercent;
  byId("setting-academy").value = state.settings.academyLevel;
  byId("setting-speed").value = state.settings.researchSpeedPercent;
  byId("setting-boost").value = state.settings.researchSpeedBoostPercent;
  updateGuildHelpLimit();
  byId("language-select").value = state.locale;
  byId("resource-display-mode").value = state.settings.resourceDisplayMode;
  document.querySelectorAll("[data-resource]").forEach((input) => { input.value = state.settings.resources[input.dataset.resource] || 0; input.previousElementSibling.textContent = RESOURCE_NAMES[state.locale][input.dataset.resource]; });
  updateVipHint();
  populateBulkCategoryOptions();
  renderBulkLevels();
  renderCastle();
}

function updateGuildHelpLimit() {
  const input = byId("setting-helps");
  if (!input) return;
  const limit = maxGuildHelpsForCastle(state.settings.castleLevel);
  state.settings.maxGuildHelps = guildHelpCount(state.settings);
  input.max = String(limit);
  input.value = String(state.settings.maxGuildHelps);
  input.title = `城Lv.${state.settings.castleLevel}では最大${limit}回です。`;
  const hint = byId("guild-help-limit");
  if (hint) hint.textContent = `上限 ${limit}回`;
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
    row.append(open, numberStepper(input), create("span", "max-label", `/ ${node.maxLevel}`)); return row;
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

function bindCastle() {
  byId("construction-target").addEventListener("change", (event) => {
    constructionTargetBuildingId = event.target.value || "castle";
    constructionFacilityTargetLevel = 0;
    renderCastle();
  });
  byId("castle-current").addEventListener("input", (event) => {
    if (constructionTargetBuildingId !== "castle") {
      const building = castleCatalog.buildings.get(constructionTargetBuildingId);
      const minimum = Number(minimumBuildingLevels(castleCatalog, state.settings.castleLevel)[constructionTargetBuildingId] || 0);
      const current = Math.max(minimum, Math.min(building.maxLevel, Math.trunc(Number(event.target.value) || 0)));
      state.buildingLevels[constructionTargetBuildingId] = current;
      constructionFacilityTargetLevel = Math.min(building.maxLevel, current + 1);
      scheduleSave();
      renderCastle();
      return;
    }
    state.settings.castleLevel = Math.max(1, Math.min(25, Math.trunc(Number(event.target.value) || 1)));
    if (state.settings.castleLevel < 25) state.settings.castleManaStage = 0;
    byId("setting-castle").value = state.settings.castleLevel;
    castleTargetLevel = Math.min(25, state.settings.castleLevel + 1);
    castleTargetManaStage = state.settings.castleLevel === 25 && state.settings.castleManaStage < castleCatalog.maxManaStage
      ? state.settings.castleManaStage + 1
      : 0;
    state.settings.castleTargetLevel = castleTargetLevel;
    state.settings.castleTargetManaStage = castleTargetManaStage;
    scheduleSave();
    renderCastle();
  });
  byId("castle-current-mana").addEventListener("input", (event) => {
    if (constructionTargetBuildingId !== "castle") return;
    state.settings.castleManaStage = state.settings.castleLevel === 25
      ? Math.max(0, Math.min(castleCatalog.maxManaStage, Math.trunc(Number(event.target.value) || 0)))
      : 0;
    byId("setting-castle-mana").value = state.settings.castleManaStage;
    castleTargetManaStage = state.settings.castleManaStage < castleCatalog.maxManaStage
      ? state.settings.castleManaStage + 1
      : state.settings.castleManaStage;
    state.settings.castleTargetManaStage = castleTargetManaStage;
    scheduleSave();
    renderCastle();
  });
  byId("castle-target").addEventListener("input", (event) => {
    if (constructionTargetBuildingId !== "castle") {
      const building = castleCatalog.buildings.get(constructionTargetBuildingId);
      const current = Math.max(0, Number(state.buildingLevels[constructionTargetBuildingId] || 0));
      constructionFacilityTargetLevel = Math.max(current, Math.min(building.maxLevel, Math.trunc(Number(event.target.value) || current)));
      renderCastle();
      return;
    }
    castleTargetLevel = Math.max(state.settings.castleLevel, Math.min(25, Math.trunc(Number(event.target.value) || state.settings.castleLevel)));
    if (castleTargetLevel < 25) castleTargetManaStage = 0;
    state.settings.castleTargetLevel = castleTargetLevel;
    state.settings.castleTargetManaStage = castleTargetManaStage;
    scheduleSave();
    renderCastle();
  });
  byId("castle-target-mana").addEventListener("input", (event) => {
    if (constructionTargetBuildingId !== "castle") return;
    const minimum = state.settings.castleLevel === 25 ? state.settings.castleManaStage : 0;
    castleTargetManaStage = castleTargetLevel === 25
      ? Math.max(minimum, Math.min(castleCatalog.maxManaStage, Math.trunc(Number(event.target.value) || 0)))
      : 0;
    state.settings.castleTargetManaStage = castleTargetManaStage;
    scheduleSave();
    renderCastle();
  });
}

function renderCastle() {
  if (!castleCatalog) return;
  const targetSelect = byId("construction-target");
  if (!targetSelect.options.length) {
    targetSelect.replaceChildren(...castleCatalog.order.map((buildingId) => {
      const option = create("option", "", castleCatalog.buildingName(buildingId, state.locale));
      option.value = buildingId;
      return option;
    }));
  }
  if (!castleCatalog.buildings.has(constructionTargetBuildingId)) constructionTargetBuildingId = "castle";
  targetSelect.value = constructionTargetBuildingId;
  const isCastleTarget = constructionTargetBuildingId === "castle";
  const currentCastle = Math.max(1, Math.min(25, Number(state.settings.castleLevel) || 1));
  const currentManaStage = currentCastle === 25 ? Math.max(0, Math.min(castleCatalog.maxManaStage, Number(state.settings.castleManaStage) || 0)) : 0;
  state.settings.castleManaStage = currentManaStage;
  if (!castleTargetLevel) castleTargetLevel = Number(state.settings.castleTargetLevel || 0) || Math.min(25, currentCastle + 1);
  if (castleTargetLevel < currentCastle) castleTargetLevel = currentCastle;
  if (castleTargetLevel === 25 && isCastleTarget) {
    if (!castleTargetManaStage) {
      castleTargetManaStage = Number(state.settings.castleTargetManaStage || 0);
      if (currentCastle === 25 && castleTargetManaStage <= currentManaStage && currentManaStage < castleCatalog.maxManaStage) castleTargetManaStage = currentManaStage + 1;
    }
    const minimum = currentCastle === 25 ? currentManaStage : 0;
    castleTargetManaStage = Math.max(minimum, Math.min(castleCatalog.maxManaStage, castleTargetManaStage));
  } else if (isCastleTarget) castleTargetManaStage = 0;
  if (isCastleTarget) {
    state.settings.castleTargetLevel = castleTargetLevel;
    state.settings.castleTargetManaStage = castleTargetManaStage;
  }
  const minimums = minimumBuildingLevels(castleCatalog, currentCastle);
  const selectedBuilding = castleCatalog.buildings.get(constructionTargetBuildingId);
  const selectedMinimum = isCastleTarget ? 1 : Number(minimums[constructionTargetBuildingId] || 0);
  const selectedCurrent = isCastleTarget
    ? currentCastle
    : Math.max(selectedMinimum, Number(state.buildingLevels[constructionTargetBuildingId] || 0));
  if (!isCastleTarget && (!constructionFacilityTargetLevel || constructionFacilityTargetLevel < selectedCurrent)) {
    constructionFacilityTargetLevel = Math.min(selectedBuilding.maxLevel, selectedCurrent + 1);
  }
  const selectedTarget = isCastleTarget ? castleTargetLevel : constructionFacilityTargetLevel;
  byId("castle-current").min = String(selectedMinimum);
  byId("castle-current").max = String(selectedBuilding.maxLevel);
  byId("castle-current").value = String(selectedCurrent);
  byId("castle-current-mana").value = String(currentManaStage);
  byId("castle-current-mana").disabled = currentCastle !== 25;
  byId("castle-current-mana-field").hidden = !isCastleTarget;
  byId("castle-target").min = String(selectedCurrent);
  byId("castle-target").max = String(selectedBuilding.maxLevel);
  byId("castle-target").value = String(selectedTarget);
  byId("castle-target-mana").min = String(currentCastle === 25 ? currentManaStage : 0);
  byId("castle-target-mana").value = String(castleTargetManaStage);
  byId("castle-target-mana").disabled = castleTargetLevel !== 25;
  byId("castle-target-mana-field").hidden = !isCastleTarget;
  byId("setting-castle-mana").value = String(currentManaStage);
  byId("setting-castle-mana").disabled = currentCastle !== 25;
  for (const inputId of ["castle-current", "castle-current-mana", "castle-target", "castle-target-mana", "setting-castle-mana"]) {
    refreshNumberStepper(byId(inputId));
  }
  const plan = createCastlePlan(castleCatalog, state, castleTargetLevel, castleTargetManaStage, {
    targetBuildingId: constructionTargetBuildingId,
    targetBuildingLevel: selectedTarget,
  });
  const summary = byId("castle-summary");
  const summaryItems = [
    [castleCatalog.buildingName(constructionTargetBuildingId, state.locale), `${castleProgressLabel(selectedCurrent, isCastleTarget ? plan.currentManaStage : 0)} → ${castleProgressLabel(plan.targetBuildingLevel, isCastleTarget ? plan.targetManaStage : 0)}`],
    ["有効建設速度", `+${(Number(state.settings.constructionSpeedPercent || 0) + Number(state.settings.constructionSpeedBoostPercent || 0)).toLocaleString(state.locale)}%`],
    ["合計時間", formatDuration(plan.totals.adjustedSeconds)],
  ];
  byId("construction-selection").textContent = `${castleCatalog.buildingName(constructionTargetBuildingId, state.locale)}　Lv.${selectedCurrent} → Lv.${selectedTarget}`;
  for (const key of CASTLE_RESOURCE_KEYS.filter((key) => Number(plan.totals.costs[key] || 0) > 0)) {
    summaryItems.push([RESOURCE_NAMES[state.locale][key], formatResource(plan.totals.costs[key])]);
  }
  if (plan.totals.totalGems > 0) summaryItems.push(["ジェム目安", Number(plan.totals.totalGems).toLocaleString(state.locale)]);
  summary.replaceChildren(...summaryItems.map(([label, value]) => {
    const card = create("div", "castle-summary-card");
    card.append(create("span", "", label), create("strong", "", value));
    return card;
  }));

  const requiredById = new Map(plan.buildings.map((item) => [item.buildingId, item.targetLevel]));
  const levelList = byId("castle-level-list");
  levelList.replaceChildren(...castleCatalog.order.filter((buildingId) => buildingId !== "castle").map((buildingId) => {
    const building = castleCatalog.buildings.get(buildingId);
    const minimum = Number(minimums[buildingId] || 0);
    const value = Math.max(minimum, Number(state.buildingLevels[buildingId] || 0));
    const row = create("label", "castle-level-row");
    row.append(create("strong", "", castleCatalog.buildingName(buildingId, state.locale)));
    const input = create("input");
    input.type = "number";
    input.inputMode = "numeric";
    input.min = String(minimum);
    input.max = String(building.maxLevel);
    input.value = String(value);
    input.setAttribute("aria-label", `${castleCatalog.buildingName(buildingId, state.locale)}の現在レベル`);
    input.addEventListener("change", () => {
      state.buildingLevels[buildingId] = Math.max(minimum, Math.min(building.maxLevel, Math.trunc(Number(input.value) || 0)));
      scheduleSave();
      renderCastle();
    });
    const required = Math.max(value, Number(requiredById.get(buildingId) || value));
    row.append(numberStepper(input), create("small", "", `必要 ${required}`));
    return row;
  }));

  const list = byId("castle-plan-list");
  if (!plan.steps.length) {
    list.replaceChildren(create("div", "castle-empty", "目標レベルまでの建設は完了しています。"));
  } else {
    list.replaceChildren(...plan.steps.map((step) => {
      const card = create("article", "castle-step-row");
      const main = create("div", "castle-step-main");
      main.append(
        create("strong", "castle-step-name", `${step.manaStage ? castleCatalog.manaName(state.locale) : castleCatalog.buildingName(step.buildingId, state.locale)} ${castleProgressLabel(step.level, step.manaStage)}`),
        resourceDetails(step.costs, CASTLE_RESOURCE_KEYS),
      );
      const footer = create("div", "castle-step-footer");
      const time = create("strong", "plan-row-time", formatDuration(step.adjustedSeconds));
      time.title = `基礎時間 ${formatDuration(step.baseSeconds)}`;
      const complete = create("button", "step-complete", "完了");
      complete.type = "button";
      complete.addEventListener("click", () => completeCastleStep(step));
      footer.append(time, complete);
      card.append(main, footer);
      return card;
    }));
  }
  byId("castle-issues").textContent = plan.issues.join(" / ");
}

function completeCastleStep(step) {
  const selectedTarget = constructionTargetBuildingId === "castle"
    ? castleTargetLevel
    : constructionFacilityTargetLevel;
  const plan = createCastlePlan(castleCatalog, state, castleTargetLevel, castleTargetManaStage, {
    targetBuildingId: constructionTargetBuildingId,
    targetBuildingLevel: selectedTarget,
  });
  if (!plan.steps.some((item) => item.buildingId === step.buildingId && item.level === step.level && Number(item.manaStage || 0) === Number(step.manaStage || 0))) return;
  const completed = buildingLevelsAfterCastleStep(
    plan,
    step,
    state.settings.castleLevel,
    state.settings.castleManaStage,
    state.buildingLevels,
  );
  state.settings.castleLevel = completed.castleLevel;
  state.settings.castleManaStage = completed.castleManaStage;
  state.buildingLevels = completed.buildingLevels;
  state.settings.castleTargetLevel = castleTargetLevel;
  state.settings.castleTargetManaStage = castleTargetManaStage;
  byId("setting-castle").value = state.settings.castleLevel;
  byId("setting-castle-mana").value = state.settings.castleManaStage;
  saveNow();
  renderCastle();
  toast(`${step.manaStage ? castleCatalog.manaName(state.locale) : castleCatalog.buildingName(step.buildingId, state.locale)} ${castleProgressLabel(step.level, step.manaStage)}まで反映しました`);
}

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
    const imported = stateFromBackup(JSON.parse(await file.text())); imported.locale = state.locale; state = imported; castleTargetLevel = 0; saveNow(); populateSettings(); renderCategoryOptions(); renderTree(true); currentPlan = null; renderPlan(); renderShortest(); renderTasks(); renderCastle(); toast("バックアップを読み込みました");
  } catch (error) { toast(error.message); }
  finally { event.target.value = ""; }
}

function bindPlans() {
  byId("plan-target-mode").addEventListener("click", () => setPlanMode("target"));
  byId("plan-shortest-mode").addEventListener("click", () => setPlanMode("shortest"));
  byId("plan-tasks-mode").addEventListener("click", () => setPlanMode("tasks"));
  byId("register-plan").addEventListener("click", registerCurrentPlan);
  byId("complete-plan").addEventListener("click", completeCurrentPlan);
  byId("shortest-limit").addEventListener("change", renderShortest);
  byId("resource-display-mode").addEventListener("change", (event) => {
    state.settings.resourceDisplayMode = event.target.value === "short" ? "short" : "exact";
    saveNow(); renderPlan(); renderShortest(); renderTasks(); renderCastle();
  });
  byId("resource-display-mode").value = state.settings.resourceDisplayMode;
}

function setPlanMode(mode) {
  planMode = mode;
  byId("plan-target-mode").classList.toggle("is-active", mode === "target");
  byId("plan-shortest-mode").classList.toggle("is-active", mode === "shortest");
  byId("plan-tasks-mode").classList.toggle("is-active", mode === "tasks");
  byId("target-plan-view").hidden = mode !== "target";
  byId("shortest-plan-view").hidden = mode !== "shortest";
  byId("task-plan-view").hidden = mode !== "tasks";
  if (mode === "shortest") renderShortest();
  if (mode === "tasks") renderTasks();
}

function buildTargetPlan(researchId, level) {
  try { currentPlan = createPlan(catalog, state, researchId, level); setPlanMode("target"); renderPlan(); }
  catch (error) { toast(error.message); }
}

function refreshCurrentPlan() {
  if (!currentPlan) { renderTasks(); return; }
  const { targetId, targetLevel } = currentPlan;
  try { currentPlan = createPlan(catalog, state, targetId, targetLevel); }
  catch (error) { currentPlan = null; toast(error.message); }
  renderPlan();
  renderTasks();
}

function registerCurrentPlan() {
  if (!currentPlan?.steps.length) return;
  const exists = state.planTasks.some((task) => task.researchId === currentPlan.targetId && task.targetLevel === currentPlan.targetLevel);
  if (exists) { toast("同じ目標レベルのタスクは登録済みです"); return; }
  state.planTasks.push({ researchId: currentPlan.targetId, targetLevel: currentPlan.targetLevel, createdAt: new Date().toISOString() });
  saveNow(); renderTasks(); toast("研究計画をタスクに登録しました");
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
  renderTasks();
  toast(`目標研究と前提研究を含む${changed.length}件のレベルを反映しました`);
}

function renderPlan() {
  byId("plan-placeholder").hidden = Boolean(currentPlan);
  byId("plan-result").hidden = !currentPlan;
  if (!currentPlan) return;
  const target = catalog.nodes.get(currentPlan.targetId);
  const targetCategory = catalog.categories.find((item) => item.id === target.categoryId);
  byId("plan-target-name").textContent = `${catalog.nodeName(target, state.locale)} Lv.${currentPlan.targetLevel}`;
  byId("plan-steps-title").textContent = `必要な研究（${catalog.categoryTitle(targetCategory, state.locale)}）`;
  const partialTime = currentPlan.totals.unknownTime ? " + 未確認" : "";
  byId("plan-total-time").textContent = `開始時 ${formatDuration(currentPlan.totals.adjustedSeconds)}${partialTime}`;
  const totalHelpTime = byId("plan-total-help-time");
  const helpCount = guildHelpCount(state.settings);
  totalHelpTime.hidden = helpCount === 0;
  totalHelpTime.textContent = helpCount > 0
    ? `ヘルプ後 ${formatDuration(currentPlan.totals.afterHelpSeconds)}${partialTime}`
    : "";
  byId("plan-wisdom-summary").textContent = wisdomText(currentPlan.totals.technolabeCount, currentPlan.totals.technolabeEfficiencyPercent, currentPlan.totals.unknownTechnolabe);
  const resources = RESOURCE_NAMES[state.locale];
  const usedResources = RESOURCE_KEYS.filter((key) => Number(currentPlan.totals.costs[key] || 0) > 0);
  byId("resource-summary").replaceChildren(...usedResources.map((key) => {
    const chip = create("div", "resource-chip"); const needed = currentPlan.totals.costs[key] || 0; const available = state.settings.resources[key] || 0;
    if (needed > available) chip.classList.add("is-short");
    chip.append(create("span", "", resources[key]), create("strong", "", formatResource(needed)), create("span", "", needed > available ? `不足 ${formatResource(needed - available)}` : "所持数以内")); return chip;
  }));
  if (!usedResources.length) byId("resource-summary").append(create("div", "callout", "必要資源なし"));
  byId("plan-steps").replaceChildren(...currentPlan.steps.map((step) => planRow(step, { showCategory: false })));
  byId("complete-plan").disabled = currentPlan.steps.length === 0;
  byId("register-plan").disabled = currentPlan.steps.length === 0;
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
  list.replaceChildren(...steps.map((step) => planRow(step, { selected: step.researchId === selectedNodeId })));
  const selected = steps.find((step) => step.researchId === selectedNodeId);
  const banner = byId("shortest-selected");
  banner.hidden = !selected;
  if (selected) banner.textContent = `選択中：${catalog.nodeName(catalog.nodes.get(selected.researchId), state.locale)} Lv.${selected.level}`;
  if (!steps.length) list.append(create("div", "callout", "現在の条件で開始でき、時間データが確認済みの研究はありません。"));
}

function renderTasks() {
  if (!catalog) return;
  const list = byId("task-list");
  list.replaceChildren();
  for (const task of state.planTasks) {
    const node = catalog.nodes.get(task.researchId);
    if (!node || task.targetLevel > node.maxLevel) continue;
    let plan;
    try { plan = createPlan(catalog, state, task.researchId, task.targetLevel); }
    catch { continue; }
    const card = create("article", "task-card");
    const heading = create("div", "task-card-heading");
    const title = create("h3", "", `${catalog.nodeName(node, state.locale)} Lv.${task.targetLevel}`);
    const remaining = create("strong", "", plan.steps.length ? `開始時 ${formatDuration(plan.totals.adjustedSeconds)}` : "完了済み");
    heading.append(title, remaining);
    const helpCount = guildHelpCount(state.settings);
    const helpSummary = helpCount > 0 && plan.steps.length
      ? ` / ヘルプ後 ${formatDuration(plan.totals.afterHelpSeconds)}`
      : "";
    const meta = create("p", "muted", `残り ${plan.steps.length}手順${helpSummary} / ${wisdomText(plan.totals.technolabeCount, plan.totals.technolabeEfficiencyPercent, plan.totals.unknownTechnolabe)}`);
    const resources = create("div", "task-resources");
    const used = RESOURCE_KEYS.filter((key) => Number(plan.totals.costs[key] || 0) > 0);
    for (const key of used) resources.append(create("span", "", `${RESOURCE_NAMES[state.locale][key]} ${formatResource(plan.totals.costs[key])}`));
    if (!used.length) resources.append(create("span", "", "必要資源なし"));
    const actions = create("div", "button-row task-actions");
    const show = create("button", "primary", "計画を表示"); show.type = "button"; show.addEventListener("click", () => { buildTargetPlan(task.researchId, task.targetLevel); showTab("plan"); });
    const remove = create("button", "danger", "削除"); remove.type = "button"; remove.addEventListener("click", () => { state.planTasks = state.planTasks.filter((saved) => saved !== task); saveNow(); renderTasks(); });
    actions.append(show, remove); card.append(heading, meta, resources, actions); list.append(card);
  }
  if (!list.children.length) list.append(create("div", "callout", "登録した研究計画はありません。目標研究の計画からタスクに登録できます。"));
}

function planRow(step, { showCategory = true, selected = false } = {}) {
  const node = catalog.nodes.get(step.researchId);
  const row = create("article", "plan-row");
  if (selected) row.classList.add("is-selected");
  const nameButton = create("button", "", `${catalog.nodeName(node, state.locale)} Lv.${step.level}`); nameButton.type = "button";
  nameButton.addEventListener("click", () => jumpToNode(node));
  const categoryName = catalog.categoryTitle(catalog.categories.find((item) => item.id === node.categoryId), state.locale);
  const effect = effectFor(node, step.level) || "効果未収録";
  const main = create("div", "plan-step-main");
  main.append(nameButton);
  if (showCategory) main.append(create("span", "plan-row-category", categoryName));
  else main.classList.add("is-single-category");
  main.append(
    create("span", "plan-row-effect", `効果 ${effect}`),
    resourceDetails(step.costs, RESOURCE_KEYS),
  );
  const footer = create("div", "plan-step-footer");
  const timing = create("div", "plan-step-timing");
  timing.append(create("strong", "plan-row-time", step.adjustedSeconds == null ? "開始時 未確認" : `開始時 ${formatDuration(step.adjustedSeconds)}`));
  const helpCount = guildHelpCount(state.settings);
  if (helpCount > 0) {
    timing.append(create("span", "plan-row-help", step.afterHelpSeconds == null ? "ヘルプ後 未確認" : `ヘルプ後 ${formatDuration(step.afterHelpSeconds)}`));
  }
  timing.append(create("span", "plan-row-wisdom", wisdomText(step.technolabeCount, step.technolabeEfficiencyPercent)));
  const complete = create("button", "step-complete", "研究完了"); complete.type = "button"; complete.addEventListener("click", () => completePlanStep(step));
  footer.append(timing, complete);
  row.append(main, footer); return row;
}

function resourceDetails(costs, keys) {
  const details = create("details", "plan-resource-details");
  const used = keys.filter((key) => Number(costs[key] || 0) > 0);
  const summary = create("summary", "", used.length ? `資材 ${used.length}` : "資材なし");
  const resources = create("div", "plan-row-resources");
  for (const key of used) {
    const item = create("div", "plan-resource-item");
    item.append(create("span", "", RESOURCE_NAMES[state.locale][key]), create("strong", "", formatResource(costs[key])));
    resources.append(item);
  }
  if (!used.length) resources.append(create("div", "plan-resource-item", "必要資材なし"));
  details.append(summary, resources);
  return details;
}

function wisdomText(count, efficiencyPercent, unknownCount = 0) {
  if (count == null) return "叡智の輪 未確認";
  if (!count) return unknownCount ? `叡智の輪 未確認（${unknownCount}件）` : "叡智の輪 -";
  const text = `叡智の輪 ${count}個 / 効率${Number(efficiencyPercent || 0).toFixed(1)}%`;
  return unknownCount ? `${text}（${unknownCount}件未確認）` : text;
}

function completePlanStep(step) {
  const current = Number(state.researchLevels[step.researchId] || 0);
  if (step.level <= current) return;
  state.researchLevels[step.researchId] = step.level;
  saveNow(); populateSettings(); renderCategoryOptions(); renderTree(); refreshCurrentPlan(); renderShortest(); renderTasks();
  toast(`${catalog.nodeName(catalog.nodes.get(step.researchId), state.locale)} Lv.${step.level}を反映しました`);
}

function formatResource(value) {
  return formatResourceAmount(value, state.settings.resourceDisplayMode, state.locale);
}

function jumpToNode(node) {
  selectedNodeId = node.id;
  selectedCategoryId = node.categoryId; byId("tree-search").value = ""; byId("instant-only").checked = false;
  renderCategoryOptions(); renderTree(); showTab("tree");
  renderShortest();
  requestAnimationFrame(() => {
    const card = document.querySelector(`[data-node-id="${CSS.escape(node.id)}"]`);
    card?.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
    card?.focus({ preventScroll: true });
  });
}

function numberStepper(input) {
  if (!input || input.parentElement?.classList.contains("number-stepper")) return input?.parentElement || input;
  const wrapper = create("span", "number-stepper");
  const decrease = create("button", "", "−");
  const increase = create("button", "", "＋");
  decrease.type = "button";
  increase.type = "button";
  decrease.setAttribute("aria-label", `${input.getAttribute("aria-label") || "値"}を1下げる`);
  increase.setAttribute("aria-label", `${input.getAttribute("aria-label") || "値"}を1上げる`);
  const step = (direction) => {
    const minimum = input.min === "" ? -Infinity : Number(input.min);
    const maximum = input.max === "" ? Infinity : Number(input.max);
    const next = Math.max(minimum, Math.min(maximum, Number(input.value || 0) + direction));
    input.value = String(next);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    refreshNumberStepper(input);
  };
  decrease.addEventListener("click", () => step(-1));
  increase.addEventListener("click", () => step(1));
  input.addEventListener("input", () => refreshNumberStepper(input));
  wrapper.append(decrease, input, increase);
  refreshNumberStepper(input);
  return wrapper;
}

function refreshNumberStepper(input) {
  const wrapper = input?.parentElement;
  if (!wrapper?.classList.contains("number-stepper")) return;
  const [decrease, , increase] = wrapper.children;
  const value = Number(input.value || 0);
  decrease.disabled = input.disabled || (input.min !== "" && value <= Number(input.min));
  increase.disabled = input.disabled || (input.max !== "" && value >= Number(input.max));
}

function installStaticNumberSteppers() {
  document.querySelectorAll('input[type="number"]:not(#node-level-number)').forEach((input) => {
    if (input.closest(".bulk-level-row") || input.closest(".castle-level-row")) return;
    const parent = input.parentNode;
    const next = input.nextSibling;
    const wrapper = numberStepper(input);
    parent?.insertBefore(wrapper, next);
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
