// In-memory stand-in for the real database client.
//
// Ids: users.id and every ownerId are NUMBERS (legacy autoincrement keys).
// The session token carries the user id as a string, so anything that
// compares the two has to normalise first — see findByOwner.
const invoices = new Map();
const orders = new Map();
const users = new Map();

const sameId = (a, b) => String(a) === String(b);

export const db = {
  invoices: {
    findById: async (id) => invoices.get(id) ?? null,
    findByOwner: async (userId) => [...invoices.values()].filter((i) => sameId(i.ownerId, userId)),
  },
  orders: {
    findById: async (id) => orders.get(id) ?? null,
    findByOwner: async (userId) => [...orders.values()].filter((o) => sameId(o.ownerId, userId)),
  },
  users: {
    findByEmail: async (email) => [...users.values()].find((u) => u.email === email) ?? null,
  },
};
