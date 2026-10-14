// Cache de lectura del catálogo. Si se pierde, se reconstruye desde la base.
const TTL_S = 300;

export async function getProduct(redis, db, id) {
  const hit = await redis.get(`product:${id}`);
  if (hit) return JSON.parse(hit);
  const p = await db.findProduct(id);
  if (p) await redis.set(`product:${id}`, JSON.stringify(p), { EX: TTL_S });
  return p;
}

export async function invalidateProduct(redis, id) {
  await redis.del(`product:${id}`);
}
