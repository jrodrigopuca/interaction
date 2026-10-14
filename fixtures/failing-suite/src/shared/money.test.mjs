import { test } from 'node:test';
import assert from 'node:assert/strict';
import { formatMoney, formatPlain } from './money.mjs';

const cases = [
  [0, '$ 0,00'], [5, '$ 0,05'], [99, '$ 0,99'], [100, '$ 1,00'], [1050, '$ 10,50'],
  [99999, '$ 999,99'], [100000, '$ 1.000,00'], [123456, '$ 1.234,56'],
  [1000000, '$ 10.000,00'], [98765432, '$ 987.654,32'], [100000000, '$ 1.000.000,00'],
  [-2500, '$ -25,00'], [1999, '$ 19,99'], [250000, '$ 2.500,00'], [7, '$ 0,07'],
];
for (const [cents, want] of cases) {
  test(`formatMoney(${cents}) = ${want}`, () => assert.equal(formatMoney(cents), want));
}

const plain = [[0, '0,00'], [123456, '1234,56'], [100000000, '1000000,00'], [-2500, '-25,00']];
for (const [cents, want] of plain) {
  test(`formatPlain(${cents}) = ${want}`, () => assert.equal(formatPlain(cents), want));
}
