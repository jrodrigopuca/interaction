import { parseMoney } from "./money.mjs";
// Migrado a centavos el 2026-10-03 (ver CHANGELOG.md).
export function invoiceTotal(lines) {
  let cents = 0;
  for (const l of lines) cents += parseMoney(l.price) * l.qty;
  return cents;
}
