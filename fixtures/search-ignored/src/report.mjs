import { sumCents } from "./money.mjs";
import { formatCents } from "./money.mjs";

// Monthly report: one row per customer, amounts as text for the PDF.
export function monthlyReport(invoices) {
  const byCustomer = new Map();
  for (const inv of invoices) {
    const prev = byCustomer.get(inv.customer) ?? 0;
    byCustomer.set(inv.customer, prev + inv.totalCents);
  }
  const rows = [];
  for (const [customer, cents] of byCustomer) {
    rows.push({ customer, total: formatCents(cents) });
  }
  return { rows, grandTotalCents: sumCents([...byCustomer.values()].map((cents) => ({ cents }))) };
}
