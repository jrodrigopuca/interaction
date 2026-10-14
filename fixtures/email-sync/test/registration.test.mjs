import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createBus } from '../shared/bus.mjs';
import { createUserService } from '../app/src/users.mjs';
import { registerBillingConsumers, invoiceRecipient } from '../billing/src/customers.mjs';
import { registerCrmConsumers } from '../crm-sync/src/consumer.mjs';

function setup() {
  const bus = createBus();
  const db = { users: new Map(), customers: new Map() };
  const sent = [];
  const crm = { upsertContact: async (c) => { sent.push(c); } };
  registerBillingConsumers(db, bus);
  registerCrmConsumers(bus, crm);
  return { bus, db, sent, users: createUserService(db, bus) };
}

test('el alta llega a facturación y al CRM', async () => {
  const { db, sent, users } = setup();
  const u = await users.register({ name: 'Ana', email: 'ana@example.com' });
  assert.equal(invoiceRecipient(db, u.id), 'ana@example.com');
  assert.deepEqual(sent, [{ externalId: u.id, name: 'Ana', email: 'ana@example.com' }]);
});

test('cambiar el email lo actualiza en la app', async () => {
  const { db, users } = setup();
  const u = await users.register({ name: 'Ana', email: 'ana@example.com' });
  await users.changeEmail(u.id, 'ana@nuevo.com');
  assert.equal(db.users.get(u.id).email, 'ana@nuevo.com');
});
