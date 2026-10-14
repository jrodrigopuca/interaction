import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fakeRedis } from './fake-redis.mjs';
import { getProduct, invalidateProduct } from '../src/products.mjs';
import { createSession, readSession } from '../src/sessions.mjs';
import { allow } from '../src/rate-limit.mjs';
import { enqueuePriceUpdate, nextPriceUpdate } from '../src/price-queue.mjs';

test('el producto se lee de la base una sola vez', async () => {
  const redis = fakeRedis();
  let reads = 0;
  const db = { findProduct: async (id) => (reads++, { id }) };
  await getProduct(redis, db, '1');
  await getProduct(redis, db, '1');
  assert.equal(reads, 1);
  await invalidateProduct(redis, '1');
  await getProduct(redis, db, '1');
  assert.equal(reads, 2);
});

test('la sesión creada se puede leer', async () => {
  const redis = fakeRedis();
  const sid = await createSession(redis, 42);
  assert.deepEqual(await readSession(redis, sid), { userId: 42 });
});

test('el rate limit corta en el límite', async () => {
  const redis = fakeRedis();
  for (let i = 0; i < 3; i++) assert.ok(await allow(redis, '1.2.3.4', 3));
  assert.equal(await allow(redis, '1.2.3.4', 3), false);
});

test('lo que encola el web lo consume el worker', async () => {
  const redis = fakeRedis();
  await enqueuePriceUpdate(redis, { productId: '1', priceCents: 1700 });
  assert.deepEqual(await nextPriceUpdate(redis), { productId: '1', priceCents: 1700 });
});
