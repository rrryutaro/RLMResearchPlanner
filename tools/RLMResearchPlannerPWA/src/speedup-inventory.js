import { minimumGemsForSpeedupSeconds } from "./paid-value.js?v=0.1.7-b1";

export const SPEEDUP_KINDS = [
  "general", "research", "training", "construction", "healing", "merging", "crafting",
];

export const SPEEDUP_DURATION_SECONDS = [
  60, 3 * 60, 5 * 60, 10 * 60, 15 * 60, 30 * 60, 60 * 60,
  3 * 60 * 60, 8 * 60 * 60, 15 * 60 * 60, 24 * 60 * 60,
  3 * 24 * 60 * 60, 7 * 24 * 60 * 60, 30 * 24 * 60 * 60,
];

export const SPEEDUP_DURATION_GROUPS = [
  ["minutes", SPEEDUP_DURATION_SECONDS.slice(0, 7)],
  ["hours", SPEEDUP_DURATION_SECONDS.slice(7, 11)],
  ["days", SPEEDUP_DURATION_SECONDS.slice(11)],
];

export function speedupDurationGroup(durationSeconds) {
  const seconds = Math.max(0, Math.trunc(Number(durationSeconds) || 0));
  if (seconds <= 60 * 60) return "minutes";
  if (seconds <= 24 * 60 * 60) return "hours";
  return "days";
}

const integer = (value) => Math.max(0, Math.trunc(Number(value) || 0));

export function normalizeSpeedupInventory(entries) {
  const totals = new Map();
  for (const raw of Array.isArray(entries) ? entries : []) {
    const kind = String(raw?.kind || "general");
    const durationSeconds = integer(raw?.durationSeconds ?? raw?.duration_seconds);
    const quantity = integer(raw?.quantity);
    if (!SPEEDUP_KINDS.includes(kind) || !durationSeconds || !quantity) continue;
    const key = `${kind}\u0000${durationSeconds}`;
    totals.set(key, (totals.get(key) || 0) + quantity);
  }
  return [...totals.entries()]
    .map(([key, quantity]) => {
      const [kind, duration] = key.split("\u0000");
      return { kind, durationSeconds: Number(duration), quantity };
    })
    .sort((left, right) => SPEEDUP_KINDS.indexOf(left.kind) - SPEEDUP_KINDS.indexOf(right.kind)
      || right.durationSeconds - left.durationSeconds);
}

export function saveSpeedupInventoryEntry(entries, index, entry) {
  const normalized = normalizeSpeedupInventory(entries);
  const targetIndex = Number.isInteger(index) ? index : -1;
  if (targetIndex >= 0 && targetIndex < normalized.length) normalized.splice(targetIndex, 1, entry);
  else normalized.push(entry);
  return normalizeSpeedupInventory(normalized);
}

export function deleteSpeedupInventoryEntry(entries, index) {
  const normalized = normalizeSpeedupInventory(entries);
  const targetIndex = Number.isInteger(index) ? index : -1;
  if (targetIndex >= 0 && targetIndex < normalized.length) normalized.splice(targetIndex, 1);
  return normalized;
}

export function applicableSpeedupSeconds(entries, targetKind) {
  const eligible = new Set(["general", targetKind]);
  return normalizeSpeedupInventory(entries).reduce(
    (total, entry) => total + (eligible.has(entry.kind) ? entry.durationSeconds * entry.quantity : 0),
    0,
  );
}

function normalizedTaskSeconds(requiredSeconds, taskSeconds) {
  const required = integer(requiredSeconds);
  if (!Array.isArray(taskSeconds)) return required ? [required] : [];
  const tasks = taskSeconds.map(integer).filter((value) => value > 0);
  const knownTotal = tasks.reduce((sum, value) => sum + value, 0);
  if (knownTotal < required) tasks.push(required - knownTotal);
  return tasks;
}

function greatestCommonDivisor(left, right) {
  let a = Math.abs(integer(left));
  let b = Math.abs(integer(right));
  while (b) [a, b] = [b, a % b];
  return a;
}

function allocateWithoutOverrun(entries, targetKind, taskSeconds) {
  const remainingTaskSeconds = taskSeconds.map(integer).filter((value) => value > 0);
  const eligible = new Set(["general", targetKind]);
  const candidates = normalizeSpeedupInventory(entries)
    .filter((entry) => eligible.has(entry.kind))
    .sort((left, right) => right.durationSeconds - left.durationSeconds
      || Number(left.kind === "general") - Number(right.kind === "general"));
  // Ignore quantities that cannot fit into the individual tasks. Paid-offer
  // simulations can otherwise create enormous, unusable inventories while
  // searching for a purchase count.
  const quantities = candidates.map((entry) => Math.min(
    entry.quantity,
    remainingTaskSeconds.reduce(
      (total, seconds) => total + Math.floor(seconds / entry.durationSeconds),
      0,
    ),
  ));
  const usedQuantities = candidates.map(() => 0);
  const taskOrder = remainingTaskSeconds
    .map((seconds, index) => ({ seconds, index }))
    .sort((left, right) => left.seconds - right.seconds || left.index - right.index);

  for (const { index: taskIndex } of taskOrder) {
    const task = remainingTaskSeconds[taskIndex];
    const availableIndexes = candidates
      .map((entry, index) => ({ entry, index }))
      .filter(({ entry, index }) => quantities[index] > 0
        && entry.durationSeconds > 0
        && entry.durationSeconds <= task)
      .map(({ index }) => index);
    if (!availableIndexes.length) continue;
    const scale = availableIndexes.reduce(
      (value, index) => greatestCommonDivisor(value, candidates[index].durationSeconds),
      0,
    ) || 1;
    const capacity = Math.floor(task / scale);
    const chunks = [];
    for (const index of availableIndexes) {
      let remainingQuantity = quantities[index];
      let chunkQuantity = 1;
      const unit = Math.floor(candidates[index].durationSeconds / scale);
      while (remainingQuantity > 0) {
        const count = Math.min(chunkQuantity, remainingQuantity);
        chunks.push({ index, count, weight: unit * count });
        remainingQuantity -= count;
        chunkQuantity *= 2;
      }
    }

    const selectedCounts = new Map();
    let applied = 0;
    if (capacity <= 500_000) {
      const mask = (1n << BigInt(capacity + 1)) - 1n;
      let reachable = 1n;
      const newlyReachable = [];
      for (const chunk of chunks) {
        const states = ((reachable << BigInt(chunk.weight)) & mask) & ~reachable;
        newlyReachable.push(states);
        reachable |= states;
      }
      const target = reachable.toString(2).length - 1;
      let selected = target;
      for (let chunkIndex = chunks.length - 1; chunkIndex >= 0; chunkIndex -= 1) {
        if (((newlyReachable[chunkIndex] >> BigInt(selected)) & 1n) === 0n) continue;
        const chunk = chunks[chunkIndex];
        selectedCounts.set(chunk.index, (selectedCounts.get(chunk.index) || 0) + chunk.count);
        selected -= chunk.weight;
      }
      applied = target * scale;
    } else {
      for (const index of availableIndexes) {
        const duration = candidates[index].durationSeconds;
        const count = Math.min(quantities[index], Math.floor((task - applied) / duration));
        if (!count) continue;
        selectedCounts.set(index, count);
        applied += duration * count;
      }
    }
    remainingTaskSeconds[taskIndex] -= applied;
    for (const [index, count] of selectedCounts) {
      quantities[index] -= count;
      usedQuantities[index] += count;
    }
  }
  const usedItems = candidates
    .map((entry, index) => ({ ...entry, quantity: usedQuantities[index] }))
    .filter((entry) => entry.quantity > 0);
  return { remainingTaskSeconds, usedItems };
}

function hasUnlimitedExactDuration(seconds, durations) {
  let target = integer(seconds);
  const normalized = [...new Set(durations.map(integer).filter((value) => value > 0))]
    .sort((left, right) => left - right);
  if (!target) return true;
  if (!normalized.length) return false;
  const scale = normalized.reduce(greatestCommonDivisor, 0) || 1;
  if (target % scale) return false;
  target = Math.floor(target / scale);
  const units = normalized.map((duration) => Math.floor(duration / scale));
  if (units.includes(1)) return true;
  const reachable = new Uint8Array(target + 1);
  reachable[0] = 1;
  for (let value = 0; value <= target; value += 1) {
    if (!reachable[value]) continue;
    for (const unit of units) {
      const next = value + unit;
      if (next <= target) reachable[next] = 1;
    }
  }
  return reachable[target] === 1;
}

export function speedupCoverage(requiredSeconds, entries, targetKind, taskSeconds = null) {
  const tasks = normalizedTaskSeconds(requiredSeconds, taskSeconds);
  const required = tasks.reduce((sum, value) => sum + value, 0);
  const available = applicableSpeedupSeconds(entries, targetKind);
  const { remainingTaskSeconds, usedItems } = allocateWithoutOverrun(entries, targetKind, tasks);
  const remaining = remainingTaskSeconds.reduce((sum, value) => sum + value, 0);
  const applied = Math.max(0, required - remaining);
  return {
    targetKind,
    requiredSeconds: required,
    availableSeconds: available,
    appliedSeconds: applied,
    remainingSeconds: remaining,
    surplusSeconds: Math.max(0, available - applied),
    remainingTaskSeconds,
    usedItems,
  };
}

export function addPaidItemsToInventory(entries, paidItems) {
  return normalizeSpeedupInventory([
    ...(Array.isArray(entries) ? entries : []),
    ...(Array.isArray(paidItems) ? paidItems : [])
      .filter((item) => SPEEDUP_KINDS.includes(item?.kind))
      .map((item) => ({
        kind: item.kind,
        durationSeconds: integer(item.durationSeconds ?? item.duration_seconds),
        quantity: integer(item.quantity),
      })),
  ]);
}

export function paidOfferSpeedupSeconds(offer, targetKind) {
  const eligible = new Set(["general", targetKind]);
  return (offer?.items || []).reduce((total, item) => total + (
    eligible.has(item.kind)
      ? integer(item.durationSeconds ?? item.duration_seconds) * integer(item.quantity)
      : 0
  ), 0);
}

export function paidOfferGems(offer) {
  return integer(offer?.includedGems ?? offer?.included_gems)
    + integer(offer?.bonusGems ?? offer?.bonus_gems)
    + (offer?.items || []).reduce(
      (total, item) => total + (item?.kind === "gems" ? integer(item.quantity) : 0),
      0,
    );
}

function offerCoversShortfall(shortfall, _secondsPerPurchase, gemsPerPurchase, purchases, context) {
  const { offer, targetKind, taskSeconds, useGems } = context;
  const inventory = (offer?.items || [])
    .filter((item) => SPEEDUP_KINDS.includes(item?.kind))
    .map((item) => ({
      kind: item.kind,
      durationSeconds: integer(item.durationSeconds ?? item.duration_seconds),
      quantity: integer(item.quantity) * purchases,
    }));
  const coverage = speedupCoverage(shortfall, inventory, targetKind, taskSeconds);
  if (!coverage.remainingSeconds) return true;
  if (!useGems || !gemsPerPurchase) return false;
  const requiredGems = coverage.remainingTaskSeconds.reduce(
    (sum, seconds) => sum + minimumGemsForSpeedupSeconds(seconds).gems,
    0,
  );
  return gemsPerPurchase * purchases >= requiredGems;
}

function minimumOfferPurchases(shortfall, secondsPerPurchase, gemsPerPurchase, context) {
  const eligibleDurations = (context.offer?.items || [])
    .filter((item) => ["general", context.targetKind].includes(item?.kind)
      && integer(item.durationSeconds ?? item.duration_seconds) > 0
      && integer(item.quantity) > 0)
    .map((item) => integer(item.durationSeconds ?? item.duration_seconds));
  if ((!context.useGems || gemsPerPurchase <= 0)
    && eligibleDurations.length
    && context.taskSeconds.some((seconds) => !hasUnlimitedExactDuration(seconds, eligibleDurations))) {
    return null;
  }
  let high;
  if (context.useGems && gemsPerPurchase > 0) {
    const gemsWithoutSpeedups = context.taskSeconds.reduce(
      (sum, seconds) => sum + minimumGemsForSpeedupSeconds(seconds).gems,
      0,
    );
    high = Math.max(1, Math.ceil(gemsWithoutSpeedups / gemsPerPurchase));
  } else if (eligibleDurations.length) {
    const minimumDuration = Math.min(...eligibleDurations);
    high = Math.max(1, context.taskSeconds.reduce(
      (sum, seconds) => sum + Math.ceil(seconds / minimumDuration),
      0,
    ));
  } else return null;
  if (!offerCoversShortfall(shortfall, secondsPerPurchase, gemsPerPurchase, high, context)) return null;
  let low = 1;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (offerCoversShortfall(shortfall, secondsPerPurchase, gemsPerPurchase, middle, context)) high = middle;
    else low = middle + 1;
  }
  return low;
}

export function recommendPaidOffers(shortfallSeconds, offers, targetKind, limit = 3, options = {}) {
  const taskSeconds = normalizedTaskSeconds(shortfallSeconds, options.taskSeconds);
  const shortfall = taskSeconds.reduce((sum, value) => sum + value, 0);
  const useGems = options.useGems === true;
  if (!shortfall) return [];
  return (Array.isArray(offers) ? offers : [])
    .map((offer) => {
      const secondsPerPurchase = paidOfferSpeedupSeconds(offer, targetKind);
      const gemsPerPurchase = paidOfferGems(offer);
      if (!secondsPerPurchase && (!useGems || !gemsPerPurchase)) return null;
      const context = { offer, targetKind, taskSeconds, useGems };
      const completingPurchases = minimumOfferPurchases(shortfall, secondsPerPurchase, gemsPerPurchase, context);
      // Keep a relevant saved offer visible even when it cannot finish every
      // task without wasting an item.  One purchase still gives the user a
      // concrete contribution and remaining-time comparison.
      const purchases = completingPurchases ?? 1;
      const totalSeconds = secondsPerPurchase * purchases;
      const availableGems = gemsPerPurchase * purchases;
      const inventory = (offer?.items || [])
        .filter((item) => SPEEDUP_KINDS.includes(item?.kind))
        .map((item) => ({
          kind: item.kind,
          durationSeconds: integer(item.durationSeconds ?? item.duration_seconds),
          quantity: integer(item.quantity) * purchases,
        }));
      const coverage = speedupCoverage(shortfall, inventory, targetKind, taskSeconds);
      const gemPurchases = coverage.remainingTaskSeconds.map(minimumGemsForSpeedupSeconds);
      const requiredGems = gemPurchases.reduce((sum, item) => sum + item.gems, 0);
      const canUseGems = useGems && coverage.remainingSeconds > 0 && availableGems >= requiredGems;
      if (!coverage.appliedSeconds && !canUseGems) return null;
      const gemsUsed = canUseGems ? requiredGems : 0;
      const gemAppliedSeconds = canUseGems ? coverage.remainingSeconds : 0;
      const remainingSeconds = Math.max(0, coverage.remainingSeconds - gemAppliedSeconds);
      const diamondCostEach = integer(offer.diamondCost ?? offer.diamond_cost);
      return {
        offerId: String(offer.offerId ?? offer.offer_id ?? ""),
        title: String(offer.title || ""),
        purchases,
        secondsPerPurchase,
        totalSeconds,
        diamondCostEach,
        totalDiamondCost: diamondCostEach ? diamondCostEach * purchases : null,
        gemsPerPurchase,
        availableGems,
        appliedSpeedupSeconds: coverage.appliedSeconds,
        gemsUsed,
        gemAppliedSeconds,
        remainingSeconds,
        excessSeconds: Math.max(0, coverage.surplusSeconds
          + gemPurchases.reduce((sum, item) => sum + item.purchasedSeconds, 0)
          - gemAppliedSeconds),
      };
    })
    .filter(Boolean)
    .sort((left, right) => Number(left.remainingSeconds > 0) - Number(right.remainingSeconds > 0)
      || Number(left.totalDiamondCost === null) - Number(right.totalDiamondCost === null)
      || (left.totalDiamondCost || 0) - (right.totalDiamondCost || 0)
      || left.excessSeconds - right.excessSeconds
      || left.purchases - right.purchases
      || left.title.localeCompare(right.title))
    .slice(0, Math.max(0, Math.trunc(limit)));
}
