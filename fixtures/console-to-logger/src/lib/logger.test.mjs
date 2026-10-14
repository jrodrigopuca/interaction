import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createLogger } from './logger.mjs';

test('escribe una línea JSON con nivel, mensaje y campos', () => {
  const out = [];
  const log = createLogger({ service: 't' }, { write: (s) => out.push(s) });
  log.info('order created', { orderId: 7 });
  const line = JSON.parse(out[0]);
  assert.equal(line.level, 'info');
  assert.equal(line.msg, 'order created');
  assert.equal(line.orderId, 7);
  assert.equal(line.service, 't');
});

test('child hereda los campos base', () => {
  const out = [];
  const log = createLogger({ service: 't' }, { write: (s) => out.push(s) }).child({ module: 'x' });
  log.warn('hola');
  assert.equal(JSON.parse(out[0]).module, 'x');
});
