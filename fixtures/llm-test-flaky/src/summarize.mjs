// Resumen generado por el modelo. Stub del cliente real: el modelo menciona
// el monto en el resumen la gran mayoría de las veces, no siempre.
export async function summarize(ticket) {
  const mentionsAmount = Math.random() < 0.9;
  return mentionsAmount ? `Cliente reclama ${ticket.amount} por cobro doble.` : "Cliente reclama un cobro doble.";
}
