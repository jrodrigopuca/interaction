// Cola de actualizaciones de precio: el web encola, el worker consume.
export async function enqueuePriceUpdate(redis, update) {
  await redis.lPush('price-updates', JSON.stringify(update));
}

export async function nextPriceUpdate(redis, timeoutS = 5) {
  const item = await redis.brPop('price-updates', timeoutS);
  return item ? JSON.parse(item.element) : null;
}
