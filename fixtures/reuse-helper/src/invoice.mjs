import { formatMoney } from "./utils/money.mjs";
export function invoiceLines(items) {
  const total = items.reduce((s, i) => s + i.priceCents * i.qty, 0);
  return [...items.map((i) => `${i.name} x${i.qty}`), `Total: ${formatMoney(total)}`];
}
