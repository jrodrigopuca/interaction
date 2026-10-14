import { test } from 'node:test';
import assert from 'node:assert/strict';
import { issue, verify } from './token.mjs';

const T0 = 1_700_000_000;

for (let dt = 0; dt < 3600; dt += 30) {
  test(`válido a t0+${dt}`, () => assert.deepEqual(verify(issue('u1', T0), T0 + dt), { ok: true, userId: 'u1' }));
}
test('válido a t0+3599', () => assert.equal(verify(issue('u1', T0), T0 + 3599).ok, true));
// Un token vence EN su exp, no un segundo después.
for (const dt of [3600, 3601, 7200]) {
  test(`vencido a t0+${dt}`, () => assert.equal(verify(issue('u1', T0), T0 + dt).reason, 'expired'));
}
test('firma adulterada', () => {
  const t = issue('u1', T0).replace(/^u1/, 'u2');
  assert.equal(verify(t, T0).reason, 'bad_signature');
});
