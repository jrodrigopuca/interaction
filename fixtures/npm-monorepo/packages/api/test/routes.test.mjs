import { test } from 'node:test';
import assert from 'node:assert/strict';
import { handleCreate } from '../src/routes.mjs';

test('crea el producto con slug y precio en centavos', () => {
  const out = handleCreate({ name: 'Yerba Orgánica 1kg', price: 12.5 });
  assert.equal(out.status, 201);
  assert.equal(out.location, '/products/yerba-organica-1kg');
  assert.equal(out.product.priceCents, 1250);
});
