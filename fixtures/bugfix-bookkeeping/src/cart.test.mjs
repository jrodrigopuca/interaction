import { test } from "node:test";
import assert from "node:assert/strict";
import { subtotal, total } from "./cart.mjs";

const items = [
  { name: "yerba", unitCents: 3000, qty: 2 },
  { name: "galletitas", unitCents: 1500, qty: 1 },
];

test("subtotal suma cantidad por precio", () => {
  assert.equal(subtotal(items), 7500);
});

test("sin cupón el total es el subtotal", () => {
  assert.equal(total(items), 7500);
});

test("con cupón el descuento del 10 % se aplica una sola vez", () => {
  assert.equal(total(items, { coupon: true }), 6750);
});
