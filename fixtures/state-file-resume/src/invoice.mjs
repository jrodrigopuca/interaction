import { parseMoneyLegacy } from "./money.mjs";
export function invoiceTotal(lines) {
  let total = 0;
  for (const l of lines) total += parseMoneyLegacy(l.price) * l.qty;
  return Math.round(total * 100) / 100;
}
