function slugify(value) {
  return value.toLocaleLowerCase("en-US").replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

function localText(values, locale) {
  return values?.[locale] || values?.[locale.split("-")[0]] || values?.["en-US"] || Object.values(values || {})[0] || "";
}

export async function loadCatalog(url = "./data/research/catalog.json") {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`研究データを読み込めません (${response.status})`);
  return normalizeCatalog(await response.json());
}

export async function loadEffectLabels(url = "./data/i18n/ja-JP.json") {
  const response = await fetch(url);
  if (!response.ok) return {};
  return (await response.json()).effect_labels || {};
}

export function normalizeCatalog(raw) {
  const nameToId = new Map();
  for (const category of raw.categories) {
    const overrides = category.id_overrides || {};
    for (const row of category.rows || []) {
      for (const name of row) {
        if (!name) continue;
        nameToId.set(name, overrides[name] || `${category.id}_${slugify(name)}`);
      }
    }
  }

  const categories = [];
  const nodes = new Map();
  for (const source of raw.categories) {
    const category = {
      id: source.id,
      titles: source.titles || { "en-US": source.id },
      status: source.status || "",
      nodes: [],
      edges: [],
      rowCount: source.rows.length,
      columnCount: Math.max(1, ...source.rows.map((row) => row.length)),
      dataStats: { levels: 0, times: 0, costs: 0 },
    };
    for (let rowIndex = 0; rowIndex < source.rows.length; rowIndex += 1) {
      const row = source.rows[rowIndex];
      for (let columnIndex = 0; columnIndex < row.length; columnIndex += 1) {
        const englishName = row[columnIndex];
        if (!englishName) continue;
        const id = nameToId.get(englishName);
        const translated = source.localized_names?.[englishName] || {};
        const effect = source.effects?.[englishName] || {};
        const levels = new Map();
        for (const [levelText, levelSource] of Object.entries(source.level_data?.[englishName] || {})) {
          const requirements = (levelSource.requirements || []).map((requirement) => ({
            researchId: nameToId.get(requirement.research),
            level: Number(requirement.level || 0),
          })).filter((requirement) => requirement.researchId);
          levels.set(Number(levelText), {
            level: Number(levelText),
            academyLevel: levelSource.academy_level == null ? null : Number(levelSource.academy_level),
            baseTimeSeconds: levelSource.base_time_seconds == null ? null : Number(levelSource.base_time_seconds),
            technolabeCount: levelSource.technolabe_count == null ? null : Number(levelSource.technolabe_count),
            costs: { ...(levelSource.costs || {}) },
            power: levelSource.power == null ? null : Number(levelSource.power),
            requirements,
            buildings: { ...(levelSource.buildings || {}) },
            costsVerified: Boolean(levelSource.costs_verified),
          });
        }
        const node = {
          id,
          categoryId: category.id,
          names: { "en-US": englishName, ...translated },
          row: rowIndex,
          column: columnIndex,
          maxLevel: Number(source.max_levels?.[englishName] || Math.max(0, ...levels.keys())),
          effectLabel: String(effect.label || ""),
          effectValues: { ...(effect.levels || {}) },
          levels,
        };
        category.nodes.push(node);
        nodes.set(id, node);
        category.dataStats.levels += levels.size;
        category.dataStats.times += [...levels.values()].filter((item) => item.baseTimeSeconds != null).length;
        category.dataStats.costs += [...levels.values()].filter((item) => Object.keys(item.costs).length > 0).length;
      }
    }
    const pairs = (source.edges || []).map(([fromName, toName]) => [nameToId.get(fromName), nameToId.get(toName)])
      .filter(([from, to]) => from && to && nodes.has(from) && nodes.has(to));
    category.edges = nearestVisibleEdges(category.nodes, pairs);
    categories.push(category);
  }
  return {
    schemaVersion: Number(raw.schema_version || 1),
    datasetId: raw.dataset_id || "",
    checkedOn: raw.checked_on || "",
    gameVersion: raw.game_version || "",
    sources: [...(raw.sources || [])],
    categories,
    nodes,
    categoryTitle(category, locale) { return localText(category.titles, locale); },
    nodeName(node, locale) { return localText(node.names, locale); },
  };
}

function nearestVisibleEdges(categoryNodes, pairs) {
  const nodeById = new Map(categoryNodes.map((node) => [node.id, node]));
  const incoming = new Map();
  for (const [from, to] of pairs) {
    if (!nodeById.has(from) || !nodeById.has(to) || from === to) continue;
    if (!incoming.has(to)) incoming.set(to, []);
    incoming.get(to).push(from);
  }
  const result = [];
  for (const [to, candidates] of incoming) {
    const child = nodeById.get(to);
    const before = candidates.map((id) => nodeById.get(id)).filter((node) => node && node.row <= child.row);
    if (!before.length) continue;
    const nearestRow = Math.max(...before.map((node) => node.row));
    for (const parent of before.filter((node) => node.row === nearestRow)) result.push([parent.id, child.id]);
  }
  return [...new Map(result.map((edge) => [edge.join("\0"), edge])).values()];
}

export function currentEffect(node, level, { locale = "en-US", labels = {}, name = "" } = {}) {
  const rawFirst = String(node.effectValues["1"] || "").trim();
  let value = level <= 0 ? (isUnlock(rawFirst) ? (locale.startsWith("ja") ? "未解放" : "Not unlocked") : "0") : String(node.effectValues[String(level)] || "").trim();
  if (!value) return "";
  if (locale.startsWith("ja")) {
    if (isUnlock(value)) value = "解放";
    const minutes = value.match(/^(\d+)\s+(?:min|minutes)$/i);
    if (minutes) value = `${minutes[1]}分`;
    const hunt = value.match(/^Hunt Level (\d+) monsters$/i);
    if (hunt) value = `Lv.${hunt[1]}魔獣を討伐可能`;
  }
  let label = String(labels[node.effectLabel] || node.effectLabel || "").trim();
  const generic = new Set(["", "ATK+", "Boost", "Cost Reduction", "DEF+", "Def. Boost", "Effect", "HP+", "Reduction", "Result", "Speed+", "Unlock", "Unlocks", "Upgrade Result", "Upgrade Results"]);
  if ((locale.startsWith("ja") && !labels[node.effectLabel]) || generic.has(node.effectLabel)) {
    label = String(name || "").replace(/\s*(?:I|II|III|IV|V)$/u, "").trim();
    if (label.endsWith("補助")) label = `${label.slice(0, -2)}コスト低下`;
  }
  label = label.replace(/\+%?$/, "").trim();
  if (/^\d[\d,.]*(?:%|分)?$/.test(value)) value = `+${value}`;
  return label ? `${label}${locale.startsWith("ja") ? "" : " "}${value}` : value;
}

function isUnlock(value) { return value === "Unlocked" || /^Unlocks?\s/.test(value); }
