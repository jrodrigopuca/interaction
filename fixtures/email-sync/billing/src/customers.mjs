// Copia local del cliente para facturar sin depender de la app.
export function registerBillingConsumers(db, bus) {
  bus.subscribe('user.registered', async ({ userId, name, email }) => {
    db.customers.set(userId, { userId, name, billingEmail: email });
  });
}

export function invoiceRecipient(db, userId) {
  return db.customers.get(userId)?.billingEmail ?? null;
}
