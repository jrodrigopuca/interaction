import { formatCents, sumCents } from "./money.mjs";

// An invoice is a list of lines; totals are computed, never stored.
export function buildInvoice(customer, lines) {
  const totalCents = sumCents(lines);
  return {
    customer,
    lines: lines.map((line) => ({
      description: line.description,
      quantity: line.quantity,
      cents: line.cents,
    })),
    totalCents,
    totalLabel: formatCents(totalCents),
  };
}
