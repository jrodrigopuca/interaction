import { test } from 'node:test';
import assert from 'node:assert/strict';
import { productUrl, resolve } from './urls.mjs';

const products = [
  { id: 17, name: 'Remera Azul' },
  { id: 18, name: 'Pantalón Niño' },
];

test('URL canónica en minúsculas', () => assert.equal(productUrl(products[0]), '/p/remera-azul-17'));
test('la URL canónica resuelve 200', () =>
  assert.equal(resolve('/p/remera-azul-17', products).status, 200));
// Los mails viejos y los buscadores tienen la URL en minúsculas: tiene que
// seguir siendo la canónica, o cada link indexado pasa a redirigir.
test('la URL en minúsculas sigue siendo canónica', () =>
  assert.deepEqual(resolve('/p/pantalon-nino-18', products), { status: 200, product: products[1] }));
test('otro slug con el mismo id redirige a la canónica', () =>
  assert.deepEqual(resolve('/p/lo-que-sea-17', products), { status: 301, location: '/p/remera-azul-17' }));
test('id inexistente es 404', () => assert.equal(resolve('/p/remera-azul-99', products).status, 404));
