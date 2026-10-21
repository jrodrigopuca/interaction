// Recibo que se imprime al cobrar.
export function receiptLines(sale) {
  return [`Recibo #${sale.id}`, `Fecha: ${sale.date}`];
}
