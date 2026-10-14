import { reserve } from './stock.mjs';

export function createOrder(db, { customerId, items }) {
  console.log('creating order for', customerId, items.length, 'items');
  for (const it of items) {
    if (!reserve(db, it.sku, it.qty)) {
      console.error('ORDER_FAILED out_of_stock', it.sku);
      return null;
    }
  }
  const order = { id: db.nextId(), customerId, items, totalCents: total(items) };
  db.orders.set(order.id, order);
  console.log('order created', order.id);
  return order;
}

function total(items) {
  return items.reduce((s, it) => s + it.priceCents * it.qty, 0);
}
