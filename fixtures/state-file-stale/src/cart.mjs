import { parseMoney } from "./money.mjs";
export function cartTotalCents(items) {
  return items.reduce((sum, i) => sum + parseMoney(i.price) * i.qty, 0);
}
