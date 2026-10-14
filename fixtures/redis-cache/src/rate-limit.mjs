// 100 requests por minuto por IP.
export async function allow(redis, ip, limit = 100) {
  const key = `rl:${ip}:${Math.floor(Date.now() / 60000)}`;
  const n = await redis.incr(key);
  if (n === 1) await redis.expire(key, 60);
  return n <= limit;
}
