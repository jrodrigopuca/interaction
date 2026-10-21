import { take } from "./inventory.mjs";
import { nextOrderNumber } from "./order-number.mjs";
import { priceOf, withTax } from "./pricing.mjs";

// Confirma un pedido: descuenta stock, calcula el total con IVA y le asigna número.
export function checkout(items) {
  let subtotal = 0;
  for (const { sku, qty } of items) {
    take(sku, qty);
    subtotal += priceOf(sku) * qty;
  }
  return { number: nextOrderNumber(), total: withTax(subtotal) };
}
