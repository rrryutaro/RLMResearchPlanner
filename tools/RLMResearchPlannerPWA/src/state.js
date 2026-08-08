export const RESOURCE_KEYS = ["food", "stone", "timber", "ore", "gold", "ancient_tomes", "lunite", "mana_ore", "special"];
const STORAGE_KEY = "rlm-research-planner-pwa.player.v1";

export function defaultState() {
  return {
    schemaVersion: 1,
    locale: "ja-JP",
    settings: {
      vipLevel: 1,
      castleLevel: 1,
      castleTargetLevel: 0,
      castleManaStage: 0,
      castleTargetManaStage: 0,
      academyLevel: 1,
      constructionSpeedPercent: 0,
      researchSpeedPercent: 0,
      researchSpeedBoostPercent: 0,
      maxGuildHelps: 0,
      speedupSeconds: 0,
      resourceDisplayMode: "exact",
      resources: Object.fromEntries(RESOURCE_KEYS.map((key) => [key, 0])),
    },
    researchLevels: {},
    buildingLevels: {},
    planTasks: [],
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
  base.locale = source.locale === "en-US" ? "en-US" : "ja-JP";
  base.settings.vipLevel = Math.min(15, Math.max(1, Math.trunc(number(settings.vipLevel ?? settings.vip_level, 1))));
  base.settings.castleLevel = Math.min(25, Math.max(1, Math.trunc(number(settings.castleLevel ?? settings.castle_level, 1))));
  base.settings.castleTargetLevel = Math.min(25, Math.max(0, Math.trunc(number(settings.castleTargetLevel ?? settings.castle_target_level, 0))));
  base.settings.castleManaStage = base.settings.castleLevel === 25
    ? Math.min(5, Math.max(0, Math.trunc(number(settings.castleManaStage ?? settings.castle_mana_stage, 0))))
    : 0;
  base.settings.castleTargetManaStage = Math.min(5, Math.max(0, Math.trunc(number(settings.castleTargetManaStage ?? settings.castle_target_mana_stage, 0))));
  base.settings.academyLevel = Math.min(25, Math.max(1, Math.trunc(number(settings.academyLevel ?? settings.academy_level, 1))));
  base.settings.constructionSpeedPercent = Math.max(0, number(settings.constructionSpeedPercent ?? settings.construction_speed_percent));
  base.settings.researchSpeedPercent = Math.max(0, number(settings.researchSpeedPercent ?? settings.research_speed_percent));
  base.settings.researchSpeedBoostPercent = Math.max(0, number(settings.researchSpeedBoostPercent ?? settings.research_speed_boost_percent));
  base.settings.maxGuildHelps = Math.max(0, Math.trunc(number(settings.maxGuildHelps ?? settings.max_guild_helps)));
  base.settings.speedupSeconds = Math.max(0, Math.trunc(number(settings.speedupSeconds ?? settings.speedup_seconds)));
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
  }));
  base.observedStats = { ...(source.observedStats || source.observed_stats || {}) };
  base.updatedAt = String(source.updatedAt || source.updated_at || base.updatedAt);
  return base;
}

export function loadState(storage = localStorage) {
  try { return sanitizeState(JSON.parse(storage.getItem(STORAGE_KEY) || "null")); }
  catch { return defaultState(); }
}

export function saveState(state, storage = localStorage) {
  state.updatedAt = new Date().toISOString();
  storage.setItem(STORAGE_KEY, JSON.stringify(state));
}

export function backupPayload(state) {
  return {
    schema_version: 1,
    exported_at: new Date().toISOString(),
    player: {
      settings: {
        vip_level: state.settings.vipLevel,
        castle_level: state.settings.castleLevel,
        castle_target_level: state.settings.castleTargetLevel,
        castle_mana_stage: state.settings.castleManaStage,
        castle_target_mana_stage: state.settings.castleTargetManaStage,
        academy_level: state.settings.academyLevel,
        construction_speed_percent: state.settings.constructionSpeedPercent,
        research_speed_percent: state.settings.researchSpeedPercent,
        research_speed_boost_percent: state.settings.researchSpeedBoostPercent,
        free_speedup_seconds: freeSecondsForVip(state.settings.vipLevel),
        max_guild_helps: state.settings.maxGuildHelps,
        speedup_seconds: state.settings.speedupSeconds,
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
      })),
      updated_at: state.updatedAt,
    },
  };
}

export function stateFromBackup(raw) {
  if (Number(raw?.schema_version) !== 1 || !raw?.player?.settings || !raw?.player?.research_levels) throw new Error("対応していないバックアップ形式です");
  return sanitizeState({ settings: raw.player.settings, research_levels: raw.player.research_levels, building_levels: raw.player.building_levels, plan_tasks: raw.player.plan_tasks, observed_stats: raw.player.settings.observed_stats, updated_at: raw.player.updated_at });
}

const VIP_MINUTES = { 1: 10, 2: 24, 3: 26, 4: 30, 5: 40, 6: 50, 7: 60, 8: 70, 9: 80, 10: 90, 11: 100, 12: 110, 13: 120, 14: 130, 15: 150 };
export function freeSecondsForVip(level) { return VIP_MINUTES[Math.min(15, Math.max(1, Number(level) || 1))] * 60; }
