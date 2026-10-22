// In-memory stand-in for the real database client.
const invoices = new Map();
const orders = new Map();
const users = new Map();

export const db = {
  invoices: {
    findById: async (id) => invoices.get(id) ?? null,
    findByOwner: async (userId) => [...invoices.values()].filter((i) => i.ownerId === userId),
  },
  orders: {
    findById: async (id) => orders.get(id) ?? null,
    findByOwner: async (userId) => [...orders.values()].filter((o) => o.ownerId === userId),
  },
  users: {
    findByEmail: async (email) => [...users.values()].find((u) => u.email === email) ?? null,
  },
};
