export const SPEEDUP_ITEM_KINDS = [
  "general", "research", "training", "construction", "healing", "merging", "crafting",
];
export const PAID_GOALS = ["all_round", "account_growth", "research", "construction", "troop_training", "combat", "monster_hunt", "equipment", "familiar", "artifact", "heroes", "events", "resources"];
export const PAID_ITEM_KINDS = [
  ...SPEEDUP_ITEM_KINDS,
  "gems",
  "monster_common",
  "monster_uncommon",
  "monster_rare",
  "monster_epic",
  "monster_legendary",
  "chest",
  "resource",
  "material",
  "combat_item",
  "boost_item",
  "building_material",
  "familiar_item",
  "monster_energy",
  "hero_item",
  "artifact_item",
  "event_item",
  "currency",
  "custom",
];

const DEFAULT_POINTS_EACH = {
  monster_common: 1,
  monster_uncommon: 4,
  monster_rare: 16,
  monster_epic: 64,
  monster_legendary: 256,
};
const SPEEDUP_GEM_VALUE_BY_SECONDS = new Map([
  [60, 5], [15 * 60, 70], [60 * 60, 130], [3 * 60 * 60, 300],
  [8 * 60 * 60, 650], [15 * 60 * 60, 1000], [24 * 60 * 60, 1500],
  [3 * 24 * 60 * 60, 4400], [7 * 24 * 60 * 60, 10000], [30 * 24 * 60 * 60, 40000],
]);
let standardSpeedupGemCosts = null;
const MERGING_SPEEDUP_GEM_VALUE_BY_SECONDS = new Map([
  [15 * 60, 140], [60 * 60, 260], [3 * 60 * 60, 600], [8 * 60 * 60, 1300],
  [15 * 60 * 60, 2000], [24 * 60 * 60, 3000], [3 * 24 * 60 * 60, 8800],
  [7 * 24 * 60 * 60, 20000],
]);
export const PAID_OFFER_DOCUMENT_TYPE = "RLMResearchPlanner.paid-offers";

const finite = (value, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};
const nonNegative = (value, fallback = 0) => Math.max(0, finite(value, fallback));

function buildStandardSpeedupGemCosts() {
  if (standardSpeedupGemCosts) return standardSpeedupGemCosts;
  const presets = [...SPEEDUP_GEM_VALUE_BY_SECONDS.entries()]
    .map(([seconds, gems]) => [Math.max(1, Math.trunc(seconds / 60)), Math.max(0, Math.trunc(gems))])
    .sort((left, right) => left[0] - right[0]);
  const maximumMinutes = presets.at(-1)[0];
  const costs = Array(maximumMinutes + 1).fill(Number.MAX_SAFE_INTEGER);
  const purchasedMinutes = Array(maximumMinutes + 1).fill(0);
  costs[0] = 0;
  for (let targetMinutes = 1; targetMinutes <= maximumMinutes; targetMinutes += 1) {
    for (const [duration, cost] of presets) {
      const previous = Math.max(0, targetMinutes - duration);
      const candidateCost = cost + costs[previous];
      const candidateMinutes = duration + purchasedMinutes[previous];
      if (candidateCost < costs[targetMinutes]
        || (candidateCost === costs[targetMinutes] && candidateMinutes < purchasedMinutes[targetMinutes])) {
        costs[targetMinutes] = candidateCost;
        purchasedMinutes[targetMinutes] = candidateMinutes;
      }
    }
  }
  standardSpeedupGemCosts = { costs, purchasedMinutes, maximumMinutes };
  return standardSpeedupGemCosts;
}

export function minimumGemsForSpeedupSeconds(seconds) {
  const requiredMinutes = Math.max(0, Math.ceil(nonNegative(seconds) / 60));
  if (!requiredMinutes) return { gems: 0, purchasedSeconds: 0 };
  const { costs, purchasedMinutes, maximumMinutes } = buildStandardSpeedupGemCosts();
  const maximumCost = SPEEDUP_GEM_VALUE_BY_SECONDS.get(maximumMinutes * 60);
  const fullItems = Math.floor(requiredMinutes / maximumMinutes);
  const remainder = requiredMinutes % maximumMinutes;
  if (!remainder) {
    return {
      gems: fullItems * maximumCost,
      purchasedSeconds: fullItems * maximumMinutes * 60,
    };
  }
  const withRemainder = {
    gems: fullItems * maximumCost + costs[remainder],
    purchasedSeconds: (fullItems * maximumMinutes + purchasedMinutes[remainder]) * 60,
  };
  const withExtraFullItem = {
    gems: (fullItems + 1) * maximumCost,
    purchasedSeconds: (fullItems + 1) * maximumMinutes * 60,
  };
  return withRemainder.gems < withExtraFullItem.gems
    || (withRemainder.gems === withExtraFullItem.gems
      && withRemainder.purchasedSeconds <= withExtraFullItem.purchasedSeconds)
    ? withRemainder
    : withExtraFullItem;
}

export function defaultPaidValuation() {
  return {
    pointsPerGem: 1,
    generalSpeedupPointsPerHour: 0,
    researchSpeedupPointsPerHour: 0,
    trainingSpeedupPointsPerHour: 0,
    constructionSpeedupPointsPerHour: 0,
    healingSpeedupPointsPerHour: 0,
    mergingSpeedupPointsPerHour: 0,
    craftingSpeedupPointsPerHour: 0,
    useSpeedupGemPresets: true,
  };
}

export function emptyPaidOffer() {
  const now = new Date().toISOString();
  return {
    offerId: "",
    title: "",
    goal: "all_round",
    memo: "",
    diamondCost: 0,
    includedGems: 0,
    bonusGems: 0,
    items: [],
    createdAt: now,
    updatedAt: now,
  };
}

export function paidKindHasTime(kind) {
  return SPEEDUP_ITEM_KINDS.includes(kind);
}

export function defaultPointsEach(kind) {
  return DEFAULT_POINTS_EACH[kind] || 0;
}

export function defaultGemValueEach(kind) {
  return kind === "gems" ? 1 : 0;
}

export function sanitizePaidItem(raw) {
  const kind = PAID_ITEM_KINDS.includes(String(raw?.kind)) ? String(raw.kind) : "custom";
  return {
    kind,
    name: String(raw?.name || "").trim().slice(0, 200),
    quantity: Math.max(0, Math.trunc(finite(raw?.quantity))),
    durationSeconds: paidKindHasTime(kind)
      ? Math.max(0, Math.trunc(finite(raw?.durationSeconds ?? raw?.duration_seconds)))
      : 0,
    gemValueEach: nonNegative(raw?.gemValueEach ?? raw?.gem_value_each),
    pointsEach: nonNegative(raw?.pointsEach ?? raw?.points_each, defaultPointsEach(kind)),
  };
}

export function sanitizePaidOffer(raw) {
  const base = emptyPaidOffer();
  return {
    offerId: String(raw?.offerId || raw?.offer_id || "").trim().slice(0, 100),
    title: String(raw?.title || "").trim().slice(0, 200),
    goal: PAID_GOALS.includes(String(raw?.goal)) ? String(raw.goal) : "all_round",
    memo: String(raw?.memo || "").slice(0, 2000),
    diamondCost: Math.max(0, Math.trunc(finite(raw?.diamondCost ?? raw?.diamond_cost))),
    includedGems: Math.max(0, Math.trunc(finite(raw?.includedGems ?? raw?.included_gems))),
    bonusGems: Math.max(0, Math.trunc(finite(raw?.bonusGems ?? raw?.bonus_gems))),
    items: (Array.isArray(raw?.items) ? raw.items : []).map(sanitizePaidItem),
    createdAt: String(raw?.createdAt || raw?.created_at || base.createdAt),
    updatedAt: String(raw?.updatedAt || raw?.updated_at || base.updatedAt),
  };
}

export function sanitizePaidValuation(raw) {
  const base = defaultPaidValuation();
  return {
    pointsPerGem: nonNegative(raw?.pointsPerGem ?? raw?.points_per_gem, base.pointsPerGem),
    generalSpeedupPointsPerHour: nonNegative(raw?.generalSpeedupPointsPerHour ?? raw?.general_speedup_points_per_hour, base.generalSpeedupPointsPerHour),
    researchSpeedupPointsPerHour: nonNegative(raw?.researchSpeedupPointsPerHour ?? raw?.research_speedup_points_per_hour, base.researchSpeedupPointsPerHour),
    trainingSpeedupPointsPerHour: nonNegative(raw?.trainingSpeedupPointsPerHour ?? raw?.training_speedup_points_per_hour, base.trainingSpeedupPointsPerHour),
    constructionSpeedupPointsPerHour: nonNegative(raw?.constructionSpeedupPointsPerHour ?? raw?.construction_speedup_points_per_hour, base.constructionSpeedupPointsPerHour),
    healingSpeedupPointsPerHour: nonNegative(raw?.healingSpeedupPointsPerHour ?? raw?.healing_speedup_points_per_hour, base.healingSpeedupPointsPerHour),
    mergingSpeedupPointsPerHour: nonNegative(raw?.mergingSpeedupPointsPerHour ?? raw?.merging_speedup_points_per_hour, base.mergingSpeedupPointsPerHour),
    craftingSpeedupPointsPerHour: nonNegative(raw?.craftingSpeedupPointsPerHour ?? raw?.crafting_speedup_points_per_hour, base.craftingSpeedupPointsPerHour),
    useSpeedupGemPresets: (raw?.useSpeedupGemPresets ?? raw?.use_speedup_gem_presets) !== false,
  };
}

export function summarizePaidOffer(rawOffer, rawValuation) {
  const offer = sanitizePaidOffer(rawOffer);
  const valuation = sanitizePaidValuation(rawValuation);
  const speedupSeconds = Object.fromEntries(SPEEDUP_ITEM_KINDS.map((kind) => [kind, 0]));
  let itemGemValue = 0;
  let speedupGemValue = 0;
  let directItemPoints = 0;
  for (const item of offer.items) {
    if (paidKindHasTime(item.kind)) {
      speedupSeconds[item.kind] += item.durationSeconds * item.quantity;
      if (valuation.useSpeedupGemPresets && item.gemValueEach <= 0) {
        const preset = item.kind === "merging"
          ? MERGING_SPEEDUP_GEM_VALUE_BY_SECONDS
          : item.kind === "crafting" ? null : SPEEDUP_GEM_VALUE_BY_SECONDS;
        speedupGemValue += (preset?.get(item.durationSeconds) || 0) * item.quantity;
      }
    }
    itemGemValue += item.gemValueEach * item.quantity;
    directItemPoints += item.pointsEach * item.quantity;
  }
  const includedGems = offer.includedGems + offer.bonusGems;
  const totalGemValue = includedGems + itemGemValue + speedupGemValue;
  const rates = {
    general: valuation.generalSpeedupPointsPerHour,
    research: valuation.researchSpeedupPointsPerHour,
    training: valuation.trainingSpeedupPointsPerHour,
    construction: valuation.constructionSpeedupPointsPerHour,
    healing: valuation.healingSpeedupPointsPerHour,
    merging: valuation.mergingSpeedupPointsPerHour,
    crafting: valuation.craftingSpeedupPointsPerHour,
  };
  const speedupPoints = SPEEDUP_ITEM_KINDS.reduce((sum, kind) => sum + speedupSeconds[kind] / 3600 * rates[kind], 0);
  const totalPoints = totalGemValue * valuation.pointsPerGem + directItemPoints + speedupPoints;
  return {
    speedupSeconds,
    totalSpeedupSeconds: Object.values(speedupSeconds).reduce((sum, value) => sum + value, 0),
    includedGems,
    itemGemValue,
    speedupGemValue,
    totalGemValue,
    directItemPoints,
    speedupPoints,
    totalPoints,
    pointsPerDiamond: offer.diamondCost > 0 ? totalPoints / offer.diamondCost : null,
    gemsPerDiamond: offer.diamondCost > 0 ? totalGemValue / offer.diamondCost : null,
  };
}

export function sortedPaidOffers(offers, valuation) {
  return [...(offers || [])].map(sanitizePaidOffer).sort((left, right) => {
    const a = summarizePaidOffer(left, valuation);
    const b = summarizePaidOffer(right, valuation);
    return (b.pointsPerDiamond || 0) - (a.pointsPerDiamond || 0)
      || b.totalPoints - a.totalPoints
      || left.title.localeCompare(right.title);
  });
}

export function paidOfferExchangePayload(offers, valuation, name = "") {
  return {
    document_type: PAID_OFFER_DOCUMENT_TYPE,
    schema_version: 1,
    exported_at: new Date().toISOString(),
    name: String(name || "").trim().slice(0, 200),
    valuation: {
      points_per_gem: valuation.pointsPerGem,
      general_speedup_points_per_hour: valuation.generalSpeedupPointsPerHour,
      research_speedup_points_per_hour: valuation.researchSpeedupPointsPerHour,
      training_speedup_points_per_hour: valuation.trainingSpeedupPointsPerHour,
      construction_speedup_points_per_hour: valuation.constructionSpeedupPointsPerHour,
      healing_speedup_points_per_hour: valuation.healingSpeedupPointsPerHour,
      merging_speedup_points_per_hour: valuation.mergingSpeedupPointsPerHour,
      crafting_speedup_points_per_hour: valuation.craftingSpeedupPointsPerHour,
      use_speedup_gem_presets: valuation.useSpeedupGemPresets,
    },
    offers: (offers || []).map((raw) => {
      const offer = sanitizePaidOffer(raw);
      return {
        offer_id: offer.offerId, title: offer.title, goal: offer.goal, memo: offer.memo,
        diamond_cost: offer.diamondCost, included_gems: offer.includedGems, bonus_gems: offer.bonusGems,
        items: offer.items.map((item) => ({ kind: item.kind, name: item.name, quantity: item.quantity, duration_seconds: item.durationSeconds, gem_value_each: item.gemValueEach, points_each: item.pointsEach })),
        created_at: offer.createdAt, updated_at: offer.updatedAt,
      };
    }),
  };
}

export function paidOffersFromExchangePayload(raw) {
  if (raw?.document_type !== PAID_OFFER_DOCUMENT_TYPE || Number(raw?.schema_version) !== 1 || !Array.isArray(raw?.offers)) throw new Error("対応していない課金データです");
  const offers = raw.offers.map(sanitizePaidOffer).filter((offer) => offer.title);
  if (!offers.length && (!raw.valuation || typeof raw.valuation !== "object" || Array.isArray(raw.valuation))) throw new Error("取り込める課金項目または比較設定がありません");
  return { offers, valuation: sanitizePaidValuation(raw.valuation), name: String(raw.name || "").slice(0, 200) };
}
