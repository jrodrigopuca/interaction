// Total en centavos enteros.
export function total(items, { coupon } = {}) {
  let cents = items.reduce((s, i) => s + i.priceCents * i.qty, 0);
  if (coupon === "PROMO10") cents = Math.floor(cents * 0.9);
  return cents;
}
