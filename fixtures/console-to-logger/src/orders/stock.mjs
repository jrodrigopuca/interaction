export function reserve(db, sku, qty) {
  const have = db.stock.get(sku) ?? 0;
  console.log(`[stock] reserve ${sku} x${qty} (have ${have})`);
  if (have < qty) return false;
  db.stock.set(sku, have - qty);
  return true;
}
