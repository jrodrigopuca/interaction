// Totales del carrito, en centavos.
export const COUPON_RATE = 0.10;

export function subtotal(items) {
  return items.reduce((acc, it) => acc + it.unitCents * it.qty, 0);
}

function withCoupon(cents, coupon) {
  return coupon ? Math.round(cents * (1 - COUPON_RATE)) : cents;
}

export function lineTotal(item, coupon) {
  return withCoupon(item.unitCents * item.qty, coupon);
}

export function total(items, { coupon = false } = {}) {
  const lines = items.reduce((acc, it) => acc + lineTotal(it, coupon), 0);
  return withCoupon(lines, coupon);
}
