import assert from "node:assert/strict";
import test from "node:test";

import {
  addPaidItemsToInventory,
  deleteSpeedupInventoryEntry,
  recommendPaidOffers,
  saveSpeedupInventoryEntry,
  speedupCoverage,
} from "../src/speedup-inventory.js";

test("research coverage uses only general and research speedups", () => {
  const result = speedupCoverage(15_000, [
    { kind: "general", durationSeconds: 3600, quantity: 2 },
    { kind: "research", durationSeconds: 1800, quantity: 3 },
    { kind: "construction", durationSeconds: 86400, quantity: 1 },
  ], "research");
  assert.equal(result.availableSeconds, 12_600);
  assert.equal(result.remainingSeconds, 2_400);
});

test("construction coverage uses only general and construction speedups", () => {
  const result = speedupCoverage(10_000, [
    { kind: "general", durationSeconds: 3600, quantity: 1 },
    { kind: "construction", durationSeconds: 1800, quantity: 2 },
    { kind: "research", durationSeconds: 86400, quantity: 1 },
  ], "construction");
  assert.equal(result.availableSeconds, 7200);
  assert.equal(result.appliedSeconds, 7200);
  assert.equal(result.remainingSeconds, 2800);
});

test("speedups never overrun an individual plan step", () => {
  const result = speedupCoverage(3 * 3600 + 24 * 60, [
    { kind: "general", durationSeconds: 3 * 3600, quantity: 2 },
    { kind: "research", durationSeconds: 20 * 60, quantity: 3 },
    { kind: "construction", durationSeconds: 24 * 60, quantity: 99 },
  ], "research", [24 * 60, 3 * 3600]);
  assert.equal(result.appliedSeconds, 3 * 3600 + 20 * 60);
  assert.deepEqual(result.remainingTaskSeconds, [4 * 60, 0]);
  assert.deepEqual(result.usedItems, [
    { kind: "general", durationSeconds: 3 * 3600, quantity: 1 },
    { kind: "research", durationSeconds: 20 * 60, quantity: 1 },
  ]);
});

test("allocation chooses the best fitting combination", () => {
  const result = speedupCoverage(10 * 60, [
    { kind: "research", durationSeconds: 6 * 60, quantity: 1 },
    { kind: "research", durationSeconds: 5 * 60, quantity: 2 },
  ], "research", [10 * 60]);
  assert.equal(result.appliedSeconds, 10 * 60);
  assert.equal(result.remainingSeconds, 0);
  assert.deepEqual(result.usedItems, [
    { kind: "research", durationSeconds: 5 * 60, quantity: 2 },
  ]);
});

test("paid item speedups merge into owned inventory", () => {
  const result = addPaidItemsToInventory(
    [{ kind: "general", durationSeconds: 3600, quantity: 2 }],
    [
      { kind: "general", durationSeconds: 3600, quantity: 3 },
      { kind: "research", durationSeconds: 1800, quantity: 4 },
      { kind: "gems", durationSeconds: 0, quantity: 100 },
    ],
  );
  assert.deepEqual(result, [
    { kind: "general", durationSeconds: 3600, quantity: 5 },
    { kind: "research", durationSeconds: 1800, quantity: 4 },
  ]);
});

test("one shared editor can add, update, merge, and delete list entries", () => {
  const initial = [
    { kind: "general", durationSeconds: 3600, quantity: 2 },
    { kind: "research", durationSeconds: 1800, quantity: 4 },
  ];
  const added = saveSpeedupInventoryEntry(initial, -1, { kind: "construction", durationSeconds: 900, quantity: 5 });
  assert.equal(added.length, 3);
  const updated = saveSpeedupInventoryEntry(added, 1, { kind: "general", durationSeconds: 3600, quantity: 3 });
  assert.deepEqual(updated, [
    { kind: "general", durationSeconds: 3600, quantity: 5 },
    { kind: "construction", durationSeconds: 900, quantity: 5 },
  ]);
  assert.deepEqual(deleteSpeedupInventoryEntry(updated, 0), [
    { kind: "construction", durationSeconds: 900, quantity: 5 },
  ]);
});

test("offer recommendation repeats offers and ranks known diamond cost", () => {
  const result = recommendPaidOffers(10_800, [
    { offerId: "expensive", title: "Expensive", diamondCost: 500, items: [{ kind: "research", durationSeconds: 5400, quantity: 1 }] },
    { offerId: "cheap", title: "Cheap", diamondCost: 100, items: [{ kind: "general", durationSeconds: 3600, quantity: 1 }] },
    { offerId: "wrong", title: "Construction", diamondCost: 1, items: [{ kind: "construction", durationSeconds: 3600, quantity: 99 }] },
  ], "research");
  assert.deepEqual(result.map((item) => item.offerId), ["cheap", "expensive"]);
  assert.equal(result[0].purchases, 3);
  assert.equal(result[0].totalDiamondCost, 300);
});

test("offer recommendation separates pack speedups, included gems, and remaining time", () => {
  const [result] = recommendPaidOffers(4 * 3600, [{
    offerId: "mixed",
    title: "Mixed pack",
    diamondCost: 999,
    includedGems: 250,
    bonusGems: 50,
    items: [{ kind: "research", durationSeconds: 3600, quantity: 1 }],
  }], "research", 3, { useGems: true });
  assert.equal(result.purchases, 1);
  assert.equal(result.appliedSpeedupSeconds, 3600);
  assert.equal(result.availableGems, 300);
  assert.equal(result.gemsUsed, 300);
  assert.equal(result.gemAppliedSeconds, 3 * 3600);
  assert.equal(result.remainingSeconds, 0);
});

test("offer recommendation accepts a gem-only offer", () => {
  const [result] = recommendPaidOffers(3 * 3600, [{
    offerId: "gems",
    title: "Gem pack",
    includedGems: 300,
    items: [],
  }], "research", 3, { useGems: true });
  assert.equal(result.appliedSpeedupSeconds, 0);
  assert.equal(result.gemsUsed, 300);
  assert.equal(result.gemAppliedSeconds, 3 * 3600);
});

test("gem-only offers are hidden while gem use is disabled", () => {
  const result = recommendPaidOffers(3 * 3600, [{
    offerId: "gems",
    title: "Gem pack",
    includedGems: 300,
    items: [],
  }], "research");
  assert.deepEqual(result, []);
});

test("partial paid offers remain visible with their remaining time", () => {
  const [result] = recommendPaidOffers(6_300, [{
    offerId: "partial",
    title: "Partial pack",
    diamondCost: 100,
    items: [{ kind: "research", durationSeconds: 3_600, quantity: 1 }],
  }], "research", 3, { taskSeconds: [5_400, 900] });
  assert.equal(result.purchases, 1);
  assert.equal(result.appliedSpeedupSeconds, 3_600);
  assert.equal(result.remainingSeconds, 2_700);
});
