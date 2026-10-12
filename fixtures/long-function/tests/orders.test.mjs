import { test } from "node:test";
import assert from "node:assert/strict";
import { processOrder } from "../src/orders.mjs";

const catalog = {
  A: { priceCents: 1000, stock: 10 },
  B: { priceCents: 25000, stock: 5, bulkFrom: 3, bulkDiscountBp: 1000 },
};
const coupons = {
  TEN: { kind: "percent", bp: 1000, expires: "2099-01-01" },
  OLD: { kind: "fixed", amountCents: 500, expires: "2000-01-01" },
};
const today = "2026-10-12";

test("prices a simple order with shipping and tax", () => {
  const r = processOrder({ customerId: "c1", lines: [{ sku: "A", qty: 2 }] }, catalog, coupons, today);
  assert.equal(r.ok, true);
  assert.equal(r.value.subtotalCents, 2000);
  assert.equal(r.value.shippingCents, 1500);
  assert.equal(r.value.totalCents, 4235);
});

test("bulk discount and free shipping", () => {
  const r = processOrder({ customerId: "c1", lines: [{ sku: "B", qty: 3 }] }, catalog, coupons, today);
  assert.equal(r.value.subtotalCents, 67500);
  assert.equal(r.value.shippingCents, 0);
});

test("errors are values, never thrown", () => {
  assert.deepEqual(processOrder(null, catalog, coupons, today), { ok: false, error: "BAD_INPUT", detail: undefined });
  const r = processOrder({ customerId: "c1", lines: [{ sku: "A", qty: 1 }], coupon: "OLD" }, catalog, coupons, today);
  assert.equal(r.error, "COUPON_EXPIRED");
});
