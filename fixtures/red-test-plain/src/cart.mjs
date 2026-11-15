// Totales del carrito, en centavos.
export const COUPON_RATE = 0.10;

export function withCoupon(cents) {
  return Math.floor(cents * (1 - COUPON_RATE));
}

export function total(items, { coupon = false } = {}) {
  const sum = items.reduce((acc, it) => acc + it.unitCents * it.qty, 0);
  return coupon ? withCoupon(sum) : sum;
}
