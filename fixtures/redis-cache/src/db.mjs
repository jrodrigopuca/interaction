// Stand-in de la base para desarrollo local.
const products = new Map([['1', { id: '1', name: 'Mate', priceCents: 1500 }]]);
export const db = {
  async findProduct(id) { return products.get(id) ?? null; },
  async updatePrice(id, priceCents) { const p = products.get(id); if (p) p.priceCents = priceCents; },
};
