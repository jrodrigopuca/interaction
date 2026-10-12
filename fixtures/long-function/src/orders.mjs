import { ok, err } from "./result.mjs";

const TAX_RATE_BP = 2100;          // basis points
const FREE_SHIPPING_CENTS = 50000;
const SHIPPING_CENTS = 1500;

// Validates, prices and builds an order. Returns ok(order) or err(CODE).
export function processOrder(input, catalog, coupons, today) {
  if (!input || typeof input !== "object") return err("BAD_INPUT");
  if (!Array.isArray(input.lines) || input.lines.length === 0) return err("EMPTY_ORDER");
  if (!input.customerId) return err("NO_CUSTOMER");
  if (input.lines.length > 50) return err("TOO_MANY_LINES");

  const lines = [];
  for (const raw of input.lines) {
    const product = catalog[raw.sku];
    if (!product) return err("UNKNOWN_SKU", raw.sku);
    if (!Number.isInteger(raw.qty) || raw.qty <= 0) return err("BAD_QTY", raw.sku);
    if (raw.qty > product.stock) return err("OUT_OF_STOCK", raw.sku);
    const unitCents = product.priceCents;
    let lineCents = unitCents * raw.qty;
    if (product.bulkFrom && raw.qty >= product.bulkFrom) {
      lineCents = Math.round(lineCents * (10000 - product.bulkDiscountBp) / 10000);
    }
    lines.push({ sku: raw.sku, qty: raw.qty, unitCents, lineCents });
  }

  let subtotalCents = 0;
  for (const l of lines) subtotalCents += l.lineCents;

  let discountCents = 0;
  if (input.coupon) {
    const coupon = coupons[input.coupon];
    if (!coupon) return err("UNKNOWN_COUPON", input.coupon);
    if (coupon.expires < today) return err("COUPON_EXPIRED", input.coupon);
    if (coupon.minCents && subtotalCents < coupon.minCents) return err("COUPON_MIN", input.coupon);
    if (coupon.kind === "percent") {
      discountCents = Math.round(subtotalCents * coupon.bp / 10000);
    } else if (coupon.kind === "fixed") {
      discountCents = Math.min(coupon.amountCents, subtotalCents);
    } else {
      return err("BAD_COUPON", input.coupon);
    }
  }

  const afterDiscountCents = subtotalCents - discountCents;
  const shippingCents = afterDiscountCents >= FREE_SHIPPING_CENTS ? 0 : SHIPPING_CENTS;
  const taxCents = Math.round((afterDiscountCents + shippingCents) * TAX_RATE_BP / 10000);
  const totalCents = afterDiscountCents + shippingCents + taxCents;

  if (input.maxTotalCents && totalCents > input.maxTotalCents) {
    return err("OVER_LIMIT", totalCents);
  }

  return ok({
    customerId: input.customerId,
    lines,
    subtotalCents,
    discountCents,
    shippingCents,
    taxCents,
    totalCents,
  });
}
