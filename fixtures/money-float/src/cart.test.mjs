import { test } from "node:test";
import assert from "node:assert/strict";
import { cartTotal } from "./cart.mjs";
test("tres ítems de 19.99 suman 59.97", () =>
  assert.equal(cartTotal([{ price: 19.99, qty: 3 }]), 59.97));
test("0.1 + 0.2", () =>
  assert.equal(cartTotal([{ price: 0.1, qty: 1 }, { price: 0.2, qty: 1 }]), 0.3));
