import { test } from 'node:test';
import assert from 'node:assert/strict';
import { available, needsRestock } from './stock.mjs';

for (let s = 0; s < 1000; s++) {
  test(`disponible con stock ${s} y 3 reservados`, () => assert.equal(available(s, 3), Math.max(0, s - 3)));
  test(`reposición con stock ${s}, mínimo 5`, () => assert.equal(needsRestock(s, 0, 5), s < 5));
}
