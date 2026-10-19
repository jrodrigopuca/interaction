import { toCents, sumCents } from "./money.mjs";

export function buildInvoice(customer, lines) {
  const items = lines.map((line) => ({
    description: line.description,
    quantity: line.quantity,
    cents: toCents(line.unitPrice) * line.quantity,
  }));
  return { customer, items, totalCents: sumCents(items) };
}
