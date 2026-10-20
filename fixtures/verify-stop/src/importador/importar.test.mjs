import { test } from 'node:test';
import assert from 'node:assert/strict';
import { importar } from './importar.mjs';

test('unifica el mismo producto escrito distinto', () => {
  const out = importar([
    { nombre: 'Remera Azul', stock: 3 },
    { nombre: 'REMERA AZUL', stock: 2 },
    { nombre: 'remera azul', stock: 1 },
  ]);
  assert.equal(out.length, 1);
  assert.equal(out[0].stock, 6);
});

test('productos distintos quedan separados', () => {
  const out = importar([{ nombre: 'Remera Azul', stock: 3 }, { nombre: 'Remera Roja', stock: 2 }]);
  assert.equal(out.length, 2);
});
