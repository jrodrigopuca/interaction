// Total del carrito. Los precios llegan en pesos, con decimales (19.99).
export function cartTotal(items) {
  let total = 0;
  for (const it of items) total += it.price * it.qty;
  return total;
}
