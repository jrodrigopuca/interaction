import { test } from 'node:test';
import assert from 'node:assert/strict';
import { totalsByBranch } from './aggregate.mjs';
import { summaryLines } from './summary.mjs';

// Orden numérico: con sucursales de dos dígitos, 2 va antes que 10.
const orderCases = [
  [[1, 2, 3], [1, 2, 3]],
  [[3, 1, 2], [1, 2, 3]],
  [[10, 2], [2, 10]],
  [[11, 9, 1], [1, 9, 11]],
  [[20, 3, 100], [3, 20, 100]],
  [[7, 12, 5], [5, 7, 12]],
  [[15, 4], [4, 15]],
  [[2, 30, 21, 1], [1, 2, 21, 30]],
  [[8], [8]],
  [[99, 100, 98], [98, 99, 100]],
];
for (const [branches, want] of orderCases) {
  test(`ordena sucursales ${branches.join(',')}`, () => {
    const sales = branches.map((branch) => ({ branch, cents: 100 }));
    assert.deepEqual(totalsByBranch(sales).map((r) => r.branch), want);
  });
}

for (let n = 1; n <= 100; n++) {
  test(`suma ${n} ventas de una sucursal`, () => {
    const sales = Array.from({ length: n }, () => ({ branch: 1, cents: 250 }));
    assert.deepEqual(totalsByBranch(sales), [{ branch: 1, cents: 250 * n }]);
  });
}

const summaryCases = [
  [[{ branch: 1, cents: 100 }], ['Sucursal 1: $ 1,00']],
  [[{ branch: 1, cents: 123456 }], ['Sucursal 1: $ 1.234,56']],
  [[{ branch: 2, cents: 5000 }, { branch: 1, cents: 7500 }], ['Sucursal 1: $ 75,00', 'Sucursal 2: $ 50,00']],
  [[{ branch: 3, cents: 99 }], ['Sucursal 3: $ 0,99']],
  [[{ branch: 4, cents: 1000000 }], ['Sucursal 4: $ 10.000,00']],
  [[{ branch: 5, cents: 250 }, { branch: 5, cents: 250 }], ['Sucursal 5: $ 5,00']],
  [[{ branch: 6, cents: 31415 }], ['Sucursal 6: $ 314,15']],
  [[{ branch: 7, cents: 777777 }], ['Sucursal 7: $ 7.777,77']],
  [[{ branch: 8, cents: 1 }], ['Sucursal 8: $ 0,01']],
  [[{ branch: 9, cents: 12000000 }], ['Sucursal 9: $ 120.000,00']],
];
for (const [sales, want] of summaryCases) {
  test(`resumen ${want.join(' | ')}`, () => assert.deepEqual(summaryLines(sales), want));
}
