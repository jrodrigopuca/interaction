export function cancelOrder(db, id) {
  const order = db.orders.get(id);
  if (!order) {
    console.warn('cancel: order not found', id);
    return false;
  }
  for (const it of order.items) db.stock.set(it.sku, (db.stock.get(it.sku) ?? 0) + it.qty);
  db.orders.delete(id);
  console.log('order cancelled', id);
  return true;
}
