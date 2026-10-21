import { test } from "node:test";
import assert from "node:assert/strict";
import { total } from "../src/checkout.mjs";
test("PROMO10 sobre $10,05", () => assert.equal(total([{ priceCents: 1005, qty: 1 }], { coupon: "PROMO10" }), 905));
