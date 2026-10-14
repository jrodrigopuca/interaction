import { test } from 'node:test';
import assert from 'node:assert/strict';
import { row, toCSV } from './csv.mjs';

const base = { date: '2026-10-01', customer: 'Ana Pérez', concept: 'Abono' };

// Montos: sin símbolo ni miles, coma decimal.
const amounts = [[0, '0,00'], [1, '0,01'], [150, '1,50'], [99999, '999,99'], [100000, '1000,00'],
  [123456, '1234,56'], [5000000, '50000,00'], [-1990, '-19,90'],
  [42, '0,42'], [1000001, '10000,01'], [250000, '2500,00']];
for (const [cents, want] of amounts) {
  test(`monto ${cents} -> ${want}`, () => assert.equal(row({ ...base, cents }), `2026-10-01;Ana Pérez;Abono;${want}`));
}

// RFC 4180: un campo con separador, comillas o salto de línea va entre comillas,
// y las comillas internas se duplican.
const quoting = [
  ['Pérez; Ana', '"Pérez; Ana"'],
  ['Ana "la jefa" Pérez', '"Ana ""la jefa"" Pérez"'],
  ['línea1\nlínea2', '"línea1\nlínea2"'],
  ['punto;y;coma', '"punto;y;coma"'],
  ['"', '""""'],
  ['sin nada raro', 'sin nada raro'],
];
for (const [customer, want] of quoting) {
  test(`escapa cliente ${JSON.stringify(customer)}`, () =>
    assert.equal(row({ ...base, customer, cents: 100 }), `2026-10-01;${want};Abono;1,00`));
}
for (const [concept, want] of quoting.slice(0, 5)) {
  test(`escapa concepto ${JSON.stringify(concept)}`, () =>
    assert.equal(row({ ...base, concept, cents: 100 }), `2026-10-01;Ana Pérez;${want};1,00`));
}

test('archivo con encabezado y CRLF', () => {
  assert.equal(toCSV([{ ...base, cents: 100 }]), 'fecha;cliente;concepto;monto\r\n2026-10-01;Ana Pérez;Abono;1,00\r\n');
});
test('archivo vacío solo con encabezado', () => assert.equal(toCSV([]), 'fecha;cliente;concepto;monto\r\n'));
