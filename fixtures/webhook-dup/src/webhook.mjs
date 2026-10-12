// Handler del webhook `payment.succeeded`. El proveedor documenta entrega
// "at least once": el mismo evento puede llegar más de una vez.
export async function handlePaymentSucceeded(event, db) {
  const order = await db.orders.get(event.data.order_id);
  await db.charges.insert({
    order_id: order.id,
    amount: event.data.amount,
    provider_event_id: event.id,
  });
  await db.orders.update(order.id, { status: "paid" });
}
