export const RESOURCE_KEYS = ["food", "stone", "timber", "ore", "gold", "gold_hammer", "war_tome", "steel_cuffs", "soul_crystal", "ancient_tomes", "lunite", "mana_ore", "special"];
export const MAX_GUILD_HELPS = 30;
const PRODUCTION_STORAGE_KEY = "rlm-research-planner-pwa.player.v1";
const PREVIEW_STORAGE_KEY = "rlm-research-planner-preview.player.v1";

export function playerStorageKey(pathname = globalThis.location?.pathname || "") {
  return /\/preview(?:\/|$)/u.test(String(pathname)) ? PREVIEW_STORAGE_KEY : PRODUCTION_STORAGE_KEY;
}

export function hasSavedState(storage = globalThis.localStorage, pathname = globalThis.location?.pathname || "") {
  const storageKey = playerStorageKey(pathname);
  try {
    if (!storage) return false;
    if (storage.getItem(storageKey)) return true;
    return storageKey === PREVIEW_STORAGE_KEY && Boolean(storage.getItem(PRODUCTION_STORAGE_KEY));
  } catch { return false; }
}
export const RESEARCH_DIRECTIVE_DOCUMENT_TYPE = "RLMResearchPlanner.research-directive";
import { defaultPaidValuation, sanitizePaidOffer, sanitizePaidValuation } from "./paid-value.js?v=0.1.4-b1";
import { normalizeSpeedupInventory } from "./speedup-inventory.js?v=0.1.4-b1";

export function maxGuildHelpsForCastle(castleLevel) {
  const normalizedLevel = Math.min(25, Math.max(1, Math.trunc(number(castleLevel, 1))));
  return Math.min(MAX_GUILD_HELPS, normalizedLevel + 5);
}

export function guildHelpCount(settings) {
  return Math.min(
    maxGuildHelpsForCastle(settings?.castleLevel),
    Math.max(0, Math.trunc(number(settings?.maxGuildHelps))),
  );
}

export function defaultState() {
  return {
    schemaVersion: 1,
    locale: "",
    settings: {
      playerLevel: 60,
      vipLevel: 1,
      castleLevel: 1,
      castleTargetLevel: 0,
      castleManaStage: 0,
      castleTargetManaStage: 0,
      academyLevel: 1,
      constructionSpeedPercent: 0,
      constructionSpeedBoostPercent: 0,
      researchSpeedPercent: 0,
      researchSpeedBoostPercent: 0,
      maxGuildHelps: 0,
      speedupSeconds: 0,
      speedupInventory: [],
      useGemsForSpeedups: false,
      technolabeCount: 0,
      technolabeRecommendationThresholdPercent: 95,
      resourceDisplayMode: "exact",
      resources: Object.fromEntries(RESOURCE_KEYS.map((key) => [key, 0])),
    },
    researchLevels: {},
    buildingLevels: {},
    planTasks: [],
    talentPlanName: "",
    talentPresetId: "growth_speed",
    talentPriorityId: "",
    talentAutoFollow: true,
    talentAvailablePoints: 278,
    talentPlan: [],
    paidOffers: [],
    paidValuation: defaultPaidValuation(),
    observedStats: {},
    updatedAt: new Date().toISOString(),
  };
}

function number(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function sanitizeState(value) {
  const base = defaultState();
  const source = value || {};
  const settings = source.settings || {};
  try {
    const locale = String(source.locale || "").trim().replaceAll("_", "-");
    base.locale = /^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$/.test(locale) ? locale : "";
  } catch { base.locale = ""; }
  base.settings.playerLevel = Math.min(60, Math.max(1, Math.trunc(number(settings.playerLevel ?? settings.player_level, 60))));
  base.settings.vipLevel = Math.min(15, Math.max(1, Math.trunc(number(settings.vipLevel ?? settings.vip_level, 1))));
  base.settings.castleLevel = Math.min(25, Math.max(1, Math.trunc(number(settings.castleLevel ?? settings.castle_level, 1))));
  base.settings.castleTargetLevel = Math.min(25, Math.max(0, Math.trunc(number(settings.castleTargetLevel ?? settings.castle_target_level, 0))));
  base.settings.castleManaStage = base.settings.castleLevel === 25
    ? Math.min(5, Math.max(0, Math.trunc(number(settings.castleManaStage ?? settings.castle_mana_stage, 0))))
    : 0;
  base.settings.castleTargetManaStage = Math.min(5, Math.max(0, Math.trunc(number(settings.castleTargetManaStage ?? settings.castle_target_mana_stage, 0))));
  base.settings.academyLevel = Math.min(25, Math.max(1, Math.trunc(number(settings.academyLevel ?? settings.academy_level, 1))));
  base.settings.constructionSpeedPercent = Math.max(0, number(settings.constructionSpeedPercent ?? settings.construction_speed_percent));
  base.settings.constructionSpeedBoostPercent = Math.max(0, number(settings.constructionSpeedBoostPercent ?? settings.construction_speed_boost_percent));
  base.settings.researchSpeedPercent = Math.max(0, number(settings.researchSpeedPercent ?? settings.research_speed_percent));
  base.settings.researchSpeedBoostPercent = Math.max(0, number(settings.researchSpeedBoostPercent ?? settings.research_speed_boost_percent));
  base.settings.maxGuildHelps = Math.min(
    maxGuildHelpsForCastle(base.settings.castleLevel),
    Math.max(0, Math.trunc(number(settings.maxGuildHelps ?? settings.max_guild_helps))),
  );
  base.settings.speedupSeconds = Math.max(0, Math.trunc(number(settings.speedupSeconds ?? settings.speedup_seconds)));
  base.settings.speedupInventory = normalizeSpeedupInventory(
    settings.speedupInventory ?? settings.speedup_inventory,
  );
  if (!base.settings.speedupInventory.length && base.settings.speedupSeconds > 0) {
    base.settings.speedupInventory = [{
      kind: "general",
      durationSeconds: 1,
      quantity: base.settings.speedupSeconds,
    }];
  }
  base.settings.speedupSeconds = 0;
  base.settings.useGemsForSpeedups = (settings.useGemsForSpeedups ?? settings.use_gems_for_speedups) === true;
  base.settings.technolabeCount = Math.max(
    0,
    Math.trunc(number(settings.technolabeCount ?? settings.technolabe_count)),
  );
  base.settings.technolabeRecommendationThresholdPercent = Math.min(
    100,
    Math.max(
      0,
      number(
        settings.technolabeRecommendationThresholdPercent
          ?? settings.technolabe_recommendation_threshold_percent,
        95,
      ),
    ),
  );
  base.settings.resourceDisplayMode = (settings.resourceDisplayMode ?? settings.resource_display_mode) === "short" ? "short" : "exact";
  const resources = settings.resources || {};
  for (const key of RESOURCE_KEYS) base.settings.resources[key] = Math.max(0, Math.trunc(number(resources[key])));
  const levels = source.researchLevels || source.research_levels || {};
  base.researchLevels = Object.fromEntries(Object.entries(levels).map(([key, level]) => [key, Math.max(0, Math.trunc(number(level)))]));
  const buildingLevels = source.buildingLevels || source.building_levels || {};
  base.buildingLevels = Object.fromEntries(Object.entries(buildingLevels).map(([key, level]) => [key, Math.max(0, Math.min(25, Math.trunc(number(level))))]));
  const tasks = source.planTasks || source.plan_tasks || [];
  base.planTasks = tasks.filter((task) => task && (task.researchId || task.research_id)).map((task) => ({
    researchId: String(task.researchId || task.research_id),
    targetLevel: Math.max(1, Math.trunc(number(task.targetLevel ?? task.target_level, 1))),
    createdAt: String(task.createdAt || task.created_at || new Date().toISOString()),
    sourceName: String(task.sourceName || task.source_name || ""),
  }));
  base.talentPlanName = String(source.talentPlanName ?? source.talent_plan_name ?? "").trim().slice(0, 100);
  base.talentPresetId = String(source.talentPresetId ?? source.talent_preset_id ?? "growth_speed").trim().slice(0, 100);
  base.talentPriorityId = String(source.talentPriorityId ?? source.talent_priority_id ?? "").trim().slice(0, 100);
  base.talentAutoFollow = (source.talentAutoFollow ?? source.talent_auto_follow) !== false;
  base.talentAvailablePoints = Math.max(0, Math.min(9999, Math.trunc(number(source.talentAvailablePoints ?? source.talent_available_points, 278))));
  const talentPlan = source.talentPlan || source.talent_plan || [];
  const talentLevels = new Map();
  base.talentPlan = (Array.isArray(talentPlan) ? talentPlan : []).flatMap((step) => {
    const talentId = String(step?.talentId || step?.talent_id || "").trim();
    const targetLevel = Math.max(0, Math.trunc(number(step?.targetLevel ?? step?.target_level)));
    if (!talentId || targetLevel < 1 || targetLevel <= (talentLevels.get(talentId) || 0)) return [];
    talentLevels.set(talentId, targetLevel); return [{ talentId, targetLevel }];
  });
  base.paidOffers = (source.paidOffers || source.paid_offers || []).map(sanitizePaidOffer).filter((offer) => offer.offerId);
  base.paidValuation = sanitizePaidValuation(source.paidValuation || source.paid_valuation);
  base.observedStats = { ...(source.observedStats || source.observed_stats || {}) };
  base.updatedAt = String(source.updatedAt || source.updated_at || base.updatedAt);
  return base;
}

export function loadState(storage = localStorage, pathname = globalThis.location?.pathname || "") {
  const storageKey = playerStorageKey(pathname);
  try {
    let serialized = storage.getItem(storageKey);
    if (!serialized && storageKey === PREVIEW_STORAGE_KEY) {
      serialized = storage.getItem(PRODUCTION_STORAGE_KEY);
      if (serialized) storage.setItem(PREVIEW_STORAGE_KEY, serialized);
    }
    return sanitizeState(JSON.parse(serialized || "null"));
  }
  catch { return defaultState(); }
}

export function saveState(state, storage = localStorage, pathname = globalThis.location?.pathname || "") {
  state.updatedAt = new Date().toISOString();
  storage.setItem(playerStorageKey(pathname), JSON.stringify(state));
}

export function backupPayload(state) {
  return {
    schema_version: 1,
    exported_at: new Date().toISOString(),
    player: {
      settings: {
        player_level: state.settings.playerLevel,
        vip_level: state.settings.vipLevel,
        castle_level: state.settings.castleLevel,
        castle_target_level: state.settings.castleTargetLevel,
        castle_mana_stage: state.settings.castleManaStage,
        castle_target_mana_stage: state.settings.castleTargetManaStage,
        academy_level: state.settings.academyLevel,
        construction_speed_percent: state.settings.constructionSpeedPercent,
        construction_speed_boost_percent: state.settings.constructionSpeedBoostPercent,
        research_speed_percent: state.settings.researchSpeedPercent,
        research_speed_boost_percent: state.settings.researchSpeedBoostPercent,
        free_speedup_seconds: freeSecondsForVip(state.settings.vipLevel),
        max_guild_helps: guildHelpCount(state.settings),
        speedup_seconds: normalizeSpeedupInventory(state.settings.speedupInventory)
          .filter((item) => item.kind === "general")
          .reduce((total, item) => total + item.durationSeconds * item.quantity, 0),
        speedup_inventory: normalizeSpeedupInventory(state.settings.speedupInventory).map((item) => ({
          kind: item.kind,
          duration_seconds: item.durationSeconds,
          quantity: item.quantity,
        })),
        use_gems_for_speedups: state.settings.useGemsForSpeedups === true,
        technolabe_count: Math.max(0, Math.trunc(Number(state.settings.technolabeCount) || 0)),
        technolabe_recommendation_threshold_percent: Math.min(
          100,
          Math.max(0, Number(state.settings.technolabeRecommendationThresholdPercent) || 0),
        ),
        resource_display_mode: state.settings.resourceDisplayMode,
        resources: { ...state.settings.resources },
        observed_stats: { ...state.observedStats },
      },
      research_levels: { ...state.researchLevels },
      building_levels: { ...state.buildingLevels },
      plan_tasks: state.planTasks.map((task) => ({
        research_id: task.researchId,
        target_level: task.targetLevel,
        created_at: task.createdAt,
        source_name: task.sourceName || "",
      })),
      talent_plan_name: state.talentPlanName,
      talent_preset_id: state.talentPresetId,
      talent_priority_id: state.talentPriorityId,
      talent_auto_follow: state.talentAutoFollow !== false,
      talent_available_points: state.talentAvailablePoints,
      talent_plan: state.talentPlan.map((step) => ({ talent_id: step.talentId, target_level: step.targetLevel })),
      paid_offers: state.paidOffers.map((offer) => ({
        offer_id: offer.offerId,
        title: offer.title,
        goal: offer.goal,
        memo: offer.memo,
        diamond_cost: offer.diamondCost,
        included_gems: offer.includedGems,
        bonus_gems: offer.bonusGems,
        items: offer.items.map((item) => ({
          kind: item.kind,
          name: item.name,
          quantity: item.quantity,
          duration_seconds: item.durationSeconds,
          gem_value_each: item.gemValueEach,
          points_each: item.pointsEach,
        })),
        created_at: offer.createdAt,
        updated_at: offer.updatedAt,
      })),
      paid_valuation: {
        points_per_gem: state.paidValuation.pointsPerGem,
        general_speedup_points_per_hour: state.paidValuation.generalSpeedupPointsPerHour,
        research_speedup_points_per_hour: state.paidValuation.researchSpeedupPointsPerHour,
        training_speedup_points_per_hour: state.paidValuation.trainingSpeedupPointsPerHour,
        construction_speedup_points_per_hour: state.paidValuation.constructionSpeedupPointsPerHour,
        healing_speedup_points_per_hour: state.paidValuation.healingSpeedupPointsPerHour,
        merging_speedup_points_per_hour: state.paidValuation.mergingSpeedupPointsPerHour,
        crafting_speedup_points_per_hour: state.paidValuation.craftingSpeedupPointsPerHour,
        use_speedup_gem_presets: state.paidValuation.useSpeedupGemPresets,
      },
      updated_at: state.updatedAt,
    },
  };
}

function normalizedDirectiveTasks(tasks) {
  const normalized = [];
  const positions = new Map();
  for (const task of Array.isArray(tasks) ? tasks : []) {
    const researchId = String(task?.researchId || task?.research_id || "").trim();
    const targetLevel = Math.max(0, Math.trunc(number(task?.targetLevel ?? task?.target_level)));
    if (!researchId || targetLevel < 1) continue;
    if (positions.has(researchId)) {
      const existing = normalized[positions.get(researchId)];
      existing.targetLevel = Math.max(existing.targetLevel, targetLevel);
      continue;
    }
    positions.set(researchId, normalized.length);
    normalized.push({ researchId, targetLevel });
  }
  return normalized;
}

export function researchDirectivePayload(tasks, { name = "", datasetId = "", gameVersion = "" } = {}) {
  return {
    document_type: RESEARCH_DIRECTIVE_DOCUMENT_TYPE,
    schema_version: 1,
    exported_at: new Date().toISOString(),
    name: String(name).trim().slice(0, 100),
    dataset_id: String(datasetId || ""),
    game_version: String(gameVersion || ""),
    tasks: normalizedDirectiveTasks(tasks).map((task) => ({
      research_id: task.researchId,
      target_level: task.targetLevel,
    })),
  };
}

export function researchDirectiveFromPayload(raw) {
  if (raw?.document_type !== RESEARCH_DIRECTIVE_DOCUMENT_TYPE || Number(raw?.schema_version) !== 1 || !Array.isArray(raw?.tasks)) {
    throw new Error("対応していない研究指示データです");
  }
  const tasks = normalizedDirectiveTasks(raw.tasks);
  if (!tasks.length) throw new Error("研究指示データに有効なタスクがありません");
  return {
    name: String(raw.name || "研究指示").trim().slice(0, 100) || "研究指示",
    datasetId: String(raw.dataset_id || ""),
    gameVersion: String(raw.game_version || ""),
    tasks,
  };
}

export function mergeResearchDirectiveTasks(existingTasks, directiveTasks, sourceName = "", createdAt = new Date().toISOString()) {
  const tasks = [];
  const positions = new Map();
  for (const task of Array.isArray(existingTasks) ? existingTasks : []) {
    const researchId = String(task?.researchId || task?.research_id || "").trim();
    const targetLevel = Math.max(0, Math.trunc(number(task?.targetLevel ?? task?.target_level)));
    if (!researchId || targetLevel < 1) continue;
    if (positions.has(researchId)) {
      const existing = tasks[positions.get(researchId)];
      if (targetLevel > existing.targetLevel) existing.targetLevel = targetLevel;
      continue;
    }
    positions.set(researchId, tasks.length);
    tasks.push({
      researchId,
      targetLevel,
      createdAt: String(task.createdAt || task.created_at || createdAt),
      sourceName: String(task.sourceName || task.source_name || ""),
    });
  }
  let added = 0;
  let updated = 0;
  let unchanged = 0;
  for (const directive of normalizedDirectiveTasks(directiveTasks)) {
    if (!positions.has(directive.researchId)) {
      positions.set(directive.researchId, tasks.length);
      tasks.push({ ...directive, createdAt, sourceName: String(sourceName || "") });
      added += 1;
      continue;
    }
    const existing = tasks[positions.get(directive.researchId)];
    if (directive.targetLevel > existing.targetLevel) {
      existing.targetLevel = directive.targetLevel;
      existing.sourceName = String(sourceName || existing.sourceName || "");
      updated += 1;
    } else {
      unchanged += 1;
    }
  }
  return { tasks, added, updated, unchanged };
}

export function stateFromBackup(raw) {
  if (Number(raw?.schema_version) !== 1 || !raw?.player?.settings || !raw?.player?.research_levels) throw new Error("対応していないバックアップ形式です");
  return sanitizeState({ settings: raw.player.settings, research_levels: raw.player.research_levels, building_levels: raw.player.building_levels, plan_tasks: raw.player.plan_tasks, talent_plan_name: raw.player.talent_plan_name, talent_preset_id: raw.player.talent_preset_id, talent_priority_id: raw.player.talent_priority_id, talent_auto_follow: raw.player.talent_auto_follow, talent_available_points: raw.player.talent_available_points, talent_plan: raw.player.talent_plan, paid_offers: raw.player.paid_offers, paid_valuation: raw.player.paid_valuation, observed_stats: raw.player.settings.observed_stats, updated_at: raw.player.updated_at });
}

const VIP_MINUTES = { 1: 10, 2: 24, 3: 26, 4: 30, 5: 40, 6: 50, 7: 60, 8: 70, 9: 80, 10: 90, 11: 100, 12: 110, 13: 120, 14: 130, 15: 150 };
export function freeSecondsForVip(level) { return VIP_MINUTES[Math.min(15, Math.max(1, Number(level) || 1))] * 60; }
