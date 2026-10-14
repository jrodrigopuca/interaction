export function registerCrmConsumers(bus, crm) {
  bus.subscribe('user.registered', async ({ userId, name, email }) => {
    // El CRM identifica al contacto por email.
    await crm.upsertContact({ externalId: userId, name, email });
  });
}
