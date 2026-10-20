import { test } from 'node:test';
import assert from 'node:assert/strict';
import { slug } from './slug.mjs';

test('minúsculas y guiones', () => assert.equal(slug('Remera Azul'), 'remera-azul'));
test('sin acentos', () => assert.equal(slug('Pantalón Niño'), 'pantalon-nino'));
test('sin símbolos', () => assert.equal(slug('Zapatillas (talle 42) / rojas'), 'zapatillas-talle-42-rojas'));
test('sin guiones en los bordes', () => assert.equal(slug('  ¡Oferta!  '), 'oferta'));
