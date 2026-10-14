import { readFileSync } from 'node:fs';

const { password: policy } = JSON.parse(
  readFileSync(new URL('../../config/auth.json', import.meta.url), 'utf8'));

export function checkPassword(pw) {
  const errors = [];
  if (pw.length < policy.minLength) errors.push('too_short');
  if (policy.requireDigit && !/\d/.test(pw)) errors.push('no_digit');
  if (policy.requireSymbol && !/[^A-Za-z0-9]/.test(pw)) errors.push('no_symbol');
  return { ok: errors.length === 0, errors };
}
