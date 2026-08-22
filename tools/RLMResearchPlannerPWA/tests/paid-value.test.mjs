import assert from "node:assert/strict";
import test from "node:test";

import {
  defaultPaidValuation,
  minimumGemsForSpeedupSeconds,
  paidOfferExchangePayload,
  paidOffersFromExchangePayload,
  paidKindHasTime,
  reorderPaidItems,
  summarizePaidOffer,
} from "../src/paid-value.js";
import { backupPayload, defaultState, stateFromBackup } from "../src/state.js";

test("minimum gems use standard Gem Mall speed-up combinations", () => {
  assert.equal(minimumGemsForSpeedupSeconds(0).gems, 0);
  assert.equal(minimumGemsForSpeedupSeconds(3 * 3600).gems, 300);
  assert.deepEqual(minimumGemsForSpeedupSeconds(23 * 3600), {
    gems: 1500,
    purchasedSeconds: 24 * 3600,
  });
});

test("paid value combines gems, speedups, and arbitrary items", () => {
  const summary = summarizePaidOffer({
    offerId: "one",
    diamondCost: 100,
    includedGems: 50,
    bonusGems: 50,
    items: [
      { kind: "general", quantity: 2, durationSeconds: 3600 },
      { kind: "monster_rare", quantity: 2, pointsEach: 10 },
      { kind: "chest", quantity: 3, gemValueEach: 5, pointsEach: 2 },
    ],
  }, { ...defaultPaidValuation(), generalSpeedupPointsPerHour: 4 });
  assert.equal(summary.speedupGemValue, 260);
  assert.equal(summary.totalGemValue, 375);
  assert.equal(summary.speedupPoints, 8);
  assert.equal(summary.totalPoints, 409);
  assert.equal(summary.pointsPerDiamond, 4.09);
  assert.equal(paidKindHasTime("construction"), true);
  assert.equal(paidKindHasTime("healing"), true);
  assert.equal(paidKindHasTime("merging"), true);
  assert.equal(paidKindHasTime("crafting"), true);
  assert.equal(paidKindHasTime("chest"), false);
});

test("paid item order moves one selected detail without changing its values", () => {
  const source = [
    { kind: "custom", name: "A", quantity: 1 },
    { kind: "custom", name: "B", quantity: 2 },
    { kind: "custom", name: "C", quantity: 3 },
  ];
  const moved = reorderPaidItems(source, 1, -1);
  assert.equal(moved.moved, true);
  assert.equal(moved.index, 0);
  assert.deepEqual(moved.items.map((item) => item.name), ["B", "A", "C"]);
  assert.deepEqual(source.map((item) => item.name), ["A", "B", "C"]);
  assert.equal(reorderPaidItems(source, 0, -1).moved, false);
});

test("speed-up presets distinguish merging and Lunar Foundry crafting", () => {
  const summary = summarizePaidOffer({
    offerId: "special",
    items: [
      { kind: "healing", quantity: 1, durationSeconds: 3600 },
      { kind: "merging", quantity: 1, durationSeconds: 3600 },
      { kind: "crafting", quantity: 1, durationSeconds: 3600 },
    ],
  }, defaultPaidValuation());
  assert.equal(summary.speedupGemValue, 390);
});

test("paid offer exchange file keeps goals without replacing player state", () => {
  const valuation = { ...defaultPaidValuation(), pointsPerGem: 2, mergingSpeedupPointsPerHour: 3, craftingSpeedupPointsPerHour: 4, useSpeedupGemPresets: false };
  const offer = { offerId: "one", title: "研究パック", goal: "research", items: [{ kind: "research", quantity: 2, durationSeconds: 3600 }] };
  const restored = paidOffersFromExchangePayload(paidOfferExchangePayload([offer], valuation, "研究向け"));
  assert.equal(restored.offers[0].goal, "research");
  assert.equal(restored.valuation.pointsPerGem, 2);
  assert.equal(restored.valuation.mergingSpeedupPointsPerHour, 3);
  assert.equal(restored.valuation.craftingSpeedupPointsPerHour, 4);
  assert.equal(restored.name, "研究向け");
});

test("paid offer exchange accepts comparison settings without offers", () => {
  const valuation = { ...defaultPaidValuation(), pointsPerGem: 2.5 };
  const restored = paidOffersFromExchangePayload(paidOfferExchangePayload([], valuation, "比較設定"));
  assert.deepEqual(restored.offers, []);
  assert.equal(restored.valuation.pointsPerGem, 2.5);
  assert.equal(restored.name, "比較設定");
});

test("paid offers use the common PC/PWA backup schema", () => {
  const state = defaultState();
  state.paidOffers = [{
    offerId: "pack-1",
    title: "素材パック",
    memo: "比較用",
    diamondCost: 999,
    includedGems: 3600,
    bonusGems: 0,
    items: [{ kind: "monster_legendary", name: "伝説素材", quantity: 2, durationSeconds: 0, gemValueEach: 1200, pointsEach: 100 }],
    createdAt: "created",
    updatedAt: "updated",
  }];
  state.paidValuation = { ...defaultPaidValuation(), pointsPerGem: 2 };
  const raw = backupPayload(state);
  assert.equal(raw.player.paid_offers[0].items[0].gem_value_each, 1200);
  const restored = stateFromBackup(raw);
  assert.equal(restored.paidOffers[0].title, "素材パック");
  assert.equal(restored.paidValuation.pointsPerGem, 2);
});
