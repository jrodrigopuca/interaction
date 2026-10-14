import { getRedis } from './redis.mjs';
import { nextPriceUpdate } from './price-queue.mjs';
import { invalidateProduct } from './products.mjs';
import { db } from './db.mjs';

const redis = await getRedis();

for (;;) {
  const upd = await nextPriceUpdate(redis);
  if (!upd) continue;
  await db.updatePrice(upd.productId, upd.priceCents);
  await invalidateProduct(redis, upd.productId);
}
