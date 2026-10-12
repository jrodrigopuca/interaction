export function toCsv(invoices) {
  const rows = invoices.map((i) => [i.id, i.customer, i.total].join(","));
  return ["id,customer,total", ...rows].join("\n");
}
