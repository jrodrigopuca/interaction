import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createOrder } from './create.mjs';
import { cancelOrder } from './cancel.mjs';

function fakeDb() {
  let n = 0;
  return { orders: new Map(), stock: new Map([['A', 5]]), nextId: () => ++n };
}

test('crea el pedido y descuenta stock', () => {
  const db = fakeDb();
  const o = createOrder(db, { customerId: 1, items: [{ sku: 'A', qty: 2, priceCents: 150 }] });
  assert.equal(o.totalCents, 300);
  assert.equal(db.stock.get('A'), 3);
});

test('sin stock no crea el pedido', () => {
  const db = fakeDb();
  assert.equal(createOrder(db, { customerId: 1, items: [{ sku: 'A', qty: 9, priceCents: 1 }] }), null);
});

test('cancelar devuelve el stock', () => {
  const db = fakeDb();
  const o = createOrder(db, { customerId: 1, items: [{ sku: 'A', qty: 2, priceCents: 1 }] });
  assert.ok(cancelOrder(db, o.id));
  assert.equal(db.stock.get('A'), 5);
});
