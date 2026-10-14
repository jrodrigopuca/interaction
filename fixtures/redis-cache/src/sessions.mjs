import { randomUUID } from 'node:crypto';

const TTL_S = 60 * 60 * 24 * 7; // una semana

export async function createSession(redis, userId) {
  const sid = randomUUID();
  await redis.set(`sess:${sid}`, JSON.stringify({ userId }), { EX: TTL_S });
  return sid;
}

export async function readSession(redis, sid) {
  const raw = await redis.get(`sess:${sid}`);
  return raw ? JSON.parse(raw) : null;
}
