import { createHmac } from 'node:crypto';

const SECRET = process.env.TOKEN_SECRET ?? 'dev-secret';

export function issue(userId, now, ttlSeconds = 3600) {
  const payload = `${userId}.${now + ttlSeconds}`;
  return `${payload}.${sign(payload)}`;
}

export function verify(token, now) {
  const [userId, exp, sig] = token.split('.');
  if (sign(`${userId}.${exp}`) !== sig) return { ok: false, reason: 'bad_signature' };
  if (now > Number(exp)) return { ok: false, reason: 'expired' };
  return { ok: true, userId };
}

function sign(s) {
  return createHmac('sha256', SECRET).update(s).digest('hex').slice(0, 32);
}
