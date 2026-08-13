export const TALENT_DIRECTIVE_DOCUMENT_TYPE = "RLMResearchPlanner.talent-directive";

const number = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
const localized = (values, locale, fallback = "") => {
  const normalized = String(locale || "").replaceAll("_", "-");
  const language = normalized.split("-", 1)[0];
  for (const candidate of [normalized, language, "en-US"]) {
    if (String(values?.[candidate] || "").trim()) return String(values[candidate]);
  }
  return fallback;
};

export async function loadTalentCatalog(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`才能データを読み込めませんでした (${response.status})`);
  return normalizeTalentCatalog(await response.json());
}

export function normalizeTalentCatalog(raw) {
  if (raw?.document_type !== "RLMResearchPlanner.talent-catalog" || Number(raw?.schema_version) !== 1) {
    throw new Error("対応していない才能データです");
  }
  const talents = new Map((Array.isArray(raw.talents) ? raw.talents : []).map((item) => {
    const talent = {
      id: String(item.id || "").trim(), branch: String(item.branch || ""), row: Math.max(1, Math.trunc(number(item.row, 1))),
      order: Math.max(0, Math.trunc(number(item.order))), maxLevel: Math.max(1, Math.trunc(number(item.max_level, 1))),
      names: { ...(item.name || {}) }, effectNames: { ...(item.effect || {}) }, maxEffect: Math.max(0, number(item.effect?.max)),
      prerequisite: item.prerequisite ? { talentId: String(item.prerequisite.talent_id || ""), level: Math.max(1, Math.trunc(number(item.prerequisite.level, 1))) } : null,
    };
    return [talent.id, talent];
  }));
  const presets = (Array.isArray(raw.presets) ? raw.presets : []).map((item) => ({
    id: String(item.id || "").trim(), names: { ...(item.name || {}) }, descriptions: { ...(item.description || {}) },
    verificationStatus: String(item.verification_status || "provisional"), targets: normalizeTalentSteps(item.targets),
  }));
  if (!talents.size || !presets.length) throw new Error("才能データが空です");
  for (const talent of talents.values()) {
    if (!talent.prerequisite) continue;
    const parent = talents.get(talent.prerequisite.talentId);
    if (!parent || talent.prerequisite.level > parent.maxLevel) throw new Error(`才能の前提条件が不正です: ${talent.id}`);
  }
  const catalog = {
    version: String(raw.catalog_version || ""), defaultAvailablePoints: Math.max(0, Math.trunc(number(raw.default_available_points, 278))),
    pointRewardsByLevel: (Array.isArray(raw.talent_point_bonus_by_level) ? raw.talent_point_bonus_by_level : []).map((value) => Math.max(0, Math.trunc(number(value)))),
    talents, presets, presetById: new Map(presets.map((preset) => [preset.id, preset])), languagePack: null,
    setLanguagePack(pack) { this.languagePack = pack || null; },
    talentName(talent, locale) { return String(this.languagePack?.sections?.talents?.[talent.id] || localized(talent.names, locale, talent.id)); },
    effectName(talent, locale) { return String(this.languagePack?.sections?.talent_effects?.[talent.id] || localized(talent.effectNames, locale, talent.id)); },
    presetName(preset, locale) { return String(this.languagePack?.sections?.talent_presets?.[preset.id] || localized(preset.names, locale, preset.id)); },
    presetDescription(preset, locale) { return String(this.languagePack?.sections?.talent_preset_descriptions?.[preset.id] || localized(preset.descriptions, locale, "")); },
  };
  if (catalog.pointRewardsByLevel.length !== 60 || catalog.pointRewardsByLevel.reduce((sum, value) => sum + value, 0) !== catalog.defaultAvailablePoints) {
    throw new Error("才能ポイントのレベル配分が不正です");
  }
  for (const talent of talents.values()) {
    expandTalentTargets(catalog, [{ talentId: talent.id, targetLevel: 1 }]);
  }
  for (const preset of presets) expandTalentTargets(catalog, preset.targets);
  return catalog;
}

export function talentLayoutColumns(catalog) {
  const talents = [...catalog.talents.values()].sort((left, right) => left.order - right.order);
  const branches = [...new Set(talents.map((talent) => talent.branch))];
  const rows = [...new Set(talents.map((talent) => talent.row))].sort((left, right) => left - right);
  const widths = new Map(branches.map((branch) => [
    branch,
    Math.max(...rows.map((row) => talents.filter((talent) => talent.branch === branch && talent.row === row).length), 1),
  ]));
  const starts = new Map();
  let nextColumn = 0;
  branches.forEach((branch) => {
    starts.set(branch, nextColumn);
    nextColumn += widths.get(branch);
  });
  const columns = new Map();
  for (const row of rows) {
    for (const [branchIndex, branch] of branches.entries()) {
      const rowTalents = talents.filter((talent) => talent.row === row && talent.branch === branch);
      const unusedLanes = widths.get(branch) - rowTalents.length;
      const start = starts.get(branch) + (branchIndex < branches.length / 2 ? unusedLanes : 0);
      rowTalents.forEach((talent, offset) => columns.set(talent.id, start + offset));
    }
  }
  return { columns, columnCount: nextColumn };
}

export function normalizeTalentSteps(values) {
  const result = [];
  const latest = new Map();
  for (const item of Array.isArray(values) ? values : []) {
    const talentId = String(item?.talentId || item?.talent_id || "").trim();
    const targetLevel = Math.max(0, Math.trunc(number(item?.targetLevel ?? item?.target_level)));
    if (!talentId || targetLevel < 1 || targetLevel <= (latest.get(talentId) || 0)) continue;
    result.push({ talentId, targetLevel }); latest.set(talentId, targetLevel);
  }
  return result;
}

export function expandTalentTargets(catalog, values) {
  const expanded = [];
  const planned = new Map();
  const visiting = new Set();
  const requireTalent = (talentId, requestedLevel) => {
    const talent = catalog.talents.get(talentId);
    if (!talent) throw new Error(`存在しない才能IDです: ${talentId}`);
    if (visiting.has(talentId)) throw new Error(`才能の前提条件が循環しています: ${talentId}`);
    const targetLevel = Math.max(1, Math.min(talent.maxLevel, Math.trunc(number(requestedLevel, 1))));
    visiting.add(talentId);
    if (talent.prerequisite) requireTalent(talent.prerequisite.talentId, talent.prerequisite.level);
    visiting.delete(talentId);
    if (targetLevel <= (planned.get(talentId) || 0)) return;
    expanded.push({ talentId, targetLevel }); planned.set(talentId, targetLevel);
  };
  for (const step of normalizeTalentSteps(values)) requireTalent(step.talentId, step.targetLevel);
  return expanded;
}

export function prioritizeTalentSteps(values, priorityTalentId = "") {
  const steps = normalizeTalentSteps(values);
  const priorityId = String(priorityTalentId || "").trim();
  if (!priorityId || !steps.some((step) => step.talentId === priorityId)) return steps;
  return [
    ...steps.filter((step) => step.talentId === priorityId),
    ...steps.filter((step) => step.talentId !== priorityId),
  ];
}

export function talentPointsForPlayerLevel(catalog, playerLevel) {
  const level = Math.max(1, Math.min(catalog.pointRewardsByLevel.length, Math.trunc(number(playerLevel, 1))));
  return catalog.pointRewardsByLevel.slice(0, level).reduce((sum, value) => sum + value, 0);
}

export function talentPlayerLevelRequirement(catalog, requiredPoints, bonusPoints = 0) {
  const requiredBasePoints = Math.max(0, Math.trunc(number(requiredPoints)) - Math.max(0, Math.trunc(number(bonusPoints))));
  let cumulative = 0;
  for (let index = 0; index < catalog.pointRewardsByLevel.length; index += 1) {
    cumulative += catalog.pointRewardsByLevel[index];
    if (cumulative >= requiredBasePoints) return { playerLevel: index + 1, requiredBasePoints, shortageAtMaxLevel: 0 };
  }
  return { playerLevel: null, requiredBasePoints, shortageAtMaxLevel: Math.max(0, requiredBasePoints - catalog.defaultAvailablePoints) };
}

export function allocateTalentPlan(catalog, values, availablePoints, priorityTalentId = "") {
  const steps = expandTalentTargets(catalog, prioritizeTalentSteps(values, priorityTalentId));
  let remaining = Math.max(0, Math.trunc(number(availablePoints)));
  let used = 0; let required = 0;
  const planned = new Map();
  const allocation = steps.map((step) => {
    const startLevel = planned.get(step.talentId) || 0;
    const requiredDelta = Math.max(0, step.targetLevel - startLevel);
    const allocatedDelta = Math.min(requiredDelta, remaining);
    const allocatedLevel = startLevel + allocatedDelta;
    used += allocatedDelta; required += requiredDelta; remaining -= allocatedDelta; planned.set(step.talentId, allocatedLevel);
    return { ...step, startLevel, allocatedLevel, points: requiredDelta, allocatedPoints: allocatedDelta, cumulativePoints: used };
  });
  return { steps: allocation, availablePoints: Math.max(0, Math.trunc(number(availablePoints))), requiredPoints: required, usedPoints: used, remainingPoints: remaining };
}

export function talentDirectivePayload(steps, { name = "", catalogVersion = "" } = {}) {
  return {
    document_type: TALENT_DIRECTIVE_DOCUMENT_TYPE, schema_version: 1, exported_at: new Date().toISOString(), name: String(name).trim().slice(0, 100),
    catalog_version: String(catalogVersion || ""),
    steps: normalizeTalentSteps(steps).map((step) => ({ talent_id: step.talentId, target_level: step.targetLevel })),
  };
}

export function talentDirectiveFromPayload(raw) {
  if (raw?.document_type !== TALENT_DIRECTIVE_DOCUMENT_TYPE || Number(raw?.schema_version) !== 1 || !Array.isArray(raw?.steps)) throw new Error("対応していない才能指示データです");
  const steps = normalizeTalentSteps(raw.steps);
  if (!steps.length) throw new Error("才能指示データに有効な取得順がありません");
  return { name: String(raw.name || "才能指示").trim().slice(0, 100) || "才能指示", catalogVersion: String(raw.catalog_version || ""), steps };
}
