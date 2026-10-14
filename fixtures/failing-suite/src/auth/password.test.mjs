import { test } from 'node:test';
import assert from 'node:assert/strict';
import { checkPassword } from './password.mjs';

// Política: mínimo 8, al menos un dígito y un símbolo.
const valid = ['abc12!xy', 'Passw0rd!', 'mate#2024', 'r1ver!pl', 'z9$zzzzz', 'Hola-123',
  'tango_88', 'q1w2e3r!', 'a!1aaaaa', 'Boca*1905', 'X_7yyyyy', '8chars!a'];
for (const pw of valid) {
  test(`acepta "${pw}"`, () => assert.deepEqual(checkPassword(pw), { ok: true, errors: [] }));
}

const invalid = [
  ['ab1!', ['too_short']], ['abcdefgh!', ['no_digit']], ['abcdefg1', ['no_symbol']],
  ['abcdefgh', ['no_digit', 'no_symbol']], ['', ['too_short', 'no_digit', 'no_symbol']],
];
for (const [pw, errors] of invalid) {
  test(`rechaza "${pw}" con ${errors.join(',')}`, () =>
    assert.deepEqual(checkPassword(pw), { ok: false, errors }));
}
