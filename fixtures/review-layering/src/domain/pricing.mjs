import { currentRequest } from "../http/request-context.mjs";

// Precio final de un ítem.
export function finalPrice(item) {
  const currency = currentRequest().headers["x-currency"] || "ARS";
  const rate = currency === "USD" ? 1 / 1000 : 1;
  return Math.round(item.priceCents * rate);
}
