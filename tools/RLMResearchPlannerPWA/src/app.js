import { currentEffect, loadCatalog, loadLocaleData } from "./catalog.js?v=0.0.15-b1";
import { adjustedTime, createPlan, defaultTargetLevel, formatDuration, isInstantNextLevel, isResearchConnectionUnlocked, researchLevelsAfterPlan, shortestAvailable } from "./planning.js?v=0.0.15-b1";
import { RESOURCE_KEYS, backupPayload, defaultState, freeSecondsForVip, guildHelpCount, loadState, maxGuildHelpsForCastle, mergeResearchDirectiveTasks, researchDirectiveFromPayload, researchDirectivePayload, saveState, stateFromBackup } from "./state.js?v=0.0.15-b1";
import { explicitTreeLayout } from "./tree-layout.js?v=0.0.15-b1";
import { clampTreeZoom, fitTreeZoom } from "./tree-zoom.js?v=0.0.15-b1";
import { formatResourceAmount } from "./resource-format.js?v=0.0.15-b1";
import { CASTLE_RESOURCE_KEYS, buildingLevelsAfterCastleStep, castleProgressLabel, createCastlePlan, loadCastleCatalog, minimumBuildingLevels } from "./castle-planning.js?v=0.0.15-b1";
import { applyDocumentLanguage, installLanguagePack, languagePackTemplate, loadLanguagePacks, packText, removeLanguagePack, translateStatic } from "./language-pack.js?v=0.0.15-b1";
import { PAID_GOALS, PAID_ITEM_KINDS, defaultGemValueEach, defaultPointsEach, emptyPaidOffer, paidKindHasTime, paidOfferExchangePayload, paidOffersFromExchangePayload, sanitizePaidOffer, sortedPaidOffers, summarizePaidOffer } from "./paid-value.js?v=0.0.15-b1";

const RELEASE_VERSION = "0.0.15";
const DEVELOPMENT_BUILD = 1;
const ASSET_VERSION = "0.0.15-b1";
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
let localeDataById = {};
let languagePacks = loadLanguagePacks();
let activeLanguagePack = null;
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
let paidDraft = emptyPaidOffer();
let paidEditingId = "";
let paidView = "input";
const categoryLayouts = new Map();

const byId = (id) => document.getElementById(id);
const create = (tag, className = "", text = "") => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== "") { node.textContent = text; node.dir = "auto"; }
  return node;
};

async function start() {
  try {
    const [loadedCatalog, loadedCastleCatalog, japaneseLocaleData, englishLocaleData] = await Promise.all([
      loadCatalog(`./data/research/catalog.json?v=${ASSET_VERSION}`),
      loadCastleCatalog(`./data/buildings/castle_catalog.json?v=${ASSET_VERSION}`),
      loadLocaleData(`./data/i18n/ja-JP.json?v=${ASSET_VERSION}`),
      loadLocaleData(`./data/i18n/en-US.json?v=${ASSET_VERSION}`),
    ]);
    catalog = loadedCatalog;
    castleCatalog = loadedCastleCatalog;
    localeDataById = { "ja-JP": japaneseLocaleData, "en-US": englishLocaleData };
    activateLanguage(state.locale, { save: false, render: false });
    selectedCategoryId = catalog.categories[0]?.id || "";
    selectedBulkCategoryId = selectedCategoryId;
    bindNavigation();
    bindTreeControls();
    bindDialog();
    bindSettings();
    bindPlans();
    bindCastle();
    bindPaid();
    installStaticNumberSteppers();
    bindConnectivity();
    populateSettings();
    renderCategoryOptions();
    renderTree();
    renderShortest();
    renderTasks();
    renderCastle();
    renderPaid();
    renderCatalogStatus();
    renderCommonHelp();
    byId("app-version").textContent = APP_VERSION;
    populateLanguageOptions();
    window.rlmMarkStartupComplete?.();
  } catch (error) {
    if (window.rlmHandleStartupError) {
      window.rlmHandleStartupError(error);
      return;
    }
    const target = byId("startup-error");
    const message = byId("startup-error-message");
    if (target && message) { message.textContent = t("pwa.startup_error", `起動に必要なデータを読み込めませんでした: ${error.message}`, { error: error.message }); target.hidden = false; }
  }
}

function renderCommonHelp() {
  const required = byId("pwa-help-required");
  const plan = byId("help-plan-body");
  const construction = byId("help-construction-body");
  if (required) required.innerHTML = messages["help.required_setup.body_v003"] || "";
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
  byId("startup-retry")?.addEventListener("click", () => location.reload());
}

function showTab(tab) {
  document.querySelectorAll(".tab-button").forEach((button) => button.classList.toggle("is-active", button.dataset.tab === tab));
  document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.toggle("is-active", panel.id === `tab-${tab}`));
  if (tab === "tree") requestAnimationFrame(renderTree);
  if (tab === "plan" && planMode === "shortest") renderShortest();
  if (tab === "plan" && planMode === "tasks") renderTasks();
  if (tab === "castle") renderCastle();
  if (tab === "paid") renderPaid();
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

function bindPaid() {
  byId("paid-new")?.addEventListener("click", () => { newPaidOffer(); setPaidView("input"); });
  for (const view of ["input", "saved", "comparison"]) byId(`paid-view-${view}-button`)?.addEventListener("click", () => setPaidView(view));
  byId("paid-add-item")?.addEventListener("click", () => {
    paidDraft.items.push({ kind: "general", name: "", quantity: 0, durationSeconds: 0, gemValueEach: 0, pointsEach: 0 });
    renderPaidItems(); renderPaidSummary();
  });
  byId("paid-save")?.addEventListener("click", savePaidOffer);
  byId("paid-delete")?.addEventListener("click", deletePaidOffer);
  byId("paid-goal")?.addEventListener("change", (event) => { paidDraft.goal = event.target.value; renderPaidSummary(); });
  byId("paid-comparison-goal")?.addEventListener("change", renderPaidComparison);
  byId("paid-use-speedup-gem-presets")?.addEventListener("change", (event) => { state.paidValuation.useSpeedupGemPresets = event.target.checked; scheduleSave(); renderPaidSummary(); renderPaidComparison(); });
  byId("paid-export-selected")?.addEventListener("click", exportSelectedPaidOffer);
  byId("paid-export-all")?.addEventListener("click", exportAllPaidOffers);
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
  paidView = ["input", "saved", "comparison"].includes(view) ? view : "input";
  for (const key of ["input", "saved", "comparison"]) {
    byId(`paid-view-${key}`).hidden = key !== paidView;
    byId(`paid-view-${key}-button`).classList.toggle("is-active", key === paidView);
  }
  if (paidView === "saved") renderPaidOffers();
  if (paidView === "comparison") renderPaidComparison();
}

function newPaidOffer() {
  paidEditingId = "";
  paidDraft = emptyPaidOffer();
  renderPaid();
}

function loadPaidOffer(id) {
  const offer = state.paidOffers.find((item) => item.offerId === id);
  if (!offer) return;
  paidEditingId = id;
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
  saveNow(); renderPaid(); toast(t("paid.saved", "課金項目を保存しました"));
}

function deletePaidOffer() {
  if (!paidEditingId) { newPaidOffer(); return; }
  if (!window.confirm(t("paid.delete_confirm", "この課金項目を削除しますか？"))) return;
  state.paidOffers = state.paidOffers.filter((item) => item.offerId !== paidEditingId);
  saveNow(); newPaidOffer(); toast(t("paid.deleted", "課金項目を削除しました"));
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
    const button = create("button", `paid-offer-card${offer.offerId === paidEditingId ? " is-selected" : ""}`);
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
    return button;
  }));
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
    if (window.confirm(t("paid.import_valuation_confirm", "共有元の比較ポイント設定も取り込みますか？"))) state.paidValuation = imported.valuation;
    saveNow(); renderPaid(); setPaidView("saved"); toast(t("paid.imported", "{added}件を追加しました（重複{skipped}件）", { added, skipped }));
  } catch (error) { toast(t("paid.import_failed", `課金データを読み込めませんでした: ${error.message}`, { error: error.message })); }
  finally { event.target.value = ""; }
}

function renderPaidItems() {
  const list = byId("paid-item-list");
  if (!list) return;
  if (!paidDraft.items.length) { list.replaceChildren(create("p", "empty-state", t("paid.no_items_manual", "「行を追加」から内容を入力してください。"))); return; }
  list.replaceChildren(...paidDraft.items.map((item, index) => {
    const row = create("article", "paid-item-row");
    const kindField = create("label", "field"); kindField.append(create("span", "", t("paid.kind", "種類")));
    const kind = create("select");
    kind.append(...PAID_ITEM_KINDS.map((key) => { const option = create("option", "", paidKindLabel(key)); option.value = key; option.selected = item.kind === key; return option; }));
    kind.addEventListener("change", () => {
      const previous = item.kind; item.kind = kind.value;
      if (!paidKindHasTime(item.kind)) item.durationSeconds = 0;
      if (!item.pointsEach || item.pointsEach === defaultPointsEach(previous)) item.pointsEach = defaultPointsEach(item.kind);
      if (!item.gemValueEach || item.gemValueEach === defaultGemValueEach(previous)) item.gemValueEach = defaultGemValueEach(item.kind);
      renderPaidItems(); renderPaidSummary();
    }); kindField.append(kind);
    const makeNumber = (label, value, callback, extra = {}) => {
      const field = create("label", `field ${extra.className || ""}`); field.hidden = Boolean(extra.hidden); field.append(create("span", "", label));
      const input = create("input"); input.type = "number"; input.inputMode = "decimal"; input.min = "0"; input.step = String(extra.step || 1); input.value = String(value);
      input.addEventListener("input", () => { callback(Math.max(0, Number(input.value) || 0)); renderPaidSummary(); }); field.append(input); return field;
    };
    const nameField = create("label", "field"); nameField.append(create("span", "", t("paid.item_name", "項目名")));
    const name = create("input"); name.type = "text"; name.maxLength = 200; name.value = item.name; name.addEventListener("input", () => { item.name = name.value; }); nameField.append(name);
    const quantity = makeNumber(t("paid.quantity", "個数"), item.quantity, (value) => { item.quantity = Math.trunc(value); });
    const [durationValue, durationUnit] = paidDurationParts(item.durationSeconds);
    const duration = makeNumber(t("paid.duration", "1個の時間"), durationValue, (value) => { item.durationSeconds = Math.trunc(value * paidUnitSeconds(unit.value)); }, { className: "paid-time-field", hidden: !paidKindHasTime(item.kind) });
    const unitField = create("label", "field paid-time-field"); unitField.hidden = !paidKindHasTime(item.kind); unitField.append(create("span", "", t("paid.unit", "単位")));
    const unit = create("select");
    for (const key of ["minutes", "hours", "days", "seconds"]) { const option = create("option", "", t(`paid.unit.${key}`, key)); option.value = key; option.selected = durationUnit === key; unit.append(option); }
    unit.addEventListener("change", () => { item.durationSeconds = Math.trunc((Number(duration.querySelector("input").value) || 0) * paidUnitSeconds(unit.value)); renderPaidSummary(); }); unitField.append(unit);
    const gem = makeNumber(t("paid.gem_value_each", "1個のジェム換算"), item.gemValueEach, (value) => { item.gemValueEach = value; }, { step: .01 });
    const points = makeNumber(t("paid.points_each", "1個の追加ポイント"), item.pointsEach, (value) => { item.pointsEach = value; }, { step: .01 });
    const remove = create("button", "remove-paid-item", "−"); remove.type = "button"; remove.setAttribute("aria-label", t("paid.delete_row", "この行を削除")); remove.addEventListener("click", () => { paidDraft.items.splice(index, 1); renderPaidItems(); renderPaidSummary(); });
    row.append(kindField, nameField, quantity, duration, unitField, gem, points, remove);
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
    const label = create("label", "field");
    const caption = create("span", "", resourceName(key)); caption.id = `resource-label-${key}`; label.append(caption);
    const input = create("input"); input.type = "number"; input.inputMode = "numeric"; input.min = "0"; input.dataset.resource = key;
    input.addEventListener("input", () => { state.settings.resources[key] = Math.max(0, Math.trunc(Number(input.value) || 0)); scheduleSave(); refreshCurrentPlan(); });
    label.append(input); resourceInputs.append(label);
  }
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
    const locale = state.locale; state = defaultState(); state.locale = locale; paidEditingId = ""; paidDraft = emptyPaidOffer(); castleTargetLevel = 0; castleTargetManaStage = 0; saveNow(); populateSettings(); renderCategoryOptions(); renderTree(true); currentPlan = null; renderPlan(); renderShortest(); renderTasks(); renderCastle(); renderPaid(); toast(t("pwa.cleared", "設定をクリアしました"));
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
  document.querySelectorAll("[data-resource]").forEach((input) => {
    const key = input.dataset.resource;
    input.value = state.settings.resources[key] || 0;
    const caption = byId(`resource-label-${key}`);
    if (caption) caption.textContent = resourceName(key);
  });
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
    const open = create("button", "", catalog.nodeName(node, state.locale)); open.type = "button";
    open.addEventListener("click", () => { jumpToNode(node); requestAnimationFrame(() => openNodeDialog(node.id)); });
    const input = create("input"); input.type = "number"; input.inputMode = "numeric"; input.min = "0"; input.max = String(node.maxLevel); input.value = String(Math.min(node.maxLevel, Number(state.researchLevels[node.id] || 0))); input.setAttribute("aria-label", t("pwa.current_level_aria", "{name}の現在レベル", { name: catalog.nodeName(node, state.locale) }));
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
    const imported = stateFromBackup(JSON.parse(await file.text())); imported.locale = state.locale; state = imported; paidEditingId = ""; paidDraft = emptyPaidOffer(); castleTargetLevel = 0; saveNow(); populateSettings(); renderCategoryOptions(); renderTree(true); currentPlan = null; renderPlan(); renderShortest(); renderTasks(); renderCastle(); renderPaid(); toast(t("player.backup_restored", "バックアップを読み込みました"));
  } catch (error) { toast(error.message); }
  finally { event.target.value = ""; }
}

function activeLocaleData(locale) {
  return localeDataById[locale] || localeDataById[locale?.split("-", 1)[0]] || localeDataById["en-US"] || { messages: {}, effect_labels: {} };
}

function formatMessage(template, values = {}) {
  return String(template || "").replace(/\{([A-Za-z0-9_]+)\}/g, (match, key) => (key in values ? String(values[key]) : match));
}

function t(key, fallback = key, values = {}) {
  return formatMessage(messages[key] || fallback, values);
}

function resourceName(key) {
  const fallback = RESOURCE_NAMES[state.locale]?.[key] || RESOURCE_NAMES["en-US"]?.[key] || key;
  return packText(activeLanguagePack, "resources", key, messages[`resource.${key}`] || fallback);
}

function populateLanguageOptions() {
  const select = byId("language-select");
  if (!select) return;
  const options = [
    { locale: "ja-JP", name: "日本語", custom: false },
    { locale: "en-US", name: "English", custom: false },
    ...Object.values(languagePacks).map((pack) => ({ locale: pack.locale, name: pack.name, custom: true })),
  ];
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
  activeLanguagePack = languagePacks[locale] || null;
  if (!activeLanguagePack && !localeDataById[locale]) locale = "en-US";
  state.locale = locale;
  const fallbackData = localeDataById["en-US"] || { messages: {}, effect_labels: {} };
  const localeData = activeLocaleData(activeLanguagePack?.fallbackLocale || locale);
  messages = {
    ...(fallbackData.messages || {}),
    ...(localeData.messages || {}),
    ...(activeLanguagePack?.sections?.messages || {}),
  };
  effectLabels = { ...(fallbackData.effect_labels || {}), ...(localeData.effect_labels || {}) };
  catalog?.setLanguagePack(activeLanguagePack);
  castleCatalog?.setLanguagePack(activeLanguagePack);
  applyDocumentLanguage(locale, activeLanguagePack?.direction);
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
  const englishMessages = localeDataById["en-US"]?.messages || {};
  downloadJson(
    languagePackTemplate({ catalog, castleCatalog, messages: englishMessages }),
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
  activateLanguage("en-US");
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
  if (!currentPlan) return;
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
  byId("plan-wisdom-summary").textContent = wisdomText(currentPlan.totals.technolabeCount, currentPlan.totals.technolabeEfficiencyPercent, currentPlan.totals.unknownTechnolabe);
  const resources = Object.fromEntries(RESOURCE_KEYS.map((key) => [key, resourceName(key)]));
  const usedResources = RESOURCE_KEYS.filter((key) => Number(currentPlan.totals.costs[key] || 0) > 0);
  byId("resource-summary").replaceChildren(...usedResources.map((key) => {
    const chip = create("div", "resource-chip"); const needed = currentPlan.totals.costs[key] || 0; const available = state.settings.resources[key] || 0;
    if (needed > available) chip.classList.add("is-short");
    chip.append(create("span", "", resources[key]), create("strong", "", formatResource(needed)), create("span", "", needed > available ? t("pwa.shortage", "不足 {amount}", { amount: formatResource(needed - available) }) : t("pwa.within_owned", "所持数以内"))); return chip;
  }));
  if (!usedResources.length) byId("resource-summary").append(create("div", "callout", t("pwa.no_required_resources", "必要資源なし")));
  byId("plan-steps").replaceChildren(...currentPlan.steps.map((step) => planRow(step, { showCategory: false })));
  byId("complete-plan").disabled = currentPlan.steps.length === 0;
  byId("register-plan").disabled = currentPlan.steps.length === 0;
  const issueParts = [];
  if (currentPlan.totals.unknownTime) issueParts.push(t("pwa.unknown_time_count", "時間未確認 {count}件", { count: currentPlan.totals.unknownTime }));
  if (currentPlan.totals.unknownCosts) issueParts.push(t("pwa.unknown_cost_count", "資源未確認 {count}件", { count: currentPlan.totals.unknownCosts }));
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
    resourceDetails(step.costs, RESOURCE_KEYS),
  );
  const footer = create("div", "plan-step-footer");
  const timing = create("div", "plan-step-timing");
  timing.append(create("strong", "plan-row-time", step.adjustedSeconds == null ? `${t("plan.time", "開始時")} ${t("common.unknown", "未確認")}` : `${t("plan.time", "開始時")} ${formatDuration(step.adjustedSeconds)}`));
  const helpCount = guildHelpCount(state.settings);
  if (helpCount > 0) {
    timing.append(create("span", "plan-row-help", step.afterHelpSeconds == null ? `${t("plan.after_help", "ヘルプ後")} ${t("common.unknown", "未確認")}` : `${t("plan.after_help", "ヘルプ後")} ${formatDuration(step.afterHelpSeconds)}`));
  }
  timing.append(create("span", "plan-row-wisdom", wisdomText(step.technolabeCount, step.technolabeEfficiencyPercent)));
  const complete = create("button", "step-complete", t("plan.complete_step", "研究完了")); complete.type = "button"; complete.addEventListener("click", () => completePlanStep(step));
  footer.append(timing, complete);
  row.append(main, footer); return row;
}

function resourceDetails(costs, keys) {
  const details = create("details", "plan-resource-details");
  const used = keys.filter((key) => Number(costs[key] || 0) > 0);
  const summary = create("summary", "", used.length ? t("pwa.material_count", "資材 {count}", { count: used.length }) : t("pwa.no_materials", "資材なし"));
  const resources = create("div", "plan-row-resources");
  for (const key of used) {
    const item = create("div", "plan-resource-item");
    item.append(create("span", "", resourceName(key)), create("strong", "", formatResource(costs[key])));
    resources.append(item);
  }
  if (!used.length) resources.append(create("div", "plan-resource-item", t("pwa.no_required_materials", "必要資材なし")));
  details.append(summary, resources);
  return details;
}

function wisdomText(count, efficiencyPercent, unknownCount = 0) {
  const label = t("plan.technolabe", "叡智の輪");
  if (count == null) return `${label} ${t("common.unknown", "未確認")}`;
  if (!count) return unknownCount ? t("pwa.wisdom_unknown_count", "{label} 未確認（{count}件）", { label, count: unknownCount }) : `${label} -`;
  const text = t("pwa.wisdom_efficiency", "{label} {count}個 / 効率{efficiency}%", { label, count, efficiency: Number(efficiencyPercent || 0).toFixed(1) });
  return unknownCount ? t("pwa.wisdom_with_unknown", "{text}（{count}件未確認）", { text, count: unknownCount }) : text;
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
  });
}

function toast(message) {
  const target = byId("toast"); target.textContent = message; target.classList.add("is-visible"); clearTimeout(toastTimer); toastTimer = setTimeout(() => target.classList.remove("is-visible"), 2800);
}

function debounce(callback, delay) { let timer; return (...args) => { clearTimeout(timer); timer = setTimeout(() => callback(...args), delay); }; }

start();
