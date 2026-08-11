function localText(values, locale) {
  return values?.[locale] || values?.[locale.split("-")[0]] || values?.["en-US"] || Object.values(values || {})[0] || "";
}

function expectDocument(value, type, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`${label}の形式が正しくありません`);
  if (value.document_type !== type) throw new Error(`${label}のdocument_typeが正しくありません`);
  if (Number(value.schema_version) !== 2) throw new Error(`${label}のschema_versionに対応していません`);
  return value;
}

const SUPPORTED_DATASET_ID = "lords_mobile_research_data";
const SUPPORTED_DATASET_VERSION = "0.1.0";

function datasetResourceUrl(root, relative, version = "") {
  const path = String(relative || "");
  if (!path || path.includes("\\") || path.startsWith("/") || path.split("/").includes("..") || /[?#]/u.test(path)) {
    throw new Error(`研究データ内のパスが正しくありません: ${path}`);
  }
  const url = `${String(root).replace(/\/$/u, "")}/${path}`;
  return version ? `${url}?v=${encodeURIComponent(version)}` : url;
}

export async function loadCatalog(root = "./data/research-dataset", version = "") {
  const manifest = expectDocument(
    await loadJsonResource(datasetResourceUrl(root, "manifest.json", version), "研究データ一覧"),
    "RLMResearchData.manifest",
    "研究データ一覧",
  );
  if (manifest.dataset_id !== SUPPORTED_DATASET_ID) throw new Error("研究データIDに対応していません");
  if (manifest.dataset_version !== SUPPORTED_DATASET_VERSION) throw new Error(`研究データ版 ${manifest.dataset_version || "不明"} に対応していません`);
  const [sources, evidence, aliases, treeEntries, localeEntries] = await Promise.all([
    loadJsonResource(datasetResourceUrl(root, manifest.sources_path, version), "研究データ出典"),
    loadJsonResource(datasetResourceUrl(root, manifest.evidence_path, version), "研究データ確認情報"),
    loadJsonResource(datasetResourceUrl(root, manifest.aliases_path, version), "研究ID互換情報"),
    Promise.all((manifest.trees || []).map(async (entry) => [
      String(entry.id),
      expectDocument(await loadJsonResource(datasetResourceUrl(root, entry.path, version), `研究分野 ${entry.id}`), "RLMResearchData.tree", `研究分野 ${entry.id}`),
    ])),
    Promise.all((manifest.locales || []).map(async (entry) => [
      String(entry.locale),
      expectDocument(await loadJsonResource(datasetResourceUrl(root, entry.path, version), `研究翻訳 ${entry.locale}`), "RLMResearchData.locale", `研究翻訳 ${entry.locale}`),
    ])),
  ]);
  return normalizeCatalog({
    manifest,
    sources: expectDocument(sources, "RLMResearchData.sources", "研究データ出典"),
    evidence: expectDocument(evidence, "RLMResearchData.evidence", "研究データ確認情報"),
    aliases: expectDocument(aliases, "RLMResearchData.aliases", "研究ID互換情報"),
    trees: Object.fromEntries(treeEntries),
    locales: Object.fromEntries(localeEntries),
  });
}

export async function loadEffectLabels(url = "./data/i18n/ja-JP.json") {
  return (await loadJsonResource(url, "効果ラベル")).effect_labels || {};
}

export async function loadLocaleData(url = "./data/i18n/ja-JP.json") {
  return loadJsonResource(url, "表示言語データ");
}

export async function loadJsonResource(url, label = "データ") {
  let lastError;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const retryUrl = attempt === 0 ? url : `${url}${String(url).includes("?") ? "&" : "?"}reload=${Date.now()}`;
    try {
      const response = await fetch(retryUrl, { cache: attempt === 0 ? "default" : "reload" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const text = await response.text();
      if (/^\s*</u.test(text)) throw new Error("JSONの代わりにHTMLが返されました");
      const value = JSON.parse(text);
      if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("JSONの形式が正しくありません");
      return value;
    } catch (error) {
      lastError = error;
    }
  }
  throw new Error(`${label}を読み込めません (${lastError?.message || "不明なエラー"})`);
}

export function normalizeCatalog(documents) {
  const raw = documents?.manifest;
  if (!raw || raw.document_type !== "RLMResearchData.manifest" || Number(raw.schema_version) !== 2) {
    throw new Error("研究データ一覧の形式が正しくありません");
  }
  const treeDocuments = documents.trees || {};
  const localeDocuments = documents.locales || {};
  let languagePack = null;
  const categories = [];
  const nodes = new Map();
  for (const entry of raw.trees || []) {
    const source = treeDocuments[String(entry.id)];
    if (!source || source.tree_id !== entry.id) throw new Error(`研究分野 ${entry.id} が見つかりません`);
    const category = {
      id: source.tree_id,
      titles: Object.fromEntries(Object.entries(localeDocuments).flatMap(([locale, document]) => (
        document.trees?.[source.tree_id] ? [[locale, document.trees[source.tree_id]]] : []
      ))),
      status: source.legacy_compatibility?.verification_status || source.default_verification?.status || "",
      scope: source.legacy_compatibility?.scope || source.coverage || "",
      nodes: [],
      edges: [],
      connectionGroups: (source.display_connections || []).map((group) => ({
        fromIds: [...(group.from_ids || [])],
        toIds: [...(group.to_ids || [])],
      })),
      rowCount: 0,
      columnCount: 0,
      dataStats: { levels: 0, times: 0, costs: 0 },
    };
    for (const levelSourceNode of source.nodes || []) {
      const id = String(levelSourceNode.id);
      const effect = (levelSourceNode.effects || [])[0] || null;
      const levels = new Map();
      for (const levelSource of levelSourceNode.levels || []) {
        const requirements = (levelSource.prerequisites || []).map((requirement) => ({
          researchId: String(requirement.research_id),
          level: Number(requirement.level || 0),
        }));
        levels.set(Number(levelSource.level), {
          level: Number(levelSource.level),
          academyLevel: levelSource.academy_level == null ? null : Number(levelSource.academy_level),
          baseTimeSeconds: levelSource.base_time_seconds == null ? null : Number(levelSource.base_time_seconds),
          technolabeCount: levelSource.technolabe_count == null ? null : Number(levelSource.technolabe_count),
          costs: { ...(levelSource.costs || {}) },
          power: levelSource.power == null ? null : Number(levelSource.power),
          requirements,
          buildings: { ...(levelSource.buildings || {}) },
          costsVerified: levelSource.costs != null,
          verificationStatus: String(levelSource.legacy_verification_status || levelSource.verification?.status || source.default_verification?.status || "provisional"),
        });
      }
      const names = Object.fromEntries(Object.entries(localeDocuments).flatMap(([locale, document]) => (
        document.research?.[id] ? [[locale, document.research[id]]] : []
      )));
      const node = {
        id,
        categoryId: category.id,
        names,
        row: Number(levelSourceNode.layout?.row || 0),
        column: Number(levelSourceNode.layout?.column || 0),
        maxLevel: Number(levelSourceNode.max_level || Math.max(0, ...levels.keys())),
        effectLabel: effect ? String(localeDocuments["en-US"]?.metrics?.[effect.metric_id] || "") : "",
        effectValues: effect ? Object.fromEntries((effect.values || []).map((item) => [String(item.level), String(item.display_fallback ?? item.value ?? "")])) : {},
        levels,
      };
      category.nodes.push(node);
      nodes.set(id, node);
      category.dataStats.levels += levels.size;
      category.dataStats.times += [...levels.values()].filter((item) => item.baseTimeSeconds != null).length;
      category.dataStats.costs += [...levels.values()].filter((item) => Object.keys(item.costs).length > 0).length;
    }
    category.rowCount = Math.max(1, ...category.nodes.map((node) => node.row + 1));
    category.columnCount = Math.max(1, ...category.nodes.map((node) => node.column + 1));
    const nodeIds = new Set(category.nodes.map((node) => node.id));
    const pairs = category.connectionGroups.flatMap((group) => group.fromIds.flatMap((from) => group.toIds.map((to) => [from, to])))
      .filter(([from, to]) => from !== to && nodeIds.has(from) && nodeIds.has(to));
    category.edges = [...new Map(pairs.map((edge) => [edge.join("\0"), edge])).values()];
    categories.push(category);
  }
  return {
    schemaVersion: Number(raw.schema_version || 1),
    datasetId: raw.dataset_id || "",
    checkedOn: raw.checked_on || "",
    gameVersion: raw.game_version || "",
    datasetVersion: raw.dataset_version || "",
    sources: [...(documents.sources?.sources || [])],
    categories,
    nodes,
    setLanguagePack(pack) { languagePack = pack || null; },
    sourceCategoryTitle(category, locale) { return localText(category.titles, locale); },
    sourceNodeName(node, locale) { return localText(node.names, locale); },
    categoryTitle(category, locale) { return languagePack?.sections?.categories?.[category.id] || localText(category.titles, languagePack?.fallbackLocale || locale); },
    nodeName(node, locale) { return languagePack?.sections?.research?.[node.id] || localText(node.names, languagePack?.fallbackLocale || locale); },
  };
}

export function currentEffect(node, level, { locale = "en-US", labels = {}, name = "", translatedLabel = "" } = {}) {
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
  let label = String(translatedLabel || labels[node.effectLabel] || node.effectLabel || "").trim();
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
