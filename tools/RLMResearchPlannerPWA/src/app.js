import { currentEffect, loadCatalog } from "./catalog.js?v=0.1.4-b1";
import { adjustedTime, createPlan, defaultTargetLevel, formatDuration, isInstantNextLevel, isResearchConnectionUnlocked, isTechnolabeRecommended, paginateItems, researchLevelsAfterPlan, shortestAvailable, technolabeUsage } from "./planning.js?v=0.1.4-b1";
import { RESOURCE_KEYS, backupPayload, defaultState, freeSecondsForVip, guildHelpCount, hasSavedState, loadState, maxGuildHelpsForCastle, mergeResearchDirectiveTasks, researchDirectiveFromPayload, researchDirectivePayload, saveState, stateFromBackup } from "./state.js?v=0.1.4-b1";
import { explicitTreeLayout, visibleTreeLayout } from "./tree-layout.js?v=0.1.4-b1";
import { clampTreeZoom, fitTreeZoom } from "./tree-zoom.js?v=0.1.4-b1";
import { formatResourceAmount } from "./resource-format.js?v=0.1.4-b1";
import { CASTLE_RESOURCE_KEYS, buildingLevelsAfterCastleStep, castleProgressLabel, createCastlePlan, loadCastleCatalog, minimumBuildingLevels } from "./castle-planning.js?v=0.1.4-b1";
import { applyDocumentLanguage, installLanguagePack, languagePackTemplate, loadBundledLanguagePacks, loadLanguagePacks, packText, removeLanguagePack, resolveLanguagePack, selectPreferredLocale, translateStatic } from "./language-pack.js?v=0.1.4-b1";
import { PAID_GOALS, PAID_ITEM_KINDS, defaultGemValueEach, defaultPointsEach, emptyPaidOffer, minimumGemsForSpeedupSeconds, paidKindHasTime, paidOfferExchangePayload, paidOffersFromExchangePayload, sanitizePaidOffer, sortedPaidOffers, summarizePaidOffer } from "./paid-value.js?v=0.1.4-b1";
import { SPEEDUP_KINDS, addPaidItemsToInventory, deleteSpeedupInventoryEntry as deleteOwnedSpeedupEntry, normalizeSpeedupInventory, recommendPaidOffers, saveSpeedupInventoryEntry as saveOwnedSpeedupEntry, speedupCoverage } from "./speedup-inventory.js?v=0.1.4-b1";
import { allocateTalentPlan, expandTalentTargets, loadTalentCatalog, talentDirectiveFromPayload, talentDirectivePayload, talentLayoutColumns, talentPlayerLevelRequirement, talentPointsForPlayerLevel } from "./talent-planning.js?v=0.1.4-b1";

const RELEASE_VERSION = "0.1.4";
const DEVELOPMENT_BUILD = 1;
const ASSET_VERSION = "0.1.4-b1";
const IS_PREVIEW = /\/preview(?:\/|$)/u.test(window.location.pathname);
const APP_VERSION = RELEASE_VERSION;
const CARD_WIDTH = 250;
const CARD_HEIGHT = 174;
const GAP_X = 42;
const GAP_Y = 62;
const PADDING = 36;

let catalog;
let castleCatalog;
let talentCatalog;
let effectLabels = {};
let messages = {};
let localeManifest = null;
let bundledLanguagePacks = {};
let languagePacks = loadLanguagePacks();
let activeLanguagePack = null;
const hadSavedState = hasSavedState();
let state = loadState();
let selectedCategoryId = "";
let selectedBulkCategoryId = "";
let selectedNodeId = "";
let zoom = window.innerWidth < 650 ? 0.72 : 1;
let activeTab = "tree";
let playerView = "level";
let planMode = "target";
let planDirty = false;
let shortestPage = 0;
let currentPlan = null;
let castleTargetLevel = 0;
let castleTargetManaStage = 0;
let constructionTargetBuildingId = "castle";
let constructionFacilityTargetLevel = 0;
let toastTimer;
let saveTimer;
let suppressCardClick = false;
let paidDraft = emptyPaidOffer();
let paidEditingId = "";
let paidView = "input";
let paidItemEditingIndex = -1;
let speedupEditingIndex = -1;
let talentAutoFollowPending = false;
const categoryLayouts = new Map();

const byId = (id) => document.getElementById(id);
const create = (tag, className = "", text = "") => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== "") { node.textContent = text; node.dir = "auto"; }
  return node;
};

function ensureTalentPlan() {
  if (!talentCatalog || state.talentPlan.length) return;
  const preset = talentCatalog.presetById.get(state.talentPresetId) || talentCatalog.presets[0];
  state.talentPresetId = preset.id;
  state.talentPlan = expandTalentTargets(talentCatalog, preset.targets);
  if (!state.talentPlanName) state.talentPlanName = talentCatalog.presetName(preset, state.locale);
}

function syncTalentPointCapacity() {
  if (!talentCatalog) return { levelPoints: 0, researchPoints: 0, totalPoints: 0 };
  const levelPoints = talentPointsForPlayerLevel(talentCatalog, state.settings.playerLevel);
  const researchPoints = Math.max(0, Math.trunc(Number(state.researchLevels.military_command_hidden_talent) || 0));
  const totalPoints = levelPoints + researchPoints;
  state.talentAvailablePoints = totalPoints;
  return { levelPoints, researchPoints, totalPoints };
}

function renderTalentPointCapacity() {
  const points = syncTalentPointCapacity();
  if (byId("talent-level-points")) byId("talent-level-points").textContent = points.levelPoints.toLocaleString(state.locale);
  if (byId("talent-research-points")) byId("talent-research-points").textContent = `+${points.researchPoints.toLocaleString(state.locale)}`;
  if (byId("talent-total-points")) byId("talent-total-points").textContent = points.totalPoints.toLocaleString(state.locale);
  if (byId("talent-available-points")) byId("talent-available-points").textContent = points.totalPoints.toLocaleString(state.locale);
  return points;
}

async function start() {
  try {
    const [loadedCatalog, loadedCastleCatalog, loadedTalentCatalog, bundledLanguages] = await Promise.all([
      loadCatalog("./data/research-dataset", ASSET_VERSION),
      loadCastleCatalog(`./data/buildings/castle_catalog.json?v=${ASSET_VERSION}`),
      loadTalentCatalog(`./data/talents/catalog.json?v=${ASSET_VERSION}`),
      loadBundledLanguagePacks("./data/i18n/manifest.json", ASSET_VERSION),
    ]);
    catalog = loadedCatalog;
    castleCatalog = loadedCastleCatalog;
    talentCatalog = loadedTalentCatalog;
    syncTalentPointCapacity();
    ensureTalentPlan();
    localeManifest = bundledLanguages.manifest;
    bundledLanguagePacks = bundledLanguages.packs;
    if (!hadSavedState) {
      const browserLanguages = globalThis.navigator?.languages?.length
        ? [...globalThis.navigator.languages]
        : [globalThis.navigator?.language || ""];
      state.locale = selectPreferredLocale(
        browserLanguages,
        [...Object.keys(bundledLanguagePacks), ...Object.keys(languagePacks)],
        localeManifest.fallbackLocale,
      );
      try { saveState(state); } catch { /* Keep the selected language for this session. */ }
    }
    activateLanguage(state.locale, { save: false, render: false });
    selectedCategoryId = catalog.categories[0]?.id || "";
    selectedBulkCategoryId = selectedCategoryId;
    bindNavigation();
    bindTreeControls();
    bindDialog();
    bindSettings();
    bindPlans();
    bindTalent();
    bindCastle();
    bindPaid();
    installStaticNumberSteppers();
    bindConnectivity();
    populateSettings();
    renderCategoryOptions();
    renderTree();
    renderShortest();
    renderTasks();
    renderTalent();
    renderCastle();
    renderPaid();
    renderCatalogStatus();
    renderCommonHelp();
    const versionLabel = IS_PREVIEW
      ? t("pwa.preview_version", `v${APP_VERSION} Preview`, { version: APP_VERSION })
      : `v${APP_VERSION}`;
    byId("app-version").textContent = APP_VERSION;
    byId("dataset-version").textContent = t("app.dataset_version", `研究データ ${catalog.datasetVersion}`, { version: catalog.datasetVersion });
    byId("header-version").textContent = versionLabel;
    byId("header-version").classList.toggle("is-preview", IS_PREVIEW);
    document.title = `RLM Research Planner ${versionLabel}`;
    populateLanguageOptions();
    window.rlmMarkStartupComplete?.();
  } catch (error) {
    if (window.rlmHandleStartupError) {
      window.rlmHandleStartupError(error);
      return;
    }
    const target = byId("startup-error");
    const message = byId("startup-error-message");
    if (target && message) { message.textContent = t("pwa.startup_error", `研究データを読み込めませんでした: ${error.message}`, { error: error.message }); target.hidden = false; }
  }
}

function renderCommonHelp() {
  const required = byId("pwa-help-required");
  const plan = byId("help-plan-body");
  const talent = byId("help-talent-body");
  const construction = byId("help-construction-body");
  const files = byId("help-files-body");
  const license = byId("help-license-body");
  if (required) required.innerHTML = messages["help.required_setup.body_v003"] || "";
  if (plan) plan.innerHTML = messages["help.plan.body"] || "";
  if (talent) talent.innerHTML = messages["help.talent.body"] || "";
  if (construction) construction.innerHTML = messages["help.castle.body"] || "";
  if (files) files.innerHTML = messages["help.files.body"] || "";
  if (license) license.innerHTML = messages["help.license.body"] || "";
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
  status.textContent = t("pwa.catalog_status", "{categories}分野・{research}研究を収録しています。全{maximum}レベル中、詳細{levels}、研究時間{times}、資源{costs}レベル分が登録済みです。", {
    categories: catalog.categories.length, research: nodes.length, maximum: maximum.toLocaleString(state.locale), levels: levels.toLocaleString(state.locale), times: times.toLocaleString(state.locale), costs: costs.toLocaleString(state.locale),
  });
  const incomplete = catalog.categories.filter((category) => {
    const expected = category.nodes.reduce((sum, node) => sum + node.maxLevel, 0);
    return category.dataStats.times < expected || category.dataStats.costs < expected;
  }).map((category) => catalog.categoryTitle(category, state.locale));
  notes.textContent = incomplete.length
    ? t("pwa.catalog_incomplete", "公開元で数値を確認できていないレベルを含む分野: {categories}。未収録値は推測で補完しません。", { categories: incomplete.join(", ") })
    : t("pwa.catalog_complete", "全レベルの時間・資源データを収録しています。");
}

function bindNavigation() {
  document.querySelectorAll(".tab-button").forEach((button) => button.addEventListener("click", () => showTab(button.dataset.tab)));
  const bar = byId("tab-bar");
  const previous = byId("tab-scroll-previous");
  const next = byId("tab-scroll-next");
  const update = () => {
    if (!bar || !previous || !next) return;
    const clippedLabel = [...bar.querySelectorAll(".tab-button")].some(
      (button) => button.scrollWidth > button.clientWidth + 1,
    );
    const overflowing = bar.scrollWidth > bar.clientWidth + 1 || clippedLabel;
    bar.classList.toggle("is-overflowing", overflowing);
    previous.hidden = !overflowing;
    next.hidden = !overflowing;
    previous.disabled = bar.scrollLeft <= 1;
    next.disabled = bar.scrollLeft + bar.clientWidth >= bar.scrollWidth - 1;
  };
  const scrollPage = (direction) => {
    const buttons = [...bar.querySelectorAll(".tab-button")];
    if (!buttons.length) return;
    const firstOffset = buttons[0].offsetLeft;
    const currentIndex = buttons.reduce((closest, button, index) => (
      Math.abs(button.offsetLeft - firstOffset - bar.scrollLeft)
        < Math.abs(buttons[closest].offsetLeft - firstOffset - bar.scrollLeft) ? index : closest
    ), 0);
    const targetIndex = Math.max(0, Math.min(buttons.length - 1, currentIndex + direction * 3));
    bar.scrollTo({ left: Math.max(0, buttons[targetIndex].offsetLeft - firstOffset), behavior: "smooth" });
  };
  previous?.addEventListener("click", () => scrollPage(-1));
  next?.addEventListener("click", () => scrollPage(1));
  bar?.addEventListener("scroll", update, { passive: true });
  if (bar && "ResizeObserver" in window) new ResizeObserver(update).observe(bar);
  requestAnimationFrame(update);
  byId("startup-retry")?.addEventListener("click", () => location.reload());
}

function showTab(tab) {
  activeTab = tab;
  document.querySelectorAll(".tab-button").forEach((button) => button.classList.toggle("is-active", button.dataset.tab === tab));
  document.querySelector(`.tab-button[data-tab="${CSS.escape(tab)}"]`)?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.toggle("is-active", panel.id === `tab-${tab}`));
  if (tab === "tree") requestAnimationFrame(renderTree);
  if (tab === "plan") {
    planDirty = false;
    if (planMode === "target") refreshCurrentPlan();
    if (planMode === "shortest") renderShortest();
    if (planMode === "tasks") renderTasks();
  }
  if (tab === "settings") {
    setPlayerView(playerView);
  }
  if (tab === "castle") renderCastle();
  if (tab === "paid") renderPaid();
}

function setPlayerView(view) {
  playerView = ["level", "talent", "resources", "acceleration"].includes(view) ? view : "level";
  byId("player-view-level-button")?.classList.toggle("is-active", playerView === "level");
  byId("player-view-acceleration-button")?.classList.toggle("is-active", playerView === "acceleration");
  byId("player-view-resources-button")?.classList.toggle("is-active", playerView === "resources");
  byId("player-view-talent-button")?.classList.toggle("is-active", playerView === "talent");
  if (byId("player-view-level")) byId("player-view-level").hidden = playerView === "talent";
  if (byId("player-view-talent")) byId("player-view-talent").hidden = playerView !== "talent";
  document.querySelectorAll("[data-player-section]").forEach((section) => {
    section.hidden = section.dataset.playerSection !== playerView;
  });
  document.querySelectorAll("#player-view-level .settings-card:not([data-player-section])").forEach((section) => {
    section.hidden = playerView !== "level";
  });
  if (playerView === "level") renderBulkLevels();
  else if (playerView === "acceleration") renderSpeedupInventory();
  else if (playerView === "talent") renderTalent();
}

function bindTalent() {
  byId("player-view-level-button")?.addEventListener("click", () => setPlayerView("level"));
  byId("player-view-acceleration-button")?.addEventListener("click", () => setPlayerView("acceleration"));
  byId("player-view-resources-button")?.addEventListener("click", () => setPlayerView("resources"));
  byId("player-view-talent-button")?.addEventListener("click", () => setPlayerView("talent"));
  byId("talent-preset")?.addEventListener("change", (event) => {
    const preset = talentCatalog.presetById.get(event.target.value);
    if (!preset) return;
    state.talentPresetId = preset.id;
    state.talentPriorityId = "";
    state.talentPlan = expandTalentTargets(talentCatalog, preset.targets);
    state.talentPlanName = talentCatalog.presetName(preset, state.locale);
    saveNow(); renderTalent();
  });
  byId("talent-priority")?.addEventListener("change", (event) => {
    state.talentPriorityId = String(event.target.value || "");
    talentAutoFollowPending = true;
    saveNow(); renderTalent();
  });
  const cycleSelect = (id, direction) => {
    const select = byId(id);
    if (!select?.options.length) return;
    const current = Math.max(0, select.selectedIndex);
    select.selectedIndex = (current + direction + select.options.length) % select.options.length;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  };
  byId("talent-priority-previous")?.addEventListener("click", () => cycleSelect("talent-priority", -1));
  byId("talent-priority-next")?.addEventListener("click", () => cycleSelect("talent-priority", 1));
  byId("talent-settings-toggle")?.addEventListener("click", () => {
    const button = byId("talent-settings-toggle");
    const panel = byId("talent-settings-panel");
    const expanded = button?.getAttribute("aria-expanded") !== "true";
    button?.setAttribute("aria-expanded", String(expanded));
    if (panel) panel.hidden = !expanded;
  });
  byId("talent-auto-follow")?.addEventListener("change", (event) => {
    state.talentAutoFollow = event.target.checked;
    talentAutoFollowPending = state.talentAutoFollow;
    saveNow(); renderTalent();
  });
  byId("talent-directive-name")?.addEventListener("input", (event) => {
    state.talentPlanName = String(event.target.value || "").trim().slice(0, 100); scheduleSave();
  });
  byId("export-talent-directive")?.addEventListener("click", exportTalentDirective);
  byId("import-talent-directive")?.addEventListener("change", importTalentDirective);
}

function renderTalent() {
  if (!talentCatalog || !byId("talent-tree-cards")) return;
  renderTalentPointCapacity();
  const presetSelect = byId("talent-preset");
  const presetOptions = talentCatalog.presets.map((preset) => {
    const option = create("option", "", talentCatalog.presetName(preset, state.locale)); option.value = preset.id; return option;
  });
  if (state.talentPresetId === "custom") {
    const custom = create("option", "", t("talent.custom", "読み込んだ指示")); custom.value = "custom"; presetOptions.push(custom);
  }
  presetSelect.replaceChildren(...presetOptions); presetSelect.value = state.talentPresetId;
  byId("talent-directive-name").value = state.talentPlanName;
  byId("talent-auto-follow").checked = state.talentAutoFollow !== false;
  const prioritySelect = byId("talent-priority");
  const priorityOptions = [create("option", "", t("talent.priority.default", "プリセット順"))];
  priorityOptions[0].value = "";
  const priorityTargets = new Map();
  for (const step of state.talentPlan) {
    if (!talentCatalog.talents.has(step.talentId)) continue;
    priorityTargets.set(step.talentId, Math.max(priorityTargets.get(step.talentId) || 0, step.targetLevel));
  }
  for (const [talentId, targetLevel] of priorityTargets) {
    const talent = talentCatalog.talents.get(talentId);
    const option = create("option", "", `${talentCatalog.talentName(talent, state.locale)} Lv.${targetLevel}`);
    option.value = talentId; priorityOptions.push(option);
  }
  if (!priorityTargets.has(state.talentPriorityId)) state.talentPriorityId = "";
  prioritySelect.replaceChildren(...priorityOptions); prioritySelect.value = state.talentPriorityId;
  byId("talent-priority-label").textContent = prioritySelect.selectedOptions[0]?.textContent || t("talent.priority.default", "プリセット順");
  byId("talent-controls-selection").textContent = `${presetSelect.selectedOptions[0]?.textContent || "-"} / ${prioritySelect.selectedOptions[0]?.textContent || "-"}`;
  const preset = talentCatalog.presetById.get(state.talentPresetId);
  byId("talent-description").textContent = preset
    ? talentCatalog.presetDescription(preset, state.locale)
    : t("talent.imported_description", "読み込んだ才能指示を、現在の使用可能ポイントで割り当てます。");
  let allocation;
  try { allocation = allocateTalentPlan(talentCatalog, state.talentPlan, state.talentAvailablePoints, state.talentPriorityId); }
  catch (error) {
    byId("talent-level-summary").textContent = "";
    byId("talent-tree-cards").replaceChildren(create("p", "empty-state", error.message));
    return;
  }
  byId("talent-required-points").textContent = allocation.requiredPoints.toLocaleString(state.locale);
  byId("talent-used-points").textContent = allocation.usedPoints.toLocaleString(state.locale);
  byId("talent-remaining-points").textContent = allocation.remainingPoints.toLocaleString(state.locale);
  const bonusPoints = Math.max(0, Number(state.researchLevels.military_command_hidden_talent || 0));
  const planRequirement = talentPlayerLevelRequirement(talentCatalog, allocation.requiredPoints, bonusPoints);
  const levelText = (requirement) => requirement.playerLevel !== null
    ? `Lv.${requirement.playerLevel}`
    : t("talent.level_over_max", `Lv.60でも${requirement.shortageAtMaxLevel}ポイント不足`, { shortage: requirement.shortageAtMaxLevel });
  byId("talent-level-summary").textContent = t(
    "talent.required_player_level",
    `プリセット必要プレイヤーレベル: ${levelText(planRequirement)}（研究追加 +${bonusPoints}）`,
    { level: levelText(planRequirement), bonus: bonusPoints },
  );
  renderTalentTree(allocation);
}

function renderTalentTree(allocation) {
  const talents = [...talentCatalog.talents.values()].sort((left, right) => left.order - right.order);
  const rows = new Map();
  for (const talent of talents) {
    if (!rows.has(talent.row)) rows.set(talent.row, []);
    rows.get(talent.row).push(talent);
  }
  const layout = talentLayoutColumns(talentCatalog);
  const columnCount = layout.columnCount;
  const cardWidth = 210; const cardHeight = 132; const gapX = 30; const gapY = 46; const padding = 28;
  const width = padding * 2 + columnCount * cardWidth + (columnCount - 1) * gapX;
  const height = padding * 2 + rows.size * cardHeight + Math.max(0, rows.size - 1) * gapY;
  const stage = byId("talent-tree-stage"); stage.style.width = `${width}px`; stage.style.height = `${height}px`;
  const positions = new Map();
  for (const [rowNumber, row] of [...rows.entries()].sort((left, right) => left[0] - right[0])) {
    row.forEach((talent) => positions.set(talent.id, {
      x: padding + layout.columns.get(talent.id) * (cardWidth + gapX), y: padding + (rowNumber - 1) * (cardHeight + gapY), width: cardWidth, height: cardHeight,
    }));
  }
  const allocatedById = new Map(allocation.steps.map((step) => [step.talentId, step]));
  const svg = byId("talent-tree-lines"); svg.setAttribute("viewBox", `0 0 ${width} ${height}`); svg.setAttribute("width", width); svg.setAttribute("height", height);
  const inactive = []; const active = [];
  for (const talent of talents) {
    if (!talent.prerequisite) continue;
    const from = positions.get(talent.prerequisite.talentId); const to = positions.get(talent.id); if (!from || !to) continue;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const parent = allocatedById.get(talent.prerequisite.talentId);
    const unlocked = Boolean(parent && parent.allocatedLevel >= talent.prerequisite.level);
    path.classList.add(unlocked ? "is-active" : "is-inactive");
    if (from.y === to.y) {
      const y = from.y + from.height / 2;
      const x1 = from.x < to.x ? from.x + from.width : from.x;
      const x2 = from.x < to.x ? to.x : to.x + to.width;
      path.setAttribute("d", `M ${x1} ${y} H ${x2}`);
    } else {
      const x1 = from.x + from.width / 2; const y1 = from.y + from.height; const x2 = to.x + to.width / 2; const y2 = to.y; const mid = y1 + (y2 - y1) / 2;
      path.setAttribute("d", `M ${x1} ${y1} V ${mid} H ${x2} V ${y2}`);
    }
    (unlocked ? active : inactive).push(path);
  }
  svg.replaceChildren(...inactive, ...active);
  byId("talent-tree-cards").replaceChildren(...talents.map((talent) => {
    const position = positions.get(talent.id); const step = allocatedById.get(talent.id); const level = step?.allocatedLevel || 0; const target = step?.targetLevel || 0;
    const card = create("button", "talent-tree-card"); card.type = "button"; card.style.left = `${position.x}px`; card.style.top = `${position.y}px`; card.style.width = `${position.width}px`; card.style.height = `${position.height}px`;
    if (target && level >= target) card.classList.add("is-complete"); else if (target) card.classList.add("is-short"); else card.classList.add("is-unplanned");
    if (talent.id === state.talentPriorityId) card.classList.add("is-priority");
    card.append(
      create("strong", "talent-tree-name", talentCatalog.talentName(talent, state.locale)),
      create("span", "talent-tree-meter", ""),
      create("span", "talent-tree-level", `${level} / ${talent.maxLevel}`),
      create("span", "talent-tree-effect", `${talentCatalog.effectName(talent, state.locale)} +${talent.maxEffect}%`),
      create("span", "talent-tree-target", target ? t("talent.target_level", `目標 Lv.${target}`, { level: target }) : t("talent.status.not_planned", "計画外")),
    );
    card.querySelector(".talent-tree-meter").style.setProperty("--talent-progress", `${talent.maxLevel ? level / talent.maxLevel * 100 : 0}%`);
    card.addEventListener("click", () => {
      const priority = byId("talent-priority"); if (![...priority.options].some((option) => option.value === talent.id)) return;
      talentAutoFollowPending = true;
      state.talentPriorityId = talent.id; saveNow(); renderTalent();
    });
    return card;
  }));
  if (talentAutoFollowPending && state.talentAutoFollow !== false && state.talentPriorityId) {
    const position = positions.get(state.talentPriorityId);
    const viewport = byId("talent-tree-viewport");
    if (position && viewport) {
      requestAnimationFrame(() => viewport.scrollTo({
        left: Math.max(0, position.x + position.width / 2 - viewport.clientWidth / 2),
        top: Math.max(0, position.y + position.height / 2 - viewport.clientHeight / 2),
        behavior: "smooth",
      }));
    }
  }
  talentAutoFollowPending = false;
}

function exportTalentDirective() {
  if (!state.talentPlan.length) { toast(t("talent.directive_empty", "書き出す才能計画がありません。")); return; }
  downloadJson(talentDirectivePayload(state.talentPlan, {
    name: state.talentPlanName, catalogVersion: talentCatalog.version,
  }), `RLMResearchPlanner-talent-${new Date().toISOString().slice(0, 10)}.json`);
  toast(t("talent.exported", "才能指示データを書き出しました。"));
}

async function importTalentDirective(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    const directive = talentDirectiveFromPayload(JSON.parse(await file.text()));
    state.talentPlan = expandTalentTargets(talentCatalog, directive.steps);
    state.talentPlanName = directive.name; state.talentPresetId = "custom"; state.talentPriorityId = "";
    saveNow(); renderTalent(); toast(t("talent.imported", `${directive.name} を読み込みました。`, { name: directive.name }));
  } catch (error) { toast(t("talent.import_failed", `才能指示データを読み込めませんでした: ${error.message}`, { error: error.message })); }
  finally { event.target.value = ""; }
}

function paidKindLabel(kind) {
  const fallbacks = {
    general: "スピードアップ", research: "研究スピードアップ", training: "訓練スピードアップ", construction: "建設スピードアップ",
    healing: "治療スピードアップ", merging: "召喚の書・スキル核融合スピードアップ", crafting: "月晶工房スピードアップ",
    gems: "ジェム", monster_common: "魔獣素材・コモン", monster_uncommon: "魔獣素材・アンコモン", monster_rare: "魔獣素材・レア",
    monster_epic: "魔獣素材・エピック", monster_legendary: "魔獣素材・レジェンド", chest: "宝箱", resource: "資源", material: "素材",
    combat_item: "戦闘アイテム", boost_item: "ブースト", building_material: "建設用特殊資材", familiar_item: "召喚獣アイテム", monster_energy: "行動力・魔獣討伐", hero_item: "ヒーローアイテム", artifact_item: "アーティファクト", event_item: "イベントアイテム", currency: "通貨", custom: "任意項目",
  };
  return t(`paid.kind.${kind}`, fallbacks[kind] || kind);
}

function paidGoalLabel(goal) {
  const fallbacks = { all_round: "総合", account_growth: "アカウント成長", research: "研究", construction: "建設", troop_training: "兵士訓練", combat: "戦闘・戦争", monster_hunt: "魔獣討伐", equipment: "装備", familiar: "召喚獣", artifact: "アーティファクト", heroes: "ヒーロー", events: "イベント", resources: "資源確保" };
  return t(`paid.goal.${goal}`, fallbacks[goal] || goal);
}

function paidDurationParts(seconds) {
  const value = Math.max(0, Math.trunc(Number(seconds) || 0));
  for (const [divisor, unit] of [[86400, "days"], [3600, "hours"], [60, "minutes"]]) {
    if (value > 0 && value % divisor === 0) return [value / divisor, unit];
  }
  return [value, "seconds"];
}

function paidUnitSeconds(unit) {
  return { seconds: 1, minutes: 60, hours: 3600, days: 86400 }[unit] || 1;
}

function speedupSimulationParts(requiredSeconds, targetKind, taskSeconds = null) {
  const coverage = speedupCoverage(requiredSeconds, state.settings.speedupInventory, targetKind, taskSeconds);
  return {
    coverage,
    recommendations: coverage.remainingSeconds
      ? recommendPaidOffers(coverage.remainingSeconds, state.paidOffers, targetKind, 3, {
        taskSeconds: coverage.remainingTaskSeconds,
        useGems: state.settings.useGemsForSpeedups,
      })
      : [],
  };
}

function speedupUsageText(usedItems) {
  return usedItems.map((item) => {
    const [duration, unit] = paidDurationParts(item.durationSeconds);
    return `${paidKindLabel(item.kind)} ${duration.toLocaleString(state.locale)}${t(`paid.unit.${unit}`, unit)}×${item.quantity.toLocaleString(state.locale)}`;
  }).join(" / ");
}

function renderSpeedupSimulation(target, requiredSeconds, targetKind, unknownTimeCount = 0, taskSeconds = null) {
  if (!target) return;
  const result = speedupSimulationParts(requiredSeconds, targetKind, taskSeconds);
  const disclosure = create("summary", "speedup-simulation-toggle", t("plan.speedup_simulation_title", "速度アップ充当シミュレーション"));
  const hint = create("span", "speedup-simulation-hint", t("plan.speedup_simulation_hint", "不足時は［課金］タブの［保存済み］から、利用可能な時短を含む候補を最大3件表示します。"));
  const gemOption = create("label", "speedup-gem-option");
  const gemCheckbox = create("input");
  gemCheckbox.type = "checkbox";
  gemCheckbox.checked = state.settings.useGemsForSpeedups === true;
  gemCheckbox.addEventListener("change", () => {
    state.settings.useGemsForSpeedups = gemCheckbox.checked;
    saveNow();
    refreshCurrentPlan();
    renderCastle();
  });
  gemOption.append(gemCheckbox, create("span", "", t("plan.speedup_use_gems", "課金候補の付属ジェムも時短に使用")));
  if (unknownTimeCount > 0) {
    target.replaceChildren(
      disclosure,
      hint,
      gemOption,
      create("span", "speedup-remaining", t("plan.speedup_unknown_time", "研究時間が未収録のため計算できません")),
    );
    target.hidden = false;
    return;
  }
  const summary = create("section", "speedup-allocation-section speedup-owned-section");
  summary.append(
    create("strong", "speedup-section-title", t("plan.speedup_owned_section", "所持スピードアップ")),
    create("span", "", t("plan.speedup_owned", "利用可能: {time}", { time: formatDuration(result.coverage.availableSeconds) })),
    create("span", "", t("plan.speedup_applied", "使用: {time}", { time: formatDuration(result.coverage.appliedSeconds) })),
  );
  if (result.coverage.usedItems.length) {
    summary.append(create("span", "speedup-used-items", t(
      "plan.speedup_used_items",
      "使用内訳: {items}",
      { items: speedupUsageText(result.coverage.usedItems) },
    )));
  }
  if (result.coverage.surplusSeconds > 0) {
    summary.append(create("span", "speedup-surplus", t("plan.speedup_surplus", "余り: {time}", { time: formatDuration(result.coverage.surplusSeconds) })));
  }
  const remaining = create("section", "speedup-allocation-section speedup-missing-section");
  remaining.append(
    create("strong", "speedup-section-title", t("plan.speedup_remaining_section", "足りない短縮")),
    create("span", "speedup-remaining", t("plan.speedup_remaining", "不足: {time}", { time: formatDuration(result.coverage.remainingSeconds) })),
  );
  if (state.settings.useGemsForSpeedups && result.coverage.remainingSeconds > 0) {
    const directGems = result.coverage.remainingTaskSeconds.reduce(
      (sum, seconds) => sum + minimumGemsForSpeedupSeconds(seconds).gems,
      0,
    );
    remaining.append(create("span", "speedup-direct-gems", t(
      "plan.speedup_direct_gems",
      "ジェムで即時終了: {gems}ジェム（{time}短縮）",
      {
        gems: directGems.toLocaleString(state.locale),
        time: formatDuration(result.coverage.remainingSeconds),
      },
    )));
  }
  const offerList = create("div", "speedup-offer-list");
  if (result.coverage.remainingSeconds > 0) {
    offerList.append(create("strong", "speedup-section-title", t("plan.speedup_purchase_options", "登録済み課金で補う場合")));
    if (result.recommendations.some((offer) => offer.gemsUsed > 0)) {
      offerList.append(create("span", "speedup-gem-basis", t("plan.speedup_gem_basis", "ジェムショップの定型スピードアップ価格で換算")));
    }
    if (!result.recommendations.length) {
      offerList.append(create("span", "muted", t("plan.speedup_no_offer", "残りを補える課金登録なし")));
    } else {
      for (const offer of result.recommendations) {
        const price = offer.totalDiamondCost === null
          ? t("common.unknown", "不明")
          : offer.totalDiamondCost.toLocaleString(state.locale);
        const card = create("article", "speedup-recommendation-card");
        const breakdown = create("div", "speedup-recommendation-breakdown");
        if (offer.appliedSpeedupSeconds > 0) breakdown.append(
          create("span", "speedup-breakdown-part", t(
            "plan.speedup_offer_speedups",
            "パック内の速度アップ: {time}",
            { time: formatDuration(offer.appliedSpeedupSeconds) },
          )),
        );
        if (offer.gemsUsed > 0) breakdown.append(
          create("span", "speedup-breakdown-part", t(
            "plan.speedup_offer_gems",
            "付属ジェム: {available}（{used}使用）→ {time}短縮",
            {
              available: offer.availableGems.toLocaleString(state.locale),
              used: offer.gemsUsed.toLocaleString(state.locale),
              time: formatDuration(offer.gemAppliedSeconds),
            },
          )),
        );
        breakdown.append(
          create("span", `speedup-breakdown-part ${offer.remainingSeconds ? "speedup-remaining" : "speedup-surplus"}`, t(
            "plan.speedup_offer_remaining",
            "適用後の不足: {time}",
            { time: formatDuration(offer.remainingSeconds) },
          )),
        );
        card.append(
          create("strong", "speedup-recommendation-title", t(
            "plan.speedup_offer",
            "{title} ×{count}（ダイヤ {price}）",
            { title: offer.title, count: offer.purchases, price },
          )),
          breakdown,
        );
        offerList.append(card);
      }
    }
  }
  const sections = [disclosure, hint, gemOption, summary, remaining];
  if (result.coverage.remainingSeconds > 0) sections.push(offerList);
  target.replaceChildren(...sections);
  target.hidden = requiredSeconds <= 0;
}

function bindPaid() {
  byId("paid-new")?.addEventListener("click", () => { newPaidOffer(); setPaidView("input"); });
  for (const view of ["input", "saved", "comparison", "share"]) byId(`paid-view-${view}-button`)?.addEventListener("click", () => setPaidView(view));
  byId("paid-add-item")?.addEventListener("click", () => openPaidItemEditor());
  byId("paid-item-save")?.addEventListener("click", savePaidItem);
  byId("paid-item-cancel")?.addEventListener("click", closePaidItemEditor);
  byId("paid-item-delete")?.addEventListener("click", deletePaidItem);
  byId("paid-item-kind")?.addEventListener("change", () => refreshPaidItemEditorKind(true));
  byId("paid-save")?.addEventListener("click", savePaidOffer);
  byId("paid-delete")?.addEventListener("click", deletePaidOffer);
  byId("paid-goal")?.addEventListener("change", (event) => { paidDraft.goal = event.target.value; renderPaidSummary(); });
  byId("paid-comparison-goal")?.addEventListener("change", renderPaidComparison);
  byId("paid-use-speedup-gem-presets")?.addEventListener("change", (event) => { state.paidValuation.useSpeedupGemPresets = event.target.checked; scheduleSave(); renderPaidSummary(); renderPaidComparison(); });
  byId("paid-export-selected")?.addEventListener("click", exportSelectedPaidOffer);
  byId("paid-export-all")?.addEventListener("click", exportAllPaidOffers);
  byId("paid-export-valuation")?.addEventListener("click", exportPaidValuation);
  byId("paid-import")?.addEventListener("change", importPaidOffers);
  const draftFields = {
    "paid-title-input": "title", "paid-memo-input": "memo", "paid-price": "diamondCost",
    "paid-included-gems": "includedGems", "paid-bonus-gems": "bonusGems",
  };
  for (const [id, key] of Object.entries(draftFields)) byId(id)?.addEventListener("input", (event) => {
    paidDraft[key] = ["title", "memo"].includes(key) ? event.target.value : Math.max(0, Number(event.target.value) || 0);
    renderPaidSummary();
  });
  const rates = {
    "paid-rate-gem": "pointsPerGem", "paid-rate-general": "generalSpeedupPointsPerHour",
    "paid-rate-research": "researchSpeedupPointsPerHour", "paid-rate-training": "trainingSpeedupPointsPerHour",
    "paid-rate-construction": "constructionSpeedupPointsPerHour",
    "paid-rate-healing": "healingSpeedupPointsPerHour", "paid-rate-merging": "mergingSpeedupPointsPerHour",
    "paid-rate-crafting": "craftingSpeedupPointsPerHour",
  };
  for (const [id, key] of Object.entries(rates)) byId(id)?.addEventListener("input", (event) => {
    state.paidValuation[key] = Math.max(0, Number(event.target.value) || 0);
    scheduleSave(); renderPaidSummary(); renderPaidOffers(); renderPaidComparison();
  });
}

function setPaidView(view) {
  paidView = ["input", "saved", "comparison", "share"].includes(view) ? view : "input";
  for (const key of ["input", "saved", "comparison", "share"]) {
    byId(`paid-view-${key}`).hidden = key !== paidView;
    byId(`paid-view-${key}-button`).classList.toggle("is-active", key === paidView);
  }
  if (paidView === "saved") renderPaidOffers();
  if (paidView === "comparison") renderPaidComparison();
}

function newPaidOffer() {
  paidEditingId = "";
  closePaidItemEditor();
  paidDraft = emptyPaidOffer();
  renderPaid();
}

function loadPaidOffer(id) {
  const offer = state.paidOffers.find((item) => item.offerId === id);
  if (!offer) return;
  paidEditingId = id;
  closePaidItemEditor();
  paidDraft = sanitizePaidOffer(structuredClone(offer));
  paidView = "input";
  renderPaid();
}

function savePaidOffer() {
  const title = paidDraft.title.trim();
  if (!title) { toast(t("paid.title_required", "タイトルを入力してください")); byId("paid-title-input")?.focus(); return; }
  const now = new Date().toISOString();
  const offerId = paidEditingId || globalThis.crypto?.randomUUID?.() || `offer-${Date.now()}`;
  const saved = sanitizePaidOffer({ ...paidDraft, offerId, title, createdAt: paidDraft.createdAt || now, updatedAt: now });
  const index = state.paidOffers.findIndex((item) => item.offerId === offerId);
  if (index >= 0) state.paidOffers[index] = saved; else state.paidOffers.push(saved);
  paidEditingId = offerId;
  paidDraft = sanitizePaidOffer(structuredClone(saved));
  saveNow(); renderPaid(); refreshCurrentPlan(); renderCastle(); toast(t("paid.saved", "課金項目を保存しました"));
}

function deletePaidOffer() {
  if (!paidEditingId) { newPaidOffer(); return; }
  if (!window.confirm(t("paid.delete_confirm", "この課金項目を削除しますか？"))) return;
  state.paidOffers = state.paidOffers.filter((item) => item.offerId !== paidEditingId);
  saveNow(); newPaidOffer(); refreshCurrentPlan(); renderCastle(); toast(t("paid.deleted", "課金項目を削除しました"));
}

function renderPaid() {
  if (!byId("paid-title-input")) return;
  byId("paid-title-input").value = paidDraft.title;
  byId("paid-memo-input").value = paidDraft.memo;
  populatePaidGoalOptions();
  byId("paid-price").value = paidDraft.diamondCost;
  byId("paid-included-gems").value = paidDraft.includedGems;
  byId("paid-bonus-gems").value = paidDraft.bonusGems;
  const rates = state.paidValuation;
  byId("paid-rate-gem").value = rates.pointsPerGem;
  byId("paid-rate-general").value = rates.generalSpeedupPointsPerHour;
  byId("paid-rate-research").value = rates.researchSpeedupPointsPerHour;
  byId("paid-rate-training").value = rates.trainingSpeedupPointsPerHour;
  byId("paid-rate-construction").value = rates.constructionSpeedupPointsPerHour;
  byId("paid-rate-healing").value = rates.healingSpeedupPointsPerHour;
  byId("paid-rate-merging").value = rates.mergingSpeedupPointsPerHour;
  byId("paid-rate-crafting").value = rates.craftingSpeedupPointsPerHour;
  byId("paid-use-speedup-gem-presets").checked = rates.useSpeedupGemPresets;
  byId("paid-delete").disabled = !paidEditingId;
  setPaidView(paidView); renderPaidOffers(); renderPaidComparison(); renderPaidItems(); renderPaidSummary();
}

function populatePaidGoalOptions() {
  const editor = byId("paid-goal");
  const comparison = byId("paid-comparison-goal");
  if (editor && editor.options.length !== PAID_GOALS.length) editor.replaceChildren(...PAID_GOALS.map((goal) => { const option = create("option", "", paidGoalLabel(goal)); option.value = goal; return option; }));
  if (editor) editor.value = paidDraft.goal || "all_round";
  if (comparison && comparison.options.length !== PAID_GOALS.length + 1) {
    const any = create("option", "", t("paid.goal.any", "すべて")); any.value = "";
    comparison.replaceChildren(any, ...PAID_GOALS.map((goal) => { const option = create("option", "", paidGoalLabel(goal)); option.value = goal; return option; }));
  }
}

function renderPaidOffers() {
  const list = byId("paid-offer-list");
  if (!list) return;
  const offers = [...state.paidOffers].sort((left, right) => String(right.updatedAt).localeCompare(String(left.updatedAt)) || left.title.localeCompare(right.title));
  if (!offers.length) { list.replaceChildren(create("p", "empty-state", t("paid.no_saved", "保存した課金項目はありません。"))); return; }
  list.replaceChildren(...offers.map((offer) => {
    const card = create("article", `paid-offer-card${offer.offerId === paidEditingId ? " is-selected" : ""}`);
    const button = create("button", "paid-offer-open");
    button.type = "button";
    const heading = create("span", "paid-offer-heading");
    heading.append(create("strong", "", offer.title));
    if (offer.memo) heading.append(create("span", "", offer.memo));
    button.append(
      heading,
      create("strong", "", paidGoalLabel(offer.goal)),
      create("span", "", `${offer.diamondCost.toLocaleString(state.locale)} ◇`),
      create("span", "", offer.updatedAt ? offer.updatedAt.slice(0, 10) : ""),
    );
    button.addEventListener("click", () => loadPaidOffer(offer.offerId));
    const addInventory = create("button", "paid-add-inventory", t("paid.add_to_inventory", "所持時短へ追加"));
    addInventory.type = "button";
    addInventory.addEventListener("click", () => addPaidOfferToInventory(offer));
    card.append(button, addInventory);
    return card;
  }));
}

function addPaidOfferToInventory(offer) {
  const before = JSON.stringify(normalizeSpeedupInventory(state.settings.speedupInventory));
  const updated = addPaidItemsToInventory(state.settings.speedupInventory, offer.items);
  if (JSON.stringify(updated) === before) {
    toast(t("paid.no_speedups_to_add", "この課金項目に追加できる時短はありません。"));
    return;
  }
  state.settings.speedupInventory = updated;
  state.settings.speedupSeconds = 0;
  saveNow();
  closeSpeedupInventoryEditor();
  refreshCurrentPlan();
  renderCastle();
  toast(t("paid.added_to_inventory", "課金項目の時短を所持数へ追加しました。"));
}

function renderPaidComparison() {
  const list = byId("paid-comparison-list");
  if (!list) return;
  const goal = byId("paid-comparison-goal")?.value || "";
  const offers = sortedPaidOffers(state.paidOffers.filter((offer) => !goal || offer.goal === goal), state.paidValuation);
  if (!offers.length) { list.replaceChildren(create("p", "empty-state", t("paid.no_comparison", "比較できる課金項目はありません。"))); return; }
  list.replaceChildren(...offers.map((offer, index) => {
    const summary = summarizePaidOffer(offer, state.paidValuation);
    const card = create("button", `paid-offer-card paid-comparison-card${offer.offerId === paidEditingId ? " is-selected" : ""}`);
    card.type = "button";
    const heading = create("span", "paid-offer-heading");
    heading.append(create("strong", "", `${index + 1}. ${offer.title}`), create("span", "", paidGoalLabel(offer.goal)));
    card.append(
      heading,
      create("strong", "", summary.pointsPerDiamond == null ? "-" : `${summary.pointsPerDiamond.toFixed(2)} pt/◇`),
      create("span", "", `${offer.diamondCost.toLocaleString(state.locale)} ◇ · ${summary.totalGemValue.toLocaleString(state.locale)} gem換算`),
      create("span", "", `${summary.totalPoints.toFixed(1)} pt`),
    );
    card.addEventListener("click", () => loadPaidOffer(offer.offerId));
    return card;
  }));
}

function exportSelectedPaidOffer() {
  const offer = state.paidOffers.find((item) => item.offerId === paidEditingId);
  if (!offer) { toast(t("paid.select_offer_export", "書き出す課金項目を一覧から選択してください。")); return; }
  downloadJson(paidOfferExchangePayload([offer], state.paidValuation, offer.title), `RLMResearchPlanner-paid-${new Date().toISOString().slice(0, 10)}.json`);
  toast(t("paid.exported", "課金項目を書き出しました", { count: 1 }));
}

function exportAllPaidOffers() {
  if (!state.paidOffers.length) { toast(t("paid.no_saved", "保存した課金項目はありません。")); return; }
  downloadJson(
    paidOfferExchangePayload(state.paidOffers, state.paidValuation, t("paid.shared_data_name", "課金比較データ")),
    `RLMResearchPlanner-paid-${new Date().toISOString().slice(0, 10)}.json`,
  );
  toast(t("paid.exported", "課金項目を書き出しました", { count: state.paidOffers.length }));
}

function exportPaidValuation() {
  downloadJson(
    paidOfferExchangePayload([], state.paidValuation, t("paid.valuation_shared_data_name", "課金比較設定")),
    `RLMResearchPlanner-paid-settings-${new Date().toISOString().slice(0, 10)}.json`,
  );
  toast(t("paid.valuation_exported", "比較設定を書き出しました。"));
}

async function importPaidOffers(event) {
  const file = event.target.files?.[0]; if (!file) return;
  try {
    const imported = paidOffersFromExchangePayload(JSON.parse(await file.text()));
    const existing = new Map(state.paidOffers.map((offer) => [offer.offerId, offer]));
    let added = 0; let skipped = 0;
    for (const source of imported.offers) {
      let offer = source;
      if (existing.has(offer.offerId) && JSON.stringify(existing.get(offer.offerId)) === JSON.stringify(offer)) { skipped += 1; continue; }
      if (existing.has(offer.offerId)) offer = { ...offer, offerId: globalThis.crypto?.randomUUID?.() || `offer-${Date.now()}-${added}` };
      state.paidOffers.push(offer); existing.set(offer.offerId, offer); added += 1;
    }
    const valuationOnly = imported.offers.length === 0;
    const valuationApplied = valuationOnly || window.confirm(t("paid.import_valuation_confirm", "共有元の比較ポイント設定も取り込みますか？"));
    if (valuationApplied) state.paidValuation = imported.valuation;
    saveNow(); renderPaid(); setPaidView(valuationOnly ? "comparison" : "saved"); refreshCurrentPlan(); renderCastle();
    toast(valuationOnly
      ? t("paid.valuation_imported", "比較設定を取り込みました。")
      : t(valuationApplied ? "paid.imported_with_valuation" : "paid.imported", "課金項目{added}件を追加しました。重複{skipped}件は変更していません。", { added, skipped }));
  } catch (error) { toast(t("paid.import_failed", `課金データを読み込めませんでした: ${error.message}`, { error: error.message })); }
  finally { event.target.value = ""; }
}

function refreshPaidItemEditorKind(applyDefaults = false) {
  const kindInput = byId("paid-item-kind");
  const kind = kindInput?.value || "general";
  const previous = kindInput?.dataset.previousKind || kind;
  if (applyDefaults) {
    const gemValue = Number(byId("paid-item-gem-value").value) || 0;
    const points = Number(byId("paid-item-points").value) || 0;
    if (!gemValue || gemValue === defaultGemValueEach(previous)) byId("paid-item-gem-value").value = String(defaultGemValueEach(kind));
    if (!points || points === defaultPointsEach(previous)) byId("paid-item-points").value = String(defaultPointsEach(kind));
  }
  if (kindInput) kindInput.dataset.previousKind = kind;
  const hasTime = paidKindHasTime(kind);
  byId("paid-item-duration-field").hidden = !hasTime;
  byId("paid-item-unit-field").hidden = !hasTime;
}

function openPaidItemEditor(index = -1) {
  const items = paidDraft.items || [];
  paidItemEditingIndex = Number.isInteger(index) && index >= 0 && index < items.length ? index : -1;
  const item = paidItemEditingIndex >= 0
    ? items[paidItemEditingIndex]
    : { kind: "general", name: "", quantity: 1, durationSeconds: 3600, gemValueEach: 0, pointsEach: 0 };
  const kind = byId("paid-item-kind");
  kind.replaceChildren(...PAID_ITEM_KINDS.map((key) => {
    const option = create("option", "", paidKindLabel(key));
    option.value = key;
    return option;
  }));
  kind.value = item.kind;
  kind.dataset.previousKind = item.kind;
  byId("paid-item-name").value = item.name || "";
  byId("paid-item-quantity").value = String(Math.max(1, Math.trunc(Number(item.quantity) || 1)));
  const [durationValue, durationUnit] = paidDurationParts(item.durationSeconds);
  byId("paid-item-duration").value = String(Math.max(0, durationValue));
  const unit = byId("paid-item-unit");
  unit.replaceChildren(...["seconds", "minutes", "hours", "days"].map((key) => {
    const option = create("option", "", t(`paid.unit.${key}`, key));
    option.value = key;
    return option;
  }));
  unit.value = durationUnit;
  byId("paid-item-gem-value").value = String(Math.max(0, Number(item.gemValueEach) || 0));
  byId("paid-item-points").value = String(Math.max(0, Number(item.pointsEach) || 0));
  byId("paid-item-editor-title").textContent = paidItemEditingIndex >= 0
    ? t("paid.item_edit", "内容を編集")
    : t("paid.item_new", "内容を追加");
  byId("paid-item-delete").hidden = paidItemEditingIndex < 0;
  byId("paid-item-editor").hidden = false;
  refreshPaidItemEditorKind();
  renderPaidItems();
}

function closePaidItemEditor() {
  paidItemEditingIndex = -1;
  const editor = byId("paid-item-editor");
  if (editor) editor.hidden = true;
  renderPaidItems();
}

function savePaidItem() {
  const kind = byId("paid-item-kind").value;
  const hasTime = paidKindHasTime(kind);
  const durationSeconds = hasTime
    ? Math.max(0, Number(byId("paid-item-duration").value) || 0) * paidUnitSeconds(byId("paid-item-unit").value)
    : 0;
  const item = {
    kind,
    name: byId("paid-item-name").value.trim(),
    quantity: Math.max(1, Math.trunc(Number(byId("paid-item-quantity").value) || 1)),
    durationSeconds: Math.max(0, Math.trunc(durationSeconds)),
    gemValueEach: Math.max(0, Number(byId("paid-item-gem-value").value) || 0),
    pointsEach: Math.max(0, Number(byId("paid-item-points").value) || 0),
  };
  if (paidItemEditingIndex >= 0 && paidItemEditingIndex < paidDraft.items.length) paidDraft.items[paidItemEditingIndex] = item;
  else paidDraft.items.push(item);
  closePaidItemEditor();
  renderPaidSummary();
}

function deletePaidItem() {
  if (paidItemEditingIndex < 0 || paidItemEditingIndex >= paidDraft.items.length) return;
  paidDraft.items.splice(paidItemEditingIndex, 1);
  closePaidItemEditor();
  renderPaidSummary();
}

function paidItemListDetail(item) {
  const parts = [paidKindLabel(item.kind), `${Math.max(0, Math.trunc(Number(item.quantity) || 0)).toLocaleString(state.locale)}${t("paid.quantity_suffix", "個")}`];
  if (paidKindHasTime(item.kind) && item.durationSeconds > 0) parts.push(formatDuration(item.durationSeconds));
  return parts.join(" / ");
}

function renderPaidItems() {
  const list = byId("paid-item-list");
  if (!list) return;
  if (!paidDraft.items.length) { list.replaceChildren(create("p", "empty-state", t("paid.no_items_manual", "「行を追加」から内容を入力してください。"))); return; }
  list.replaceChildren(...paidDraft.items.map((item, index) => {
    const row = create("button", "speedup-inventory-row paid-item-summary-row");
    row.type = "button";
    row.classList.toggle("is-selected", paidItemEditingIndex === index && !byId("paid-item-editor").hidden);
    row.setAttribute("aria-pressed", String(paidItemEditingIndex === index && !byId("paid-item-editor").hidden));
    const main = create("span", "speedup-inventory-row-main");
    main.append(
      create("strong", "", item.name || paidKindLabel(item.kind)),
      create("span", "", paidItemListDetail(item)),
    );
    const total = paidKindHasTime(item.kind) && item.durationSeconds > 0
      ? formatDuration(item.durationSeconds * Math.max(0, Math.trunc(Number(item.quantity) || 0)))
      : "";
    row.append(main, create("span", "speedup-inventory-row-total", total));
    row.addEventListener("click", () => openPaidItemEditor(index));
    return row;
  }));
}

function renderPaidSummary() {
  const target = byId("paid-current-summary");
  if (!target) return;
  const summary = summarizePaidOffer(paidDraft, state.paidValuation);
  const value = (label, content) => { const card = create("div", "paid-summary-value"); card.append(create("span", "", label), create("strong", "", content)); return card; };
  target.replaceChildren(
    value(t("paid.total_time", "合計時間"), formatDuration(summary.totalSpeedupSeconds)),
    value(t("paid.total_gem_value", "ジェム換算"), summary.totalGemValue.toLocaleString(state.locale, { maximumFractionDigits: 2 })),
    value(t("paid.total_points", "総合ポイント"), `${summary.totalPoints.toLocaleString(state.locale, { maximumFractionDigits: 2 })} / ${summary.pointsPerDiamond == null ? "-" : summary.pointsPerDiamond.toFixed(2)} pt/◇`),
  );
}

function bindTreeControls() {
  byId("category-select").addEventListener("change", (event) => { selectedCategoryId = event.target.value; renderTree(true); });
  byId("category-drawer-open")?.addEventListener("click", () => {
    renderCategoryOptions();
    byId("category-drawer")?.showModal();
  });
  byId("tree-search").addEventListener("input", () => { renderCategoryOptions(); renderTree(true); });
  byId("instant-only").addEventListener("change", (event) => {
    if (event.target.checked) byId("technolabe-only").checked = false;
    renderCategoryOptions(); renderTree(true);
  });
  byId("technolabe-only").addEventListener("change", (event) => {
    if (event.target.checked) byId("instant-only").checked = false;
    renderCategoryOptions(); renderTree(true);
  });
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

function treeContentSize(category, nodes = category.nodes) {
  const layout = visibleTreeLayout(nodes);
  return {
    width: PADDING * 2 + layout.columnCount * CARD_WIDTH + Math.max(0, layout.columnCount - 1) * GAP_X,
    height: PADDING * 2 + layout.rowCount * CARD_HEIGHT + Math.max(0, layout.rowCount - 1) * GAP_Y,
  };
}

function fittedZoom(category, nodes = category.nodes) {
  const viewport = byId("tree-viewport");
  const size = treeContentSize(category, nodes);
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
  const nodes = matchingNodes(category);
  zoom = clampTreeZoom(value, fittedZoom(category, nodes.length ? nodes : category.nodes));
  renderTree();
  viewport.scrollLeft = contentX * zoom - localX;
  viewport.scrollTop = contentY * zoom - localY;
}

function fitWholeTree() {
  const category = catalog?.categories.find((item) => item.id === selectedCategoryId) || catalog?.categories[0];
  if (!category) return;
  const nodes = matchingNodes(category);
  zoom = fittedZoom(category, nodes.length ? nodes : category.nodes);
  renderTree(true);
}

function matchingNodes(category) {
  const term = byId("tree-search")?.value.trim().toLocaleLowerCase(state.locale) || "";
  const instantOnly = Boolean(byId("instant-only")?.checked);
  const technolabeOnly = Boolean(byId("technolabe-only")?.checked);
  return category.nodes.filter((node) => {
    const name = catalog.nodeName(node, state.locale).toLocaleLowerCase(state.locale);
    return (!term || name.includes(term) || node.id.includes(term))
      && (!instantOnly || isInstantNextLevel(node, state))
      && (!technolabeOnly || isTechnolabeNextLevel(node));
  });
}

function isTechnolabeNextLevel(node) {
  const current = Math.max(0, Number(state.researchLevels[node.id] || 0));
  if (current >= Number(node.maxLevel || 0)) return false;
  const data = node.levels.get(current + 1);
  if (!data) return false;
  const usage = technolabeUsage(data.baseTimeSeconds, data.technolabeCount);
  return Number(usage.count) > 0 && isTechnolabeRecommended(
    usage.efficiencyPercent,
    state.settings.technolabeRecommendationThresholdPercent,
  );
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
    button.append(create("span", "", catalog.categoryTitle(category, state.locale)), create("small", "", t("pwa.item_count", "{count}件", { count: matchingNodes(category).length })));
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
  if (!nodes.length) {
    byId("tree-empty").hidden = false;
    byId("tree-viewport").hidden = true;
    return;
  }
  byId("tree-viewport").hidden = false;
  const layout = visibleTreeLayout(nodes);
  zoom = clampTreeZoom(zoom, fittedZoom(category, nodes));
  const visibleIds = new Set(nodes.map((node) => node.id));
  const contentSize = treeContentSize(category, nodes);
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
  byId("tree-empty").hidden = true;
  byId("tree-viewport").hidden = false;
  byId("zoom-output").textContent = `${Math.round(zoom * 100)}%`;
  if (resetScroll) {
    const viewport = byId("tree-viewport");
    viewport.scrollLeft = Math.max(0, (width - viewport.clientWidth) / 2);
    viewport.scrollTop = 0;
  }
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
    path.dataset.toId = toId;
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

function updateLineStates() {
  const svg = byId("tree-lines");
  if (!svg) return;
  const activePaths = [];
  svg.querySelectorAll("path[data-to-id]").forEach((path) => {
    const target = catalog.nodes.get(path.dataset.toId);
    const unlocked = Boolean(target && isResearchConnectionUnlocked(target, state));
    path.classList.toggle("is-active", unlocked);
    path.classList.toggle("is-inactive", !unlocked);
    if (unlocked) activePaths.push(path);
  });
  activePaths.forEach((path) => svg.append(path));
}

function updateVisibleResearchState(changedNode) {
  if (!catalog || !changedNode) return;
  if (byId("instant-only")?.checked) {
    renderCategoryOptions();
    renderTree();
    return;
  }
  const category = catalog.categories.find((item) => item.id === selectedCategoryId);
  if (!category || changedNode.categoryId !== category.id) return;
  const visibleIds = new Set(matchingNodes(category).map((node) => node.id));
  const affectedIds = new Set([changedNode.id]);
  for (const [fromId, toId] of category.edges) {
    if (fromId === changedNode.id) affectedIds.add(toId);
  }
  const matching = matchingNodes(category);
  const layout = visibleTreeLayout(matching.length ? matching : category.nodes);
  for (const researchId of affectedIds) {
    if (!visibleIds.has(researchId)) continue;
    const node = catalog.nodes.get(researchId);
    const existing = byId("tree-cards")?.querySelector(`[data-node-id="${CSS.escape(researchId)}"]`);
    if (!node || !existing) continue;
    const slot = layout.slots.get(node.id) ?? node.column;
    const position = {
      x: (PADDING + slot * (CARD_WIDTH + GAP_X)) * zoom,
      y: (PADDING + (layout.rowSlots.get(node.row) ?? node.row) * (CARD_HEIGHT + GAP_Y)) * zoom,
      width: CARD_WIDTH * zoom,
      height: CARD_HEIGHT * zoom,
    };
    existing.replaceWith(renderCard(node, position));
  }
  updateLineStates();
  if (changedNode.id === "military_command_hidden_talent") {
    renderTalentPointCapacity();
    renderTalent();
  }
}

function updateResearchCardSelection() {
  const cards = byId("tree-cards")?.querySelectorAll(".research-card");
  if (!cards) return;
  for (const card of cards) {
    card.classList.toggle("is-selected", card.dataset.nodeId === selectedNodeId);
  }
}

function updateBulkLevelValue(nodeId, level) {
  const input = byId("bulk-level-list")?.querySelector(`[data-node-id="${CSS.escape(nodeId)}"] input[type="number"]`);
  if (input) input.value = String(level);
  const category = catalog.categories.find((item) => item.id === selectedBulkCategoryId);
  if (category) updateBulkProgress(category);
}

function markResearchPlansDirty() {
  planDirty = true;
  if (activeTab !== "plan") return;
  planDirty = false;
  if (planMode === "target") refreshCurrentPlan();
  if (planMode === "shortest") renderShortest();
  if (planMode === "tasks") renderTasks();
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
    const previousLevel = Math.min(node.maxLevel, Number(state.researchLevels[node.id] || 0));
    number.value = level; range.value = level; state.researchLevels[node.id] = level;
    updateStepButtons(level);
    renderDialogEffects(node, level); populateTargetLevels(node, level);
    if (level === previousLevel) return;
    scheduleSave();
    updateVisibleResearchState(node);
    updateBulkLevelValue(node.id, level);
    markResearchPlansDirty();
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
  updateResearchCardSelection();
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
  const next = create("p", "", level < node.maxLevel ? effectFor(node, level + 1) || "—" : t("pwa.maximum_level", "最大レベルです"));
  box.replaceChildren(current, next);
  renderNodeNextDetails(node, level);
}

function renderNodeNextDetails(node, level) {
  const target = byId("node-next-detail");
  if (!target) return;
  if (level >= node.maxLevel) {
    target.replaceChildren(create("p", "muted", t("pwa.maximum_level_reached", "最大レベルに到達しています。")));
    return;
  }
  const nextLevel = level + 1;
  const data = node.levels.get(nextLevel);
  const heading = create("h3", "", t("pwa.next_requirements", "Lv.{level} の必要条件", { level: nextLevel }));
  if (!data) {
    target.replaceChildren(heading, create("p", "muted", t("pwa.level_data_missing", "このレベルの時間・資源・前提条件データは未収録です。現在レベルの記録はできます。")));
    return;
  }
  const grid = create("div", "detail-grid");
  const time = create("div", "detail-item");
  time.append(create("span", "", t("plan.time", "研究時間")), create("strong", "", data.baseTimeSeconds == null ? t("common.unknown", "未収録") : formatDuration(adjustedTime(data.baseTimeSeconds, state.settings))));
  const academy = Math.max(Number(data.academyLevel || 0), Number(data.buildings.academy || 0));
  const facility = create("div", "detail-item");
  const facilityParts = [];
  if (academy) facilityParts.push(`${castleCatalog.buildingName("academy", state.locale)} Lv.${academy}`);
  if (data.buildings.mana_academy) facilityParts.push(`${castleCatalog.buildingName("mana_academy", state.locale)} Lv.${data.buildings.mana_academy}`);
  facility.append(create("span", "", t("castle.required", "必要施設")), create("strong", "", facilityParts.join(" / ") || t("common.none", "なし")));
  const effect = create("div", "detail-item detail-effect");
  effect.append(create("span", "", t("plan.effect", "効果")), create("strong", "", effectFor(node, nextLevel) || t("common.unknown", "未収録")));
  grid.append(time, facility, effect);
  const resourceBox = create("div", "detail-resources");
  const costs = RESOURCE_KEYS.filter((key) => Number(data.costs[key] || 0) > 0);
  if (costs.length) {
    for (const key of costs) {
      const item = create("div", "detail-resource");
      item.append(create("span", "", resourceName(key)), create("strong", "", formatResource(data.costs[key])));
      resourceBox.append(item);
    }
  } else {
    const item = create("div", "detail-resource");
    item.append(create("span", "", data.costsVerified ? t("pwa.no_resources", "資源なし") : t("pwa.resource_data_missing", "資源データ未収録")));
    resourceBox.append(item);
  }
  const requirements = create("ul", "detail-requirements");
  if (data.requirements.length) {
    for (const requirement of data.requirements) {
      const prerequisite = catalog.nodes.get(requirement.researchId);
      requirements.append(create("li", "", `${prerequisite ? catalog.nodeName(prerequisite, state.locale) : requirement.researchId} Lv.${requirement.level}`));
    }
  } else requirements.append(create("li", "", t("pwa.no_prerequisite", "前提研究なし")));
  target.replaceChildren(heading, grid, resourceBox, requirements);
}

function bindSettings() {
  const inputs = {
    "setting-player-level": ["playerLevel", true], "setting-vip": ["vipLevel", true], "setting-castle": ["castleLevel", true], "setting-castle-mana": ["castleManaStage", true], "setting-academy": ["academyLevel", true],
    "setting-construction-speed": ["constructionSpeedPercent", false], "setting-construction-boost": ["constructionSpeedBoostPercent", false],
    "setting-speed": ["researchSpeedPercent", false], "setting-boost": ["researchSpeedBoostPercent", false], "setting-helps": ["maxGuildHelps", true],
    "setting-technolabe-count": ["technolabeCount", true],
    "setting-technolabe-threshold": ["technolabeRecommendationThresholdPercent", false],
  };
  for (const [id, [key, integer]] of Object.entries(inputs)) {
    byId(id).addEventListener("input", (event) => {
      state.settings[key] = Math.max(0, integer ? Math.trunc(Number(event.target.value) || 0) : Number(event.target.value) || 0);
      if (key === "playerLevel") state.settings[key] = Math.max(1, Math.min(60, state.settings[key]));
      if (key === "vipLevel") state.settings[key] = Math.max(1, Math.min(15, state.settings[key]));
      if (key === "castleLevel" || key === "academyLevel") state.settings[key] = Math.max(1, Math.min(25, state.settings[key]));
      if (key === "castleManaStage") state.settings[key] = state.settings.castleLevel === 25 ? Math.max(0, Math.min(5, state.settings[key])) : 0;
      if (key === "castleLevel") {
        if (state.settings.castleLevel < 25) state.settings.castleManaStage = 0;
        castleTargetLevel = Math.min(25, state.settings.castleLevel + 1);
        state.settings.maxGuildHelps = guildHelpCount(state.settings);
      }
      if (key === "maxGuildHelps") state.settings.maxGuildHelps = guildHelpCount(state.settings);
      if (key === "technolabeRecommendationThresholdPercent") {
        state.settings[key] = Math.max(0, Math.min(100, state.settings[key]));
      }
      if (key === "castleLevel" || key === "castleManaStage") {
        castleTargetManaStage = state.settings.castleLevel === 25 && state.settings.castleManaStage < 5
          ? state.settings.castleManaStage + 1
          : state.settings.castleManaStage;
        state.settings.castleTargetManaStage = castleTargetManaStage;
      }
      updateGuildHelpLimit(); updateVipHint(); scheduleSave();
      if (key === "playerLevel") { renderTalentPointCapacity(); renderTalent(); }
      if (key === "technolabeRecommendationThresholdPercent" && byId("technolabe-only")?.checked) renderCategoryOptions();
      renderTree(); refreshCurrentPlan(); renderCastle(); if (planMode === "shortest") renderShortest();
    });
  }
  const resourceInputs = byId("resource-inputs");
  for (const key of RESOURCE_KEYS) {
    const label = create("label", "field");
    const caption = create("span", "", resourceName(key)); caption.id = `resource-label-${key}`; label.append(caption);
    const input = create("input"); input.type = "number"; input.inputMode = "numeric"; input.min = "0"; input.dataset.resource = key;
    input.addEventListener("input", () => { state.settings.resources[key] = Math.max(0, Math.trunc(Number(input.value) || 0)); scheduleSave(); refreshCurrentPlan(); });
    label.append(input); resourceInputs.append(label);
  }
  byId("speedup-inventory-add")?.addEventListener("click", () => openSpeedupInventoryEditor());
  byId("speedup-inventory-save")?.addEventListener("click", saveSpeedupInventoryEntry);
  byId("speedup-inventory-cancel")?.addEventListener("click", closeSpeedupInventoryEditor);
  byId("speedup-inventory-delete")?.addEventListener("click", deleteSpeedupInventoryEntry);
  byId("bulk-category-select")?.addEventListener("change", (event) => { selectedBulkCategoryId = event.target.value; renderBulkLevels(); });
  byId("bulk-level-search")?.addEventListener("input", renderBulkLevels);
  byId("language-select").addEventListener("change", (event) => activateLanguage(event.target.value));
  byId("export-backup").addEventListener("click", exportBackup);
  byId("import-backup").addEventListener("change", importBackup);
  byId("export-directive").addEventListener("click", exportResearchDirective);
  byId("import-directive").addEventListener("change", importResearchDirective);
  byId("export-language-template")?.addEventListener("click", exportLanguageTemplate);
  byId("import-language-pack")?.addEventListener("change", importCustomLanguagePack);
  byId("remove-language-pack")?.addEventListener("click", removeCustomLanguagePack);
  byId("reset-player").addEventListener("click", () => {
    if (!window.confirm(t("pwa.clear_confirm", "プレイヤー設定と全研究レベルをクリアしますか？"))) return;
    const locale = state.locale; state = defaultState(); state.locale = locale; ensureTalentPlan(); paidEditingId = ""; paidItemEditingIndex = -1; paidDraft = emptyPaidOffer(); castleTargetLevel = 0; castleTargetManaStage = 0; saveNow(); populateSettings(); renderCategoryOptions(); renderTree(true); currentPlan = null; renderPlan(); renderShortest(); renderTasks(); renderTalent(); renderCastle(); renderPaid(); toast(t("pwa.cleared", "設定をクリアしました"));
  });
}

function populateSettings() {
  byId("setting-player-level").value = state.settings.playerLevel;
  byId("setting-vip").value = state.settings.vipLevel;
  byId("setting-castle").value = state.settings.castleLevel;
  byId("setting-castle-mana").value = state.settings.castleManaStage;
  byId("setting-castle-mana").disabled = state.settings.castleLevel !== 25;
  byId("setting-construction-speed").value = state.settings.constructionSpeedPercent;
  byId("setting-construction-boost").value = state.settings.constructionSpeedBoostPercent;
  byId("setting-academy").value = state.settings.academyLevel;
  byId("setting-speed").value = state.settings.researchSpeedPercent;
  byId("setting-boost").value = state.settings.researchSpeedBoostPercent;
  byId("setting-technolabe-count").value = state.settings.technolabeCount;
  byId("setting-technolabe-threshold").value = state.settings.technolabeRecommendationThresholdPercent;
  updateGuildHelpLimit();
  byId("language-select").value = state.locale;
  byId("resource-display-mode").value = state.settings.resourceDisplayMode;
  document.querySelectorAll("[data-resource]").forEach((input) => {
    const key = input.dataset.resource;
    input.value = state.settings.resources[key] || 0;
    const caption = byId(`resource-label-${key}`);
    if (caption) caption.textContent = resourceName(key);
  });
  updateVipHint();
  renderTalentPointCapacity();
  renderSpeedupInventory();
  populateBulkCategoryOptions();
  renderBulkLevels();
  renderCastle();
}

function speedupInventoryChanged() {
  state.settings.speedupSeconds = 0;
  updateSpeedupInventorySummary();
  scheduleSave();
  refreshCurrentPlan();
  renderCastle();
  if (planMode === "tasks") renderTasks();
}

function speedupInventoryEntryLabel(entry) {
  const [durationValue, durationUnit] = paidDurationParts(entry.durationSeconds);
  return t(
    "player.speedup_entry",
    "{duration}{unit} × {quantity}個",
    {
      duration: durationValue.toLocaleString(state.locale),
      unit: t(`paid.unit.${durationUnit}`, durationUnit),
      quantity: entry.quantity.toLocaleString(state.locale),
    },
  );
}

function openSpeedupInventoryEditor(index = -1) {
  const entries = normalizeSpeedupInventory(state.settings.speedupInventory);
  speedupEditingIndex = Number.isInteger(index) && index >= 0 && index < entries.length ? index : -1;
  const entry = speedupEditingIndex >= 0
    ? entries[speedupEditingIndex]
    : { kind: "general", durationSeconds: 3600, quantity: 1 };
  const kind = byId("speedup-inventory-kind");
  kind.replaceChildren(...SPEEDUP_KINDS.map((key) => {
    const option = create("option", "", paidKindLabel(key));
    option.value = key;
    return option;
  }));
  kind.value = entry.kind;
  const [durationValue, durationUnit] = paidDurationParts(entry.durationSeconds);
  byId("speedup-inventory-duration").value = String(Math.max(1, durationValue));
  const unit = byId("speedup-inventory-unit");
  unit.replaceChildren(...["seconds", "minutes", "hours", "days"].map((key) => {
    const option = create("option", "", t(`paid.unit.${key}`, key));
    option.value = key;
    return option;
  }));
  unit.value = durationUnit;
  byId("speedup-inventory-quantity").value = String(Math.max(1, entry.quantity));
  byId("speedup-inventory-editor-title").textContent = speedupEditingIndex >= 0
    ? t("player.speedup_edit", "スピードアップを編集")
    : t("player.speedup_new", "スピードアップを追加");
  byId("speedup-inventory-delete").hidden = speedupEditingIndex < 0;
  byId("speedup-inventory-editor").hidden = false;
  renderSpeedupInventory();
}

function closeSpeedupInventoryEditor() {
  speedupEditingIndex = -1;
  byId("speedup-inventory-editor").hidden = true;
  renderSpeedupInventory();
}

function saveSpeedupInventoryEntry() {
  const entries = normalizeSpeedupInventory(state.settings.speedupInventory);
  const entry = {
    kind: byId("speedup-inventory-kind").value,
    durationSeconds: Math.max(1, Math.trunc(Number(byId("speedup-inventory-duration").value) || 1))
      * paidUnitSeconds(byId("speedup-inventory-unit").value),
    quantity: Math.max(1, Math.trunc(Number(byId("speedup-inventory-quantity").value) || 1)),
  };
  state.settings.speedupInventory = saveOwnedSpeedupEntry(entries, speedupEditingIndex, entry);
  closeSpeedupInventoryEditor();
  speedupInventoryChanged();
}

function deleteSpeedupInventoryEntry() {
  const entries = normalizeSpeedupInventory(state.settings.speedupInventory);
  if (speedupEditingIndex < 0 || speedupEditingIndex >= entries.length) return;
  state.settings.speedupInventory = deleteOwnedSpeedupEntry(entries, speedupEditingIndex);
  closeSpeedupInventoryEditor();
  speedupInventoryChanged();
}

function renderSpeedupInventory() {
  const list = byId("speedup-inventory-list");
  if (!list) return;
  const entries = normalizeSpeedupInventory(state.settings.speedupInventory);
  state.settings.speedupInventory = entries;
  list.replaceChildren(...entries.map((entry, index) => {
    const row = create("button", "speedup-inventory-row");
    row.type = "button";
    row.classList.toggle("is-selected", speedupEditingIndex === index && !byId("speedup-inventory-editor").hidden);
    row.setAttribute("aria-pressed", String(speedupEditingIndex === index && !byId("speedup-inventory-editor").hidden));
    const main = create("span", "speedup-inventory-row-main");
    main.append(create("strong", "", paidKindLabel(entry.kind)), create("span", "", speedupInventoryEntryLabel(entry)));
    row.append(main, create("span", "speedup-inventory-row-total", formatDuration(entry.durationSeconds * entry.quantity)));
    row.addEventListener("click", () => openSpeedupInventoryEditor(index));
    return row;
  }));
  byId("speedup-inventory-empty").hidden = entries.length > 0;
  updateSpeedupInventorySummary();
}

function updateSpeedupInventorySummary() {
  const summary = byId("speedup-inventory-summary");
  if (!summary) return;
  const total = normalizeSpeedupInventory(state.settings.speedupInventory)
    .reduce((value, item) => value + item.durationSeconds * item.quantity, 0);
  summary.textContent = t("player.speedup_total", "全種類の合計: {time}", { time: formatDuration(total) });
}

function updateGuildHelpLimit() {
  const input = byId("setting-helps");
  if (!input) return;
  const limit = maxGuildHelpsForCastle(state.settings.castleLevel);
  state.settings.maxGuildHelps = guildHelpCount(state.settings);
  input.max = String(limit);
  input.value = String(state.settings.maxGuildHelps);
  input.title = t("player.guild_helps_hint", "城Lv.{level}では最大{count}回です。", { level: state.settings.castleLevel, count: limit });
  const hint = byId("guild-help-limit");
  if (hint) hint.textContent = t("pwa.help_limit", "上限 {count}回", { count: limit });
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
    row.dataset.nodeId = node.id;
    const open = create("button", "", catalog.nodeName(node, state.locale)); open.type = "button";
    open.addEventListener("click", () => { jumpToNode(node); requestAnimationFrame(() => openNodeDialog(node.id)); });
    const input = create("input"); input.type = "number"; input.inputMode = "numeric"; input.min = "0"; input.max = String(node.maxLevel); input.value = String(Math.min(node.maxLevel, Number(state.researchLevels[node.id] || 0))); input.setAttribute("aria-label", t("pwa.current_level_aria", "{name}の現在レベル", { name: catalog.nodeName(node, state.locale) }));
    input.addEventListener("input", () => {
      const level = Math.max(0, Math.min(node.maxLevel, Math.trunc(Number(input.value) || 0)));
      state.researchLevels[node.id] = level;
      updateBulkProgress(category);
      scheduleSave();
      updateVisibleResearchState(node);
      markResearchPlansDirty();
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

function updateVipHint() { byId("vip-free-time").textContent = t("pwa.vip_free_time", "VIP {level} の無料スピードアップ: {minutes}分", { level: state.settings.vipLevel, minutes: Math.round(freeSecondsForVip(state.settings.vipLevel) / 60) }); }

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
    [t("player.effective_construction_speed", "有効建設速度"), `+${(Number(state.settings.constructionSpeedPercent || 0) + Number(state.settings.constructionSpeedBoostPercent || 0)).toLocaleString(state.locale)}%`],
    [t("pwa.total_time", "合計時間"), formatDuration(plan.totals.adjustedSeconds)],
  ];
  byId("construction-selection").textContent = `${castleCatalog.buildingName(constructionTargetBuildingId, state.locale)}　Lv.${selectedCurrent} → Lv.${selectedTarget}`;
  for (const key of CASTLE_RESOURCE_KEYS.filter((key) => Number(plan.totals.costs[key] || 0) > 0)) {
    summaryItems.push([resourceName(key), formatResource(plan.totals.costs[key])]);
  }
  if (plan.totals.totalGems > 0) summaryItems.push([t("castle.gem_estimate", "ジェム目安"), Number(plan.totals.totalGems).toLocaleString(state.locale)]);
  summary.replaceChildren(...summaryItems.map(([label, value]) => {
    const card = create("div", "castle-summary-card");
    card.append(create("span", "", label), create("strong", "", value));
    return card;
  }));
  const castleSpeedup = create("details", "speedup-simulation castle-speedup-simulation");
  summary.append(castleSpeedup);
  renderSpeedupSimulation(
    castleSpeedup,
    plan.totals.adjustedSeconds,
    "construction",
    0,
    plan.steps.map((step) => step.adjustedSeconds),
  );

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
    input.setAttribute("aria-label", t("pwa.current_level_aria", "{name}の現在レベル", { name: castleCatalog.buildingName(buildingId, state.locale) }));
    input.addEventListener("change", () => {
      state.buildingLevels[buildingId] = Math.max(minimum, Math.min(building.maxLevel, Math.trunc(Number(input.value) || 0)));
      scheduleSave();
      renderCastle();
    });
    const required = Math.max(value, Number(requiredById.get(buildingId) || value));
    row.append(numberStepper(input), create("small", "", t("pwa.required_level", "必要 {level}", { level: required })));
    return row;
  }));

  const list = byId("castle-plan-list");
  if (!plan.steps.length) {
    list.replaceChildren(create("div", "castle-empty", t("castle.no_work", "目標レベルまでの建設は完了しています。")));
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
      time.title = `${t("castle.base_time", "基礎時間")} ${formatDuration(step.baseSeconds)}`;
      const complete = create("button", "step-complete", t("plan.complete_step", "完了"));
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
  toast(t("pwa.construction_applied", "{name} {level}まで反映しました", { name: step.manaStage ? castleCatalog.manaName(state.locale) : castleCatalog.buildingName(step.buildingId, state.locale), level: castleProgressLabel(step.level, step.manaStage) }));
}

function scheduleSave() { byId("save-indicator").textContent = t("pwa.saving", "保存中…"); clearTimeout(saveTimer); saveTimer = setTimeout(saveNow, 250); }
function saveNow() { saveState(state); byId("save-indicator").textContent = t("pwa.saved", "保存済み"); }

function exportBackup() {
  saveNow();
  const blob = new Blob([JSON.stringify(backupPayload(state), null, 2)], { type: "application/json" });
  const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = `RLMResearchPlanner_${new Date().toISOString().slice(0, 10)}.json`; link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000); toast(t("player.backup_exported", "バックアップを書き出しました"));
}

async function importBackup(event) {
  const file = event.target.files?.[0]; if (!file) return;
  try {
    const imported = stateFromBackup(JSON.parse(await file.text())); imported.locale = state.locale; state = imported; ensureTalentPlan(); paidEditingId = ""; paidItemEditingIndex = -1; paidDraft = emptyPaidOffer(); castleTargetLevel = 0; saveNow(); populateSettings(); renderCategoryOptions(); renderTree(true); currentPlan = null; renderPlan(); renderShortest(); renderTasks(); renderTalent(); renderCastle(); renderPaid(); toast(t("player.backup_restored", "バックアップを読み込みました"));
  } catch (error) { toast(error.message); }
  finally { event.target.value = ""; }
}

function formatMessage(template, values = {}) {
  return String(template || "").replace(/\{([A-Za-z0-9_]+)\}/g, (match, key) => (key in values ? String(values[key]) : match));
}

function t(key, fallback = key, values = {}) {
  return formatMessage(messages[key] || fallback, values);
}

function resourceName(key) {
  return packText(activeLanguagePack, "resources", key, messages[`resource.${key}`] || key);
}

function populateLanguageOptions() {
  const select = byId("language-select");
  if (!select) return;
  const options = (localeManifest?.locales || []).map((entry) => ({
    locale: entry.locale,
    name: languagePacks[entry.locale]?.name || entry.name,
    custom: Boolean(languagePacks[entry.locale]),
  }));
  for (const pack of Object.values(languagePacks)) {
    if (!options.some((entry) => entry.locale === pack.locale)) options.push({ locale: pack.locale, name: pack.name, custom: true });
  }
  select.replaceChildren(...options.map((item) => {
    const option = create("option", "", item.custom ? `${item.name} (${item.locale})` : item.name);
    option.value = item.locale;
    option.selected = item.locale === state.locale;
    return option;
  }));
  const remove = byId("remove-language-pack");
  if (remove) remove.disabled = !languagePacks[state.locale];
}

function activateLanguage(locale, { save = true, render = true } = {}) {
  const available = [...Object.keys(bundledLanguagePacks), ...Object.keys(languagePacks)];
  locale = selectPreferredLocale([locale], available, localeManifest?.fallbackLocale || "en-US");
  state.locale = locale;
  activeLanguagePack = resolveLanguagePack(
    locale,
    bundledLanguagePacks,
    languagePacks,
    localeManifest?.fallbackLocale || "en-US",
  );
  messages = { ...(activeLanguagePack?.sections?.messages || {}) };
  effectLabels = {};
  catalog?.setLanguagePack(activeLanguagePack);
  castleCatalog?.setLanguagePack(activeLanguagePack);
  talentCatalog?.setLanguagePack(activeLanguagePack);
  applyDocumentLanguage(locale, activeLanguagePack?.direction || localeManifest?.byLocale?.[locale]?.direction);
  translateStatic(document, messages);
  renderConnectivity();
  populateLanguageOptions();
  renderCommonHelp();
  if (save) scheduleSave();
  if (!render || !catalog) return;
  populateSettings();
  renderCategoryOptions();
  renderTree();
  renderPlan();
  renderShortest();
  renderTasks();
  renderTalent();
  renderCastle();
  renderPaid();
  renderCatalogStatus();
}

function downloadJson(payload, filename) {
  const blob = new Blob([`${JSON.stringify(payload, null, 2)}\n`], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

function exportLanguageTemplate() {
  const fallbackPack = bundledLanguagePacks[localeManifest?.fallbackLocale] || null;
  const englishMessages = fallbackPack?.sections?.messages || {};
  downloadJson(
    languagePackTemplate({ catalog, castleCatalog, talentCatalog, messages: englishMessages, fallbackPack }),
    "RLMResearchPlanner-language-template.json",
  );
  toast(t("language.pack_exported", "翻訳ひな形を書き出しました"));
}

async function importCustomLanguagePack(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    const pack = installLanguagePack(JSON.parse(await file.text()));
    languagePacks = loadLanguagePacks();
    activateLanguage(pack.locale);
    toast(t("language.pack_imported", "翻訳を読み込みました", { name: pack.name }));
  } catch (error) {
    toast(t("language.pack_invalid", `翻訳ファイルを読み込めませんでした: ${error.message}`, { error: error.message }));
  } finally {
    event.target.value = "";
  }
}

function removeCustomLanguagePack() {
  if (!activeLanguagePack) return;
  if (!window.confirm(t("language.pack_remove_confirm", `追加翻訳 ${state.locale} を削除しますか？`, { locale: state.locale }))) return;
  if (!removeLanguagePack(state.locale)) return;
  languagePacks = loadLanguagePacks();
  activateLanguage(bundledLanguagePacks[state.locale] ? state.locale : localeManifest.fallbackLocale);
  toast(t("language.pack_removed", "追加翻訳を削除しました"));
}

function exportResearchDirective() {
  const name = byId("directive-name").value.trim() || t("plan.directive_default_name", "研究指示");
  const payload = researchDirectivePayload(state.planTasks, {
    name,
    datasetId: catalog?.datasetId,
    gameVersion: catalog?.gameVersion,
  });
  if (!payload.tasks.length) { toast(t("plan.directive_empty", "書き出す登録タスクがありません")); return; }
  const safeName = name.replace(/[\\/:*?"<>|]+/g, "_").replace(/\s+/g, "_").slice(0, 60) || "ResearchDirective";
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = `RLMResearchDirective_${safeName}_${new Date().toISOString().slice(0, 10)}.json`; link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000); toast(t("plan.directive_exported", "{count}件の研究タスクを書き出しました", { count: payload.tasks.length }));
}

async function importResearchDirective(event) {
  const file = event.target.files?.[0]; if (!file) return;
  try {
    const directive = researchDirectiveFromPayload(JSON.parse(await file.text()));
    const validTasks = directive.tasks.filter((task) => {
      const node = catalog?.nodes.get(task.researchId);
      return node && task.targetLevel <= node.maxLevel;
    });
    const skipped = directive.tasks.length - validTasks.length;
    if (!validTasks.length) throw new Error(t("plan.directive_invalid", "現在の研究データで使用できるタスクがありません"));
    const merged = mergeResearchDirectiveTasks(state.planTasks, validTasks, directive.name);
    state.planTasks = merged.tasks;
    byId("directive-name").value = directive.name;
    saveNow();
    setPlanMode("tasks");
    showTab("plan");
    toast(t("plan.directive_imported", "{name}: 追加{added}件 / 目標更新{updated}件 / 登録済み{unchanged}件 / 対象外{skipped}件", {
      name: directive.name, added: merged.added, updated: merged.updated, unchanged: merged.unchanged, skipped,
    }));
  } catch (error) { toast(error.message); }
  finally { event.target.value = ""; }
}

function bindPlans() {
  byId("plan-target-mode").addEventListener("click", () => setPlanMode("target"));
  byId("plan-shortest-mode").addEventListener("click", () => setPlanMode("shortest"));
  byId("plan-tasks-mode").addEventListener("click", () => setPlanMode("tasks"));
  byId("register-plan").addEventListener("click", registerCurrentPlan);
  byId("complete-plan").addEventListener("click", completeCurrentPlan);
  byId("shortest-limit").addEventListener("change", () => {
    shortestPage = 0;
    renderShortest();
  });
  byId("shortest-previous").addEventListener("click", () => {
    shortestPage = Math.max(0, shortestPage - 1);
    renderShortest();
  });
  byId("shortest-next").addEventListener("click", () => {
    shortestPage += 1;
    renderShortest();
  });
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
  const merged = mergeResearchDirectiveTasks(state.planTasks, [{ researchId: currentPlan.targetId, targetLevel: currentPlan.targetLevel }]);
  if (!merged.added && !merged.updated) { toast(t("plan.task_already_registered", "同じ研究の同等以上の目標は登録済みです")); return; }
  state.planTasks = merged.tasks;
  saveNow(); renderTasks(); toast(merged.updated ? t("pwa.task_updated", "登録済みタスクの目標レベルを更新しました") : t("plan.task_registered", "研究計画をタスクに登録しました"));
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
  toast(t("pwa.plan_applied", "目標研究と前提研究を含む{count}件のレベルを反映しました", { count: changed.length }));
}

function renderPlan() {
  byId("plan-placeholder").hidden = Boolean(currentPlan);
  byId("plan-result").hidden = !currentPlan;
  if (!currentPlan) {
    byId("plan-speedup-summary").hidden = true;
    renderPlanTree();
    return;
  }
  const target = catalog.nodes.get(currentPlan.targetId);
  const targetCategory = catalog.categories.find((item) => item.id === target.categoryId);
  byId("plan-target-name").textContent = `${catalog.nodeName(target, state.locale)} Lv.${currentPlan.targetLevel}`;
  byId("plan-steps-title").textContent = t("pwa.required_research_category", "必要な研究（{category}）", { category: catalog.categoryTitle(targetCategory, state.locale) });
  const partialTime = currentPlan.totals.unknownTime ? ` + ${t("common.unknown", "未確認")}` : "";
  byId("plan-total-time").textContent = `${t("plan.time", "開始時")} ${formatDuration(currentPlan.totals.adjustedSeconds)}${partialTime}`;
  const totalHelpTime = byId("plan-total-help-time");
  const helpCount = guildHelpCount(state.settings);
  totalHelpTime.hidden = helpCount === 0;
  totalHelpTime.textContent = helpCount > 0
    ? `${t("plan.after_help", "ヘルプ後")} ${formatDuration(currentPlan.totals.afterHelpSeconds)}${partialTime}`
    : "";
  const wisdomSummary = byId("plan-wisdom-summary");
  wisdomSummary.textContent = wisdomText(currentPlan.totals.technolabeCount, currentPlan.totals.technolabeEfficiencyPercent, currentPlan.totals.unknownTechnolabe);
  wisdomSummary.classList.toggle("is-recommended", technolabeRecommended(currentPlan.totals.technolabeCount, currentPlan.totals.technolabeEfficiencyPercent, currentPlan.totals.unknownTechnolabe));
  const resources = Object.fromEntries(RESOURCE_KEYS.map((key) => [key, resourceName(key)]));
  const usedResources = RESOURCE_KEYS.filter((key) => Number(currentPlan.totals.costs[key] || 0) > 0);
  byId("resource-summary").replaceChildren(...usedResources.map((key) => {
    const chip = create("div", "resource-chip"); const needed = currentPlan.totals.costs[key] || 0; const available = state.settings.resources[key] || 0;
    if (needed > available) chip.classList.add("is-short");
    chip.append(create("span", "", resources[key]), create("strong", "", formatResource(needed)), create("span", "", needed > available ? t("pwa.shortage", "不足 {amount}", { amount: formatResource(needed - available) }) : t("pwa.within_owned", "所持数以内"))); return chip;
  }));
  if (currentPlan.totals.unknownCosts) {
    const chip = create("div", "resource-chip is-unknown");
    chip.append(
      create("span", "", resourceName("special")),
      create("strong", "", t("common.unknown", "未確認")),
      create("span", "", t("pwa.unknown_special_material", "専用素材を含む費用データ未収録")),
    );
    byId("resource-summary").append(chip);
  } else if (!usedResources.length) {
    byId("resource-summary").append(create("div", "callout", t("pwa.no_required_resources", "必要資源なし")));
  }
  renderSpeedupSimulation(
    byId("plan-speedup-summary"),
    currentPlan.totals.afterHelpSeconds,
    "research",
    currentPlan.totals.unknownTime,
    currentPlan.steps.map((step) => step.afterHelpSeconds || 0),
  );
  renderPlanTree();
  byId("plan-steps").replaceChildren(...currentPlan.steps.map((step) => planRow(step, { showCategory: false })));
  byId("complete-plan").disabled = currentPlan.steps.length === 0;
  byId("register-plan").disabled = currentPlan.steps.length === 0;
  const issueParts = [];
  if (currentPlan.totals.unknownTime) issueParts.push(t("pwa.unknown_time_count", "時間未確認 {count}件", { count: currentPlan.totals.unknownTime }));
  if (currentPlan.totals.unknownCosts) issueParts.push(t("pwa.unknown_cost_count", "資源未確認 {count}件", { count: currentPlan.totals.unknownCosts }));
  issueParts.push(...currentPlan.issues);
  byId("plan-issues").textContent = issueParts.join(" / ");
}

function renderPlanTree() {
  const viewport = byId("plan-tree-viewport");
  const stage = byId("plan-tree-stage");
  const cards = byId("plan-tree-cards");
  const svg = byId("plan-tree-lines");
  const empty = byId("plan-tree-empty");
  if (!viewport || !stage || !cards || !svg || !empty) return;
  if (!currentPlan?.steps.length) {
    cards.replaceChildren();
    svg.replaceChildren();
    viewport.hidden = true;
    empty.hidden = false;
    return;
  }

  const required = Object.entries(currentPlan.requiredLevels || {})
    .map(([researchId, requiredLevel]) => ({ node: catalog.nodes.get(researchId), requiredLevel: Number(requiredLevel) }))
    .filter((item) => item.node);
  const categoryOrder = new Map(catalog.categories.map((category, index) => [category.id, index]));
  const rowKeys = [...new Set(required.map(({ node }) => `${categoryOrder.get(node.categoryId) ?? 999}\0${node.row}`))]
    .sort((left, right) => {
      const [leftCategory, leftRow] = left.split("\0").map(Number);
      const [rightCategory, rightRow] = right.split("\0").map(Number);
      return leftCategory - rightCategory || leftRow - rightRow;
    });
  const compactRows = new Map(rowKeys.map((key, index) => [key, index]));
  const layoutNodes = required.map(({ node, requiredLevel }) => ({
    ...node,
    row: compactRows.get(`${categoryOrder.get(node.categoryId) ?? 999}\0${node.row}`),
    requiredLevel,
  }));
  const layout = explicitTreeLayout(layoutNodes);
  const unscaledWidth = PADDING * 2 + layout.columnCount * CARD_WIDTH + Math.max(0, layout.columnCount - 1) * GAP_X;
  const unscaledHeight = PADDING * 2 + layout.rowCount * CARD_HEIGHT + Math.max(0, layout.rowCount - 1) * GAP_Y;
  const scale = Math.max(0.48, Math.min(0.86, (Math.max(320, viewport.clientWidth) - 18) / unscaledWidth));
  const width = Math.max(viewport.clientWidth - 2, unscaledWidth * scale);
  const height = Math.max(viewport.clientHeight - 2, unscaledHeight * scale);
  stage.style.width = `${width}px`;
  stage.style.height = `${height}px`;
  const positions = new Map(layoutNodes.map((node) => [node.id, {
    x: (PADDING + (layout.slots.get(node.id) ?? node.column) * (CARD_WIDTH + GAP_X)) * scale,
    y: (PADDING + node.row * (CARD_HEIGHT + GAP_Y)) * scale,
    width: CARD_WIDTH * scale,
    height: CARD_HEIGHT * scale,
  }]));
  renderPlanTreeLines(currentPlan.edges || [], positions, width, height, scale);
  cards.replaceChildren(...layoutNodes.map((node) => renderPlanTreeCard(node, positions.get(node.id), scale)));
  viewport.hidden = false;
  empty.hidden = true;
}

function renderPlanTreeLines(edges, positions, width, height, scale) {
  const svg = byId("plan-tree-lines");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("width", width);
  svg.setAttribute("height", height);
  const paths = [];
  for (const [fromId, toId] of edges) {
    const from = positions.get(fromId);
    const to = positions.get(toId);
    if (!from || !to) continue;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.classList.add("is-inactive");
    const x1 = from.x + from.width / 2;
    const y1 = from.y + from.height;
    const x2 = to.x + to.width / 2;
    const y2 = to.y;
    const middle = y1 + Math.max(10 * scale, (y2 - y1) / 2);
    path.setAttribute("d", `M ${x1} ${y1} V ${middle} H ${x2} V ${y2}`);
    paths.push(path);
  }
  svg.replaceChildren(...paths);
}

function renderPlanTreeCard(node, position, scale) {
  const current = Math.min(node.maxLevel, Number(state.researchLevels[node.id] || 0));
  const required = Math.min(node.maxLevel, Math.max(current, Number(node.requiredLevel) || 0));
  const missing = Math.max(0, required - current);
  const card = create("button", "research-card plan-research-card");
  card.type = "button";
  card.style.left = `${position.x}px`;
  card.style.top = `${position.y}px`;
  card.style.width = `${position.width}px`;
  card.style.height = `${position.height}px`;
  card.style.setProperty("--node-scale", scale);
  if (node.id === currentPlan.targetId) card.classList.add("is-target");
  const name = create("span", "research-name", catalog.nodeName(node, state.locale));
  const nameLength = [...name.textContent].reduce((sum, character) => sum + (character.charCodeAt(0) > 255 ? 1 : .58), 0);
  name.style.fontSize = `${Math.max(13, Math.min(25, 215 / Math.max(5, nameLength))) * scale}px`;
  const meter = create("span", "research-meter");
  const fill = create("span");
  fill.style.width = `${node.maxLevel ? current / node.maxLevel * 100 : 0}%`;
  meter.append(fill);
  card.append(
    name,
    meter,
    create("span", "research-level", `${current} / ${node.maxLevel}`),
    create("span", "plan-research-required", t("plan.required_level", "必要 Lv.{level}", { level: required })),
    create("span", "plan-research-missing", t("plan.missing_levels", "不足 {count}レベル", { count: missing })),
  );
  card.addEventListener("click", () => jumpToNode(node));
  return card;
}

function renderShortest() {
  if (!catalog) return;
  const limit = Number(byId("shortest-limit")?.value || 20);
  const result = paginateItems(shortestAvailable(catalog, state), shortestPage, limit);
  shortestPage = result.page;
  const steps = result.items;
  const currentPage = result.totalPages ? result.page + 1 : 0;
  byId("shortest-page-status").textContent = t(
    "plan.page_status",
    "{current} / {total}（全{count}件）",
    { current: currentPage, total: result.totalPages, count: result.totalItems },
  );
  byId("shortest-previous").disabled = result.page === 0;
  byId("shortest-next").disabled = result.page + 1 >= result.totalPages;
  const list = byId("shortest-list");
  list.replaceChildren(...steps.map((step) => planRow(step, { selected: step.researchId === selectedNodeId })));
  const selected = steps.find((step) => step.researchId === selectedNodeId);
  const banner = byId("shortest-selected");
  banner.hidden = !selected;
  if (selected) banner.textContent = t("pwa.selected_research", "選択中：{name} Lv.{level}", { name: catalog.nodeName(catalog.nodes.get(selected.researchId), state.locale), level: selected.level });
  if (!steps.length) list.append(create("div", "callout", t("pwa.no_short_research", "現在の条件で開始でき、時間データが確認済みの研究はありません。")));
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
    const remaining = create("strong", "", plan.steps.length ? `${t("plan.time", "開始時")} ${formatDuration(plan.totals.adjustedSeconds)}` : t("plan.task_completed", "完了済み"));
    heading.append(title, remaining);
    const helpCount = guildHelpCount(state.settings);
    const helpSummary = helpCount > 0 && plan.steps.length
      ? ` / ${t("plan.after_help", "ヘルプ後")} ${formatDuration(plan.totals.afterHelpSeconds)}`
      : "";
    const currentLevel = Math.min(node.maxLevel, Number(state.researchLevels[task.researchId] || 0));
    const meta = create("p", "muted", t("pwa.task_meta", "現在 Lv.{current} / 残り {steps}手順{help} / {wisdom}", { current: currentLevel, steps: plan.steps.length, help: helpSummary, wisdom: wisdomText(plan.totals.technolabeCount, plan.totals.technolabeEfficiencyPercent, plan.totals.unknownTechnolabe) }));
    meta.classList.toggle("wisdom-recommended", technolabeRecommended(plan.totals.technolabeCount, plan.totals.technolabeEfficiencyPercent, plan.totals.unknownTechnolabe));
    const source = task.sourceName ? create("p", "task-source", t("pwa.directive_source", "指示: {name}", { name: task.sourceName })) : null;
    const resources = create("div", "task-resources");
    const used = RESOURCE_KEYS.filter((key) => Number(plan.totals.costs[key] || 0) > 0);
    for (const key of used) resources.append(create("span", "", `${resourceName(key)} ${formatResource(plan.totals.costs[key])}`));
    if (!used.length) resources.append(create("span", "", t("pwa.no_required_resources", "必要資源なし")));
    const actions = create("div", "button-row task-actions");
    const show = create("button", "primary", t("plan.show_task", "計画を表示")); show.type = "button"; show.addEventListener("click", () => { buildTargetPlan(task.researchId, task.targetLevel); showTab("plan"); });
    const remove = create("button", "danger", t("plan.remove_task", "削除")); remove.type = "button"; remove.addEventListener("click", () => { state.planTasks = state.planTasks.filter((saved) => saved !== task); saveNow(); renderTasks(); });
    actions.append(show, remove); card.append(heading); if (source) card.append(source); card.append(meta, resources, actions); list.append(card);
  }
  if (!list.children.length) list.append(create("div", "callout", t("pwa.no_tasks", "登録した研究計画はありません。目標研究の計画からタスクに登録できます。")));
}

function planRow(step, { showCategory = true, selected = false } = {}) {
  const node = catalog.nodes.get(step.researchId);
  const row = create("article", "plan-row");
  if (selected) row.classList.add("is-selected");
  const nameButton = create("button", "", `${catalog.nodeName(node, state.locale)} Lv.${step.level}`); nameButton.type = "button";
  nameButton.addEventListener("click", () => jumpToNode(node));
  const categoryName = catalog.categoryTitle(catalog.categories.find((item) => item.id === node.categoryId), state.locale);
  const effect = effectFor(node, step.level) || t("pwa.effect_missing", "効果未収録");
  const main = create("div", "plan-step-main");
  main.append(nameButton);
  if (showCategory) main.append(create("span", "plan-row-category", categoryName));
  else main.classList.add("is-single-category");
  main.append(
    create("span", "plan-row-effect", `${t("plan.effect", "効果")} ${effect}`),
    resourceDetails(step.costs, RESOURCE_KEYS, step.costsVerified),
  );
  const footer = create("div", "plan-step-footer");
  const timing = create("div", "plan-step-timing");
  timing.append(create("strong", "plan-row-time", step.adjustedSeconds == null ? `${t("plan.time", "開始時")} ${t("common.unknown", "未確認")}` : `${t("plan.time", "開始時")} ${formatDuration(step.adjustedSeconds)}`));
  const helpCount = guildHelpCount(state.settings);
  if (helpCount > 0) {
    timing.append(create("span", "plan-row-help", step.afterHelpSeconds == null ? `${t("plan.after_help", "ヘルプ後")} ${t("common.unknown", "未確認")}` : `${t("plan.after_help", "ヘルプ後")} ${formatDuration(step.afterHelpSeconds)}`));
  }
  const wisdom = create("span", "plan-row-wisdom", wisdomText(step.technolabeCount, step.technolabeEfficiencyPercent));
  wisdom.classList.toggle("is-recommended", technolabeRecommended(step.technolabeCount, step.technolabeEfficiencyPercent));
  timing.append(wisdom);
  const complete = create("button", "step-complete", t("plan.complete_step", "研究完了")); complete.type = "button"; complete.addEventListener("click", () => completePlanStep(step));
  footer.append(timing, complete);
  row.append(main, footer); return row;
}

function resourceDetails(costs, keys, costsVerified = true) {
  const details = create("details", "plan-resource-details");
  const used = keys.filter((key) => Number(costs[key] || 0) > 0);
  const summary = create(
    "summary",
    "",
    used.length
      ? t("pwa.material_count", "資材 {count}", { count: used.length })
      : costsVerified
        ? t("pwa.no_materials", "資材なし")
        : t("pwa.materials_unknown", "資材 未確認"),
  );
  const resources = create("div", "plan-row-resources");
  for (const key of used) {
    const item = create("div", "plan-resource-item");
    item.append(create("span", "", resourceName(key)), create("strong", "", formatResource(costs[key])));
    resources.append(item);
  }
  if (!used.length) {
    resources.append(create(
      "div",
      "plan-resource-item",
      costsVerified
        ? t("pwa.no_required_materials", "必要資材なし")
        : t("pwa.unknown_special_material", "専用素材を含む費用データ未収録"),
    ));
  }
  details.append(summary, resources);
  return details;
}

function wisdomText(count, efficiencyPercent, unknownCount = 0) {
  const label = t("plan.technolabe", "叡智の輪");
  if (count == null) return `${label} ${t("common.unknown", "未確認")}`;
  if (!count) return unknownCount ? t("pwa.wisdom_unknown_count", "{label} 未確認（{count}件）", { label, count: unknownCount }) : `${label} -`;
  let text = t("pwa.wisdom_efficiency", "{label} {count}個 / 効率{efficiency}%", { label, count, efficiency: Number(efficiencyPercent || 0).toFixed(1) });
  if (technolabeRecommended(count, efficiencyPercent, unknownCount)) {
    text = t("plan.technolabe_recommended", "★ 叡智の輪推奨 — {detail}", { detail: text });
  }
  text = t("plan.technolabe_owned", "{detail}（所持 {owned} / 必要 {required}）", {
    detail: text,
    owned: Math.max(0, Math.trunc(Number(state.settings.technolabeCount) || 0)),
    required: count,
  });
  return unknownCount ? t("pwa.wisdom_with_unknown", "{text}（{count}件未確認）", { text, count: unknownCount }) : text;
}

function technolabeRecommended(count, efficiencyPercent, unknownCount = 0) {
  return Number(unknownCount) <= 0 && Number(count) > 0 && isTechnolabeRecommended(
    efficiencyPercent,
    state.settings.technolabeRecommendationThresholdPercent,
  );
}

function completePlanStep(step) {
  const current = Number(state.researchLevels[step.researchId] || 0);
  if (step.level <= current) return;
  state.researchLevels[step.researchId] = step.level;
  saveNow(); populateSettings(); renderCategoryOptions(); renderTree(); refreshCurrentPlan(); renderShortest(); renderTasks();
  toast(t("pwa.research_applied", "{name} Lv.{level}を反映しました", { name: catalog.nodeName(catalog.nodes.get(step.researchId), state.locale), level: step.level }));
}

function formatResource(value) {
  return formatResourceAmount(value, state.settings.resourceDisplayMode, state.locale);
}

function jumpToNode(node) {
  selectedNodeId = node.id;
  selectedCategoryId = node.categoryId; byId("tree-search").value = ""; byId("instant-only").checked = false; byId("technolabe-only").checked = false;
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
  const label = input.getAttribute("aria-label") || t("pwa.value", "値");
  decrease.setAttribute("aria-label", t("pwa.decrease_one", "{name}を1下げる", { name: label }));
  increase.setAttribute("aria-label", t("pwa.increase_one", "{name}を1上げる", { name: label }));
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

function renderConnectivity() {
  const status = byId("connection-status");
  if (!status) return;
  status.textContent = navigator.onLine ? t("pwa.online", "オンライン") : t("pwa.offline", "オフライン");
  status.classList.toggle("is-offline", !navigator.onLine);
}

function bindConnectivity() {
  window.addEventListener("online", renderConnectivity);
  window.addEventListener("offline", renderConnectivity);
  renderConnectivity();
}

function effectFor(node, level) {
  return currentEffect(node, level, {
    locale: state.locale,
    labels: effectLabels,
    name: catalog.nodeName(node, state.locale),
    translatedLabel: packText(activeLanguagePack, "effects", node.id),
    languagePack: activeLanguagePack,
  });
}

function toast(message) {
  const target = byId("toast"); target.textContent = message; target.classList.add("is-visible"); clearTimeout(toastTimer); toastTimer = setTimeout(() => target.classList.remove("is-visible"), 2800);
}

function debounce(callback, delay) { let timer; return (...args) => { clearTimeout(timer); timer = setTimeout(() => callback(...args), delay); }; }

start();
