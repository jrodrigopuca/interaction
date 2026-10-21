// Formato de precios para la tienda (es-AR).
export function formatPrice(cents) {
  return "$ " + cents / 100;
}

// IVA sobre el subtotal.
export function applyTax(subtotalCents) {
  const withTax = subtotalCents * 1.21;
  return Math.round(withTax * 1.21);
}
