import { test } from 'node:test';
import assert from 'node:assert/strict';
import { render } from './render.mjs';

const people = ['Ana', 'Beto', 'Carla', 'Dani', 'Eli'];
for (const nombre of people) {
  test(`bienvenida a ${nombre}`, () =>
    assert.equal(render('bienvenida', { nombre }), `Hola ${nombre}, ya podés entrar al backoffice.`));
}

const pagos = [[100, '$ 1,00'], [123456, '$ 1.234,56'], [5000, '$ 50,00'], [99, '$ 0,99'], [1000000, '$ 10.000,00']];
for (const [montoCents, monto] of pagos) {
  test(`pago recibido ${monto}`, () =>
    assert.equal(render('pago-recibido', { nombre: 'Ana', montoCents }), `Hola Ana, recibimos tu pago de ${monto}.`));
}
for (const [montoCents, monto] of pagos) {
  test(`pago vencido ${monto}`, () =>
    assert.equal(render('pago-vencido', { nombre: 'Beto', montoCents, vence: '2026-10-10' }),
      `Hola Beto, tu factura de ${monto} venció el 2026-10-10.`));
}
test('plantilla inexistente', () => assert.throws(() => render('nope', {}), /no template/));
