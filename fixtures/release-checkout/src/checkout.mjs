export function total(items, { coupon } = {}) {
  let cents = items.reduce((s, i) => s + i.priceCents * i.qty, 0);
  if (coupon === "PROMO10") cents = Math.round(cents * 0.9);
  return cents;
}
// Confirma el pedido cuando llega el webhook del proveedor de pagos.
export function onPaymentWebhook(order, event) {
  if (event.type === "payment.succeeded") order.status = "paid";
  if (event.type === "payment.refunded") order.status = "refunded";
  return order;
}
