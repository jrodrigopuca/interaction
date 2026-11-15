import { test } from "node:test";
import assert from "node:assert/strict";
import { total } from "./cart.mjs";

test("sin cupón el total es la suma", () => {
  assert.equal(total([{ unitCents: 1995, qty: 1 }]), 1995);
});

test("con cupón descuenta el 10 % y redondea al centavo", () => {
  assert.equal(total([{ unitCents: 1995, qty: 1 }], { coupon: true }), 1796);
});
