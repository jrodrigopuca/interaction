import { test } from "node:test";
import assert from "node:assert/strict";
import { total } from "../src/checkout.mjs";
test("suma ítems", () => assert.equal(total([{ priceCents: 1000, qty: 2 }]), 2000));
test("PROMO10 descuenta 10%", () => assert.equal(total([{ priceCents: 1000, qty: 1 }], { coupon: "PROMO10" }), 900));
